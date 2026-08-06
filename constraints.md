## The word list (defines validity)

- The Moby Project single-word list, the exact file
  [`data/moby-single.txt`](data/moby-single.txt), pinned by SHA-256
  `2056d03ea1189904b98a13843dd258277f394470229c1e212460eac5074066c5`. The verifier
  refuses to run against any other file: a different list would change the spec.
- Canonical form, which defines the target set `D`: uppercase every line and sort
  byte-lexicographically. (The verifier also drops non-letter and length-1 tokens and
  de-duplicates; this file has none, so those steps are no-ops.) `D` is 351,049 words,
  3,321,695 letters, longest 31, shortest 2.
- Record `i` in the submitted file is word `D[i]`, in exactly this order, so the word
  itself is never stored.

## Validity rules (any failure means `invalid`)

The verifier reconstructs the grid from `(n, records)` by painting each word's letters
from `D`, then requires all of:

1. **Well-formed and in range**: correct magic, exact file length, `2 <= n <= 3388`
   (a grid wider than the baseline side could not beat the baseline), every record's
   `p < n*n`, and every word fits wholly inside the `n x n` grid (an across word needs
   `col + len <= n`, a down word needs `row + len <= n`).
2. **Consistent overlaps**: wherever two words cross they agree on the shared letter.
   A cell two words would fill differently is `invalid`.
3. **No lone cells**: every filled cell belongs to at least one entry. An isolated
   single letter is `invalid`.
4. **Exact lexicon match**: an entry is a maximal run of 2 or more consecutive filled
   cells in one row (across) or column (down), bounded by a blank or the grid edge
   ("maximal" means `CATS` is one entry, not also `CAT`). The multiset of all entries,
   across and down, must equal `D` exactly: every word once, no non-word, no duplicate,
   none missing. This rule alone decides coverage; the records only build the grid.
5. **Connected**: all filled cells form a single 4-connected component (up, down, left,
   right, not diagonal).

Reading is across (left to right) and down (top to bottom) only: no diagonals, no
reversed words.

Rules 1 and 2 alone fix the score, so the verifier compares it to the current best first
(or to the baseline on an empty board). A grid that cannot beat the best can never take
the record, so it returns `skipped` without running rules 3 to 5. That is a cost
optimization only: a grid that could take the record is always checked in full.
