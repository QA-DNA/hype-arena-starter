# Knowledge base atlas sources

Sources for [the knowledge base research](../knowledge-base.md) and its interactive page
(<https://claude.ai/artifact/NJFDojtSqqVys7a6pCCfeN>). Edit these, not the generated files.

- `catalogue.json`: the 63 entries. Fields: name, kind, steps, verdict, insanity, what, fit,
  pros, cons, rust, python, why, links.
- `summary.md`: the report text; `<!-- CATALOGUE -->` marks where the entries go.
- `template.html`: the page shell, with placeholders `__SUMMARY__`, `__ENTRIES__`, `__DATE__`
  and `__FOOTER__`.
- `build.py`: renders both outputs.
- `kb-atlas.html`: generated; the same page as the artifact. Open it in a browser (Mermaid loads
  from a CDN, so the diagram needs a network connection).
- `patch.py`: a one-off that added the measured notes and two entries. Already applied; it
  refuses a second run.

```sh
uv venv --python 3.12 .venv-atlas
uv pip install --python .venv-atlas/bin/python markdown
cd docs/research/atlas
../../../.venv-atlas/bin/python build.py ../knowledge-base.md   # writes the report and kb-atlas.html
```

Verified 2026-10-28: a rebuild reproduced the committed `knowledge-base.md` and `kb-atlas.html`
byte for byte before the "Where everything is" section was added.
