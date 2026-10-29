# Diagram PNG provenance and prompts

Generated on 2026-10-28 with the built-in `image_gen` tool, with opaque backgrounds.
These are presentation assets; they contain no runtime inference or training material.
The selected outputs were copied into the repository and visually inspected.

- [Stack PNG](../../apps/web/assets/stack.png): 1536 x 1024, served at `/assets/stack.png`.
- [Pipeline PNG](../../apps/web/assets/pipeline.png): 1774 x 887, served at `/assets/pipeline.png`.

Both were generated from new descriptions, without input reference images. No CLI
fallback, API key, image editing, synthetic performance metric or external runtime
service was used. The following is the prompt set supplied to the built-in tool.

## Stack prompt

Create a premium, exceptionally clear professional software architecture infographic as a finished high-resolution landscape PNG for the VERIDYCT local evidence workbench. This is an explanatory engineering diagram for a live presentation, not a website screenshot. Use a very wide landscape composition, elegant editorial typography, huge legible headings, precise consistent alignment, fine connector arrows, generous whitespace, subtle shadows, beautifully drawn simple technical icons. Palette: warm off-white #F6F7F9 background, ink navy #171E2C text, vivid violet #7055DE for shared computation, pale mint #C7F0DE for trusted evidence. White rounded cards with fine gray borders, restrained premium style. All text in English, exact spelling. No invented metrics, no robot illustrations, no decorative illegible text.

Title: "VERIDYCT" and "The system stack". Subtitle: "Two entry points. One offline Rust engine. Traceable results."

Arrange four horizontal numbered layers with clearly visible arrows flowing DOWN between layers.

Layer 01 label "INPUT & INTERFACES": two large cards side by side: "LOCAL BROWSER" with "HTML · CSS · JavaScript" and "Upload CSV · Run · Inspect · Download"; "COMPETITION CLI" with "Rust command line" and "/universe/universe.csv → /output/output.csv". Small data chips below: "practice.csv: labelled examples + forms", "lexicon.json: subjects + aliases + attributes", "universe.csv: known + unlabelled rows".

Layer 02 label "ADAPTERS": under Browser show "AXUM HTTP API" with "JSON endpoints · bounded jobs · real progress". Under CLI show "FILE ADAPTER" with "Strict CSV validation · atomic output write". Both arrows converge into ONE shared Rust core below, labeled "same implementation".

Layer 03 label "SHARED RUST CORE": one violet-outlined broad panel containing four readable cards: "NORMALIZE & EXTRACT" / "Mihai's alias matcher" / "subject · attribute · typed value"; "DATED EVIDENCE" / "Source row ID + observation date" / "Trusted labels stay separate from predictions"; "RANDOM FOREST" / "48 trees · 80 features" / "True / False / Unsure scores"; "CLAIMS + MMR" / "Contract templates + diversity selection" / "1,000 claims from trusted evidence". Use distinct connecting arrows and a mint branch from DATED EVIDENCE to CLAIMS + MMR explicitly labeled "known-true evidence only". Do NOT imply predicted-true outputs become trusted generation evidence. Below panel output strip: "VERDICTS + EVIDENCE + OFFICIAL CSV" with small exact columns "id · type · text · form · label · confidence".

Layer 04 label "RUNTIME": a navy horizontal footer panel "LINUX AMD64 · CPU ONLY" with crisp chips "2 CPUs", "6 GiB RAM", "UID 10001", "Read-only root", "30-minute deadline", "Offline competition run". Very small but legible footnote: "The browser uses local HTTP. Competition execution has no network. No LLM at runtime."

Make this diagram visually outstanding, dramatically better than generic box diagrams, and easy to understand from a projector. Prefer clarity and correct readable labels over ornament. Use distinct layers, a purposeful visual hierarchy, and clean orthogonal arrows that never cross text.

## Pipeline prompt

Create a premium landscape explanatory software workflow infographic PNG, matching a sophisticated VERIDYCT engineering presentation. Off-white #F6F7F9 background, ink navy text, violet #7055DE computation, mint #C7F0DE trusted evidence, muted rose for mistakes. Crisp vector-like technical illustration, elegant editorial typography, generous spacing, precise orthogonal connector arrows, substantial readable type, beautiful restrained premium aesthetic. This is a finished diagram, not a website screenshot. High resolution wide landscape layout.

Title exactly "VERIDYCT" / "From a sentence to a testable verdict". Subtitle exactly "Inspect the facts. Trace the evidence. Measure the result."

TOP half is one clear numbered six-step pipeline with arrows flowing left to right across large cards:

- "01 READ" / "CSV + lexicon" / "id · text · date · label"
- "02 NORMALIZE" / "Canonical entities" / "Aliases + longest name match"
- "03 EXTRACT" / "Typed assertions" / "Subject + attribute + value"
- "04 ESTIMATE" / "48-tree Random Forest" / "True / False / Unsure scores"
- "05 EXPLAIN" / "Source evidence" / "Row IDs + dates + conflicts"
- "06 EXPORT" / "Official CSV" / "Verdicts + 1,000 claims"

Below these steps one subtle illustrative fact strip: "EXAMPLE" then "Hooly Cloud covers 3 regions." then arrow then "Hooly Cloud | regions | quantity: 3 region". Caption "An assertion is not automatically accepted as truth."

Separate mint horizontal branch below: "KNOWN-TRUE OBSERVATIONS ONLY" arrow "Contract templates" arrow "MMR: support + diversity" arrow "1,000 new claims". Explicit small line "Model-predicted true rows are never promoted to trusted generation evidence."

BOTTOM half heading "TWO DIFFERENT QUALITY CHECKS". Two equally large side-by-side panels, unmistakably distinguished:

LEFT PANEL violet accent title "HIDDEN-LABEL ACCURACY". Vertical three stages connected with simple down arrows: "Hold out 380 labelled rows" / "Remove matching texts from training; hide labels and forms" / "Predict first. Reveal reference labels afterwards.". Bottom metric chips "Accuracy", "Macro-F1", "Per-class recall", "Confusion matrix". Footnote "Diagnostic split: shared facts and templates remain."

RIGHT PANEL mint accent title "AGREEMENT WITH LLM REVIEW". Vertical three stages: "Download a 20-row unlabelled demo CSV" / "Run the offline Rust engine" / "Compare with separate LLM labels + cited evidence". Bottom chips "Matches / 20", "Disagreements", "Inspect each source". Footnote in bold "LLM agreement is not verified ground-truth accuracy."

Bottom navy ribbon exact text "Unknown reference labels → accuracy unknown. A model score is not measured accuracy." and small footer "No LLM at runtime · CPU only · All results inspectable".

Do not invent a numerical accuracy result, no charts with made-up data, no claim of flawless truth. Avoid unreadable tiny labels. Align every card and arrow meticulously. Make a diagram that an engineering judge can understand immediately.
