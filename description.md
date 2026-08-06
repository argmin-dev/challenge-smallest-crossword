Pack every word of a fixed public word list into a single square grid so the whole
thing reads as one connected crossword, and make that grid as small as you can.
Smaller side wins; among grids of the same side, fewer filled cells wins.

The word list is the Moby Project single-word list, filtered to words of length at
least 2, uppercased, de-duplicated, and sorted: 351,049 words (3,321,695 letters,
longest 31, shortest 2). It is pinned by hash inside the verifier, so it cannot change
under you.

A valid grid is a real crossword over that whole list: every across-run and every
down-run of two or more letters is a distinct word of the list, every word appears
exactly once, no run is a non-word, and all letters form one connected block.
