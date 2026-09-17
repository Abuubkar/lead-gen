# The submission video

`docs/media/walkthrough.webm` is the screen recording: 1:42, 1600x900, silent.
It is scripted and reproducible, not a live take, so it can be re-shot without
losing the pacing.

The voice has to be yours. Read the script below over the clip; the marks are
measured off this recording, not estimated, so a line started on its mark lands
on the right frame. Word counts are sized for roughly 150 words a minute, which
is the pace the marks assume.

## The script

**0:00 — the gap** (36 words)

> SaaSquatch gives searchers filters and a CSV export. But a searcher doesn't
> want a list of plumbers. They want the three most likely to sell. So the score
> comes first: a hundred points across four groups, and every point has to name
> the fact behind it.

**0:13 — a finished run** (33 words)

> This run found ninety-three HVAC businesses in Phoenix and read ninety of their
> websites. Each bar is the score cut into its four groups, so you can see where
> the points came from before opening anything.

**0:26 — the argument. Slow down here; it is half the video.** (67 words)

> Accurate Energy: sixty-seven out of a hundred, on eighty-six percent of the
> rubric. Forty-six years trading. The copyright still reads 2019, seven years
> stale. Built on Wix. Every line shows its points and where the fact came from,
> the listing or the company's own site. A searcher has to defend a shortlist to
> their investors, and a number nobody can audit is worth less than a smaller one
> they can trace.

**0:51 — the searcher's call** (26 words)

> I mark it contacted and leave a note. The note is keyed to the business, not to
> this search, so it survives re-running the search tomorrow.

**1:04 — confidence, not score** (37 words)

> Now the top-ranked business: seventy-one points, but on only fifty-five percent
> of the rubric, because there is no website to read. Missing data lowers
> confidence, never the score. The least digitally present businesses are often
> the best targets.

**1:18 — narrowing** (28 words)

> Thirty years or more trading, and thirty-one becomes nine. Rows below the
> evidence floor are hidden by default, and it says so, with one click to show
> all ninety.

**1:30 — the export** (10 words)

> The CSV export follows the filters, not the whole table.

**1:34 — the judgement call. Land this one; it is the closing line.** (24 words)

> Better Business Bureau is switched off. Its terms forbid compiling a competing
> dataset. The best decision here was not taking data we could reach.

## What is deliberately not in the clip

**No live search.** The recording runs against the dataset that ships with the
repo, so it is identical every time and cannot be derailed by a source refusing
mid-take. The cost is that the streaming table never appears. If you want that
beat, start a real search in a second tab before recording and cut fifteen
seconds of rows arriving into the 0:13 mark; say what is happening while it runs
rather than talking over the rows.

**No competitor screen.** The earlier outline opened on SaaSquatch's own page.
The gap is easier to state in one sentence than to prove with a tour, and cutting
to a competitor spends ten seconds before the product appears.

**No code.** The README covers the detail. The video makes one argument.

## Two things to know before you read it out

The filter beat narrows on **years trading**, not on a known owner. Filtering to
a known owner returns exactly one business in this run: owner names survive a
deliberately strict cleaner, so they are sparse. One row is honest and makes a
poor demo, and thirty years of trading tells the succession story anyway.

The score bars in the drawer include greyed lines reading "not enough
information". Those are unresolved signals, and they are meant to be visible: it
is the same mechanism as the confidence figure. Do not apologise for them on
camera.

## Re-shooting it

The flow is a Playwright script driven against a local server, with an injected
cursor so a viewer can follow the clicks. Start the app on port 8099, clear the
`review` table so the list starts clean, and run the recorder. Playwright's
bundled ffmpeg only encodes VP8, so the output is `.webm`. That uploads fine to
YouTube, Drive and Loom; if the submission form insists on `.mp4`, a system
ffmpeg will convert it in one pass.
