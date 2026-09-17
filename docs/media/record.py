"""Records the walkthrough in VIDEO.md against a local server on port 8099.

Not part of the application. It drives the real pages with Playwright, which
scrapling already installs, and writes docs/media/walkthrough.webm. The flow is
scripted so the pacing survives a re-shoot: the marks in VIDEO.md are measured
off this script's waits.

Playwright records no mouse pointer, so a cursor is injected and moved to each
target before the click. Clear the review table first if you want the list to
start clean.

    uv run python docs/media/record.py
"""

import pathlib
import shutil
import tempfile

from playwright.sync_api import sync_playwright

FINAL = pathlib.Path("docs/media/walkthrough.webm")
OUT = pathlib.Path(tempfile.mkdtemp(prefix="walkthrough-"))
BASE = "http://localhost:8099"
W, H = 1600, 900

CURSOR = """
(() => {
  function mk() {
    try {
      var root = document.documentElement || document.body;
      if (!root) return null;
      var d = document.getElementById('__cur');
      if (d) return d;
      d = document.createElement('div');
      d.id = '__cur';
      d.style.cssText = 'position:fixed;left:800px;top:840px;width:22px;height:22px;'
        + 'border:2px solid #111;background:#c6f25e;border-radius:50%;'
        + 'z-index:2147483647;pointer-events:none;opacity:.95;'
        + 'transform:translate(-50%,-50%);transition:left .5s cubic-bezier(.4,0,.2,1),'
        + 'top .5s cubic-bezier(.4,0,.2,1),width .12s,height .12s;';
      root.appendChild(d);
      return d;
    } catch (e) { return null; }
  }
  window.__cur = function (x, y, ms) {
    var d = mk();
    if (!d) return;
    d.style.transitionDuration = (ms/1000)+'s, '+(ms/1000)+'s, .12s, .12s';
    d.style.left = x+'px'; d.style.top = y+'px';
  };
  window.__pulse = function () {
    var d = mk();
    if (!d) return;
    d.style.width = '12px'; d.style.height = '12px';
    setTimeout(function () { d.style.width='22px'; d.style.height='22px'; }, 160);
  };
  try {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', mk);
    } else { mk(); }
  } catch (e) {}
})();
"""


def beat(page, ms):
    page.wait_for_timeout(ms)


def move(page, x, y, ms=520):
    page.wait_for_function("() => typeof window.__cur === 'function'")
    page.evaluate("([x,y,m]) => window.__cur(x,y,m)", [x, y, ms])
    beat(page, ms + 90)


def tap(page, loc, ms=520, settle=260):
    loc.scroll_into_view_if_needed()
    beat(page, 140)
    b = loc.bounding_box()
    move(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, ms)
    page.evaluate("window.__pulse()")
    beat(page, settle)
    loc.click()


def glide(page, target, sel=None, step=90, pause=110):
    js = "([s,t]) => (s ? document.querySelector(s) : document.scrollingElement).scrollTop = t"
    cur = page.evaluate(
        "(s) => (s ? document.querySelector(s) : document.scrollingElement).scrollTop", sel
    )
    n = max(1, int(abs(target - cur) / step))
    for i in range(1, n + 1):
        page.evaluate(js, [sel, cur + (target - cur) * i / n])
        beat(page, pause)


def point(page, loc, ms=700, hold=0):
    """Put the cursor on an element without clicking it."""
    loc.scroll_into_view_if_needed()
    b = loc.bounding_box()
    move(page, b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, ms)
    if hold:
        beat(page, hold)


