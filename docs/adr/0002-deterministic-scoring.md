# The Score is computed by rule, not by a language model

Every point of a Business's Score comes from a named Signal with a stated contribution and a link to where it was observed. A language model is used only to extract facts and to draft an outreach line, never to produce or adjust the number.

We considered having a model score each Business directly, which would have been faster to build and would have handled messy input gracefully. We rejected it because a Searcher has to defend a shortlist to their investors, and a number nobody can audit is worth less than a smaller number they can trace. It also keeps the tool fully functional with no API key present.
