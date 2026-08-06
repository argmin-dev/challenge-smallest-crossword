// Fast production verifier for the Smallest Complete Crossword challenge.
//
// This is the PERFORMANCE twin of verifier/checker.py. checker.py is the readable spec;
// this file must agree with it on every input's status, its metrics when valid, and its
// fingerprint (enforced by the differential test in tests/; reason strings and the display-
// only density rounding may differ). It implements the identical artifact format and rules V1-V5,
// reads $ARGMIN_INPUT / writes $ARGMIN_OUTPUT, and supports mode "verify" and "fingerprint".
//
// Design: sparse (never materializes an n x n grid); works only in the filled cells, so
// cost is ~O(F log F) in the number of filled cells F, independent of n.

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::HashMap;

// --- constants (identical to checker.py) ---
const MAGIC: &[u8; 3] = b"XWD";
const N_MAX: i64 = 3388;  // the shipped baseline side; n > N_MAX is rejected. Also keeps
                          // p < n*n < 2^24, so a record fits in u32.
const HEADER_LEN: usize = 5; // 3 magic + 2 n (u16)
const RECORD_LEN: usize = 4; // one u32 per word
const ORIENT_BIT: u32 = 1 << 31;
const P_MASK: u32 = ORIENT_BIT - 1;
const DICT_SRC: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../data/moby-single.txt"));

#[derive(Deserialize)]
struct Input {
    artifact_path: String,
    #[serde(default)]
    mode: Option<String>,
    #[serde(default)]
    current_best: Option<HashMap<String, f64>>,
}

// Canonicalize the dictionary exactly like checker.py: uppercase, keep ^[A-Z]{2,}$,
// dedup, sort byte-lexicographically.
fn load_dict() -> (Vec<String>, HashMap<String, u32>, u64) {
    let mut v: Vec<String> = DICT_SRC
        .lines()
        .map(|l| l.trim().to_ascii_uppercase())
        .filter(|w| w.len() >= 2 && w.bytes().all(|b| b.is_ascii_uppercase()))
        .collect();
    v.sort();
    v.dedup();
    let mut idx = HashMap::with_capacity(v.len() * 2);
    for (i, w) in v.iter().enumerate() {
        idx.insert(w.clone(), i as u32);
    }
    let total: u64 = v.iter().map(|w| w.len() as u64).sum();
    (v, idx, total)
}

// (row, col, orient): orient 0 = across, 1 = down.
fn decode(raw: &[u8], words: &[String]) -> Result<(i64, Vec<(i64, i64, u8)>), String> {
    let n_words = words.len();
    let expected = HEADER_LEN + RECORD_LEN * n_words;
    if raw.len() != expected {
        return Err(format!(
            "artifact is {} bytes; expected exactly {} ({} header + {} x {} records).",
            raw.len(), expected, HEADER_LEN, RECORD_LEN, n_words
        ));
    }
    let ml = MAGIC.len();
    if &raw[0..ml] != MAGIC {
        return Err(format!("bad magic: expected {:?}, got {:?}.", MAGIC, &raw[0..ml]));
    }
    let n = u16::from_le_bytes([raw[ml], raw[ml + 1]]) as i64;
    if n < 2 {
        return Err(format!("n = {} is too small (must be >= 2).", n));
    }
    if n > N_MAX {
        return Err(format!("n = {} exceeds N_MAX = {}.", n, N_MAX));
    }
    let n2 = n * n;
    let mut placements = Vec::with_capacity(n_words);
    let mut off = HEADER_LEN;
    for i in 0..n_words {
        let mut b = [0u8; RECORD_LEN];
        b.copy_from_slice(&raw[off..off + RECORD_LEN]);
        off += RECORD_LEN;
        let v = u32::from_le_bytes(b);
        let orient: u8 = if v & ORIENT_BIT != 0 { 1 } else { 0 };
        let p = (v & P_MASK) as i64;
        if p >= n2 {
            return Err(format!("record {} ({}): anchor {} out of range [0, {}).", i, words[i], p, n2));
        }
        let row = p % n;
        let col = p / n;
        let l = words[i].len() as i64;
        if orient == 0 {
            if col + l > n {
                return Err(format!("record {} ({}): across word runs off the grid.", i, words[i]));
            }
        } else if row + l > n {
            return Err(format!("record {} ({}): down word runs off the grid.", i, words[i]));
        }
        placements.push((row, col, orient));
    }
    Ok((n, placements))
}

