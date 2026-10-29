#!/usr/bin/env python3
"""
scripts/run_competition_benchmark.py - Full end-to-end competition simulation.

Runs both algorithms:
1. ML Labeling Engine (label_rows.py on 18,000 unlabelled rows)
2. Claim Generation Engine (generate_claims.py on 1,000 claims)

Simulates official competition arena conditions for:
- Step-5 dataset (sample_label_step5.csv: 18k rows)
- GLM-5.3 dataset (sample_label_glm5.csv: 18k rows)

Validates against:
- scripts/check_output.py (Official contest referee checker)
- Ground truth benchmarks (data/ground_truth_step5.csv and data/ground_truth_glm5.csv)
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_competition_universe(practice_path, unlabelled_path, dest_dir):
    """Combines practice.csv (labelled) + 18k unlabelled samples into universe.csv."""
    os.makedirs(dest_dir, exist_ok=True)
    univ_path = os.path.join(dest_dir, "universe.csv")
    lex_path = os.path.join(dest_dir, "lexicon.json")

    practice_rows = read_csv(practice_path)
    unlabelled_rows = read_csv(unlabelled_path)

    with open(univ_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text", "date", "label"])
        # 1. Practice rows (with their ground truth labels)
        for r in practice_rows:
            writer.writerow([r["id"], r["text"], r["date"], r.get("label", "")])
        # 2. Unlabelled test rows (with empty labels)
        for r in unlabelled_rows:
            writer.writerow([r["id"], r["text"], r["date"], ""])

    shutil.copy("data/lexicon.json", lex_path)
    return univ_path, len(practice_rows), len(unlabelled_rows)


def run_benchmark_for_dataset(name, unlabelled_csv, ground_truth_csv):
    print("\n" + "=" * 65)
    print(f"  STARTING COMPETITION SIMULATION: {name.upper()}")
    print("=" * 65)

    sim_dir = f"temp_arena_{name}"
    out_dir = f"temp_output_{name}"
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    univ_path, n_prac, n_unlabelled = build_competition_universe(
        "data/practice.csv", unlabelled_csv, sim_dir
    )
    print(f"  • Constructed universe: {n_prac:,} practice + {n_unlabelled:,} unlabelled = {n_prac+n_unlabelled:,} total rows.")

    # Run entrypoint with simulated arena environment variables
    env = os.environ.copy()
    env["ARENA_UNIVERSE"] = sim_dir
    env["ARENA_OUTPUT"] = out_dir

    t_engine_start = time.time()
    proc = subprocess.run(
        [sys.executable, "entrypoint.py"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    t_engine_end = time.time()

    stdout_text = proc.stdout or ""
    print("\n  [ENGINE OUTPUT LOGS]:")
    for line in stdout_text.strip().splitlines()[-15:]:
        print("    " + line)

    if proc.returncode != 0:
        print("\n  [ERROR] Engine crashed with error:")
        print(proc.stderr)
        return False

    out_csv = os.path.join(out_dir, "output.csv")
    out_size_mb = os.path.getsize(out_csv) / (1024 * 1024)
    out_rows = read_csv(out_csv)
    claims_rows = [r for r in out_rows if r.get("type")]
    label_rows = [r for r in out_rows if not r.get("type")]

    print(f"\n  [OUTPUT STATS]:")
    print(f"  • Total rows in output.csv : {len(out_rows):,}")
    print(f"  • Input label rows         : {len(label_rows):,}")
    print(f"  • Generated claims rows    : {len(claims_rows):,}")
    print(f"  • File size on disk        : {out_size_mb:.2f} MiB (limit: 16 MiB)")
    print(f"  • Total engine time        : {t_engine_end - t_engine_start:.2f}s (deadline: 1800s)")

    # Official referee check
    print("\n  [OFFICIAL REFEREE CHECK - check_output.py]:")
    ref_proc = subprocess.run(
        [sys.executable, "scripts/check_output.py", out_dir, "data/practice.csv", univ_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    print("    " + "\n    ".join(ref_proc.stdout.strip().splitlines()))

    # Evaluate predictions against ground truth
    gt_rows = read_csv(ground_truth_csv)
    gt_dict = {r["id"].strip(): r["gold_label"].strip().lower() for r in gt_rows}

    pred_labels = {r["id"].strip(): (r.get("label") or "").strip().lower() for r in label_rows}
    pred_confs = {r["id"].strip(): r.get("confidence") or "" for r in label_rows}

    eval_total = len(gt_dict)
    eval_preds = Counter()
    gold_counts = Counter(gt_dict.values())
    match_counts = Counter()

    for rid, gold in gt_dict.items():
        pred = pred_labels.get(rid, "unsure")
        eval_preds[pred] += 1
        if pred == gold:
            match_counts[gold] += 1

    overall_acc = sum(match_counts.values()) / max(eval_total, 1)

    print("\n  [ACCURACY & CALIBRATION BENCHMARK (on 18,000 Unseen Samples)]:")
    print(f"  • Overall Gold distribution : {dict(gold_counts)}")
    print(f"  • Model Pred distribution   : {dict(eval_preds)}")
    print(f"  • Accuracy (Exact match)    : {overall_acc * 100:.2f}% ({sum(match_counts.values()):,}/{eval_total:,})")
    for k in ["true", "false", "unsure"]:
        correct = match_counts[k]
        total_k = gold_counts[k]
        acc_k = (correct / total_k) * 100 if total_k else 0
        print(f"    - {k:<6} accuracy       : {acc_k:.1f}% ({correct:,}/{total_k:,})")

    # Clean up temporary test directories
    shutil.rmtree(sim_dir, ignore_errors=True)
    shutil.rmtree(out_dir, ignore_errors=True)
    return True


def main():
    print("=" * 65)
    print("  HYPE ARENA - END-TO-END COMPETITION SIMULATION BENCHMARK")
    print("  Tests: Step-5 & GLM-5.3 (18,000 unlabelled samples each)")
    print("=" * 65)

    t_start = time.time()
    # 1. Benchmark on Step-5 Dataset
    ok1 = run_benchmark_for_dataset(
        "step5",
        "sample_label_step5.csv",
        "data/ground_truth_step5.csv"
    )

    # 2. Benchmark on GLM-5.3 Dataset
    ok2 = run_benchmark_for_dataset(
        "glm5",
        "sample_label_glm5.csv",
        "data/ground_truth_glm5.csv"
    )

    print("\n" + "=" * 65)
    if ok1 and ok2:
        print(f"  [ALL ARENA TESTS COMPLETED SUCCESSFULLY IN {time.time()-t_start:.2f}s!]")
    else:
        print("  [SOME TESTS FAILED]")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
