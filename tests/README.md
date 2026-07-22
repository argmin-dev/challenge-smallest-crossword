# tests/

The verifier's own test suite, declared as the `[test] command` in `manifest.toml`
(`bash tests/run_all.sh`). Run it with:

```bash
bash tests/run_all.sh
```

It runs three layers, and the priority is input validation (the worst failure mode is
a verifier that scores an invalid submission, since the verifier is the spec):

1. `test_checker.py` (Python unit tests). Drives the checker's testable core with tiny
   synthetic word lists so each validity rule V1-V5 can be triggered in isolation
   (bad magic, wrong length, out-of-range anchor, overlap conflict, lone cell, non-word
   run, duplicate word, missing word, disconnected grid), each asserting the status is
   `invalid` with the right reason. Also covers valid acceptance, determinism, and the
   fingerprint against the real pinned dictionary and the baseline.

2. Rust build and unit tests (`cargo test --release` in `verifier/rust/`). Confirms the
   production verifier builds (which re-checks the pinned dictionary hash via
   `build.rs`) and that its own unit tests pass (dictionary size and letter count, the
   baseline metrics, rejection cases, and the baseline fingerprint constant).

3. `differential.py` (Python vs Rust). Runs both verifiers on a battery that reaches
   every rule path: the real baseline, byte-level corruptions (V1), full-size grids
   engineered to hit V2, V4-duplicate, V4-non-word, V4-missing, and V5-disconnected
   (each guarded by an assertion that it reached that rule), seeded random garbage,
   `current_best` skip-vs-validate scenarios, and a shifted baseline for fingerprint
   translation invariance. It requires identical status, metrics, and fingerprint on
   every one. This is what lets us ship the fast Rust verifier while trusting
   `checker.py` as the readable spec: if they ever diverge, this fails.

Needs `python3` and a Rust toolchain (`cargo`) on the host.
