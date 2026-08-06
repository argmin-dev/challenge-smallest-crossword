Pack every word of a fixed public word list into a single square grid so the whole
thing reads as one connected crossword, and make that grid as small as you can.
Smaller side wins; among grids of the same side, fewer filled cells wins.

The word list is the Moby Project single-word list, filtered to words of length at least
2, uppercased, de-duplicated, and sorted: 351,049 words (3,321,695 letters, longest 31,
shortest 2). It is pinned by hash in the verifier (see [`constraints.md`](constraints.md)).

A valid grid is a real crossword over that whole list: every across-run and every
down-run of two or more letters is a distinct word of the list, every word appears
exactly once, no run is a non-word, and all letters form one connected block.

## What you submit

You submit only, for each word, where it goes: an anchor cell and an orientation
(across or down). The verifier paints the letters itself, taking them from the trusted
word list, then checks the result. So a submission can only choose positions for the
real dictionary words; it can never inject a letter or a word that is not on the list.

The artifact is a fixed-size binary file (the format is in [`constraints.md`](constraints.md)):
a 3-byte magic, the grid side `n`, then one fixed-width record per word, in dictionary
order, so a record's position in the file is its word. For the full list the file is
exactly `5 + 4 * 351049 = 1,404,201` bytes.

## Score

Two metrics, ranked lexicographically (the first decides; the second only breaks an
exact tie on the first):

1. `side` (minimize): `max(bbox_width, bbox_height)`, the side of the smallest square
   enclosing all filled cells (so blank borders never help or hurt).
2. `filled_cells` (minimize): the count of cells that hold a letter. Fewer at a given
   side means more letters shared between crossing words.

A new record must be strictly better on the first metric where it differs from the
current best. A submission that ties on both metrics does not displace the incumbent,
so exact ties resolve to the earliest submission. There is no minimum-improvement
margin.

Also reported next to each entry, for context only and never ranked: `density`
(`filled_cells / side^2`), `crossings` (the number of shared cells, total letters minus
`filled_cells`), `bbox_width`, and `bbox_height`.
