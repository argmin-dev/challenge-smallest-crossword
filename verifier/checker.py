"""
checker.py -- the Smallest Complete Crossword verifier (reference implementation).

THIS FILE IS THE SPEC. It is public and canonical: whatever this code accepts is, by
definition, a valid submission. The optimized Rust verifier in verifier/rust/ must agree
with this file on every input's status, its metrics when valid, and its fingerprint (a
differential test enforces exactly that; submitter-facing reason strings and the display-
only density rounding may differ). Read this file to understand exactly how a submission
is judged.

------------------------------------------------------------------------------------------
WHAT A SUBMISSION IS
------------------------------------------------------------------------------------------
A submission places EVERY word of the target list D (the Moby Project single-word list,
filtered to length >= 2, uppercased, de-duplicated, sorted byte-lexicographically --
351,049 words) into one square grid so the whole thing reads as a single connected crossword.

The submitter does NOT send the grid or any letters. They send only, for each word (in
dictionary order), WHERE it goes: an anchor cell and an orientation. The verifier paints
the letters itself, taking them from the trusted dictionary D. This is the single most
important safety property: a submission can never inject an arbitrary letter or an
arbitrary word -- it can only choose positions for the real dictionary words.

------------------------------------------------------------------------------------------
ARTIFACT FORMAT (binary, little-endian)
------------------------------------------------------------------------------------------
  bytes 0..3   : magic, the 3 ASCII bytes "XWD"
  bytes 3..5   : n, a u16 -- the side of the coordinate space (the working grid is n x n)
  then EXACTLY len(D) records, each a u32:
       bit 31        : orientation (0 = across / horizontal, 1 = down / vertical)
       bits 0..=30   : p, the anchor index, where  p = row + n * col
                       (0 <= row < n, 0 <= col < n, so 0 <= p < n*n)
  Record i is word D[i] (index == word; the word itself is never stored).
  The file length MUST be exactly 5 + 4*len(D) bytes. Any other length is invalid.

  n is capped at N_MAX = 3388, the side of the shipped baseline: no submission worth
  making is larger (you must strictly beat the baseline, and the record only shrinks), so
  n > 3388 is rejected outright. That cap lets the anchor p (< n*n <= 3388^2, which needs
  24 bits) share a u32 with the 1-bit orientation, halving the artifact size versus a u64.

Decoding a record: row = p % n, col = p // n. The word's first letter goes at (row, col);
an across word extends to the right (increasing col), a down word extends down (increasing
row). "First letter" means leftmost cell for across, topmost cell for down.

------------------------------------------------------------------------------------------
VALIDITY RULES (all must hold; any failure -> status "invalid")
------------------------------------------------------------------------------------------
  V1  Well-formed & in range: correct magic, exact file length, 2 <= n <= N_MAX, every
      record's p < n*n, and every word fits fully inside the n x n grid.
  V2  Consistent cells: where two words paint the same cell they must agree on the letter.
      (They always agree implicitly because letters come from D, but two DIFFERENT words'
      overlapping cells could disagree; that is the V2 failure.)
  V3  No lone cells: every filled cell belongs to at least one entry (a run of length >= 2).
  V4  Exact lexicon match: the multiset of all maximal entries (across and down, length
      >= 2) equals D exactly -- every word appears exactly once, no run is a non-word, no
      word is duplicated, none is missing. THIS RULE, over the reconstructed grid's maximal
      runs, is the sole authority for coverage. The placement records are only a way to
      build the grid; whether a word "counts" is decided here.
  V5  Connected: all filled cells form a single 4-connected component.

On valid, the metrics are:
  side          = max(bbox_width, bbox_height) of the filled cells   (RANKED, minimize)
  filled_cells  = number of filled cells                             (RANKED, minimize)
and info (display only, never ranked): density = filled/side^2, crossings = L - filled,
bbox_width, bbox_height.
Ranking is done by the platform (side first, then filled_cells; earliest submission wins
ties). This verifier never ranks.
"""

import hashlib
import os

# ---------------------------------------------------------------------------------------
# Constants (mirrored exactly in verifier/rust/src/main.rs)
# ---------------------------------------------------------------------------------------
MAGIC = b"XWD"
N_MAX = 3388              # the shipped baseline side; n > N_MAX is rejected (see the format
                          # note above). Also keeps p < n*n < 2^24, so a record fits in u32.
