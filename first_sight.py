#!/usr/bin/env python3
"""
first_sight.py - First-sight EDA and visualization for Hype Arena (Nexxt AI Hackathon).

Explores `data/practice.csv` and `data/lexicon.json`:
- Computes comprehensive dataset, entity, attribute, and temporal statistics.
- Generates high-res visual charts saved to `visuals/dataset_overview.png`.
- Builds a standalone, interactive HTML report saved to `visuals/first_sight_report.html`.
"""

import argparse
import base64
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="First-sight analysis of Hype Arena dataset.")
    parser.add_argument("--csv", default="data/practice.csv", help="Path to practice.csv")
    parser.add_argument("--lexicon", default="data/lexicon.json", help="Path to lexicon.json")
    parser.add_argument("--out", default="visuals", help="Output directory for visual artifacts")
    return parser.parse_args()


def load_data(csv_path, lexicon_path):
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if not os.path.isfile(lexicon_path):
        raise FileNotFoundError(f"Lexicon file not found: {lexicon_path}")

    df = pd.read_csv(csv_path)
    with open(lexicon_path, "r", encoding="utf-8") as f:
        lexicon = json.load(f)

    # Parse JSON forms
    parsed_forms = []
    for raw in df["form"]:
        try:
            parsed_forms.append(json.loads(raw) if pd.notna(raw) else [])
        except Exception:
            parsed_forms.append([])
    df["parsed_form"] = parsed_forms
    df["fact_count"] = df["parsed_form"].apply(len)
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    df["char_len"] = df["text"].apply(lambda t: len(str(t)))
    df["word_len"] = df["text"].apply(lambda t: len(str(t).split()))
    df["year_month"] = df["dt"].dt.to_period("M").astype(str)

    return df, lexicon


def extract_fact_metrics(df):
    subjects = []
    attributes = []
    kinds = []
    subject_label_map = defaultdict(lambda: Counter())

    for _, row in df.iterrows():
        lbl = row["label"]
        for fact in row["parsed_form"]:
            s = fact.get("subject", "Unknown")
            a = fact.get("attribute", "Unknown")
            v = fact.get("value", {})
            k = v.get("kind", "unknown") if isinstance(v, dict) else "raw"

            subjects.append(s)
            attributes.append(a)
            kinds.append(k)
            subject_label_map[s][lbl] += 1

    return {
        "subjects": Counter(subjects),
        "attributes": Counter(attributes),
        "kinds": Counter(kinds),
        "subject_label_map": subject_label_map,
    }


