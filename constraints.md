## The word list (defines validity)

- The Moby Project single-word list, the exact file
  [`data/moby-single.txt`](data/moby-single.txt), pinned by SHA-256
  `2056d03ea1189904b98a13843dd258277f394470229c1e212460eac5074066c5`. The verifier
  refuses to run against any other file: a different list would change the spec.
- Canonical form (this defines the target set `D`): uppercase every line and sort
  byte-lexicographically. (The verifier also drops any non-letter or length-1 token and
  de-duplicates, but this file contains none of those, so those steps change nothing
  here.) `D`: 351,049 words, 3,321,695 letters total, longest 31, shortest 2.
- The record order in the artifact is exactly this canonical order: record `i` is
  word `D[i]`, so the word itself is never stored.

## Validity rules (any failure means `invalid`)

The verifier reconstructs the grid from `(n, records)` by painting each word's letters
from `D`, then requires all of:

1. V1, well-formed and in range: correct magic, exact file length, `2 <= n <= 3388`
   (`N_MAX = 3388`, the baseline side; a larger grid could not beat the baseline, so
   `n > 3388` is `invalid`), every record's `p < n*n`, and every word fits wholly
   inside the `n x n` grid (an across word needs `col + len <= n`; a down word needs
   `row + len <= n`).
2. V2, consistent overlaps: wherever two words cross, they must agree on the shared
   letter. A cell that two different words would fill with different letters is
   `invalid`.
3. V3, no lone cells: every filled cell must belong to at least one entry (a maximal
   run of length at least 2). An isolated single letter is `invalid`.
4. V4, exact lexicon match: an entry is a maximal run of 2 or more consecutive filled
   cells in a single row (across) or column (down), bounded by a blank or the grid
   edge ("maximal" means `CATS` is one entry, not also `CAT`). The multiset of all
   entries (across and down) must equal `D` exactly: every word appears exactly once,
   no entry is a non-word, no word is duplicated, none is missing. This single rule is
   the sole authority for coverage; the records only build the grid.
5. V5, connected: all filled cells form a single 4-connected component (up, down,
   left, right; not diagonal).

Reading is across (left to right) and down (top to bottom) only. No diagonals, no
reversed reading.

The score is fixed by V1 and V2 alone. The verifier compares it to the current best (or
the baseline when the board is empty): a grid that cannot beat or match the best can
never take the record, so the verifier returns `skipped` without running V3 to V5. This
is only a cost optimization; a grid that could take the record is always fully checked.