// Paint letters into a cell map; V2 = consistent overlaps.
fn build_grid(placements: &[(i64, i64, u8)], words: &[String]) -> Result<HashMap<(i64, i64), u8>, String> {
    let mut cell: HashMap<(i64, i64), u8> = HashMap::new();
    for (i, &(row, col, orient)) in placements.iter().enumerate() {
        let wb = words[i].as_bytes();
        for (j, &ch) in wb.iter().enumerate() {
            let jc = j as i64;
            let pos = if orient == 0 { (row, col + jc) } else { (row + jc, col) };
            match cell.get(&pos) {
                None => {
                    cell.insert(pos, ch);
                }
                Some(&prev) => {
                    if prev != ch {
                        return Err(format!(
                            "cell {:?} has conflicting letters '{}' and '{}' (from word {}).",
                            pos, prev as char, ch as char, words[i]
                        ));
                    }
                }
            }
        }
    }
    Ok(cell)
}

enum Outcome {
    Valid { side: i64, filled: u64, density: f64, crossings: u64, bw: i64, bh: i64 },
    Invalid(String),
    Skipped(String),
}

// True if a valid grid with these metrics is strictly worse than best on the lexicographic
// (side, then filled_cells) order, so it can never take the record and V3-V5 can be skipped.
fn cannot_beat_or_match(side: i64, filled: u64, best: &HashMap<String, f64>) -> bool {
    let (bs, bf) = match (best.get("side"), best.get("filled_cells")) {
        (Some(&s), Some(&f)) => (s, f),
        _ => return false,
    };
    let (side, filled) = (side as f64, filled as f64);
    if side > bs {
        return true;
    }
    if side == bs && filled > bf {
        return true;
    }
    false
}