HEADER_LEN = 5            # 3 magic + 2 n (u16)
RECORD_LEN = 4            # one u32 per word
ORIENT_BIT = 1 << 31
P_MASK = ORIENT_BIT - 1   # bits 0..=30

# The exact Moby snapshot this verifier is pinned to. If data/moby-single.txt does not hash
# to this, the verifier refuses to run (a wrong word list would silently change the spec).
DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "moby-single.txt")
DICT_SHA256 = "2056d03ea1189904b98a13843dd258277f394470229c1e212460eac5074066c5"

_DICT = None  # lazily loaded: (words:list[str], index:dict[str,int], total_letters:int)


class Invalid(Exception):
    """Raised with a submitter-facing reason; verify() turns it into status 'invalid'."""


def _load_dictionary():
    """Load, verify, and canonicalize the target word list. Cached after first call.

    Canonical form (this defines D and the record ordering): read the file, uppercase each
    line, keep only tokens matching ^[A-Z]{2,}$, de-duplicate, sort byte-lexicographically.
    The file's SHA-256 must match the pinned constant.
    """
    global _DICT
    if _DICT is not None:
        return _DICT
    with open(DICT_PATH, "rb") as f:
        raw = f.read()
    got = hashlib.sha256(raw).hexdigest()
    if got != DICT_SHA256:
        raise RuntimeError(
            f"dictionary file hash mismatch: expected {DICT_SHA256}, got {got}. "
            "The verifier will not run against an unpinned word list."
        )
    words = []
    for line in raw.decode("ascii").splitlines():
        w = line.strip().upper()
        if len(w) >= 2 and w.isalpha() and w.isascii():
            words.append(w)
    words = sorted(set(words))
    index = {w: i for i, w in enumerate(words)}
    total_letters = sum(len(w) for w in words)
    _DICT = (words, index, total_letters)
    return _DICT


# ---------------------------------------------------------------------------------------
# Decode: bytes -> (n, placements). placements[i] = (row, col, orient) for word D[i].
# ---------------------------------------------------------------------------------------
def _decode(raw: bytes, words):
    n_words = len(words)
    expected_len = HEADER_LEN + RECORD_LEN * n_words
    if len(raw) != expected_len:
        raise Invalid(
            f"artifact is {len(raw)} bytes; expected exactly {expected_len} "
            f"({HEADER_LEN} header + {RECORD_LEN} x {n_words} records)."
        )
    ml = len(MAGIC)
    if raw[:ml] != MAGIC:
        raise Invalid(f"bad magic: expected {MAGIC!r}, got {raw[:ml]!r}.")
    n = int.from_bytes(raw[ml:HEADER_LEN], "little")
    if n < 2:
        raise Invalid(f"n = {n} is too small (must be >= 2).")
    if n > N_MAX:
        raise Invalid(f"n = {n} exceeds N_MAX = {N_MAX}.")
    n2 = n * n
    placements = []
    off = HEADER_LEN
    for i in range(n_words):
        v = int.from_bytes(raw[off:off + RECORD_LEN], "little")
        off += RECORD_LEN
        orient = 1 if (v & ORIENT_BIT) else 0
        p = v & P_MASK
        if p >= n2:
            raise Invalid(f"record {i} ({words[i]}): anchor {p} out of range [0, {n2}).")
        row = p % n
        col = p // n
        L = len(words[i])
        if orient == 0:  # across -> extends in +col
            if col + L > n:
                raise Invalid(f"record {i} ({words[i]}): across word runs off the grid.")
        else:            # down -> extends in +row
            if row + L > n:
                raise Invalid(f"record {i} ({words[i]}): down word runs off the grid.")
        placements.append((row, col, orient))
    return n, placements


