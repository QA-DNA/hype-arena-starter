# Project knowledge graph

This is project memory for humans and development agents. It is separate from the
future Hooly evidence graph used by the application.

## Current artifact

[graph.json](graph.json) is a manually curated project graph. It connects foundation
modules, instruction files and decisions. Status explicitly separates the working
foundation from planned reasoning and deferred native acceleration.

Each node has a stable id, kind, status, and a repository-relative source path.
Module paths refer to source manifests, assets or scoped instructions as appropriate.
Status distinguishes the foundation from future behavior.
Each edge has a relation and a source document that explains the intended connection.

## Authority and updates

- The official contract is authoritative for the challenge. Design decisions record team proposals.
- Source code and reproducible test results establish implemented behavior.
- Keep manually declared architectural relations separate from future extracted import/call edges.
- Extraction must record the source commit plus a fingerprint for relevant dirty files;
  label its output stale if either changes. It must not silently turn an inference into a fact.
- Validate unique node IDs, known edge endpoints, allowed relation types, and existing source
  paths. A missing document is an error; a planned code module is never described as implemented.
- A task updates its affected graph entries when changing a module boundary or decision.
  Do not store generated binary databases or embeddings in Git.

## Commands

`cargo xtask context --scope core --task workspace-foundation --max-chars 16000` retrieves
root rules, scoped rules, declared module relationships, relevant decisions and the named
handoff. Output includes the source commit, content fingerprint and visible truncation.
The task argument is optional. No embedding service or external LLM is required.

`cargo xtask graph` exports artifacts/project-graph.json. It combines the curated graph
with actual workspace dependency edges extracted from Cargo metadata. It records the
commit and a fingerprint including relevant dirty/untracked source files. This is package
dependency extraction, not a function-call or symbol index. Snapshots are ignored in Git;
regenerate after edits rather than treating an old snapshot as current.

`cargo xtask docs` validates links, graph identities/relations/source paths and the original
organizer-file checksums. It reports drift instead of silently accepting changed evidence.

## Application evidence graph: separate rules

The future application graph stores typed assertions, source row IDs, observation dates,
supported validity intervals, and evidence status. It must distinguish claims from established
facts. A false compound sentence does not make all its components false; unknown is not false;
unlabelled repetition does not establish truth; an observation date does not prove a validity
interval. These are design constraints, not an implemented reasoning algorithm.

The project graph must never supply Hooly facts to the application. Development LLMs may help
write code and test material, but their background knowledge is not a source of universe truth.