fn verify(
    raw: &[u8],
    words: &[String],
    idx: &HashMap<String, u32>,
    total_letters: u64,
    current_best: Option<&HashMap<String, f64>>,
) -> Outcome {
    let (_n, placements) = match decode(raw, words) {
        Ok(x) => x,
        Err(m) => return Outcome::Invalid(m),
    };
    let cell = match build_grid(&placements, words) {
        Ok(c) => c,
        Err(m) => return Outcome::Invalid(m),
    };

    // Collect cells into a sortable vec.
    let mut cells: Vec<((i64, i64), u8)> = cell.iter().map(|(&k, &v)| (k, v)).collect();
    let filled = cells.len() as u64;

    // Metrics (from V1 + V2; independent of V3-V5). min/max is order-independent, so it is
    // safe to compute before the sorts below.
    let (mut minr, mut minc, mut maxr, mut maxc) = (i64::MAX, i64::MAX, i64::MIN, i64::MIN);
    for &((r, c), _) in cells.iter() {
        minr = minr.min(r);
        maxr = maxr.max(r);
        minc = minc.min(c);
        maxc = maxc.max(c);
    }
    let bw = maxc - minc + 1;
    let bh = maxr - minr + 1;
    let side = bw.max(bh);

    // Early exit: a grid that cannot beat or match the current best can never take the
    // record, so skip the expensive lexicon (V4) and connectivity (V5) checks.
    if let Some(best) = current_best {
        if cannot_beat_or_match(side, filled, best) {
            return Outcome::Skipped(format!(
                "cannot beat the current best (side={}, filled_cells={}).", side, filled
            ));
        }
    }

    let mut coverage = vec![0u32; words.len()];
    let mut covered = 0u64; // count of cells in >= 1 maximal run of length >= 2

    // A cell may be covered by an across run and/or a down run; count each cell once.
    // We mark coverage by inserting into a set of covered cells.
    let mut covered_set: HashMap<(i64, i64), ()> = HashMap::new();

    // Helper to tally a run string.
    macro_rules! tally {
        ($s:expr) => {{
            match idx.get(&$s) {
                None => return Outcome::Invalid(format!("\"{}\" is a run but not a word in the list.", $s)),
                Some(&id) => {
                    coverage[id as usize] += 1;
                    if coverage[id as usize] == 2 {
                        return Outcome::Invalid(format!(
                            "\"{}\" appears more than once (each word must appear once).", $s
                        ));
                    }
                }
            }
        }};
    }

    // ACROSS: sort by (row, col), scan consecutive columns in a row.
    cells.sort_unstable_by_key(|&((r, c), _)| (r, c));
    {
        let mut i = 0;
        while i < cells.len() {
            let (r, c0) = cells[i].0;
            let mut j = i + 1;
            let mut prev_c = c0;
            while j < cells.len() {
                let (r2, c2) = cells[j].0;
                if r2 == r && c2 == prev_c + 1 {
                    prev_c = c2;
                    j += 1;
                } else {
                    break;
                }
            }
            if j - i >= 2 {
                let s: String = cells[i..j].iter().map(|&(_, ch)| ch as char).collect();
                tally!(s);
                for k in i..j {
                    if covered_set.insert(cells[k].0, ()).is_none() {
                        covered += 1;
                    }
                }
            }
            i = j;
        }
    }

    // DOWN: sort by (col, row), scan consecutive rows in a column.
    cells.sort_unstable_by_key(|&((r, c), _)| (c, r));
    {
        let mut i = 0;
        while i < cells.len() {
            let (r0, c) = cells[i].0;
            let mut j = i + 1;
            let mut prev_r = r0;
            while j < cells.len() {
                let (r2, c2) = cells[j].0;
                if c2 == c && r2 == prev_r + 1 {
                    prev_r = r2;
                    j += 1;
                } else {
                    break;
                }
            }
            if j - i >= 2 {
                let s: String = cells[i..j].iter().map(|&(_, ch)| ch as char).collect();
                tally!(s);
                for k in i..j {
                    if covered_set.insert(cells[k].0, ()).is_none() {
                        covered += 1;
                    }
                }
            }
            i = j;
        }
    }

    // V3: no lone cells. Defense-in-depth: every real word has length >= 2 and paints a
    // contiguous run, so with the pinned dictionary this can never fire.
    if covered != filled {
        return Outcome::Invalid("a cell is a lone letter (not part of any entry).".to_string());
    }

    // V4: every word exactly once (no missing).
    let mut missing: Vec<&str> = Vec::new();
    for (i, &cnt) in coverage.iter().enumerate() {
        if cnt == 0 {
            missing.push(&words[i]);
            if missing.len() > 5 {
                break;
            }
        }
    }
    if !missing.is_empty() {
        let total_missing = coverage.iter().filter(|&&c| c == 0).count();
        return Outcome::Invalid(format!(
            "{} word(s) missing, e.g. {}.",
            total_missing,
            missing.iter().take(5).cloned().collect::<Vec<_>>().join(", ")
        ));
    }

    // V5: single 4-connected component (union-find over cells).
    let mut id_of: HashMap<(i64, i64), usize> = HashMap::with_capacity(cells.len());
    for (i, &(pos, _)) in cells.iter().enumerate() {
        id_of.insert(pos, i);
    }
    let mut parent: Vec<usize> = (0..cells.len()).collect();
    fn find(p: &mut Vec<usize>, mut x: usize) -> usize {
        while p[x] != x {
            p[x] = p[p[x]];
            x = p[x];
        }
        x
    }
    for (i, &((r, c), _)) in cells.iter().enumerate() {
        for nb in [(r + 1, c), (r, c + 1)] {
            if let Some(&j) = id_of.get(&nb) {
                let (a, b) = (find(&mut parent, i), find(&mut parent, j));
                if a != b {
                    parent[a] = b;
                }
            }
        }
    }
    let mut roots = 0usize;
    for i in 0..cells.len() {
        if find(&mut parent, i) == i {
            roots += 1;
        }
    }
    if roots != 1 {
        return Outcome::Invalid("the filled cells are not a single connected component.".to_string());
    }

    // Metrics were computed above (bw, bh, side).
    let density = round6(filled as f64 / (side as f64 * side as f64));
    Outcome::Valid { side, filled, density, crossings: total_letters - filled, bw, bh }
}

