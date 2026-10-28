# Browser interface scope

Read [root instructions](../../AGENTS.md). The responsive workbench runs the actual
Rust API, presents estimates and evidence, and shows architecture and stack diagrams.

- The required demo displays architecture and runs the actual system on uploaded rows.
- Show progress, validation errors, unknowns, labels, confidence, and evidence clearly.
- Use the Rust API; browser-side presentation must not become a separate solver.
- The shell is local HTML/CSS with minimal browser JavaScript. Record
  the UI stack decision before adding React, Rust/WASM, or another toolchain.
- Bundle required assets locally; do not rely on CDNs, third-party fonts, or remote APIs.
- Keep setup diagnostics and internal agent coordination out of the product flow.
- Support keyboard use, readable contrast, explicit labels, and a responsive layout.
- Render untrusted input as text, not executable markup. Validate uploaded files in the API too.
- Verify the main user flow against a real API response. Mock screens alone are not a live demo.
