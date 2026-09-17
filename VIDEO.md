# Two-minute walkthrough outline

Aim: show the product working on real data, and make one argument. Do not tour
the code.

## 0:00 to 0:20, the gap

Open SaaSquatch's own page. Read the two lines out loud: "30+ entrepreneurs and
searchers" next to "2,000+ sales teams". Point at the filters: industry, size,
location, tech stack. Point at the navigation item "AI Company Scoring" and note
that nothing sits behind it.

Say the line: a searcher does not want a list of plumbers, they want the three
plumbers most likely to sell.

## 0:20 to 0:45, the search

On the home page, pick a trade and a market, and start a search. While it runs,
say what is happening: three sources, then we read each business's own website.
Let the rows appear on screen. Do not talk over the streaming; let it be seen.

Point at the per-source line. Say that a blocked source says so, because an
empty column has to read as a refusal and not as an empty market.

## 0:45 to 1:20, the score

Click the top row. This is the whole argument, so slow down.

Walk the panel: thirty-nine years trading, a named owner, a copyright four years
stale, its own domain, sixty reviews. Each line shows the points and links to
where it was seen.

Say: a searcher has to defend a shortlist to their investors. A number nobody can
audit is worth less than a smaller number they can trace.

Then click a thinly-evidenced row. Show the confidence figure and the
provisional marker. Say: missing data lowers confidence, never the score,
because the least digitally present businesses are often the best targets, and a
rubric that punished thin evidence would bury them.

## 1:20 to 1:40, the workflow

Filter to businesses trading twenty years or more with a known owner. Mark one
contacted, add a note. Export the CSV and show that it matches what is on screen
rather than the whole table.

Say: notes are keyed to the business, not the search, so they survive re-running
it.

## 1:40 to 2:00, the judgement call

Show the BBB toggle, switched off. Say the three reasons in one breath: its
robots policy disallows the search endpoint, its terms forbid compiling a
competing dataset, and it blocked us at the network edge anyway. The adapter is
written; the switch is off.

Close on that: the most interesting engineering decision here was choosing not
to take data we could technically have reached.

## Notes

- Have a completed run open in a second tab, in case a live source refuses
  during recording. A refusal is honest but it is not the story.
- Show the deployed link and `/api/rubric` for a second each, no more.
- Do not read the README aloud. The video is for the argument; the README is for
  the detail.
