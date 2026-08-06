The submission is a fixed-size little-endian binary file:

```
bytes 0..3    magic: the 3 ASCII bytes "XWD"
bytes 3..5    n: u16, the side of the coordinate space (the grid is n x n)
then exactly |D| = 351,049 records, each a u32:
    bit 31        orientation: 0 = across (horizontal), 1 = down (vertical)
    bits 0..=30   p: the anchor index, with p = row + n * col
```

The file is exactly `5 + 4 * 351049 = 1,404,201` bytes; any other length is
`invalid`.

Records are in the canonical dictionary order defined in
[Constraints](constraints.md), so record `i` is word `D[i]` and the word itself is
never stored. Decoding a record: `row = p % n`, `col = p // n`. The word's first letter
(leftmost for across, topmost for down) goes at `(row, col)`. An across word extends
right (increasing column); a down word extends down (increasing row).
