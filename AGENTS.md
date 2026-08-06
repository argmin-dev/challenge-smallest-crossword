# Solving this challenge (guide for coding agents)

You have been asked to solve the Smallest Complete Crossword challenge. This file is
the operational summary; [`README.md`](README.md), and the five documents ([`description.md`](description.md), [`submit.md`](submit.md),
[`constraints.md`](constraints.md), [`score.md`](score.md), [`verifier.md`](verifier.md)) hold the full spec. The verifier is public and
canonical: the verifier is the spec ([`verifier/checker.py`](verifier/checker.py) is
the readable reference).

## The goal

Produce one binary artifact (`XWD` format) that places all 351,049 Moby words into a
single connected, valid crossword with the smallest square side possible, then the
fewest filled cells. Smaller `side` wins; `filled_cells` breaks exact ties; an exact
tie on both keeps the earlier submission.

You submit only a position (anchor cell) and orientation (across or down) per word, in
dictionary order. The verifier paints the letters from the trusted list, so you cannot
inject letters or fake words; you can only choose where the real words go.

## The rules you must not break (any failure means `invalid`, no score)

- V1, artifact well-formed: magic `XWD`, exact length `1,404,201` bytes, `2 <= n <=
  3388`, every anchor in range, every word fits on the grid.
- V2, overlapping words agree on shared letters.
- V3, no lone letters: every filled cell is in a run of length at least 2.
- V4, the multiset of maximal across/down runs equals the whole list exactly: every
  word once, no non-word run, no duplicate, none missing. This is the hard one.
- V5, all filled cells are one 4-connected component.

The trap is V4 combined with density. As you interlock words tightly, you will create
incidental runs (a column of letters that spells a non-word, or a second copy of a
word). Any incidental non-word run, or any word appearing twice, is `invalid`.
Buffering (blank cells) prevents incidental runs but costs area. The whole game is
packing tightly while keeping every maximal run a distinct real word.

## How the score works

Two ranked metrics, primary first:

1. `side` (minimize) = `max(bbox_width, bbox_height)`.
2. `filled_cells` (minimize), tie-breaker only.

Ranking is strictly lexicographic and done by the platform, not the verifier. Both are
exact integers, so scoring is deterministic. `density`, `crossings`, `bbox_width`,
`bbox_height` are reported for context but never ranked.

On the backend, a submission that cannot beat or match the current leaderboard best (or
the baseline, if the board is empty) comes back `skipped` rather than `valid`/`invalid`:
it cannot take the record, so the verifier does not fully check it. Locally (no current
best) you always get `valid` or `invalid`.

## Build and check locally

Your solver produces the placements; encode them to the artifact and check it:

```bash
python3 tools/encode.py my_placements.txt my.xwd    # placements text -> XWD
```

Check with either verifier (they agree on every tested input; `tests/differential.py`
enforces it):

```bash
# Python reference (spec; needs only Python 3):
echo '{"artifact_path":"my.xwd","mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json

# Rust production (fast; needs a Rust toolchain):
( cd verifier/rust && cargo build --release )
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json ./verifier/rust/target/release/xword-verifier && cat out.json
```

An `invalid` result carries a specific `reason` (the conflicting cell, the offending
run, the duplicated word, a count of missing words, or the connectivity failure). Use
it to debug your placement.

## Approach (directions, not an answer)

- The lower bound is `side = 1289` (`filled_cells >= total_letters / 2`), and the
  baseline to beat is `side = 3388`, so there is a large gap and the early gains are
  easy.
- Adding crossings (letters shared between an across and a down word) is what shrinks
  the grid: each shared cell serves two words instead of one.
- Interlock high-overlap words first; place short words (there are only 419 two-letter
  words) throughout rather than last, so they are not stranded in dense cores. Track
  and forbid incidental runs as you place, and back off when a placement would create
  one or a duplicate.

## Don't waste time on

Trying to break the verifier by encoding tricks: letters come from the trusted list,
the length and range checks are exact, and V4 is decided on the reconstructed grid's
maximal runs, not on your records. Win by finding a smaller valid weave.