# ---------------------------------------------------------------------------------------
# Build: paint every word's letters into a cell map, checking V2 (consistent overlaps).
# ---------------------------------------------------------------------------------------
def _build_grid(placements, words):
    cell = {}  # (row, col) -> letter
    for i, (row, col, orient) in enumerate(placements):
        w = words[i]
        for j, ch in enumerate(w):
            pos = (row, col + j) if orient == 0 else (row + j, col)
            prev = cell.get(pos)
            if prev is None:
                cell[pos] = ch
            elif prev != ch:
                raise Invalid(
                    f"cell {pos} has conflicting letters '{prev}' and '{ch}' "
                    f"(from word {words[i]})."
                )
            # prev == ch: a legitimate crossing; nothing to do.
    return cell


# ---------------------------------------------------------------------------------------
# Maximal runs. Returns (runs, covered) where runs is a list of entry strings (length >= 2)
# and covered is the set of cells that belong to at least one such run (for V3).
# ---------------------------------------------------------------------------------------
def _maximal_runs(cell):
    runs = []
    covered = set()

    # ACROSS: group by row, walk columns left-to-right.
    by_row = {}
    for (r, c) in cell:
        by_row.setdefault(r, []).append(c)
    for r, cols in by_row.items():
        cols.sort()
        i = 0
        while i < len(cols):
            j = i
            while j + 1 < len(cols) and cols[j + 1] == cols[j] + 1:
                j += 1
            if j - i + 1 >= 2:  # maximal run of length >= 2
                s = "".join(cell[(r, cols[k])] for k in range(i, j + 1))
                runs.append(s)
                for k in range(i, j + 1):
                    covered.add((r, cols[k]))
            i = j + 1

    # DOWN: group by column, walk rows top-to-bottom.
    by_col = {}
    for (r, c) in cell:
        by_col.setdefault(c, []).append(r)
    for c, rows in by_col.items():
        rows.sort()
        i = 0
        while i < len(rows):
            j = i
            while j + 1 < len(rows) and rows[j + 1] == rows[j] + 1:
                j += 1
            if j - i + 1 >= 2:
                s = "".join(cell[(rows[k], c)] for k in range(i, j + 1))
                runs.append(s)
                for k in range(i, j + 1):
                    covered.add((rows[k], c))
            i = j + 1

    return runs, covered


def _connected_one_component(cell):
    """V5: are all filled cells one 4-connected component? Iterative flood fill."""
    if not cell:
        return True
    start = next(iter(cell))
    seen = {start}
    stack = [start]
    while stack:
        r, c = stack.pop()
        for nb in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if nb in cell and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(cell)


# ---------------------------------------------------------------------------------------
# Testable core. These take the word list explicitly so tests can drive the exact same
# logic with a small synthetic dictionary and craft one scenario per validity rule.
# ---------------------------------------------------------------------------------------
def build_index(words):
    return {w: i for i, w in enumerate(words)}


def encode(n: int, records) -> bytes:
    """Build an artifact from records = [(row, col, orient), ...] in word order.
    Inverse of _decode. Used by the baseline encoder and the tests."""
    out = bytearray(MAGIC)
    out += int(n).to_bytes(HEADER_LEN - len(MAGIC), "little")   # n as u16
    for (row, col, orient) in records:
        p = row + n * col
        v = (ORIENT_BIT if orient else 0) | p
        out += v.to_bytes(RECORD_LEN, "little")        # record as u32
    return bytes(out)


def _cannot_beat_or_match(side, filled, current_best) -> bool:
    """True if a valid grid with these metrics is strictly worse than current_best on the
    lexicographic (side, then filled_cells) order, so it could never take the record and the
    expensive V3-V5 checks can be skipped. current_best is the harness-supplied {label: value}
    of the record to beat (the leaderboard best, or the baseline when the board is empty), or
    None. With no current_best we never skip (we cannot know what to beat)."""
    if not current_best:
        return False
    best_side = current_best.get("side")
    best_filled = current_best.get("filled_cells")
    if best_side is None or best_filled is None:
        return False
    if side > best_side:
        return True
    if side == best_side and filled > best_filled:
        return True
    return False


