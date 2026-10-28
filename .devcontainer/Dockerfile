FROM rust:1.90.0-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rustup component add rustfmt clippy \
    && useradd --create-home --shell /bin/bash --uid 1000 vscode \
    && mkdir -p /usr/local/cargo/registry /usr/local/cargo/git \
    && chown -R vscode:vscode /usr/local/cargo /usr/local/rustup
USER vscode
