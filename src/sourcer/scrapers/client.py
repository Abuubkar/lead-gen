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

import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import certifi
from protego import Protego
from scrapling.engines.toolbelt.proxy_rotation import ProxyRotator
from scrapling.fetchers import FetcherSession, StealthySession

from sourcer.config import browser_enabled, proxies, selector_store_path


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

# Which certificate authorities to trust. The HTTP client ships its own list,
# which lacks GlobalSign's Root R46: data.texas.gov is signed under it and was
# refused as an unknown issuer, though browsers and Python both accept it.
# certifi is Mozilla's list, the one browsers use.
CA_BUNDLE = certifi.where()

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


class Unreachable(Blocked):
    """No tier got any answer at all: a timeout or a refused connection.

    A server that is down or overloaded is not refusing us, and reporting it as
    blocked would send a rep looking for a policy problem that does not exist.
    A subclass, so code that only cares that the Source failed still catches it.
    """


class Disallowed(Exception):
    """The site's robots policy forbids this path. Not an error, a boundary."""

    def __init__(self, url):
        self.url = url
        super().__init__(f"robots policy disallows {url}")


class NotConfigured(Exception):
    """A Source that needs setup it has not been given, such as an API key.

    Distinct from Blocked so a Search Run reports "not set up" rather than an
    empty market: zero results from an unconfigured Source says nothing about
    how many businesses exist.
    """

    def __init__(self, source, needs):
        self.source = source
        self.needs = needs
        super().__init__(f"{source} is not configured: {needs}")


def _title_of(response):
    try:
        return (response.css("title::text").get() or "").strip().lower()
    except Exception:
        return ""


def _timed_out(error):
    """Whether a request failed for want of an answer, not for a bad one.

    The HTTP client reports curl's error code in its message; 28 is a timeout.
    """
    message = str(error)
    return "curl: (28)" in message or "timed out" in message.lower()


def looks_blocked(response):
    """Whether a response is a refusal rather than content."""
    if response is None:
        return True
    if getattr(response, "status", None) in BLOCKED_STATUSES:
        return True
    title = _title_of(response)
    return any(marker in title for marker in BLOCK_TITLE_MARKERS)


class HostGate:
    """Politeness per website, shared by every Fetcher in the process.

    One request at a time to any one host, and a pause after each before the
    next one to that host may start. The pause is measured from the end of a
    request, not its start, so a slow site is never asked again sooner because
    it was slow.

    Shared, not per Fetcher, because websites are now read in parallel and up
    to three searches run at once: each with its own record, two workers or two
    searches could reach the same site back to back. Each host has its own
    lock, so waiting on one site never holds up a request to another.
    """

    def __init__(self):
        self._guard = threading.Lock()
        self._locks = {}
        self._last_finished = {}

    @contextmanager
    def turn(self, url, delay_seconds):
        host = urlsplit(url).netloc.lower()
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            previous = self._last_finished.get(host)
            if previous is not None:
                remaining = delay_seconds - (time.monotonic() - previous)
                if remaining > 0:
                    time.sleep(remaining)
            try:
                yield
            finally:
                self._last_finished[host] = time.monotonic()


HOSTS = HostGate()


