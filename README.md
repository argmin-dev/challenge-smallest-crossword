# Smallest Complete Crossword

Pack the entire Moby single-word list into the smallest square crossword you can. This
README is self-contained: read it and you can build, encode, and check a submission
locally. [`objective.md`](objective.md) and [`constraints.md`](constraints.md) restate
the same rules in spec form.

## The problem

Arrange all 351,049 words of the [Moby Project single-word list](https://www.gutenberg.org/ebooks/3201)
(public domain, by Grady Ward; filtered to words of length at least 2, so the whole
list is in play) into one square grid so it reads as a single connected crossword, and
make the grid as small as possible.

A grid is valid when it is a real, complete crossword over the whole list:

- every maximal across-run and down-run of 2 or more letters is a word of the list,
- every word appears exactly once, no run is a non-word, none is missing,
- overlapping words agree on shared letters, no letter stands alone, and
- all filled cells form one connected block.

You are scored on two things, ranked lexicographically:

1. `side` (smaller wins): the side of the smallest square enclosing all letters.
2. `filled_cells` (fewer wins): tie-breaker; fewer filled cells means a tighter weave
   (more shared letters).

Exact ties keep the earlier submission. See [`objective.md`](objective.md) for the
full scoring text and the display-only metrics.

## What you submit

Not the grid, and not any letters: only where each word goes. The artifact is a binary
file, `XWD`, holding the grid side `n` and one record per word (in dictionary order)
giving that word's anchor cell and orientation (across or down). The verifier paints
the letters from the trusted list and checks the result, so you can only position the
real words, never inject a letter or a fake word. Full format in
[`constraints.md`](constraints.md); for the full list the file is exactly `1,404,201`
bytes.

## How small can it get

- Lower bound `side >= 1289`. Each filled cell is shared by at most two words, so
  `filled_cells >= ceil(total_letters / 2) = 1,660,848` and
  `side >= ceil(sqrt(1,660,848)) = 1289`. This is a floor no valid grid can beat, not a
  claim that a grid this small exists.
- The baseline record to beat is `side = 3388` (`filled_cells = 2,970,647`), far
  above the 1289 floor, so there is a large gap to close.

## Build an artifact

Your solver decides where each word goes and produces the `XWD` binary. You can write
the bytes directly from the format in [`constraints.md`](constraints.md), or emit a
plain-text placements file (line 1 = word count, then one `row col orient` per word in
dictionary order, `orient` 0 = across / 1 = down) and encode it:

```bash
python3 tools/encode.py my_placements.txt my.xwd
```

## Check a submission locally

Two verifiers that agree on every tested input (a differential test enforces it). Both
read the artifact the same way the platform does (input JSON at `$ARGMIN_INPUT`, result
at `$ARGMIN_OUTPUT`).

### Python reference (easiest; this file is the spec)

Needs only Python 3.

```bash
echo '{"artifact_path":"my.xwd","params":{},"current_best":null,"mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json
# -> {"status":"valid","metrics":{"side":...,"filled_cells":...},"reason":"","info":{...}}
```

Fingerprint (dedup key) mode:

```bash
echo '{"artifact_path":"my.xwd","mode":"fingerprint"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json
```

The full-list grid checks in a few seconds in Python and about a second in Rust.

### Rust production verifier (fast; runs on the backend)

Needs a Rust toolchain. The word list is compiled into the binary.

```bash
( cd verifier/rust && cargo build --release )
echo '{"artifact_path":"my.xwd","mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json ./verifier/rust/target/release/xword-verifier && cat out.json
```

## How verification works

1. Decode (V1): check magic, exact file length, `2 <= n <= 3388`, every anchor in
   range, every word fits on the grid.
2. Paint (V2): place each word's letters (from the trusted list) into a sparse cell
   map; any two words disagreeing on a shared cell is `invalid`.
3. Runs (V3, V4): find every maximal across/down run of length at least 2. Every
   filled cell must lie in one (V3), and the multiset of runs must equal the whole word
   list exactly (V4): every word once, no non-word run, no duplicate, none missing.
4. Connectivity (V5): all filled cells must be one 4-connected component.
5. Metrics: `side = max(bbox_width, bbox_height)`, `filled_cells`, plus the
   display-only `density`, `crossings`, `bbox_width`, `bbox_height`.

The design is sparse (a cell map, two sorts for the runs, a flood fill for
connectivity); it never materializes an `n x n` grid, so cost scales with the number of
filled cells, not `n^2`.

## Run the verifier's own test suite

```bash
bash tests/run_all.sh    # Python unit tests + Rust build/tests + Python/Rust differential
```

See [`tests/README.md`](tests/README.md) for what each layer covers.

## Layout

```
manifest.toml          technical contract (metrics, dedup, limits, descriptions)
objective.md           problem statement + scoring
constraints.md         word list, artifact format, validity rules V1-V5
data/moby-single.txt   the pinned Moby word list (SHA-256 in the verifier)
verifier/
  entrypoint.py        IO-contract boilerplate (verify + fingerprint). Do not edit.
  checker.py           the readable reference verifier (the spec)
  rust/                the fast production verifier
  Dockerfile           production image: builds the Rust verifier, runs it non-root
reference/
  baseline.xwd         the baseline record to beat (side 3388)
tools/
  encode.py            placements text -> XWD artifact
  make_samples.py      regenerate samples/ from the baseline
samples/               small example artifacts + expected verify statuses
tests/                 the verifier test suite ([test] command in manifest.toml)
```


## License

Copyright (C) 2026 argmin.dev

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE)
for the full text.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

The Moby single-word list in `data/moby-single.txt` is a public-domain work (Grady Ward's
Moby Project, https://www.gutenberg.org/ebooks/3201) and is not covered by this license.