fn round6(x: f64) -> f64 {
    (x * 1_000_000.0).round() / 1_000_000.0
}

/// The eight symmetries of the square (the dihedral group D4). Must stay
/// byte-identical in order and effect to `_D4` in verifier/checker.py.
const D4: [fn(i64, i64) -> (i64, i64); 8] = [
    |r, c| (r, c),
    |r, c| (r, -c),
    |r, c| (-r, c),
    |r, c| (-r, -c),
    |r, c| (c, r),
    |r, c| (c, -r),
    |r, c| (-c, r),
    |r, c| (-c, -r),
];

/// Canonical bytes for ONE image: translate to the origin, sort by (row, column),
/// then 9 bytes per cell (row u32 LE, column u32 LE, one ASCII letter).
///
/// Returns None if a normalized coordinate will not fit in a u32. It cannot with
/// N_MAX as it stands, but `as u32` would wrap silently and collide two distinct
/// grids onto one fingerprint, so the check is explicit rather than assumed.
fn serialize_image(cells: &[((i64, i64), u8)]) -> Option<Vec<u8>> {
    let minr = cells.iter().map(|&((r, _), _)| r).min()?;
    let minc = cells.iter().map(|&((_, c), _)| c).min()?;
    let mut sorted: Vec<((i64, i64), u8)> = cells.to_vec();
    sorted.sort_unstable_by_key(|&((r, c), _)| (r, c));
    let mut out = Vec::with_capacity(sorted.len() * 9);
    for ((r, c), ch) in sorted {
        let nr = r - minr;
        let nc = c - minc;
        if nr < 0 || nc < 0 || nr > u32::MAX as i64 || nc > u32::MAX as i64 {
            return None;
        }
        out.extend_from_slice(&(nr as u32).to_le_bytes());
        out.extend_from_slice(&(nc as u32).to_le_bytes());
        out.push(ch);
    }
    Some(out)
}

/// Canonical dedup key: SHA-256 of the smallest of the eight D4 serializations.
///
/// Dedup is up to the full symmetry of the square, not just translation: a
/// crossword rotated or mirrored is the same solution and scores identically, so
/// it must collide. Pick the lexicographically smallest serialized BYTE STRING
/// first, then hash that once; taking the smallest of eight hashes would be
/// deterministic but not canonical, and would cost eight hashes.
///
/// Mirrors fingerprint_bytes() in verifier/checker.py byte for byte; the
/// differential test enforces it.
fn fingerprint(raw: &[u8], words: &[String]) -> String {
    let fallback = || hex(&Sha256::digest(raw));
    let (_n, placements) = match decode(raw, words) {
        Ok(x) => x,
        Err(_) => return fallback(),
    };
    let cell = match build_grid(&placements, words) {
        Ok(c) => c,
        Err(_) => return fallback(),
    };
    if cell.is_empty() {
        return fallback();
    }
    let base: Vec<((i64, i64), u8)> = cell.iter().map(|(&k, &v)| (k, v)).collect();
    let mut best: Option<Vec<u8>> = None;
    for t in D4.iter() {
        let image: Vec<((i64, i64), u8)> =
            base.iter().map(|&((r, c), ch)| (t(r, c), ch)).collect();
        let s = match serialize_image(&image) {
            Some(s) => s,
            None => return fallback(),
        };
        if best.as_ref().map_or(true, |b| s < *b) {
            best = Some(s);
        }
    }
    match best {
        Some(b) => hex(&Sha256::digest(&b)),
        None => fallback(),
    }
}

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{:02x}", b));
    }
    s
}