def generate_plots(df, fact_metrics, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    chart_path = os.path.join(output_dir, "dataset_overview.png")

    fig, axes = plt.subplots(3, 2, figsize=(16, 18), dpi=150)
    plt.subplots_adjust(hspace=0.35, wspace=0.25)
    fig.patch.set_facecolor("#0f172a")

    label_colors = {"true": "#10b981", "false": "#ef4444", "unsure": "#f59e0b"}

    def style_ax(ax, title):
        ax.set_facecolor("#1e293b")
        ax.set_title(title, fontsize=13, fontweight="bold", color="#f8fafc", pad=12)
        ax.tick_params(colors="#94a3b8", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#334155")
        ax.grid(color="#334155", linestyle="--", linewidth=0.5, alpha=0.6)

    # 1. Label Distribution (Donut)
    ax1 = axes[0, 0]
    ax1.set_facecolor("#1e293b")
    lbl_counts = df["label"].value_counts()
    colors = [label_colors.get(k, "#64748b") for k in lbl_counts.index]
    wedges, texts, autotexts = ax1.pie(
        lbl_counts.values,
        labels=[f"{k.upper()}\n({v:,})" for k, v in lbl_counts.items()],
        colors=colors,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.75,
        wedgeprops=dict(width=0.45, edgecolor="#0f172a", linewidth=2),
    )
    for text in texts:
        text.set_color("#cbd5e1")
        text.set_fontsize(10)
        text.set_fontweight("bold")
    for autotext in autotexts:
        autotext.set_color("#ffffff")
        autotext.set_fontsize(10)
        autotext.set_fontweight("bold")
    ax1.set_title("Label Distribution (Ground Truth)", fontsize=13, fontweight="bold", color="#f8fafc", pad=12)

    # 2. Monthly Timeline by Label
    ax2 = axes[0, 1]
    style_ax(ax2, "Timeline of Claims by Month")
    monthly_labels = df.groupby(["year_month", "label"]).size().unstack(fill_value=0)
    all_months = sorted(df["year_month"].unique())
    monthly_labels = monthly_labels.reindex(all_months, fill_value=0)
    bottom = np.zeros(len(all_months))
    for lbl in ["true", "false", "unsure"]:
        if lbl in monthly_labels.columns:
            vals = monthly_labels[lbl].values
            ax2.bar(all_months, vals, bottom=bottom, label=lbl.upper(), color=label_colors[lbl], width=0.65)
            bottom += vals
    ax2.tick_params(axis="x", rotation=45)
    ax2.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0", loc="upper left")
    ax2.set_ylabel("Number of Sentences", color="#94a3b8")

    # 3. Value Kinds Distribution
    ax3 = axes[1, 0]
    style_ax(ax3, "Distribution of Fact Value Kinds")
    kind_series = pd.Series(fact_metrics["kinds"]).sort_values(ascending=True)
    palette = plt.cm.viridis(np.linspace(0.3, 0.9, len(kind_series)))
    bars = ax3.barh(kind_series.index, kind_series.values, color=palette, height=0.65)
    for bar in bars:
        w = bar.get_width()
        ax3.text(w + 12, bar.get_y() + bar.get_height() / 2, f"{int(w):,}", va="center", color="#cbd5e1", fontsize=9)
    ax3.set_xlim(0, max(kind_series.values) * 1.15)
    ax3.set_xlabel("Occurrences", color="#94a3b8")

    # 4. Top 12 Most Discussed Subjects
    ax4 = axes[1, 1]
    style_ax(ax4, "Top 12 Subjects (with True / False / Unsure breakdown)")
    top_subj = [s for s, _ in fact_metrics["subjects"].most_common(12)][::-1]
    sub_df = pd.DataFrame([fact_metrics["subject_label_map"][s] for s in top_subj], index=top_subj).fillna(0)
    b = np.zeros(len(top_subj))
    for lbl in ["true", "false", "unsure"]:
        if lbl in sub_df.columns:
            vals = sub_df[lbl].values
            ax4.barh(top_subj, vals, left=b, label=lbl.upper(), color=label_colors[lbl], height=0.65)
            b += vals
    ax4.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0", loc="lower right")
    ax4.set_xlabel("Total Mentions in Facts", color="#94a3b8")

    # 5. Top 12 Attributes
    ax5 = axes[2, 0]
    style_ax(ax5, "Top 12 Most Frequent Attributes")
    top_attrs = pd.Series(dict(fact_metrics["attributes"].most_common(12))).iloc[::-1]
    ax5.barh(top_attrs.index, top_attrs.values, color="#38bdf8", height=0.65)
    for i, v in enumerate(top_attrs.values):
        ax5.text(v + 3, i, f"{v}", va="center", color="#cbd5e1", fontsize=9)
    ax5.set_xlim(0, max(top_attrs.values) * 1.15)
    ax5.set_xlabel("Occurrences", color="#94a3b8")

    # 6. Sentence Word Count Distribution
    ax6 = axes[2, 1]
    style_ax(ax6, "Sentence Length Distribution (Words)")
    bins = np.linspace(0, 45, 30)
    for lbl in ["true", "false", "unsure"]:
        subset = df[df["label"] == lbl]["word_len"]
        if len(subset) > 0:
            ax6.hist(
                subset,
                bins=bins,
                alpha=0.65,
                label=f"{lbl.upper()} (avg: {subset.mean():.1f})",
                color=label_colors[lbl],
                edgecolor="#0f172a",
            )
    ax6.legend(facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")
    ax6.set_xlabel("Word Count", color="#94a3b8")
    ax6.set_ylabel("Sentence Count", color="#94a3b8")

    fig.suptitle(
        f"Hype Arena - Practice Dataset First-Sight (Total Sentences: {len(df):,})",
        fontsize=16,
        fontweight="bold",
        color="#f1f5f9",
        y=0.995,
    )

    plt.tight_layout()
    fig.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return chart_path


def generate_html_report(df, lexicon, fact_metrics, chart_path, output_dir):
    html_path = os.path.join(output_dir, "first_sight_report.html")

    # Encode chart as base64 for standalone portability
    with open(chart_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    lbl_counts = df["label"].value_counts().to_dict()
    total_rows = len(df)
    true_pct = (lbl_counts.get("true", 0) / total_rows) * 100
    false_pct = (lbl_counts.get("false", 0) / total_rows) * 100
    unsure_pct = (lbl_counts.get("unsure", 0) / total_rows) * 100

    subjects_list = lexicon.get("subjects", [])
    events_list = lexicon.get("events", [])
    total_attrs = sum(len(s.get("attributes", [])) for s in subjects_list)

    # Sample rows for interactive inspection
    samples = {
        "true": df[df["label"] == "true"].head(6).to_dict(orient="records"),
        "false": df[df["label"] == "false"].head(6).to_dict(orient="records"),
        "unsure": df[df["label"] == "unsure"].head(6).to_dict(orient="records"),
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hype Arena - First Sight Dataset Analysis</title>
<style>
  :root {{
    --bg: #0b0f19;
    --card: #151d30;
    --border: #23304c;
    --text: #e2e8f0;
    --text-muted: #889bb6;
    --accent: #38bdf8;
    --true: #10b981;
    --false: #ef4444;
    --unsure: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    line-height: 1.5;
    padding: 2rem;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
  }}
  header h1 {{ font-size: 1.8rem; font-weight: 700; color: #fff; }}
  header .badge {{
    background: #1e293b;
    border: 1px solid #334155;
    padding: 0.35rem 0.8rem;
    border-radius: 9999px;
    font-size: 0.85rem;
    color: var(--accent);
  }}
  .grid-4 {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1.25rem;
    margin-bottom: 2rem;
  }}
  .kpi-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1.25rem;
  }}
  .kpi-title {{ font-size: 0.82rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi-val {{ font-size: 2rem; font-weight: 800; margin: 0.25rem 0; color: #fff; }}
  .kpi-sub {{ font-size: 0.82rem; color: var(--text-muted); }}

  .section-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }}
  .section-title {{
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 1rem;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  .chart-img {{
    width: 100%;
    height: auto;
    border-radius: 0.5rem;
    border: 1px solid var(--border);
  }}
  .table-responsive {{ overflow-x: auto; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
    text-align: left;
  }}
  th, td {{
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border);
  }}
  th {{
    background: #0f172a;
    color: var(--text-muted);
    font-size: 0.8rem;
    text-transform: uppercase;
  }}
  tr:hover td {{ background: #1a243c; }}
  .badge-true {{ background: rgba(16, 185, 129, 0.15); color: var(--true); border: 1px solid var(--true); padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.75rem; }}
  .badge-false {{ background: rgba(239, 68, 68, 0.15); color: var(--false); border: 1px solid var(--false); padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.75rem; }}
  .badge-unsure {{ background: rgba(245, 158, 11, 0.15); color: var(--unsure); border: 1px solid var(--unsure); padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.75rem; }}
  .code-block {{
    background: #0d121f;
    padding: 0.35rem 0.6rem;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.8rem;
    color: #93c5fd;
  }}
  .tab-buttons {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }}
  .tab-btn {{
    background: #1e293b;
    border: 1px solid #334155;
    color: #cbd5e1;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font-weight: 600;
  }}
  .tab-btn.active {{
    background: var(--accent);
    color: #0b0f19;
    border-color: var(--accent);
  }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .insights-list {{
    list-style: none;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1rem;
  }}
  .insight-item {{
    background: #0f172a;
    border-left: 4px solid var(--accent);
    padding: 1rem;
    border-radius: 0 0.5rem 0.5rem 0;
  }}
  .insight-item h4 {{ color: #fff; margin-bottom: 0.35rem; font-size: 0.95rem; }}
  .insight-item p {{ font-size: 0.85rem; color: var(--text-muted); }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>Hype Arena Dataset Overview</h1>
      <p style="color: var(--text-muted); font-size: 0.95rem;">QA-DNA Hackathon Challenge &bull; Hooly Universe Exploratory Analysis</p>
    </div>
    <div class="badge">Nexxt AI Hackathon 2026</div>
  </header>

  <!-- Key Metrics -->
  <div class="grid-4">
    <div class="kpi-card">
      <div class="kpi-title">Practice Sentences</div>
      <div class="kpi-val">{total_rows:,}</div>
      <div class="kpi-sub">Date range: {df['date'].min()} &rarr; {df['date'].max()}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">True Sentences</div>
      <div class="kpi-val" style="color: var(--true);">{lbl_counts.get('true', 0):,}</div>
      <div class="kpi-sub">{true_pct:.1f}% of total claims</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">False Sentences (Contradictions)</div>
      <div class="kpi-val" style="color: var(--false);">{lbl_counts.get('false', 0):,}</div>
      <div class="kpi-sub">{false_pct:.1f}% of total claims</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Unsure Sentences</div>
      <div class="kpi-val" style="color: var(--unsure);">{lbl_counts.get('unsure', 0):,}</div>
      <div class="kpi-sub">{unsure_pct:.1f}% of total claims</div>
    </div>
  </div>

  <div class="grid-4">
    <div class="kpi-card">
      <div class="kpi-title">Lexicon Subjects</div>
      <div class="kpi-val">{len(subjects_list)}</div>
      <div class="kpi-sub">Total canonical entities & people</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Lexicon Attributes</div>
      <div class="kpi-val">{total_attrs}</div>
      <div class="kpi-sub">Across all subjects</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Lexicon Events</div>
      <div class="kpi-val">{len(events_list)}</div>
      <div class="kpi-sub">Key temporal milestones</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Extracted Facts</div>
      <div class="kpi-val">{sum(fact_metrics['kinds'].values()):,}</div>
      <div class="kpi-sub">Avg {df['fact_count'].mean():.2f} facts per sentence</div>
    </div>
  </div>

  <!-- Key Insights for Hackathon -->
  <div class="section-card">
    <div class="section-title">Essential Tactical Insights for the Arena</div>
    <div class="insights-list">
      <div class="insight-item" style="border-left-color: #38bdf8;">
        <h4>1. Temporal Evolution & Changing Facts</h4>
        <p>The universe spans from Oct 2025 to Oct 2026. Metric values (prices, staff, versions) change over time. The contest deadline references values on <strong>29 Oct 2026</strong>.</p>
      </div>
      <div class="insight-item" style="border-left-color: #10b981;">
        <h4>2. Deterministic Claim Generation</h4>
        <p>We must generate <strong>exactly 1,000 new, true claims</strong> in the format of <code>fact</code>, <code>compare</code>, <code>change</code>, <code>at_event</code>, or <code>relation</code>. All entity and attribute names must strictly conform to <code>lexicon.json</code>.</p>
      </div>
      <div class="insight-item" style="border-left-color: #ef4444;">
        <h4>3. The 14.6% Falsehood Rate</h4>
        <p>False sentences represent pages that lie, outdated claims, or incorrect numbers. Catching false values requires tracking the latest ground truth per (subject, attribute) pair.</p>
      </div>
      <div class="insight-item" style="border-left-color: #f59e0b;">
        <h4>4. The "Unsure" Catch-all</h4>
        <p>Sentences that state facts whose values cannot be confirmed or disproven from the dataset must be labelled <code>unsure</code> with no confidence score.</p>
      </div>
    </div>
  </div>

  <!-- Comprehensive Visual Dashboard -->
  <div class="section-card">
    <div class="section-title">Visual Analytics Dashboard</div>
    <img src="data:image/png;base64,{img_b64}" class="chart-img" alt="Dataset Overview Chart" />
  </div>

  <!-- Sample Rows Browser -->
  <div class="section-card">
    <div class="section-title">Interactive Sentence Explorer</div>
    <div class="tab-buttons">
      <button class="tab-btn active" onclick="showTab('tab-false')">False Sentences ({lbl_counts.get('false',0)})</button>
      <button class="tab-btn" onclick="showTab('tab-unsure')">Unsure Sentences ({lbl_counts.get('unsure',0)})</button>
      <button class="tab-btn" onclick="showTab('tab-true')">True Sentences ({lbl_counts.get('true',0)})</button>
    </div>

    <div id="tab-false" class="tab-content active table-responsive">
      <table>
        <thead><tr><th>ID</th><th>Date</th><th>Sentence</th><th>Form Facts</th></tr></thead>
        <tbody>
          {"".join(f'<tr><td><code>{r["id"]}</code></td><td>{r["date"]}</td><td>{r["text"]}</td><td><span class="code-block">{json.dumps(r["parsed_form"])}</span></td></tr>' for r in samples["false"])}
        </tbody>
      </table>
    </div>

    <div id="tab-unsure" class="tab-content table-responsive">
      <table>
        <thead><tr><th>ID</th><th>Date</th><th>Sentence</th><th>Form Facts</th></tr></thead>
        <tbody>
          {"".join(f'<tr><td><code>{r["id"]}</code></td><td>{r["date"]}</td><td>{r["text"]}</td><td><span class="code-block">{json.dumps(r["parsed_form"])}</span></td></tr>' for r in samples["unsure"])}
        </tbody>
      </table>
    </div>

    <div id="tab-true" class="tab-content table-responsive">
      <table>
        <thead><tr><th>ID</th><th>Date</th><th>Sentence</th><th>Form Facts</th></tr></thead>
        <tbody>
          {"".join(f'<tr><td><code>{r["id"]}</code></td><td>{r["date"]}</td><td>{r["text"]}</td><td><span class="code-block">{json.dumps(r["parsed_form"])}</span></td></tr>' for r in samples["true"])}
        </tbody>
      </table>
    </div>
  </div>
</div>

<script>
function showTab(tabId) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(tabId).classList.add('active');
  event.target.classList.add('active');
}}
</script>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


def main():
    args = parse_args()

    print(f"\n=======================================================")
    print(f"  HYPE ARENA - FIRST SIGHT DATASET EXPLORATION")
    print(f"=======================================================\n")

    print(f"[1/4] Loading {args.csv} and {args.lexicon}...")
    df, lexicon = load_data(args.csv, args.lexicon)
    print(f"      Loaded {len(df):,} sentences from practice dataset.")
    print(f"      Date range: {df['date'].min()} to {df['date'].max()}")

    print(f"\n[2/4] Analyzing labels and structured fact semantics...")
    lbl_counts = df["label"].value_counts()
    for lbl, cnt in lbl_counts.items():
        pct = (cnt / len(df)) * 100
        print(f"      - {lbl.upper():<7}: {cnt:>5,} rows ({pct:5.1f}%)")

    fact_metrics = extract_fact_metrics(df)
    total_facts = sum(fact_metrics["kinds"].values())
    print(f"      Total extracted facts in dataset: {total_facts:,}")
    print(f"      Top Value Types:")
    for kind, cnt in fact_metrics["kinds"].most_common():
        print(f"        * {kind:<10}: {cnt:>4,}")

    print(f"\n      Top 5 Most Mentioned Subjects:")
    for subj, cnt in fact_metrics["subjects"].most_common(5):
        t_cnt = fact_metrics["subject_label_map"][subj]["true"]
        f_cnt = fact_metrics["subject_label_map"][subj]["false"]
        u_cnt = fact_metrics["subject_label_map"][subj]["unsure"]
        print(f"        * {subj:<24}: {cnt:>3} facts (True: {t_cnt}, False: {f_cnt}, Unsure: {u_cnt})")

    print(f"\n[3/4] Generating high-resolution visuals at '{args.out}/'...")
    chart_path = generate_plots(df, fact_metrics, args.out)
    print(f"      Saved chart dashboard -> {chart_path}")

    print(f"\n[4/4] Building interactive HTML report...")
    html_path = generate_html_report(df, lexicon, fact_metrics, chart_path, args.out)
    print(f"      Saved HTML report     -> {html_path}")

    print(f"\n=======================================================")
    print(f"  EDA COMPLETE!")
    print(f"  Open the HTML report in your browser to view:")
    print(f"  file:///{os.path.abspath(html_path).replace(os.sep, '/')}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
