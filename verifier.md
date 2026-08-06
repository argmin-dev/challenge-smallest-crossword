Paints each word's letters from the pinned word list into a grid at the placement you
gave it, checks every rule in [Constraints](constraints.md), then scores `side` and
`filled_cells`. It enforces those rules and nothing more: the verifier is the spec.

There are two implementations. [`verifier/checker.py`](verifier/checker.py) is the
readable reference and the authoritative one; the Rust verifier in
[`verifier/rust/`](verifier/rust/) is the fast production one, mirroring it constant for
constant. A differential test ([`tests/differential.py`](tests/differential.py)) runs
both on the same inputs and requires them to agree; they are kept in lockstep, not
formally proven equivalent.

## Determinism and duplicates

- No randomness: one fixed instance, the whole list, checked in full. No seed or sample
  is involved, and the same submission always scores the same.
- Fingerprint (the dedup key): the grid is shifted so its filled bounding box starts at
  the origin, then hashed with SHA-256 over the sorted filled cells (each as row,
  column, letter). Two files describing the same grid up to a translation therefore
  collide, whatever their byte encoding. Rotations and reflections do not: a mirrored
  grid is a different fingerprint. A malformed file falls back to the SHA-256 of its raw
  bytes, so dedup still works. None of this affects the score.
- Dedup scope is the whole challenge, so a grid any solver has already submitted is
  rejected as a duplicate.
