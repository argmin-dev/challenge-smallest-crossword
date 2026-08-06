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
- Fingerprint (the dedup key): canonical up to the eight symmetries of the square, so a
  grid, its rotations and its mirror images are all one key. Each of the eight images of
  the reconstructed grid is shifted so its filled bounding box starts at the origin,
  sorted by (row, column), and serialized as 9 bytes per cell (row as u32 little-endian,
  column as u32 little-endian, one ASCII letter); the lexicographically smallest of those
  eight byte strings is hashed once with SHA-256. Two files describing the same crossword
  up to translation, rotation or reflection therefore collide, whatever their byte
  encoding. A malformed file falls back to the SHA-256 of its raw bytes, so dedup still
  works. None of this affects the score.
- Dedup scope is the whole challenge, so a grid any solver has already submitted is
  rejected as a duplicate.
