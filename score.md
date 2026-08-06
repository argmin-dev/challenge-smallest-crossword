Two metrics, ranked lexicographically. The first decides; the second only breaks an
exact tie on the first.

1. `side` (minimize): `max(bbox_width, bbox_height)`, the side of the smallest square
   enclosing all filled cells, so blank borders never help or hurt.
2. `filled_cells` (minimize): the count of cells that hold a letter. Fewer at a given
   side means more letters shared between crossing words.

A new record must be strictly better on the first metric where it differs from the
current best. A submission that ties on both metrics does not displace the incumbent,
so exact ties resolve to the earliest submission. There is no minimum-improvement
margin. Ranking is done by the platform, not the verifier.

Both metrics are exact integers read off the reconstructed grid, so scoring is
deterministic: the same artifact always yields the same metrics.

Also reported next to each entry, for context only and never ranked: `density`
(`filled_cells / side^2`), `crossings` (the number of shared cells, `total_letters -
filled_cells`, where `total_letters` is 3,321,695), `bbox_width`, and `bbox_height`.