class Fetcher:
    """A polite fetcher for the life of one Search Run.

    Holds the HTTP session so cookies and connections persist across pages of
    the same site, which a fresh request per page would throw away. Opens a
    browser session only if something actually needs one.
    """

    def __init__(
        self,
        delay_seconds=DEFAULT_DELAY_SECONDS,
        allow_browser=None,
        timeout_seconds=30,
        attempts=2,
        give_up_when_silent=False,
    ):
        """delay_seconds is the pause per website between requests.

        timeout_seconds and attempts bound how long one request can take: each
        attempt waits up to timeout_seconds, and attempts counts the first try.

        give_up_when_silent stops asking a host whose robots.txt timed out: its
        pages would only time out in turn. For reading business websites, where
        one dead site cost 48 seconds of timeouts. Only a timeout counts. Other
        failures are quick, and some come from sites that work: two Norwich
        dentists redirect robots.txt to a broken address yet serve their pages.
        Not for Sources, whose robots.txt may be what is blocked.
        """
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.give_up_when_silent = give_up_when_silent
        self._silent = set()
        self.allow_browser = browser_enabled() if allow_browser is None else allow_browser
        self._http = None
        self._http_owner = None
        self._browser = None
        self._browser_owner = None
        self._robots = {}
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
                timeout=self.timeout_seconds,
                retries=self.attempts,
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

    def _turn(self, url):
        """This Fetcher's turn at a host, through the shared HostGate."""
        return HOSTS.turn(url, self.delay_seconds)

    def _robots_for(self, url, tier="http"):
        parts = urlsplit(url)
        origin = (parts.scheme, parts.netloc)
        if origin in self._robots:
            return self._robots[origin]

        robots_url = urlunsplit((*origin, "/robots.txt", "", ""))
        policy = None
        # Reading the policy is a request to the same host, so it waits its turn
        # like any other.
        try:
            with self._turn(robots_url):
                if tier == "browser" and self.allow_browser:
                    response = self._browser_session().fetch(robots_url, google_search=False)
                else:
                    response = self._http_session().get(
                        robots_url,
                        stealthy_headers=True,
                        timeout=min(15, self.timeout_seconds),
                        verify=CA_BUNDLE,
                    )
            if response.status == 200:
                body = response.body
                policy = Protego.parse(
                    body.decode("utf-8", "ignore") if isinstance(body, bytes) else str(body)
                )
        except Exception as error:
            policy = None
            if self.give_up_when_silent and _timed_out(error):
                self._silent.add(origin[1])

        # A robots file we cannot read is not permission. It is also not a
        # refusal: a site that blocks robots.txt has told us nothing, so we
        # proceed under our own rate limit rather than inventing rules.
        #
        # But a failure is only cached until the policy is read once. Sites that
        # refuse us intermittently refuse robots.txt too, and caching that
        # failure would silently widen what we consider allowed for the rest of
        # the process, after we had already been told the rules.
        if policy is not None or origin not in self._robots:
            self._robots[origin] = policy
        return self._robots[origin]

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

    def get(self, url, referer=None, tier="http", obey_robots=True, headers=None, timeout=None):
        """Fetch a page, or raise Disallowed or Blocked.

        The referer chains from the previous page when given. Without it the
        HTTP client attaches a Google referer to every request, which is
        incoherent on page three of a paginated crawl and is a known tell.

        headers is for API Sources that require their own, such as a version or
        an authorisation header. A request that carries them is sent as itself
        rather than disguised as a browser: a government API should see who is
        calling it.

        timeout overrides the session's thirty seconds for one request. Overpass
        can take well over a minute to answer; raising the default for every
        site instead would let one dead website stall a whole Search Run.
        """
        if obey_robots and not self.allowed(url, tier=tier):
            raise Disallowed(url)
        if urlsplit(url).netloc in self._silent:
            raise Unreachable(url, reason="its robots.txt timed out")

        last = None
        answered = False
        for attempt in self._tier_order(tier):
            fetch_at_tier = self._http_get if attempt == "http" else self._browser_get
            with self._turn(url):
                try:
                    response = fetch_at_tier(url, referer, headers, timeout)
                except Exception as error:  # a transport failure is not a refusal
                    last = f"{type(error).__name__}: {error}"
                    continue
            answered = True
            if not looks_blocked(response):
                return response
            last = _title_of(response) or f"status {getattr(response, 'status', '?')}"

        if not answered:
            raise Unreachable(url, reason=last or "no answer")
        raise Blocked(url, reason=last or "no tier succeeded")

    def post(self, url, data, headers=None, timeout=None, obey_robots=True):
        """Send a form, or raise Disallowed, Blocked or Unreachable.

        For the one Source whose listings only arrive through a site's own
        search form. HTTP tier only: a form post needs no rendering, and the
        same robots check, delay and block detection apply as to a page.
        """
        if obey_robots and not self.allowed(url):
            raise Disallowed(url)

        extra = {"timeout": timeout} if timeout else {}
        try:
            with self._turn(url):
                response = self._http_session().post(
                    url,
                    data=data,
                    headers=dict(headers or {}),
                    stealthy_headers=not headers,
                    verify=CA_BUNDLE,
                    **extra,
                )
        except Exception as error:  # a transport failure is not a refusal
            raise Unreachable(url, reason=f"{type(error).__name__}: {error}") from error
        if looks_blocked(response):
            raise Blocked(url, reason=_title_of(response) or f"status {response.status}")
        return response

    def _http_get(self, url, referer, headers=None, timeout=None):
        session = self._http_session()
        extra = {"verify": CA_BUNDLE, **({"timeout": timeout} if timeout else {})}
        if headers or referer:
            sent = dict(headers or {})
            if referer:
                sent["referer"] = referer
            return session.get(url, headers=sent, stealthy_headers=False, **extra)
        return session.get(url, stealthy_headers=True, **extra)

    def _browser_get(self, url, referer, headers=None, timeout=None):
        # API headers belong to the HTTP tier; a browser fetch renders a page.
        session = self._browser_session()
        if referer:
            return session.fetch(url, google_search=False, extra_headers={"referer": referer})
        return session.fetch(url, google_search=True)
