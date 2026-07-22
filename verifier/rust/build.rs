// Build guard: the dictionary baked into the binary (via include_str! in main.rs) must
// hash to the pinned SHA-256. If data/moby-single.txt is ever changed, the build fails
// loudly rather than silently shipping a verifier bound to a different word list (which
// would change the spec). Keep DICT_SHA256 identical to the constant in checker.py.
use sha2::{Digest, Sha256};

const DICT_SHA256: &str = "2056d03ea1189904b98a13843dd258277f394470229c1e212460eac5074066c5";

fn main() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../data/moby-single.txt");
    println!("cargo:rerun-if-changed={}", path);
    let bytes = std::fs::read(path).unwrap_or_else(|e| panic!("cannot read {path}: {e}"));
    let got = hex(&Sha256::digest(&bytes));
    if got != DICT_SHA256 {
        panic!("dictionary hash mismatch: expected {DICT_SHA256}, got {got}");
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{:02x}", b)).collect()
}
