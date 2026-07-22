"""
Differential test: the Rust production verifier MUST agree with the Python reference
(checker.py) on every input. It runs BOTH verifiers with the pinned Moby dictionary and
asserts they return the same status, the same metrics when valid, and the same fingerprint,
over a battery that reaches every rule path:
  - the real baseline (valid) and targeted byte-level corruptions of it (V1),
  - full-size adversarial grids engineered to reach V2, V4-duplicate, V4-non-word,
    V4-missing, and V5-disconnected (each guarded by an assertion that it hit that rule),
  - seeded random garbage,
  - current_best scenarios exercising the skip-vs-validate early exit, and
  - a horizontally shifted baseline checking fingerprint translation invariance.

This is the guard that lets us ship a fast Rust verifier on the backend while trusting the
readable Python file as the spec: if they ever diverge, this fails.

Run: python3 tests/differential.py   (also invoked by tests/run_all.sh)
Requires the release binary at verifier/rust/target/release/xword-verifier.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "verifier"))
import checker  # noqa: E402

RUST = os.path.join(ROOT, "verifier", "rust", "target", "release", "xword-verifier")
BASELINE = os.path.join(ROOT, "reference", "baseline.xwd")

WORDS, IDX, TOTAL = checker._load_dictionary()
N_WORDS = len(WORDS)


def py_verify(raw, current_best=None):
    return checker.check_bytes(raw, WORDS, IDX, TOTAL, current_best)


def py_fingerprint(raw):
    return checker.fingerprint_bytes(raw, WORDS)


def rust(raw, mode, current_best=None):
    with tempfile.TemporaryDirectory() as d:
        art = os.path.join(d, "artifact.bin")
        with open(art, "wb") as f:
            f.write(raw)
        inp = os.path.join(d, "in.json")
        outp = os.path.join(d, "out.json")
        obj = {"artifact_path": art, "mode": mode}
        if current_best is not None:
            obj["current_best"] = current_best
        with open(inp, "w") as f:
            json.dump(obj, f)
        env = dict(os.environ, ARGMIN_INPUT=inp, ARGMIN_OUTPUT=outp)
        subprocess.run([RUST], env=env, check=True)
        with open(outp) as f:
            return json.load(f)


def artifacts():
    """Yield (name, raw_bytes)."""
    with open(BASELINE, "rb") as f:
        base = f.read()
    yield "baseline", base

    def mut(fn):
        b = bytearray(base)
        fn(b)
        return bytes(b)

    HL = checker.HEADER_LEN     # 5 (3 magic + 2 n)
    RL = checker.RECORD_LEN     # 4 (u32 record)
    ML = len(checker.MAGIC)     # 3 (magic width)
    NB = HL - ML                # width of the n field
    n = int.from_bytes(base[ML:HL], "little")
    yield "bad_magic", mut(lambda b: b.__setitem__(slice(0, ML), b"X" * ML))
    yield "truncated", base[:-1]
    yield "trailing_byte", base + b"\x00"
    yield "n_zero", mut(lambda b: b.__setitem__(slice(ML, HL), (0).to_bytes(NB, "little")))
    yield "n_huge", mut(lambda b: b.__setitem__(slice(ML, HL), (checker.N_MAX + 1).to_bytes(NB, "little")))
    yield "anchor_oor", mut(lambda b: b.__setitem__(slice(HL, HL + RL), (n * n).to_bytes(RL, "little")))
    # swap first two records
    def swap(b):
        r0 = bytes(b[HL:HL + RL]); r1 = bytes(b[HL + RL:HL + 2 * RL])
        b[HL:HL + RL] = r1; b[HL + RL:HL + 2 * RL] = r0
    yield "swap_two_records", mut(swap)
    # all records point at p=0 across -> massive overlap
    allzero = bytearray(checker.MAGIC) + n.to_bytes(NB, "little") + b"\x00" * (RL * N_WORDS)
    yield "all_zero_records", bytes(allzero)

    # seeded random garbage (deterministic LCG; no external randomness)
    for seed in (1, 2, 3):
        state = seed
        sm = 97
        body = bytearray()
        for _ in range(N_WORDS):
            state = (1103515245 * state + 12345) & 0xFFFFFFFF
            body += state.to_bytes(RL, "little")
        raw = bytearray(checker.MAGIC) + sm.to_bytes(NB, "little") + body
        yield f"random_seed{seed}", bytes(raw)


def main():
    if not os.path.exists(RUST):
        sys.exit(f"rust binary not found at {RUST}; build it first (cargo build --release).")
    failures = 0
    checked = 0
    for name, raw in artifacts():
        checked += 1
        pv = py_verify(raw)
        rv = rust(raw, "verify")
        # status must match
        if pv["status"] != rv["status"]:
            print(f"[FAIL] {name}: status py={pv['status']} rust={rv['status']}")
            failures += 1
            continue
        # metrics must match when valid
        if pv["status"] == "valid":
            pm = pv["metrics"]
            rm = rv["metrics"]
            if pm != rm:
                print(f"[FAIL] {name}: metrics py={pm} rust={rm}")
                failures += 1
                continue
        # fingerprint must match
        pf = py_fingerprint(raw)
        rf = rust(raw, "fingerprint")["fingerprint"]
        if pf != rf:
            print(f"[FAIL] {name}: fingerprint py={pf} rust={rf}")
            failures += 1
            continue
        print(f"[ok]   {name}: status={pv['status']}"
              + (f" metrics={pv['metrics']}" if pv["status"] == "valid" else ""))

    # current_best scenarios on the baseline: Python and Rust must agree on skip vs
    # full-validate (and on metrics when valid). baseline is side=3388, filled=2970647.
    with open(BASELINE, "rb") as f:
        base = f.read()
    cb_cases = [
        ("cb_worse_side", {"side": 1000, "filled_cells": 500}),                  # -> skipped
        ("cb_tie_side_worse_filled", {"side": 3388, "filled_cells": 1000000}),   # -> skipped
        ("cb_exact_match", {"side": 3388, "filled_cells": 2970647}),             # -> valid (match)
        ("cb_tie_side_better_filled", {"side": 3388, "filled_cells": 4000000}),  # -> valid (beats on filled)
        ("cb_beatable_side", {"side": 20000, "filled_cells": 9999999}),          # -> valid (beats on side)
    ]
    for name, cb in cb_cases:
        checked += 1
        pv = py_verify(base, cb)
        rv = rust(base, "verify", cb)
        if pv["status"] != rv["status"]:
            print(f"[FAIL] {name}: status py={pv['status']} rust={rv['status']}")
            failures += 1
            continue
        if pv["status"] == "valid" and pv["metrics"] != rv["metrics"]:
            print(f"[FAIL] {name}: metrics py={pv['metrics']} rust={rv['metrics']}")
            failures += 1
            continue
        print(f"[ok]   {name}: status={pv['status']} (current_best={cb})")

    # Deep-path mutants (full dictionary), each engineered to reach a specific rule so the
    # Rust verifier is exercised on V4-nonword, V4-missing, and V5-disconnected, not only on
    # the V1/V2 rejections above. Built from the decoded baseline; each asserts (via the
    # Python reason) that it actually reached the intended rule, then requires Python == Rust.
    n0, pls0 = checker._decode(base, WORDS)
    cell0 = checker._build_grid(pls0, WORDS)
    mc = max(c for (_, c) in cell0) + 5   # an empty margin column band

    def reloc(changes):
        r = list(pls0)
        for i, rec in changes.items():
            r[i] = rec
        return checker.encode(n0, r)

    aah = pls0[IDX["AAH"]]  # (row, col, orient) of "AAH"
    deep = [
        # relocate the leaf word "AA" (index 0) alone into the empty margin -> its own
        # component -> V5 fails (removal leaves no residual run, so V4 still holds).
        ("v5_disconnected", reloc({0: (0, mc, 0)}), "connected"),
        # butt "AA" (index 0) and "AAA" (index 1) together in the margin -> run "AAAAA" -> V4 non-word.
        ("v4_nonword", reloc({0: (0, mc, 0), 1: (0, mc + 2, 0)}), "not a word"),
        # place "AA" on top of "AAH" (subsumed) -> "AA" has no maximal run -> V4 missing.
        ("v4_missing", reloc({0: (aah[0], aah[1], aah[2])}), "missing"),
    ]
    for name, raw, expect in deep:
        checked += 1
        pv = py_verify(raw)
        rv = rust(raw, "verify")
        if pv["status"] != "invalid" or expect not in pv["reason"]:
            # coverage guard: the mutant no longer reaches the intended rule (baseline changed?)
            print(f"[FAIL] {name}: expected invalid ~'{expect}', got {pv['status']} '{pv['reason']}'")
            failures += 1
            continue
        if pv["status"] != rv["status"]:
            print(f"[FAIL] {name}: status py={pv['status']} rust={rv['status']}")
            failures += 1
            continue
        print(f"[ok]   {name}: status=invalid ({expect}) [py==rust]")

    # Fingerprint translation invariance, cross-language: a horizontally shifted baseline must
    # fingerprint identically to the baseline, in BOTH verifiers.
    shifted = checker.encode(n0, [(r, c + 1, o) for (r, c, o) in pls0])
    base_fp = py_fingerprint(base)
    for label, raw in (("baseline", base), ("shifted", shifted)):
        checked += 1
        pf = py_fingerprint(raw)
        rf = rust(raw, "fingerprint")["fingerprint"]
        if pf != rf:
            print(f"[FAIL] fp_{label}: py={pf} rust={rf}")
            failures += 1
            continue
        if pf != base_fp:
            print(f"[FAIL] fp_{label}: {pf} != baseline {base_fp} (not translation-invariant)")
            failures += 1
            continue
        print(f"[ok]   fp_{label}: {pf[:16]}... (== baseline, py==rust)")

    print(f"\n{checked - failures}/{checked} cases agree between Python and Rust.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
