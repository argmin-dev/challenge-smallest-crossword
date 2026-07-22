#!/usr/bin/env python3
"""
Encode a plain-text placements file into the challenge's binary artifact format (XWD),
so it can be submitted and verified.

Placements text format (matches the record order the verifier expects):
  line 1        : the word count (must equal |D| = 351,049)
  next |D| lines: "row col orient" per word, in dictionary order,
                  orient 0 = across (horizontal), 1 = down (vertical),
                  (row, col) = the word's first-letter cell (leftmost for across,
                  topmost for down). Coordinates must be >= 0.

Usage: python3 tools/encode.py <placements.txt> <out.xwd>
"""
import os
import sys

MAGIC = b"XWD"
N_MAX = 3388  # max grid side (the baseline); larger grids cannot be encoded or submitted


def load_dict():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "moby-single.txt")
    words = []
    for line in open(path, "rb").read().decode("ascii").splitlines():
        w = line.strip().upper()
        if len(w) >= 2 and w.isalpha() and w.isascii():
            words.append(w)
    return sorted(set(words))


def main():
    src, out = sys.argv[1], sys.argv[2]
    words = load_dict()
    with open(src) as f:
        n_words = int(f.readline().strip())
        pls = []
        for _ in range(n_words):
            r, c, o = map(int, f.readline().split())
            pls.append((r, c, o))
    if n_words != len(words):
        sys.exit(f"placement count {n_words} != |D| {len(words)}")
    if any(o == -1 for _, _, o in pls):
        sys.exit("placements contain unplaced words (-1); cannot encode a partial grid.")

    # grid side n: every cell (including a word's full extent) must satisfy row < n, col < n.
    max_coord = 0
    for i, (r, c, o) in enumerate(pls):
        L = len(words[i])
        if o == 0:      # across: extends in +col
            max_coord = max(max_coord, r, c + L - 1)
        else:           # down: extends in +row
            max_coord = max(max_coord, r + L - 1, c)
    n = max_coord + 1
    if n > N_MAX:
        sys.exit(f"grid side n={n} exceeds the max {N_MAX}; this grid cannot be submitted "
                 f"(it could not beat the baseline anyway).")

    with open(out, "wb") as f:
        f.write(MAGIC)
        f.write(n.to_bytes(2, "little"))              # n as u16
        for r, c, o in pls:
            p = r + n * c
            v = (o << 31) | p                         # orientation in bit 31
            f.write(v.to_bytes(4, "little"))          # record as u32
    print(f"encoded {n_words} placements, n={n}, {len(MAGIC) + 2 + 4*n_words} bytes -> {out}")


if __name__ == "__main__":
    main()
