# 0002: Offline evidence MVP with a small CPU forest

Authorized: Teodor, 2026-10-28. Status: implemented and locally validated MVP.

The local demonstration and competition CLI call one Rust core. The model is a seeded
Random Forest with bounded trees and CPU work. The system is not an LLM. The frontend
keeps the existing local HTML/CSS/JavaScript stack and Axum HTTP adapter.

Mihai's analysis (commit 4478b99) supplies normalization, alias and typed assertion
findings. Training includes the public practice data, as the contract permits. Every
displayed assertion and candidate claim must retain source row IDs and observation dates.
Model score distributions are estimates; they are not certified calibrated probabilities.

New claims are constructed with contract templates from accepted evidence and selected
with maximal marginal relevance (MMR). A format check cannot prove their truth or the
organizer's private grammar checks. Unknown statements do not become trusted evidence
solely because the model predicts true. Observations do not establish precise change
boundaries or prove that a mutable fact remains current on 29 October.

The competition container is checked offline, read-only, as UID 10001, with 2 CPU and
6 GiB RAM. The separate local web container publishes a loopback HTTP port, which needs
Docker networking; its computation uses the same core. The Windows team wrapper
[arena-check.ps1](../../tools/arena-check.ps1) reproduces organizer restrictions and calls
their preserved input/output scripts. It retains run artifacts outside Git.

Task agreement and validation: [live MVP handoff](../handoffs/live-mvp.md).
