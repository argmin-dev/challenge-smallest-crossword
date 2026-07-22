#!/usr/bin/env bash
# The challenge's full verifier test suite (declared as [test] command in manifest.toml).
# challenge-validator runs this on the host under --run and requires exit 0.
#
# It runs three layers:
#   1. Python reference unit tests (per-rule input validation, on tiny + real dictionaries)
#   2. Rust build + Rust unit tests
#   3. Differential test: Python reference vs Rust production verifier agree on every input
#
# Needs python3 and a Rust toolchain (cargo) on the host.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== [1/3] Python reference unit tests =="
python3 -m unittest discover -s tests -p 'test_*.py'

echo "== [2/3] Rust build + unit tests =="
( cd verifier/rust && cargo build --release && cargo test --release )

echo "== [3/3] Differential (Python reference vs Rust production) =="
python3 tests/differential.py

echo "ALL VERIFIER TESTS PASSED"
