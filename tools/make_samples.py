#!/usr/bin/env python3
"""
Regenerate the samples/ directory from reference/baseline.xwd. These small example
artifacts let a solver poke the verifier via the dev path and see each shape of
result; the exhaustive per-rule coverage lives in tests/ (test_checker.py +
differential.py), not here.

Produces (and samples/expected.json records the expected verify status of each):
  valid.xwd               the baseline, unchanged                      -> valid
  invalid_wrong_length    3 bytes                                      -> invalid (length)
  invalid_bad_magic.xwd   baseline with the magic clobbered            -> invalid (magic)
  invalid_anchor_oor.xwd  baseline with record 0's anchor set to n*n   -> invalid (V1 range)

Usage: python3 tools/make_samples.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
BASELINE = os.path.join(ROOT, "reference", "baseline.xwd")
SAMPLES = os.path.join(ROOT, "samples")


def main():
    with open(BASELINE, "rb") as f:
        base = f.read()
    # Format: 3-byte magic "XWD", then u16 n, then u32 records.
    n = int.from_bytes(base[3:5], "little")   # u16 header n
    os.makedirs(SAMPLES, exist_ok=True)

    def write(name, data):
        with open(os.path.join(SAMPLES, name), "wb") as f:
            f.write(data)

    # valid: the baseline as-is.
    write("valid.xwd", base)

    # invalid: wrong length (fails the exact-length gate first).
    write("invalid_wrong_length", b"XWD")

    # invalid: correct length, wrong magic.
    bad_magic = bytearray(base)
    bad_magic[0:3] = b"XXX"
    write("invalid_bad_magic.xwd", bytes(bad_magic))

    # invalid: record 0's anchor set to n*n (out of range [0, n*n)). n*n <= 3388^2 < 2^24,
    # so it fits in the record's 31 anchor bits with orientation 0. Record 0 starts at byte 5.
    oor = bytearray(base)
    oor[5:9] = (n * n).to_bytes(4, "little")
    write("invalid_anchor_oor.xwd", bytes(oor))

    expected = {
        "valid.xwd": "valid",
        "invalid_wrong_length": "invalid",
        "invalid_bad_magic.xwd": "invalid",
        "invalid_anchor_oor.xwd": "invalid",
    }
    with open(os.path.join(SAMPLES, "expected.json"), "w") as f:
        json.dump(expected, f, indent=2)
        f.write("\n")
    print(f"wrote {len(expected)} samples + expected.json to {SAMPLES}")


if __name__ == "__main__":
    main()
