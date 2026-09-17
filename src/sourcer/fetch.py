"""Every outbound request this application makes.

One place so that politeness is not a thing each adapter remembers. Robots are
checked before a fetch, one request at a time per host, with a delay between.
A refusal ends that Source for the run and is recorded, rather than being
retried until someone notices.

Two tiers. Plain HTTP with Chrome TLS impersonation handles most things. A
persistent headless browser handles what refuses the HTTP client, and is only
reached when a block is detected and the browser tier is enabled, because it
needs memory the free deployment tier does not have.
"""

import os
import threading
import time
from urllib.parse import urlsplit, urlunsplit

from protego import Protego
from scrapling.engines.toolbelt.proxy_rotation import ProxyRotator
from scrapling.fetchers import FetcherSession, StealthySession

from sourcer.paths import selector_store_path


def selector_config():
    """Parsing options shared by both tiers.

    Adaptive parsing lets a saved selector be relocated by structure and text
    after a site redesign, instead of silently matching nothing. The fingerprint
    store is pointed inside the project; the library's default is a file in its
    own installed package directory, which a reinstall would discard.
    """
    return {
        "adaptive": True,
        "storage_args": {"storage_file": str(selector_store_path())},
    }


# A polite floor between two requests to the same host. YellowPages starts
# refusing after roughly ten requests in a few minutes from one address, so this
# is deliberately slower than it needs to be for a single page.
DEFAULT_DELAY_SECONDS = 12.0

# Status codes that mean "stop asking", not "try again".
BLOCKED_STATUSES = (401, 403, 407, 429, 444, 451, 503)

# Titles anti-bot vendors serve. A block page can arrive with status 200.
BLOCK_TITLE_MARKERS = (
    "attention required",
    "you have been blocked",
    "access denied",
    "just a moment",
    "are you a robot",
    "verify you are human",
)

USER_AGENT_FOR_ROBOTS = "sourcer"


class Blocked(Exception):
    """A Source refused us. Recorded against the Search Run, never retried."""

    def __init__(self, url, status=None, reason=""):
        self.url = url
        self.status = status
        self.reason = reason or f"status {status}"
        super().__init__(f"blocked by {urlsplit(url).netloc}: {self.reason}")


class Disallowed(Exception):
    """The site's robots policy forbids this path. Not an error, a boundary."""

    def __init__(self, url):
        self.url = url
        super().__init__(f"robots policy disallows {url}")


def browser_enabled():
    """Whether the browser tier may be used.

    Off by default. Headless Chromium needs more memory than the free
    deployment tier allows, and the HTTP-only Sources must keep working there.
    """
    return os.environ.get("SOURCER_BROWSER", "").strip().lower() in ("1", "true", "yes")