fn main() {
    let in_path = std::env::var("ARGMIN_INPUT").expect("ARGMIN_INPUT not set");
    let out_path = std::env::var("ARGMIN_OUTPUT").expect("ARGMIN_OUTPUT not set");
    let input_raw = std::fs::read_to_string(&in_path).expect("read ARGMIN_INPUT");
    let input: Input = serde_json::from_str(&input_raw).expect("parse ARGMIN_INPUT json");
    let mode = input.mode.as_deref().unwrap_or("verify");

    let (words, idx, total_letters) = load_dict();
    let artifact = std::fs::read(&input.artifact_path);

    let out: serde_json::Value = match mode {
        "fingerprint" => {
            let fp = match artifact {
                Ok(raw) => fingerprint(&raw, &words),
                Err(_) => hex(&Sha256::digest(b"")),
            };
            serde_json::json!({ "fingerprint": fp })
        }
        "verify" => {
            let raw = match artifact {
                Ok(r) => r,
                Err(e) => {
                    write_out(&out_path, &serde_json::json!({
                        "status": "invalid", "metrics": serde_json::Value::Null,
                        "reason": format!("cannot read artifact: {e}"),
                        "info": serde_json::Value::Null
                    }));
                    return;
                }
            };
            match verify(&raw, &words, &idx, total_letters, input.current_best.as_ref()) {
                Outcome::Valid { side, filled, density, crossings, bw, bh } => serde_json::json!({
                    "status": "valid",
                    "metrics": { "side": side, "filled_cells": filled },
                    "reason": "",
                    "info": { "density": density, "crossings": crossings,
                              "bbox_width": bw, "bbox_height": bh }
                }),
                Outcome::Invalid(msg) => serde_json::json!({
                    "status": "invalid", "metrics": serde_json::Value::Null,
                    "reason": msg, "info": serde_json::Value::Null
                }),
                Outcome::Skipped(msg) => serde_json::json!({
                    "status": "skipped", "metrics": serde_json::Value::Null,
                    "reason": msg, "info": serde_json::Value::Null
                }),
            }
        }
        other => serde_json::json!({
            "status": "invalid", "metrics": serde_json::Value::Null,
            "reason": format!("unknown mode: {other}"), "info": serde_json::Value::Null
        }),
    };
    write_out(&out_path, &out);
}

fn write_out(path: &str, v: &serde_json::Value) {
    let mut f = std::fs::File::create(path).expect("create ARGMIN_OUTPUT");
    use std::io::Write;
    f.write_all(v.to_string().as_bytes()).expect("write ARGMIN_OUTPUT");
}

#[cfg(test)]
mod tests {
    use super::*;
    const BASELINE: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../reference/baseline.xwd");

    #[test]
    fn dict_size_and_letters() {
        let (w, _, t) = load_dict();
        assert_eq!(w.len(), 351049);
        assert_eq!(t, 3_321_695);
    }

    #[test]
    fn baseline_is_valid_with_expected_metrics() {
        let (w, i, t) = load_dict();
        let raw = std::fs::read(BASELINE).unwrap();
        match verify(&raw, &w, &i, t, None) {
            Outcome::Valid { side, filled, .. } => {
                assert_eq!(side, 3388);
                assert_eq!(filled, 2_970_647);
            }
            Outcome::Invalid(m) => panic!("baseline should be valid, got: {m}"),
            Outcome::Skipped(m) => panic!("baseline should be valid, got skipped: {m}"),
        }
    }

    #[test]
    fn bad_magic_rejected() {
        let (w, i, t) = load_dict();
        let mut raw = std::fs::read(BASELINE).unwrap();
        raw[0] = b'Z';
        assert!(matches!(verify(&raw, &w, &i, t, None), Outcome::Invalid(_)));
    }

    #[test]
    fn wrong_length_rejected() {
        let (w, i, t) = load_dict();
        let raw = vec![b'X', b'W', b'D', 3, 0]; // header only (XWD + n=3), no records
        assert!(matches!(verify(&raw, &w, &i, t, None), Outcome::Invalid(_)));
    }

