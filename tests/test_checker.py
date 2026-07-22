"""
Verifier tests for the Smallest Complete Crossword.

Two layers:
  1. RULE tests: drive checker's core (check_bytes / encode) with a TINY synthetic
     dictionary so each validity rule (V1-V5) can be hit by one small, hand-verified
     grid. This is where the exhaustive input-validation coverage lives.
  2. INTEGRATION tests: run the public verify()/fingerprint() against the pinned Moby
     dictionary and the real reference/baseline.xwd.

The differential test (tests/differential.py, run by run_all.sh) separately checks that the
Rust verifier agrees with this Python reference on every input.

Tiny worlds used below (all letters are painted from the dictionary, never the artifact):

  CAT/CAR world  D = ["CAR", "CAT"]
      C A T          across row0 = CAT ; down col0 = CAR ; crossing at (0,0)=C
      A
      R
"""
import hashlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "verifier"))
import checker  # noqa: E402

BASELINE = os.path.join(os.path.dirname(__file__), "..", "reference", "baseline.xwd")

# ---- CAT/CAR tiny world -----------------------------------------------------------------
CATCAR = sorted(["CAR", "CAT"])          # ["CAR", "CAT"]
CATCAR_IDX = checker.build_index(CATCAR)
CATCAR_L = sum(len(w) for w in CATCAR)   # 6
# records in word order: CAR down @ (0,0); CAT across @ (0,0)
CATCAR_VALID = [(0, 0, 1), (0, 0, 0)]
CATCAR_N = 3


def chk(records, words, n, idx=None, total=None, current_best=None):
    idx = idx if idx is not None else checker.build_index(words)
    total = total if total is not None else sum(len(w) for w in words)
    raw = checker.encode(n, records)
    return checker.check_bytes(raw, words, idx, total, current_best)


class ValidAcceptance(unittest.TestCase):
    def test_tiny_valid(self):
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "valid", r)
        self.assertEqual(r["metrics"], {"side": 3, "filled_cells": 5})
        self.assertEqual(r["info"]["crossings"], 1)          # L(6) - filled(5)
        self.assertEqual(r["info"]["bbox_width"], 3)
        self.assertEqual(r["info"]["bbox_height"], 3)

    def test_baseline_valid_real_dict(self):
        r = checker.verify(BASELINE, {}, None)
        self.assertEqual(r["status"], "valid", r)
        self.assertEqual(r["metrics"], {"side": 3388, "filled_cells": 2970647})