def check_bytes(raw: bytes, words, index, total_letters, current_best=None) -> dict:
    """The full verify pipeline on raw bytes, given an explicit dictionary. Returns the
    verify() result dict. This is exactly what verify() runs with the pinned dictionary.

    current_best (optional) is the record to beat. The score (side, filled_cells) is fixed by
    V1 + V2 alone, so once it is known we compare it to current_best: a grid that cannot beat
    or match the best can never take the record, so we return "skipped" WITHOUT running the
    lexicon (V4) and connectivity (V5) checks. This is only a cost optimization; the "valid"
    path is unchanged and always runs the complete check."""
    try:
        n, placements = _decode(raw, words)            # V1
        cell = _build_grid(placements, words)          # V2

        # Metrics come from the painted grid (V1 + V2); they do not depend on V3-V5.
        rows = [r for (r, _) in cell]
        cols = [c for (_, c) in cell]
        bbox_w = max(cols) - min(cols) + 1
        bbox_h = max(rows) - min(rows) + 1
        side = max(bbox_w, bbox_h)
        filled = len(cell)

        # Early exit: can this grid even take the record? If not, don't fully validate it.
        if _cannot_beat_or_match(side, filled, current_best):
            return {"status": "skipped", "metrics": None,
                    "reason": f"cannot beat the current best (side={side}, "
                              f"filled_cells={filled}).", "info": None}

        runs, covered = _maximal_runs(cell)

        # V3: no lone cells. Defense-in-depth: every real word has length >= 2 and paints a
        # contiguous run, so with the pinned dictionary this can never fire; it guards against
        # any future change that could admit a stray cell.
        if len(covered) != len(cell):
            lone = next(iter(set(cell) - covered))
            raise Invalid(f"cell {lone} is a lone letter (not part of any entry).")

        # V4: the multiset of maximal runs must equal D exactly.
        coverage = [0] * len(words)
        for s in runs:
            idx = index.get(s)
            if idx is None:
                raise Invalid(f'"{s}" is a run but not a word in the list.')
            coverage[idx] += 1
            if coverage[idx] == 2:
                raise Invalid(f'"{s}" appears more than once (each word must appear once).')
        missing = [words[i] for i, cnt in enumerate(coverage) if cnt == 0]
        if missing:
            sample = ", ".join(missing[:5])
            raise Invalid(f"{len(missing)} word(s) missing, e.g. {sample}.")

        # V5: connected.
        if not _connected_one_component(cell):
            raise Invalid("the filled cells are not a single connected component.")

        return {
            "status": "valid",
            "metrics": {"side": side, "filled_cells": filled},
            "reason": "",
            "info": {
                "density": round(filled / (side * side), 6),
                "crossings": total_letters - filled,
                "bbox_width": bbox_w,
                "bbox_height": bbox_h,
            },
        }
    except Invalid as e:
        return {"status": "invalid", "metrics": None, "reason": str(e), "info": None}


def fingerprint_bytes(raw: bytes, words) -> str:
    try:
        n, placements = _decode(raw, words)
        cell = _build_grid(placements, words)
        if not cell:
            return hashlib.sha256(raw).hexdigest()
        minr = min(r for (r, _) in cell)
        minc = min(c for (_, c) in cell)
        h = hashlib.sha256()
        for (r, c) in sorted(cell):  # sorted by (row, col); deterministic
            h.update((r - minr).to_bytes(4, "little"))
            h.update((c - minc).to_bytes(4, "little"))
            h.update(cell[(r, c)].encode("ascii"))
        return h.hexdigest()
    except Exception:
        return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------------------
# Public entry points (called by entrypoint.py). These bind the pinned dictionary.
# ---------------------------------------------------------------------------------------
def verify(artifact_path: str, params: dict, current_best) -> dict:
    words, index, total_letters = _load_dictionary()
    try:
        with open(artifact_path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return {"status": "invalid", "metrics": None,
                "reason": f"cannot read artifact: {e}", "info": None}
    return check_bytes(raw, words, index, total_letters, current_best)


def fingerprint(artifact_path: str) -> str:
    """Canonical dedup key. Translation-invariant: two submissions whose filled grids are
    identical up to a shift collide. Never raises -- on any malformed input it falls back
    to hashing the raw bytes so the API can still dedup."""
    words, _, _ = _load_dictionary()
    try:
        with open(artifact_path, "rb") as f:
            raw = f.read()
    except OSError:
        return hashlib.sha256(b"").hexdigest()
    return fingerprint_bytes(raw, words)
