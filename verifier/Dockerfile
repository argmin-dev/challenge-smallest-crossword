# Verifier image for Smallest Complete Crossword. Build context MUST be the challenge repo
# ROOT (the Rust build bakes in data/moby-single.txt via include_str!, and build.rs verifies
# its hash), e.g.:
#   docker build -f verifier/Dockerfile -t argmin-verifier:smallest-complete-crossword .
#
# The harness mounts /work and sets $ARGMIN_INPUT=/work/input.json,
# $ARGMIN_OUTPUT=/work/output.json, and runs --network=none, read-only rootfs, non-root,
# all caps dropped. This image is self-contained: the word list is compiled into the binary,
# so nothing is read at run time except the input JSON and the artifact it points to.

# Stage 1: build the fast Rust verifier. Repo layout is preserved (crate at
# /app/verifier/rust, dict at /app/data) so the include_str!/build.rs relative path resolves.
FROM rust:1-slim AS build
WORKDIR /app
COPY data /app/data
COPY verifier/rust /app/verifier/rust
WORKDIR /app/verifier/rust
RUN cargo build --release && cp target/release/xword-verifier /xword-verifier

# Stage 2: minimal runtime. Just the binary; no word list file, no Python, no toolchain.
FROM debian:bookworm-slim
RUN useradd --create-home --uid 10001 verifier
COPY --from=build /xword-verifier /usr/local/bin/xword-verifier
USER verifier
# Reads $ARGMIN_INPUT, writes $ARGMIN_OUTPUT.
ENTRYPOINT ["/usr/local/bin/xword-verifier"]
