#!/usr/bin/env python3
"""
Verifier entrypoint -- the argmin IO contract. Boilerplate; the challenge logic lives in
checker.py. This is the LOCAL/dev path (the [dev] entrypoint). Production runs the Rust
verifier (verifier/rust) via the Dockerfile, which implements the identical contract.

Contract:
  - Read input JSON at $ARGMIN_INPUT:
        { "artifact_path": "...", "params": {...},
          "current_best": {<label>: <num>, ...} | null,
          "mode": "verify" | "fingerprint" }        # mode defaults to "verify"
  - Write output JSON at $ARGMIN_OUTPUT:
        verify      -> { "status", "metrics"|null, "reason", "info"|null }
        fingerprint -> { "fingerprint": "<stable string>" }
"""
import json
import os
import sys

# Make `import checker` work regardless of the working directory (dev runs this from the
# repo root; the container runs it from verifier/).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.environ["ARGMIN_INPUT"]) as f:
        inp = json.load(f)

    mode = inp.get("mode") or "verify"
    artifact = inp["artifact_path"]
    params = inp.get("params") or {}
    current_best = inp.get("current_best")

    import checker
    if mode == "fingerprint":
        out = {"fingerprint": checker.fingerprint(artifact)}
    elif mode == "verify":
        out = checker.verify(artifact, params, current_best)
    else:
        out = {"status": "invalid", "metrics": None, "reason": f"unknown mode: {mode}",
               "info": None}

    with open(os.environ["ARGMIN_OUTPUT"], "w") as f:
        json.dump(out, f)
    sys.exit(0)


if __name__ == "__main__":
    main()
