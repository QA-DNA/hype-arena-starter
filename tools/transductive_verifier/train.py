"""Fixed-parameter paired GBT ablations; public gold is scoring-only for outer rows."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import unicodedata

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
import numpy as np
import sklearn
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import confusion_matrix, f1_score, log_loss

LABELS = ["true", "false", "unsure"]
SPLITS = ["random", "bundle_group", "template_group", "forward_time", "every_fifth"]
ABLATIONS = ["baseline", "global", "temporal", "statistics_only"]
PARAMETERS = {"n_estimators": 120, "learning_rate": 0.045, "max_depth": 2, "min_samples_leaf": 20,
              "subsample": 1.0, "random_state": 417}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def selected(features: dict, ablation: str) -> dict:
    if ablation not in ABLATIONS:
        raise ValueError(ablation)
    base = {k: v for k, v in features.items() if not k.startswith(("lex.", "cue.", "stat."))}
    statistics = {k: v for k, v in features.items() if k.startswith("stat.")}
    if ablation == "baseline":
        return base
    if ablation == "global":
        return base | {k: v for k, v in statistics.items() if ".global." in k}
    if ablation == "temporal":
        return base | statistics
    return statistics


def metrics(y: np.ndarray, probs: np.ndarray) -> dict:
    predictions = probs.argmax(axis=1)
    confusion = confusion_matrix(y, predictions, labels=[0, 1, 2])
    ece = 0.0
    confidence = probs.max(axis=1)
    for low in np.linspace(0, 0.9, 10):
        included = (confidence > low) & (confidence <= low + 0.1 + 1e-15)
        if included.any():
            ece += float(included.mean() * abs((predictions[included] == y[included]).mean() - confidence[included].mean()))
    return {"rows": len(y), "correct": int((predictions == y).sum()), "accuracy": float((predictions == y).mean()),
            "macro_f1": float(f1_score(y, predictions, labels=[0, 1, 2], average="macro", zero_division=0)),
            "log_loss": float(log_loss(y, probs, labels=[0, 1, 2])), "brier": float(np.mean(np.sum((probs - np.eye(3)[y]) ** 2, axis=1))),
            "ece_10_bins_descriptive": ece, "confusion": confusion.tolist(),
            "recall": {LABELS[c]: float(confusion[c, c] / max(1, confusion[c].sum())) for c in range(3)}}


def signature(row: dict) -> str:
    value = 0xcbf29ce484222325
    for byte in "\0".join(row[k] for k in ("id", "date", "label", "text")).encode():
        value = ((value ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
    return f"{value:016x}"


def provenance(request: dict) -> dict:
    rows = request["training"]
    return {"training_ids": [r["id"] for r in rows], "training_row_signatures": {r["id"]: signature(r) for r in rows},
            "training_normalized_text_sha256": [hashlib.sha256(" ".join(unicodedata.normalize("NFKC", r["text"]).casefold().split()).encode()).hexdigest() for r in rows],
            "feature_training": "five fresh pure-Rust text-hash crossfit folds, query fold excluded from extractor and labelled evidence",
            "outer_queries": "fresh pure-Rust extraction from complete cleaned outer training partition",
            "unlabelled_corpus": "all public practice texts with labels and supplied gold forms cleared",
            "statistical_estimates_only": True, "accepted_evidence_modified": False, "independent_final_evaluation": False}


def export(model, vectorizer, source: dict) -> dict:
    initial = model._raw_predict_init(np.zeros((1, len(vectorizer.feature_names_)), dtype=np.float32))[0].tolist()
    trees = []
    for estimators in model.estimators_:
        for c, estimator in enumerate(estimators):
            tree = estimator.tree_
            nodes = []
            for i in range(tree.node_count):
                nodes.append({"feature": int(max(0, tree.feature[i])), "threshold": float(tree.threshold[i]),
                              "left": int(max(0, tree.children_left[i])), "right": int(max(0, tree.children_right[i])),
                              "value": float(tree.value[i, 0, 0]), "leaf": bool(tree.children_left[i] == -1)})
            trees.append({"class": c, "nodes": nodes})
    return {"schema_version": 1, "labels": LABELS, "feature_names": vectorizer.feature_names_, "initial_logits": initial,
            "learning_rate": model.learning_rate, "trees": trees, "provenance": source}


def portable(artifact: dict, rows: list[dict]) -> np.ndarray:
    result = []
    for row in rows:
        values = row["features"]
        logits = np.array(artifact["initial_logits"])
        for tree in artifact["trees"]:
            i = 0
            while True:
                node = tree["nodes"][i]
                if node["leaf"]:
                    logits[tree["class"]] += artifact["learning_rate"] * node["value"]
                    break
                value = float(np.float32(values.get(artifact["feature_names"][node["feature"]], 0.0)))
                i = node["left"] if value <= node["threshold"] else node["right"]
        scores = np.exp(logits - logits.max())
        result.append(scores / scores.sum())
    return np.array(result)


def tuple_set(facts: list[dict]) -> set[str]:
    return {json.dumps(f, sort_keys=True, ensure_ascii=False) for f in facts}


def numeric_spelling_set(facts: list[dict]) -> set[str]:
    """Scoring only: decimal-equivalent numbers; dimensions/versions unchanged."""
    def canonical(value):
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return {"numeric_spelling": str(Decimal(str(value)).normalize())}
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    return {json.dumps(canonical(f), sort_keys=True, ensure_ascii=False) for f in facts}


def run(args) -> None:
    started = time.monotonic()
    base = args.directory
    report = {"fixed_parameters": PARAMETERS, "labels": LABELS, "selection": "Predeclared ablations and existing GBT parameters; no outer-driven tuning or model selection",
              "claims": "Statistical estimates only; never accepted evidence or generation proof; no independent sealed evaluation",
              "source_sha256": sha(base / "source-sha256.json"), "stage_audit_sha256": sha(base / "stage-audit.json"),
              "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "threads": 2}, "splits": {}}
    for split in args.splits.split(","):
        train_path = base / "features" / f"{split}-train.jsonl"
        test_path = base / "features" / f"{split}-test.jsonl"
        train = sorted(load(train_path), key=lambda r: r["id"])
        test = load(test_path)
        request = json.loads((base / "inputs" / f"{split}.json").read_text(encoding="utf-8"))
        target = json.loads((base / "targets" / f"{split}.json").read_text(encoding="utf-8"))
        targets = {r["id"]: r for r in target["training"] + target["test"]}
        y_train = np.array([LABELS.index(targets[r["id"]]["label"]) for r in train])
        if sorted(set(y_train)) != [0, 1, 2]:
            raise ValueError("All three training classes are required")
        y_test = np.array([LABELS.index(targets[r["id"]]["label"]) for r in test])
        if {r["id"] for r in train} != {r["id"] for r in request["training"]}:
            raise ValueError("Crossfit training IDs do not match the partition")
        if [r["id"] for r in test] != [r["id"] for r in request["queries"]]:
            raise ValueError("Test IDs/order mismatch")
        measurements = {"training": len(train), "test": len(test), "inputs_sha256": {str(p): sha(p) for p in (train_path, test_path)}, "ablations": {}}
        all_probs = {}
        manifests = {}
        for ablation in ABLATIONS:
            vectorizer = DictVectorizer(sparse=False, dtype=np.float32)
            x_train = vectorizer.fit_transform([selected(r["features"], ablation) for r in train])
            x_test = vectorizer.transform([selected(r["features"], ablation) for r in test])
            if not np.isfinite(x_train).all() or not np.isfinite(x_test).all():
                raise ValueError("Nonfinite feature")
            model = GradientBoostingClassifier(**PARAMETERS)
            model.fit(x_train, y_train)
            probabilities = model.predict_proba(x_test)
            all_probs[ablation] = probabilities
            artifact = export(model, vectorizer, provenance(request) | {"ablation": ablation, "split": split, "parameters": PARAMETERS,
                "source_manifest_sha256": report["source_sha256"], "feature_input_sha256": measurements["inputs_sha256"]})
            max_error = float(np.max(np.abs(portable(artifact, test) - probabilities)))
            if max_error > 1e-10:
                raise AssertionError(f"Python portable probability parity: {max_error}")
            path = base / "models" / f"{split}-{ablation}.json"
            write(path, artifact)
            manifests[ablation] = (Path("/work") / path).as_posix() if not path.is_absolute() else path.as_posix()
            score = metrics(y_test, probabilities)
            score.update({"features": len(vectorizer.feature_names_), "model_sha256": sha(path), "python_portable_probability_max_error": max_error,
                          "top_features": sorted(zip(vectorizer.feature_names_, model.feature_importances_.tolist()), key=lambda p: p[1], reverse=True)[:20]})
            measurements["ablations"][ablation] = score
            print(json.dumps({"split": split, "ablation": ablation, "correct": score["correct"], "accuracy": score["accuracy"],
                              "macro_f1": score["macro_f1"], "log_loss": score["log_loss"], "recall": score["recall"]}), flush=True)
        write(base / "model-manifests" / f"{split}.json", manifests)
        base_right = all_probs["baseline"].argmax(axis=1) == y_test
        for ablation in ABLATIONS[1:]:
            right = all_probs[ablation].argmax(axis=1) == y_test
            measurements["ablations"][ablation]["paired_against_baseline"] = {"improved": int((right & ~base_right).sum()), "regressed": int((~right & base_right).sum())}
        cover = np.array([r["features"].get("stat.atom.max.global.families", 0.0) > 0 for r in test])
        exact = np.array([tuple_set(r["feature_facts"]) == tuple_set(targets[r["id"]]["form"]) for r in test])
        numeric_equivalent = np.array([numeric_spelling_set(r["feature_facts"]) == numeric_spelling_set(targets[r["id"]]["form"]) for r in test])
        empty = np.array([not r["feature_facts"] for r in test])
        measurements["extraction"] = {"empty": int(empty.sum()), "exact": int(exact.sum()), "exact_fraction": float(exact.mean()),
                                      "exact_definition": "literal JSON tuples; numeric spelling differences count as different",
                                      "numeric_spelling_equivalent_exact": int(numeric_equivalent.sum()), "numeric_spelling_equivalent_fraction": float(numeric_equivalent.mean()),
                                      "eligible_vote_rows": int(cover.sum()), "near30_conflict_rows": sum(r["features"].get("stat.atom.max.near30.ambiguity", 0) > 0 for r in test)}
        measurements["slices"] = {}
        for name, mask in [("empty_parse", empty), ("incorrect_parse", ~exact), ("exact_parse", exact), ("eligible_votes", cover), ("no_eligible_votes", ~cover)]:
            measurements["slices"][name] = {a: metrics(y_test[mask], p[mask]) for a, p in all_probs.items()} if mask.any() else {"rows": 0}
        records = []
        for i, row in enumerate(test):
            records.append({"id": row["id"], "text": row["text"], "date": row["date"], "gold": LABELS[y_test[i]], "gold_form": targets[row["id"]]["form"],
                            "inferred_form": row["feature_facts"], "parser_exact": bool(exact[i]), "parser_numeric_spelling_equivalent": bool(numeric_equivalent[i]), "eligible_votes": bool(cover[i]), "family": row["family"],
                            "probabilities": {a: p[i].tolist() for a, p in all_probs.items()},
                            "predictions": {a: LABELS[int(p[i].argmax())] for a, p in all_probs.items()},
                            "cluster": {k: v for k, v in row["features"].items() if k.startswith("stat.atom.mean.")}})
        write(base / "predictions" / f"{split}.json", records)
        report["splits"][split] = measurements
        write(base / "report.json", report)
    report["split_mean_accuracy"] = {a: float(np.mean([v["ablations"][a]["accuracy"] for v in report["splits"].values()])) for a in ABLATIONS}
    report["split_mean_macro_f1"] = {a: float(np.mean([v["ablations"][a]["macro_f1"] for v in report["splits"].values()])) for a in ABLATIONS}
    report["seconds"] = time.monotonic() - started
    write(base / "report.json", report)
    print(json.dumps({k: report[k] for k in ("split_mean_accuracy", "split_mean_macro_f1", "seconds")}, indent=2), flush=True)


def parity(args) -> None:
    base = args.directory
    checks = {}
    for split in args.splits.split(","):
        expected = json.loads((base / "predictions" / f"{split}.json").read_text(encoding="utf-8"))
        actual = load(base / "rust-scores" / f"{split}.jsonl")
        if [r["id"] for r in expected] != [r["id"] for r in actual]:
            raise ValueError("Rust score IDs/order mismatch")
        checks[split] = {}
        for a in ABLATIONS:
            p = np.array([r["probabilities"][a] for r in expected])
            q = np.array([r["probabilities"][a] for r in actual])
            error = float(np.max(np.abs(p - q)))
            if error > 1e-10 or not (p.argmax(axis=1) == q.argmax(axis=1)).all():
                raise AssertionError(f"Rust portable parity {split}/{a}: {error}")
            checks[split][a] = {"probability_max_error": error, "verdict_equality": True, "partition_guard_executed": True}
    write(base / "rust-parity.json", checks)
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/transductive-verifier"))
    parser.add_argument("--splits", default=",".join(SPLITS))
    parser.add_argument("--parity", action="store_true")
    args = parser.parse_args()
    parity(args) if args.parity else run(args)
