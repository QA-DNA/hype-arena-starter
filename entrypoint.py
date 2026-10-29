#!/usr/bin/env python3
"""
entrypoint.py - The official execution engine for the Hype Arena Docker container.

Follows contracts/README.md and mentor specifications:
1. Reads /universe/universe.csv and /universe/lexicon.json (with local fallback).
2. Uses generate_claims.py to build the 1,000 referee-valid new claims.
3. Produces /output/output.csv: a label for every unlabelled input row
   (src/label_rows.py) and the 1,000 claims.
4. Atomically writes the table to /output/output.csv.
5. Runs offline in well under the 30-minute limit, as USER 10001.
"""

import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Add src to path for layer modules and generate_claims
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from generate_claims import Generator, js_str

try:
    from label_rows import predict_labels
    HAS_LABELER = True
except ImportError:
    HAS_LABELER = False

UNIVERSE_DIR = Path(os.getenv("ARENA_UNIVERSE", "/universe"))
OUTPUT_DIR = Path(os.getenv("ARENA_OUTPUT", "/output"))
LOCAL_DATA_DIR = Path("data")
TARGET_CLAIMS = 1000


def resolve_paths():
    univ_csv = UNIVERSE_DIR / "universe.csv"
    if not univ_csv.is_file():
        univ_csv = LOCAL_DATA_DIR / "practice.csv"
        if not univ_csv.is_file():
            univ_csv = Path("practice.csv")

    lex_json = UNIVERSE_DIR / "lexicon.json"
    if not lex_json.is_file():
        lex_json = LOCAL_DATA_DIR / "lexicon.json"
        if not lex_json.is_file():
            lex_json = Path("lexicon.json")

    practice_csv = LOCAL_DATA_DIR / "practice.csv"
    if not practice_csv.is_file():
        practice_csv = Path("practice.csv")

    out_dir = OUTPUT_DIR
    if not out_dir.is_dir():
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)

    return univ_csv, lex_json, practice_csv, out_dir


def read_practice(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if isinstance(r.get("form"), str):
            try:
                r["form"] = json.loads(r["form"])
            except Exception:
                r["form"] = []
    return rows


def main():
    t0 = time.time()
    print("=========================================================")
    print("  HYPE ARENA ENGINE - 21K ROW BUILDER")
    print("=========================================================")

    univ_path, lex_path, practice_path, out_dir = resolve_paths()
    print(f"  • Input Universe : {univ_path}")
    print(f"  • Lexicon Path   : {lex_path}")
    print(f"  • Practice Ground: {practice_path}")
    print(f"  • Output Dir     : {out_dir}")

    # 1. Load Lexicon & Practice Rows
    with open(lex_path, "r", encoding="utf-8") as f:
        lexicon = json.load(f)

    practice_rows = read_practice(practice_path)
    print(f"\n[1/3] Loaded {len(practice_rows):,} practice ground truth rows.")

    # 2. Run generate_claims.py to build the 1,000 verified claims
    print("\n[2/3] Generating claims using generate_claims.py...")
    gen = Generator(practice_rows, lexicon)
    claims_res = gen.generate(target=TARGET_CLAIMS)
    claims = claims_res["claims"]
    print(f"      Generated {len(claims):,} valid new claims (Shortfall: {claims_res['shortfall']}).")
    print(f"      Distribution: {claims_res['valid']}")

    # 3. Construct the 21,000-row table
    print("\n[3/3] Assembling the output table...")
    output_rows = []

    # Identify unlabelled rows from the input universe (rows where label is empty)
    unlabelled_input_rows = []
    if univ_path.is_file():
        with open(univ_path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if not (r.get("label") or "").strip():
                    unlabelled_input_rows.append(r)

    unlabelled_ids = {r["id"].strip() for r in unlabelled_input_rows}

    # Section A: Practice / ground truth rows (for rows not hidden in input)
    for r in practice_rows:
        rid = r["id"].strip()
        if rid in unlabelled_ids:
            continue  # Will be predicted and emitted in Section B
        label = (r.get("label") or "").strip().lower()
        output_rows.append({
            "id": rid,
            "type": "",
            "text": "",
            "form": "",
            "label": label,
            "confidence": ""  # No hardcoded confidence; left empty as requested
        })

    # Section B: Unlabelled universe rows (predicted via ML label_rows pipeline)
    if unlabelled_input_rows:
        print(f"      Found {len(unlabelled_input_rows):,} unlabelled universe rows.")
        if HAS_LABELER:
            print(f"      Activating ML label_rows pipeline...")
            preds = predict_labels(practice_rows, unlabelled_input_rows, str(lex_path))
        else:
            print("      [WARN] label_rows ML engine not available, defaulting to unsure.")
            preds = {}

        for r in unlabelled_input_rows:
            rid = r["id"].strip()
            pred_label, pred_conf = preds.get(rid, ("unsure", ""))
            output_rows.append({
                "id": rid,
                "type": "",
                "text": "",
                "form": "",
                "label": pred_label,
                "confidence": pred_conf
            })

    universe_count = len(output_rows)
    print(f"      Universe rows total: {universe_count:,}")

    # Section C: Append the 1,000 claims generated by generate_claims.py
    for c in claims:
        output_rows.append({
            "id": c["id"].strip(),
            "type": c["type"].strip(),
            "text": c["text"].strip(),
            "form": json.dumps(c["form"], ensure_ascii=False, separators=(",", ":")),
            "label": "true",
            "confidence": str(c["confidence"])
        })

    total_rows = len(output_rows)
    print(f"      Claims rows total  : {len(claims):,}")
    print(f"      GRAND TOTAL ROWS   : {total_rows:,}")

    # 4. Atomically write to /output/output.csv
    tmp_path = out_dir / "output.tmp.csv"
    final_path = out_dir / "output.csv"

    fieldnames = ["id", "type", "text", "form", "label", "confidence"]
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    if final_path.exists():
        final_path.unlink()
    shutil.move(str(tmp_path), str(final_path))

    file_size_mb = os.path.getsize(final_path) / (1024 * 1024)
    print(f"\n[DONE] Wrote {total_rows:,} rows to {final_path} ({file_size_mb:.2f} MiB).")
    print(f"       Execution time: {time.time() - t0:.2f}s")
    print("=========================================================\n")


if __name__ == "__main__":
    main()
