Decodes a binary file of one placement (anchor plus orientation) per dictionary word,
paints each word's letters from the pinned Moby single-word list into a grid, then
checks it is a valid connected crossword: consistent overlaps, no lone letters, and the
multiset of maximal across and down runs equals the whole word list exactly (every word
once, no non-word run, no duplicate, none missing). Scores the result as `side` then
`filled_cells`.

The verifier enforces exactly the rules in [Constraints](constraints.md) and nothing more: the
verifier is the spec. There are two implementations.
[`verifier/checker.py`](verifier/checker.py) is the readable reference and the
authoritative one; the Rust verifier in [`verifier/rust/`](verifier/rust/) is the fast
production one, mirroring it constant for constant. A differential test
([`tests/differential.py`](tests/differential.py)) runs both on the same inputs and
requires them to agree; they are kept in lockstep, not formally proven equivalent.

## Determinism and duplicates

- No randomness: one fixed instance (the whole list), checked in full, so no seed or
  sample is needed. The same artifact always yields the same metrics.
- Fingerprint (the dedup key): the verifier reconstructs the grid, shifts it so its
  filled bounding box starts at the origin, then returns the SHA-256 over the sorted
  filled cells (each as row, column, letter). So two artifacts that describe the same
  grid up to a translation, including different byte encodings of it, collide and are
  treated as duplicates. It is not invariant to rotation or reflection: a rotated or
  mirrored grid is a different fingerprint. This only affects dedup, never the score.
  On any malformed artifact the fingerprint falls back to the SHA-256 of the raw bytes
  so dedup still works.
- Dedup scope is the whole challenge, so a grid already submitted by any solver is
  rejected as a duplicate.