def proxies():
    """A rotation list from the environment, empty when none is configured."""
    raw = os.environ.get("SOURCER_PROXIES", "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def _title_of(response):
    try:
        return (response.css("title::text").get() or "").strip().lower()
    except Exception:
        return ""


def looks_blocked(response):
    """Whether a response is a refusal rather than content."""
    if response is None:
        return True
    if getattr(response, "status", None) in BLOCKED_STATUSES:
        return True
    title = _title_of(response)
    return any(marker in title for marker in BLOCK_TITLE_MARKERS)


class Fetcher:
    """A polite fetcher for the life of one Search Run.

    Holds the HTTP session so cookies and connections persist across pages of
    the same site, which a fresh request per page would throw away. Opens a
    browser session only if something actually needs one.
    """

    def __init__(self, delay_seconds=DEFAULT_DELAY_SECONDS, allow_browser=None):
        self.delay_seconds = delay_seconds
        self.allow_browser = browser_enabled() if allow_browser is None else allow_browser
        self._http = None
        self._http_owner = None
        self._browser = None
        self._browser_owner = None
        self._robots = {}
        self._last_request_at = {}
        self._lock = threading.Lock()
        self._proxies = proxies()
        # One proxy is just a proxy; several rotate. Without this the list was
        # accepted and only its first entry ever used.
        self._rotator = ProxyRotator(self._proxies) if len(self._proxies) > 1 else None

    # -- lifecycle ------------------------------------------------------- #

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
        return False

    def close(self):
        for owner in (self._http_owner, self._browser_owner):
            try:
                if owner is not None:
                    owner.__exit__(None, None, None)
            except Exception:
                pass
        self._http = self._http_owner = None
        self._browser = self._browser_owner = None

    def _http_session(self):
        if self._http is None:
            session = FetcherSession(
                impersonate="chrome",
                timeout=30,
                retries=2,
                retry_delay=3,
                selector_config=selector_config(),
                proxy_rotator=self._rotator,
                proxy=self._proxies[0] if self._proxies and not self._rotator else None,
            )
            # __enter__ returns the object carrying the request methods, which is
            # not the session itself. Both are kept: one to call, one to close.
            self._http = session.__enter__()
            self._http_owner = session
        return self._http

    def _browser_session(self):
        if self._browser is None:
            session = StealthySession(
                headless=True,
                network_idle=True,
                timeout=60000,
                selector_config=selector_config(),
                proxy=self._proxies[0] if self._proxies and not self._rotator else None,
                proxy_rotator=self._rotator,
            )
            self._browser = session.__enter__()
            self._browser_owner = session
        return self._browser

    # -- politeness ------------------------------------------------------ #

    def _wait_turn(self, url):
        """One request at a time per host, never faster than the delay."""
        host = urlsplit(url).netloc
        with self._lock:
            previous = self._last_request_at.get(host)
            if previous is not None:
                remaining = self.delay_seconds - (time.monotonic() - previous)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at[host] = time.monotonic()

    def _robots_for(self, url, tier="http"):
        parts = urlsplit(url)
        origin = (parts.scheme, parts.netloc)
        if origin in self._robots:
            return self._robots[origin]

        policy = None
        robots_url = urlunsplit((*origin, "/robots.txt", "", ""))
        # Reading the policy is a request to the same host, so it waits its turn
        # like any other.
        self._wait_turn(robots_url)
        try:
            if tier == "browser" and self.allow_browser:
                response = self._browser_session().fetch(robots_url, google_search=False)
            else:
                response = self._http_session().get(robots_url, stealthy_headers=True, timeout=15)
            if response.status == 200:
                body = response.body
                policy = Protego.parse(
                    body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)
                )
        except Exception:
            policy = None
        # A robots file we cannot read is not permission. It is also not a
        # refusal: a site that blocks robots.txt has told us nothing, so we
        # proceed under our own rate limit rather than inventing rules.
        self._robots[origin] = policy
        return policy

    def allowed(self, url, tier="http"):
        policy = self._robots_for(url, tier=tier)
        return True if policy is None else policy.can_fetch(url, USER_AGENT_FOR_ROBOTS)

    # -- fetching -------------------------------------------------------- #

    def _tier_order(self, preferred):
        """Which tiers to try, in order.

        Both are tried whichever way round, because a refusal is not stable:
        the same YellowPages page answered the HTTP client and refused the
        browser within the same minute during testing, and the reverse the hour
        before. A Source declares what usually works; this decides what to do
        when it does not.
        """
        order = [preferred, "browser" if preferred == "http" else "http"]
        if not self.allow_browser:
            order = [tier for tier in order if tier != "browser"]
        return order or ["http"]

    def get(self, url, referer=None, tier="http", obey_robots=True):
        """Fetch a page, or raise Disallowed or Blocked.

        The referer chains from the previous page when given. Without it the
        HTTP client attaches a Google referer to every request, which is
        incoherent on page three of a paginated crawl and is a known tell.
        """
        if obey_robots and not self.allowed(url, tier=tier):
            raise Disallowed(url)

        last = None
        for attempt in self._tier_order(tier):
            self._wait_turn(url)
            fetch_at_tier = self._http_get if attempt == "http" else self._browser_get
            try:
                response = fetch_at_tier(url, referer)
            except Exception as error:  # a transport failure is not a refusal
                last = f"{type(error).__name__}: {error}"
                continue
            if not looks_blocked(response):
                return response
            last = _title_of(response) or f"status {getattr(response, 'status', '?')}"

        raise Blocked(url, reason=last or "no tier succeeded")

    def _http_get(self, url, referer):
        session = self._http_session()
        if referer:
            return session.get(url, headers={"referer": referer}, stealthy_headers=False)
        return session.get(url, stealthy_headers=True)

    def _browser_get(self, url, referer):
        session = self._browser_session()
        if referer:
            return session.fetch(url, google_search=False, extra_headers={"referer": referer})
        return session.fetch(url, google_search=True)
