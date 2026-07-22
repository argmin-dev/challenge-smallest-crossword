# Requirements

These are the precise, checkable rules. The verifier enforces exactly these rules and
nothing more: the verifier is the spec. [`verifier/checker.py`](verifier/checker.py)
is the readable reference implementation, and the Rust verifier in
[`verifier/rust/`](verifier/rust/) is the production one. A differential test
([`tests/differential.py`](tests/differential.py)) runs both on the same inputs and
requires them to agree; they are kept in lockstep, not formally proven equivalent.

## The word list (defines validity)

- The Moby Project single-word list, the exact file
  [`data/moby-single.txt`](data/moby-single.txt), pinned by SHA-256
  `2056d03ea1189904b98a13843dd258277f394470229c1e212460eac5074066c5`. The verifier
  refuses to run against any other file (a different list would change the spec).
- Canonical form (this defines the target set `D`): uppercase every line and sort
  byte-lexicographically. (The verifier also drops any non-letter or length-1 token and
  de-duplicates, but this file contains none of those, so those steps change nothing
  here.) `D`: 351,049 words, 3,321,695 letters total, longest 31, shortest 2.
- The record order in the artifact is exactly this canonical order: record `i` is
  word `D[i]`, so the word itself is never stored.

## Submission format (artifact)

A little-endian binary file:

```
bytes 0..3    magic: the 3 ASCII bytes "XWD"
bytes 3..5    n: u16, the side of the coordinate space (the grid is n x n)
then exactly |D| = 351,049 records, each a u32:
    bit 31        orientation: 0 = across (horizontal), 1 = down (vertical)
    bits 0..=30   p: the anchor index, with p = row + n * col
```

- The file length must be exactly `5 + 4 * 351049 = 1,404,201` bytes. Any other length
  is `invalid`.
- Decoding a record: `row = p % n`, `col = p // n`. The word's first letter (leftmost
  for across, topmost for down) goes at `(row, col)`. An across word extends right
  (increasing column); a down word extends down (increasing row).

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

The score (`side`, `filled_cells`) is fixed by V1 and V2 alone. The verifier compares it
to `current_best` (the current leaderboard best, or the baseline when the board is empty,
supplied by the platform): a grid that cannot beat or match the best can never take the
record, so the verifier returns `skipped` without running V3-V5. This is only a cost
optimization; a grid that could take the record is always fully checked.

## Scoring

On `valid`, the verifier returns two ranked metrics, primary first:

1. `side` (`min`): `max(bbox_width, bbox_height)`, the side of the smallest square
   enclosing all filled cells.
2. `filled_cells` (`min`): the count of cells that hold a letter. Tie-breaker only.

Ranking is strictly lexicographic and done by the platform, not the verifier: a new
record must be strictly better on the first metric where it differs from the current
best; a tie on both keeps the incumbent (earliest submission wins). Both metrics are
exact integers read off the reconstructed grid, so scoring is deterministic: the same
artifact always yields the same metrics.

Display-only values (returned in `info`, reported but never ranked): `density =
filled_cells / side^2`, `crossings` (the number of shared cells, `total_letters -
filled_cells`, where `total_letters` is 3,321,695 for `D`), `bbox_width`, `bbox_height`.

## Determinism and duplicate rejection

- No randomness: one fixed instance (the whole list), checked in full, so no seed or
  sample is needed.
- Fingerprint (dedup key): the verifier reconstructs the grid, shifts it so its filled
  bounding box starts at the origin, then returns the SHA-256 over the sorted filled
  cells (each as row, column, letter). So two artifacts that describe the same grid up
  to a translation (including different byte encodings of it) collide and are treated
  as duplicates. It is not invariant to rotation or reflection: a rotated or mirrored
  version of a grid is a different fingerprint. This only affects dedup, never the
  score. On any malformed artifact the fingerprint falls back to the SHA-256 of the
  raw bytes so dedup still works. `[dedup] scope = "challenge"` (dedup across all
  solvers of this challenge).
