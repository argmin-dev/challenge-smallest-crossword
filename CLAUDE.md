# CLAUDE.md

This is an argmin challenge: pack the entire Moby single-word list (351,049 words) into
the smallest square crossword. The primary metric is `side` (smaller wins); the tie-breaker
is `filled_cells` (fewer wins). Exact ties keep the earliest submission.

See [AGENTS.md](./AGENTS.md) for the full solver guide (what to submit, the validity
rules V1-V5, the score, and the local build/check workflow). [`README.md`](README.md),
[`objective.md`](objective.md), and [`constraints.md`](constraints.md) hold the
complete spec.

## The verifier is the spec

There are two verifiers, and a differential test
([`tests/differential.py`](tests/differential.py)) runs both on the same inputs and
requires them to agree (they are kept in lockstep, not formally proven equivalent):

- [`verifier/checker.py`](verifier/checker.py) is the readable reference and the
  authoritative spec. Read it to understand exactly how a submission is judged.
- [`verifier/rust/`](verifier/rust/) is the fast production verifier that runs on the
  backend. It mirrors `checker.py` constant-for-constant (same magic, `N_MAX`, record
  layout, rules V1-V5, and fingerprint). The pinned Moby list is compiled into the
  binary; `build.rs` fails the build if the file's SHA-256 does not match.

Do not edit [`verifier/entrypoint.py`](verifier/entrypoint.py) (IO-contract
boilerplate). If you change a rule, change it in both verifiers and keep the
differential test green, or the spec and production diverge.

## Quick start

```bash
# encode your solver's placements and check the artifact:
python3 tools/encode.py my_placements.txt my.xwd
echo '{"artifact_path":"my.xwd","mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json
```

Run the full verifier test suite (the `[test] command`) with `bash tests/run_all.sh`:
Python unit tests, then the Rust build and unit tests, then the Python/Rust
differential.