class V1_Format(unittest.TestCase):
    def test_bad_magic(self):
        raw = bytearray(checker.encode(CATCAR_N, CATCAR_VALID))
        ml = len(checker.MAGIC)
        raw[:ml] = b"X" * ml
        r = checker.check_bytes(bytes(raw), CATCAR, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("magic", r["reason"])

    def test_wrong_length_short(self):
        raw = checker.encode(CATCAR_N, CATCAR_VALID)[:-1]
        r = checker.check_bytes(raw, CATCAR, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("bytes", r["reason"])

    def test_wrong_length_trailing(self):
        raw = checker.encode(CATCAR_N, CATCAR_VALID) + b"\x00"
        r = checker.check_bytes(raw, CATCAR, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")

    def test_n_too_small(self):
        r = chk(CATCAR_VALID, CATCAR, 1, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("too small", r["reason"])

    def test_n_too_large(self):
        r = chk(CATCAR_VALID, CATCAR, checker.N_MAX + 1, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("N_MAX", r["reason"])

    def test_anchor_out_of_range(self):
        # hand-build: record 1's p = n*n (>= n^2). Uses the format constants so it tracks
        # any header/record-width change.
        nb = checker.HEADER_LEN - len(checker.MAGIC)  # width of the n field
        rb = checker.RECORD_LEN
        raw = bytearray(checker.MAGIC) + CATCAR_N.to_bytes(nb, "little")
        raw += checker.ORIENT_BIT.to_bytes(rb, "little")       # CAR down @ p=0 (ok)
        raw += (CATCAR_N * CATCAR_N).to_bytes(rb, "little")    # CAT @ p=n^2 (out of range)
        r = checker.check_bytes(bytes(raw), CATCAR, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("out of range", r["reason"])

    def test_word_off_grid(self):
        # CAT across anchored at col 1 in an n=3 grid: 1+3 > 3 -> off grid
        r = chk([(0, 0, 1), (0, 1, 0)], CATCAR, 3, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("off the grid", r["reason"])


class V2_Overlap(unittest.TestCase):
    def test_conflicting_letters(self):
        # CAR down @ (0,1) puts C at (0,1); CAT across @ (0,0) puts A at (0,1) -> conflict
        r = chk([(0, 1, 1), (0, 0, 0)], CATCAR, 3, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("conflicting", r["reason"])


class V3_LoneCell(unittest.TestCase):
    def test_lone_cell(self):
        # V3 is defense-in-depth: with the real dictionary every word has length >= 2, so
        # every filled cell is inside a run and V3 can never fire. To exercise the branch we
        # pass a synthetic dictionary with a length-1 token placed off on its own.
        D = ["AB", "C"]                       # "C" is a length-1 token (synthetic only)
        r = chk([(0, 0, 0), (0, 3, 0)], D, 5)  # AB across at (0,0); C alone at (0,3)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("lone letter", r["reason"])


class V4_Lexicon(unittest.TestCase):
    def test_nonword_run(self):
        # CAT across @ (0,0) and CAR across @ (0,3) in one row -> "CATCAR", not a word
        r = chk([(0, 3, 0), (0, 0, 0)], CATCAR, 6, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("not a word", r["reason"])

    def test_missing_word(self):
        # CART/CAR world: CAR subsumed inside CART -> CAR never a maximal run -> missing
        D = sorted(["CAR", "CART"])                   # ["CAR", "CART"]
        # words order: CAR@(0,0) across, CART@(0,0) across
        r = chk([(0, 0, 0), (0, 0, 0)], D, 4)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("missing", r["reason"])

    def test_duplicate_word(self):
        # AB/ABA/BA world engineered so "BA" appears as both a row and a column run.
        #   row0: A B A   (ABA across @ (0,0))
        #   row1: B A     (AB down @ (0,0) gives col0=AB; BA down @ (0,1) gives col1=BA;
        #                  row1 "BA" is then an incidental duplicate of col1 "BA")
        D = sorted(["AB", "BA", "ABA"])               # ["AB", "ABA", "BA"]
        recs = [(0, 0, 1), (0, 0, 0), (0, 1, 1)]      # AB down, ABA across, BA down
        r = chk(recs, D, 3)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("more than once", r["reason"])


class V5_Connectivity(unittest.TestCase):
    def test_disconnected(self):
        # CAT @ (0,0) and CAR @ (5,5), no crossing -> two components
        r = chk([(5, 5, 0), (0, 0, 0)], CATCAR, 8, CATCAR_IDX, CATCAR_L)
        self.assertEqual(r["status"], "invalid")
        self.assertIn("connected", r["reason"])


class SkipAgainstCurrentBest(unittest.TestCase):
    # The CAT/CAR valid grid scores side=3, filled_cells=5.
    def test_skip_when_worse_side(self):
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L,
                current_best={"side": 2, "filled_cells": 100})
        self.assertEqual(r["status"], "skipped")
        self.assertIsNone(r["metrics"])

    def test_skip_when_tie_side_worse_filled(self):
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L,
                current_best={"side": 3, "filled_cells": 4})
        self.assertEqual(r["status"], "skipped")

    def test_no_skip_on_exact_match(self):
        # a match does not take the record, but we still fully validate it (returns valid).
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L,
                current_best={"side": 3, "filled_cells": 5})
        self.assertEqual(r["status"], "valid")

    def test_no_skip_when_beats_on_filled(self):
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L,
                current_best={"side": 3, "filled_cells": 6})
        self.assertEqual(r["status"], "valid")
        self.assertEqual(r["metrics"], {"side": 3, "filled_cells": 5})

    def test_no_skip_without_current_best(self):
        r = chk(CATCAR_VALID, CATCAR, CATCAR_N, CATCAR_IDX, CATCAR_L, current_best=None)
        self.assertEqual(r["status"], "valid")

    def test_skip_does_not_hide_beating_validity(self):
        # A grid that BEATS the best but is invalid (non-word run) must still be caught.
        r = chk([(0, 3, 0), (0, 0, 0)], CATCAR, 6, CATCAR_IDX, CATCAR_L,
                current_best={"side": 100, "filled_cells": 100})
        self.assertEqual(r["status"], "invalid")
        self.assertIn("not a word", r["reason"])


class Fingerprint(unittest.TestCase):
    def test_deterministic(self):
        raw = checker.encode(CATCAR_N, CATCAR_VALID)
        a = checker.fingerprint_bytes(raw, CATCAR)
        b = checker.fingerprint_bytes(raw, CATCAR)
        self.assertEqual(a, b)
        self.assertNotEqual(a, "")

    def test_translation_invariant(self):
        # same grid, shifted right/down by growing n and offsetting anchors, same fingerprint
        base = checker.fingerprint_bytes(checker.encode(3, [(0, 0, 1), (0, 0, 0)]), CATCAR)
        shifted = checker.fingerprint_bytes(checker.encode(9, [(2, 3, 1), (2, 3, 0)]), CATCAR)
        self.assertEqual(base, shifted)

    def test_malformed_falls_back_to_raw_hash(self):
        raw = b"not a valid artifact at all"
        self.assertEqual(checker.fingerprint_bytes(raw, CATCAR),
                         hashlib.sha256(raw).hexdigest())

    def test_public_fingerprint_never_raises_on_missing_file(self):
        fp = checker.fingerprint("/nonexistent/path/xyz")
        self.assertIsInstance(fp, str)
        self.assertNotEqual(fp, "")


class Determinism(unittest.TestCase):
    def test_same_artifact_same_metrics(self):
        r1 = checker.verify(BASELINE, {}, None)
        r2 = checker.verify(BASELINE, {}, None)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
