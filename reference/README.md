# reference/

`baseline.xwd` is the baseline record to beat. It packs all 351,049 Moby words into
one valid, connected crossword with:

- `side = 3388`  (the primary metric baseline in `manifest.toml`)
- `filled_cells = 2,970,647`  (the tie-breaker baseline)
- `density = 0.2588`, `crossings = 351,048`, `bbox_width = 3154`, `bbox_height = 3388`
- fingerprint `c0d1a1fbe6b216d516f01a064aa85db0c51ace50c269a03351b0d44bb79a3689`

It is a starting point, provided as-is. The `.xwd` binary format is specified in
[`../submit.md`](../submit.md).

Verify it via the dev path:

```bash
echo '{"artifact_path":"reference/baseline.xwd","mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json
```
