# Repository tooling

Read [root rules](../AGENTS.md). Keep commands portable and their errors actionable.

- Invoke processes with argument arrays, never interpolated shell strings.
- Respect Cargo.lock. Do not install software silently from doctor or check.
- Exclude secrets and generated files from context. Validate task IDs and source paths.
- Distinguish curated design relations from extracted Cargo dependency relations.
- Keep context bounded and print source commit, fingerprint, and visible truncation.
- Preserve exit codes and run long-lived servers in the foreground for predictable shutdown.
- Document command changes in the README and development guide in the same change.
