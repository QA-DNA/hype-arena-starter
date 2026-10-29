# Build-time network only. All inference code is compiled from this checkout.
ARG BUILDER_IMAGE=rust:1.90.0-bookworm
FROM ${BUILDER_IMAGE} AS solver-builder
USER 0
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,id=veridyct-rust-1.90-release-amd64,target=/workspace/target \
    cargo build --locked --release -p veridyct-cli -p veridyct-api \
    && mkdir -p /out && cp target/release/veridyct target/release/veridyct-api /out/

FROM ${BUILDER_IMAGE} AS extractor-builder
USER 0
WORKDIR /build
COPY crates/extractor/ ./
RUN --mount=type=cache,id=veridyct-native-extractor-registry,target=/usr/local/cargo/registry \
    --mount=type=cache,id=veridyct-native-extractor-target,target=/build/target \
    cargo build --locked --release \
    && mkdir -p /out && cp target/release/veridyct-extractor /out/ \
    && cp -L /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /out/libstdc++.so.6 \
    && cp -L /lib/x86_64-linux-gnu/libgcc_s.so.1 /out/libgcc_s.so.1

FROM debian:bookworm-slim AS assets
ADD --checksum=sha256:44692ff8fae56274e416b74c6cabc25801511998a2d0b9fae54bb81a7fade0c9 https://github.com/teodorbalan/VERIDYCT/releases/download/runtime-assets-20261029/veridyct-cpu-assets-20261029.tar.gz /tmp/assets.tar.gz
RUN mkdir /assets && tar -xzf /tmp/assets.tar.gz -C /assets \
    && echo '98eebdb851849f689c60499a9f4b2514305d520a523816b0505e98bba4523b6f  /assets/model/model.onnx' | sha256sum -c - \
    && echo '007d278c95e5cffc785efb89a66ca0b2d2b9428b74f02986798dd2da716c8f59  /assets/verifier.json' | sha256sum -c - \
    && echo '718c3fb0785d5ea06061b92c32ce4ad35be1bd4c71ae6192efe06f1ab21f0f8a  /assets/lib/libonnxruntime.so.1.23.2' | sha256sum -c - \
    && echo '086ec1d5388f64153d9c63470d126693db9a182c8ce236d3a1119068471b8a0d  /assets/lib/libonnxruntime_providers_shared.so' | sha256sum -c -

FROM debian:bookworm-slim AS runtime
WORKDIR /app
COPY --from=solver-builder /out/veridyct /out/veridyct-api /app/
COPY --from=extractor-builder /out/veridyct-extractor /opt/veridyct-extractor/veridyct-extractor
COPY --from=extractor-builder /out/libstdc++.so.6 /out/libgcc_s.so.1 /usr/lib/x86_64-linux-gnu/
COPY --from=assets /assets/model/ /opt/veridyct-extractor/model/
COPY --from=assets /assets/lib/ /opt/veridyct-extractor/lib/
COPY --from=assets /assets/verifier.json /app/verifier.json
ENV HOME=/tmp XDG_CACHE_HOME=/tmp VERIDYCT_ADDR=0.0.0.0:8787 \
    ORT_DYLIB_PATH=/opt/veridyct-extractor/lib/libonnxruntime.so.1.23.2 \
    VERIDYCT_NATIVE_EXTRACTOR=/opt/veridyct-extractor/veridyct-extractor \
    VERIDYCT_NEURAL_BUNDLE=/opt/veridyct-extractor/model \
    VERIDYCT_STRUCTURED_PARSER=1 VERIDYCT_PARSER_BATCHING=exact-length \
    VERIDYCT_PARSER_CONTEXT=none VERIDYCT_VERIFIER_MODEL=/app/verifier.json \
    VERIDYCT_KB_CHAIN=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
EXPOSE 8787
ENTRYPOINT ["/app/veridyct"]
CMD ["run"]
USER 10001
