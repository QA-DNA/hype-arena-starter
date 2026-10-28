"""Render summary.md + catalogue.json into the repo markdown and the artifact HTML."""
import json, sys, html
from pathlib import Path
import markdown

here = Path(__file__).parent
summary = (here / "summary.md").read_text()
entries = json.loads((here / "catalogue.json").read_text())
STEPS = {"S1": "as-of query", "S2": "conflicts + source reliability", "S3": "change over time",
         "S4": "inexact values", "S5": "blame", "S6": "labelling + calibration",
         "S7": "claim generation", "S8": "explanation"}
order = {"ADOPT": 0, "TRY": 1, "IDEA-ONLY": 2, "REJECT": 3}
entries.sort(key=lambda e: (min(int(s[1]) for s in e["steps"]), order[e["verdict"]], e["insanity"]))

def md_entry(e):
    out = [f"### {e['name']}", "",
           f"- **Kind:** {e['kind']} · **Steps:** {', '.join(f'{s} {STEPS[s]}' for s in e['steps'])}"
           f" · **Verdict:** {e['verdict']} · **Insanity:** {e['insanity']}/5",
           f"- **What:** {e['what']}",
           f"- **Fit here:** {e['fit']}",
           f"- **Pros:** " + "; ".join(e["pros"]),
           f"- **Cons:** " + "; ".join(e["cons"]),
           f"- **Rust:** {e['rust']}",
           f"- **Python (labs):** {e['python']}",
           f"- **Why this verdict:** {e['why']}",
           f"- **Sources:** " + (" · ".join(f"<{l}>" for l in e.get("links", [])) or "not verified"), ""]
    return "\n".join(out)

cat_md = ["## Full catalogue", "",
          "Sorted by first step served, then verdict, then insanity (1 = an afternoon, 5 = a research project by the deadline).", ""]
for s, label in STEPS.items():
    group = [e for e in entries if min(e["steps"], key=lambda x: int(x[1])) == s]
    if group:
        cat_md += [f"<!-- {s} -->", ""] + [md_entry(e) for e in group]
md = summary.replace("<!-- CATALOGUE -->", "\n".join(cat_md))
out_md = Path(sys.argv[1])
out_md.write_text(md)

tpl = (here / "template.html").read_text()
summary_html = markdown.markdown(summary.split("<!-- CATALOGUE -->")[0].split("\n", 2)[2],
                                 extensions=["tables", "fenced_code"])
summary_html = summary_html.replace('<pre><code class="language-mermaid">', '<pre class="mermaid">').replace("</code></pre>", "</pre>")
summary_html = summary_html.replace("<table>", '<div class="tablebox"><table>').replace("</table>", "</table></div>")
page = (tpl.replace("__SUMMARY__", f'<section class="summary">{summary_html}</section>')
           .replace("__ENTRIES__", json.dumps(entries, ensure_ascii=False).replace("</", "<\\/"))
           .replace("__DATE__", "28 Oct 2026")
           .replace("__FOOTER__", "Source of truth: <code>docs/research/knowledge-base.md</code> in teodorbalan/VERIDYCT. Research workers used free tools only; unverified citations are marked."))
(here / "kb-atlas.html").write_text(page)
print(len(entries), "entries;", out_md, here / "kb-atlas.html")