    #[test]
    fn skips_when_cannot_beat_current_best() {
        // baseline is side=3388, filled=2970647. A current_best that it cannot beat or
        // match (smaller side) -> Skipped, without running the full check.
        let (w, i, t) = load_dict();
        let raw = std::fs::read(BASELINE).unwrap();
        let best: HashMap<String, f64> =
            [("side".to_string(), 1000.0), ("filled_cells".to_string(), 500.0)].into();
        assert!(matches!(verify(&raw, &w, &i, t, Some(&best)), Outcome::Skipped(_)));
    }

    #[test]
    fn validates_when_can_beat_current_best() {
        // A current_best worse than the baseline -> baseline beats it -> full check -> Valid.
        let (w, i, t) = load_dict();
        let raw = std::fs::read(BASELINE).unwrap();
        let best: HashMap<String, f64> =
            [("side".to_string(), 20000.0), ("filled_cells".to_string(), 9_999_999.0)].into();
        assert!(matches!(verify(&raw, &w, &i, t, Some(&best)), Outcome::Valid { .. }));
    }

    #[test]
    fn lone_cell_rejected() {
        // V3 defense-in-depth: with a synthetic dictionary containing a length-1 token placed
        // on its own, the verifier reports a lone cell. The real dictionary has no length-1
        // words, so this branch is otherwise unreachable (the differential cannot hit it).
        let words = vec!["AB".to_string(), "C".to_string()];
        let mut idx = HashMap::new();
        idx.insert("AB".to_string(), 0u32);
        idx.insert("C".to_string(), 1u32);
        let n: u16 = 5;
        let mut raw = Vec::new();
        raw.extend_from_slice(MAGIC);
        raw.extend_from_slice(&n.to_le_bytes());
        raw.extend_from_slice(&0u32.to_le_bytes()); // AB at (0,0) across: p = 0
        raw.extend_from_slice(&15u32.to_le_bytes()); // C at (0,3) across: p = 0 + 5*3 = 15
        match verify(&raw, &words, &idx, 3, None) {
            Outcome::Invalid(m) => assert!(m.contains("lone letter"), "got: {m}"),
            Outcome::Valid { .. } => panic!("expected invalid (lone cell), got valid"),
            Outcome::Skipped(_) => panic!("expected invalid (lone cell), got skipped"),
        }
    }

    #[test]
    fn baseline_fingerprint_is_stable() {
        // Must match the Python reference fingerprint for the same bytes. This value
        // changed when dedup moved from translation-only to the full dihedral group;
        // any future change to it is a change to the dedup scheme, not a refactor.
        let (w, _, _) = load_dict();
        let raw = std::fs::read(BASELINE).unwrap();
        assert_eq!(
            fingerprint(&raw, &w),
            "465ea0d7b0ee824b0c1006bc80f9306b315d3e2a0b5c0b662b7ecd19d9c222ba"
        );
    }

    /// Test-only inverse of decode(). The verifier never writes an artifact, so this
    /// lives here rather than in the production path. Mirrors checker.encode().
    fn encode_artifact(n: i64, records: &[(i64, i64, u8)]) -> Vec<u8> {
        let mut out = Vec::with_capacity(HEADER_LEN + RECORD_LEN * records.len());
        out.extend_from_slice(MAGIC);
        out.extend_from_slice(&(n as u16).to_le_bytes());
        for &(row, col, orient) in records {
            let p = (row + n * col) as u32;
            let v = if orient != 0 { ORIENT_BIT | p } else { p };
            out.extend_from_slice(&v.to_le_bytes());
        }
        out
    }

    #[test]
    fn baseline_transpose_shares_the_fingerprint() {
        // The transpose swaps (row, col) and flips every orientation, and is the one
        // non-identity D4 image that is itself a valid crossword for this word list.
        // It must collide, or the same solution could be banked twice.
        let (w, _, _) = load_dict();
        let raw = std::fs::read(BASELINE).unwrap();
        let (n, placements) = decode(&raw, &w).unwrap();
        let transposed: Vec<(i64, i64, u8)> = placements
            .iter()
            .map(|&(r, c, o)| (c, r, 1 - o))
            .collect();
        let re = encode_artifact(n, &transposed);
        assert_ne!(raw, re, "fixture must be two different files");
        assert_eq!(fingerprint(&raw, &w), fingerprint(&re, &w));
    }
}
