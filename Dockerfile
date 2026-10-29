FROM rust:1.90.0-bookworm AS builder
ARG TARGETARCH
WORKDIR /workspace
RUN rustup toolchain install 1.90.0 --profile minimal --component rustfmt --component clippy
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,id=veridyct-rust-1.90-release-${TARGETARCH},target=/workspace/target \
    cargo build --locked --release --package veridyct-cli --package veridyct-api \
    && mkdir -p /out \
    && cp target/release/veridyct target/release/veridyct-api /out/

FROM debian:bookworm-slim AS runtime
WORKDIR /app
COPY --from=builder /out/veridyct /app/veridyct
COPY --from=builder /out/veridyct-api /app/veridyct-api
ENV HOME=/tmp XDG_CACHE_HOME=/tmp VERIDYCT_ADDR=0.0.0.0:8787
EXPOSE 8787
ENTRYPOINT ["/app/veridyct"]
CMD ["run"]
USER 10001
