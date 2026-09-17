# BBB is reached through category pages, never through search

BBB carries the two fields that matter most to a Searcher, the owner's name and the date the business started, but its robots policy disallows every URL carrying a query string. That covers both its search page and the JSON search endpoint behind it. We discover through the category directory path, which carries no query string, and then read the profile pages, which the policy allows explicitly.

A future reader will see us paginating a fifteen-result directory page and wonder why we do not call the search endpoint that returns the same data more conveniently. The answer is that we may not.

**Consequences**: BBB's terms of use license its content for personal, non-commercial use and separately forbid compiling its data into a competing service. Robots permits the pages; the terms do not permit this use of them. The adapter therefore ships disabled by default and is documented as a source we evaluated and declined, not one the product depends on. BBB was also unreachable from the development network, blocked at the edge for the whole address rather than challenged, which is a third and independent constraint.