def drawer_to(page, frac, pause=150):
    top = page.evaluate(
        "() => { const d = document.querySelector('.drawer');"
        " return (d.scrollHeight - d.clientHeight); }"
    )
    glide(page, int(top * frac), sel=".drawer", step=55, pause=pause)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(
        viewport={"width": W, "height": H},
        record_video_dir=str(OUT),
        record_video_size={"width": W, "height": H},
    )
    ctx.add_init_script(CURSOR)
    page = ctx.new_page()

    # 1. The rubric, stated before any data is on screen. (~12s)
    page.goto(f"{BASE}/", wait_until="networkidle")
    beat(page, 3000)
    move(page, 175, 250, 900)  # four groups, weights fixed
    beat(page, 3400)
    move(page, 175, 520, 900)  # confidence, never the score
    beat(page, 3600)

    # 2. A finished run, ranked. (~15s)
    page.goto(f"{BASE}/runs/4", wait_until="networkidle")
    beat(page, 2800)
    move(page, 1460, 110, 900)  # the bar is the breakdown
    beat(page, 3000)
    glide(page, 820)
    beat(page, 1800)
    glide(page, 0)
    beat(page, 1500)

    # 3. The argument: a business we could read, and every point behind it. (~31s)
    rich = page.locator("a.business", has_text="Accurate Energy Management").first
    tap(page, rich, ms=700)
    page.wait_for_selector("#drawer .d-head", timeout=8000)
    beat(page, 3200)
    move(page, 1500, 150, 800)  # 67 of 100, 86% evaluated
    beat(page, 3000)
    point(page, page.locator("#drawer .facts"), ms=800, hold=3000)
    drawer_to(page, 0.30)
    beat(page, 4200)  # succession, each line with its source
    drawer_to(page, 0.58)
    beat(page, 4000)  # underinvestment: stale copyright, wix
    drawer_to(page, 0.82)
    beat(page, 3600)  # acquirability, demand proof

    # 4. The searcher's call, kept with the business. (~15s)
    tap(page, page.locator("form.review .states label:has(input[value='contacted'])"), ms=620)
    beat(page, 900)
    note = page.locator("form.review textarea")
    tap(page, note, ms=560)
    note.type("Owner answered. Retiring in two years, open to talking.", delay=46)
    beat(page, 1100)
    tap(page, page.locator("form.review button[type=submit]"), ms=560)
    beat(page, 2400)
    tap(page, page.locator("#drawer .close"), ms=560)
    beat(page, 1800)

    # 5. A business we could barely read keeps its score and loses confidence. (~13s)
    glide(page, 0)
    thin = page.locator("a.business", has_text="Thermocool").first
    point(page, thin, ms=700, hold=1600)  # top of the list, and no website
    tap(page, thin, ms=520)
    page.wait_for_selector("#drawer .d-head", timeout=8000)
    beat(page, 2600)
    move(page, 1500, 155, 800)  # 71, on 55% of the rubric
    beat(page, 4200)
    tap(page, page.locator("#drawer .close"), ms=560)
    beat(page, 1600)

    # 6. Narrowing to the shape of target worth a call. (~13s)
    glide(page, 0)
    years = page.locator("input[name=min_years]")
    tap(page, years, ms=620)
    years.type("30", delay=170)
    beat(page, 1000)
    tap(page, page.locator("button.go"), ms=560)
    page.wait_for_load_state("networkidle")
    beat(page, 3400)
    point(page, page.locator(".rail .fx", has_text="Shown").first, ms=700, hold=2600)

    # 7. The export follows the filters, not the table. (~6s)
    point(page, page.locator("a.link", has_text="Export CSV").first, ms=800, hold=3400)

    # 8. The source we chose not to take. (~11s)
    page.goto(f"{BASE}/", wait_until="networkidle")
    beat(page, 1800)
    point(
        page,
        page.locator("label.check", has_text="Better Business Bureau").first,
        ms=900,
        hold=5200,
    )

    page.close()
    ctx.close()
    br.close()

vids = sorted(OUT.glob("*.webm"))
if not vids:
    raise SystemExit("no video was written")
shutil.move(str(vids[0]), FINAL)
shutil.rmtree(OUT, ignore_errors=True)
print("wrote", FINAL, FINAL.stat().st_size, "bytes")
