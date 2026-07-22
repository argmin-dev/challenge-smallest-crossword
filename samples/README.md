# samples/

Small example artifacts for poking the verifier via the dev path.
`expected.json` maps each file to its expected `verify` status. Regenerate them from
the baseline with `python3 tools/make_samples.py`.

| file | status | why |
|---|---|---|
| `valid.xwd` | valid | the baseline (side 3388) |
| `invalid_wrong_length` | invalid | not exactly `1,404,201` bytes (length gate) |
| `invalid_bad_magic.xwd` | invalid | correct length, wrong 3-byte magic |
| `invalid_anchor_oor.xwd` | invalid | a record's anchor is out of range (V1) |

These illustrate the V1 gates. The exhaustive, per-rule coverage (V2-V5, the
fingerprint, Python/Rust equivalence) is in [`../tests/`](../tests/), which is what
the `[test] command` runs.

Try one:

```bash
echo '{"artifact_path":"samples/invalid_bad_magic.xwd","mode":"verify"}' > in.json
ARGMIN_INPUT=in.json ARGMIN_OUTPUT=out.json python3 verifier/entrypoint.py && cat out.json
```
