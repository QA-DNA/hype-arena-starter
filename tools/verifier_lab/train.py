"""Fit on partition-local features; select on inner validation, report outer diagnostic."""
from __future__ import annotations

import argparse
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
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

LABELS = ["true", "false", "unsure"]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition_provenance(base: Path, name: str, mode: str) -> dict:
    path = base / "inputs" / f"{name}-{mode}.json"
    request = json.loads(path.read_text(encoding="utf-8"))
    rows = request["training"]
    normalized = [" ".join(unicodedata.normalize("NFKC", row["text"]).casefold().split()) for row in rows]
    def signature(row):
        value = 0xcbf29ce484222325
        for byte in "\0".join([row["id"],row["date"],row["label"],row["text"]]).encode():
            value = ((value ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
        return f"{value:016x}"
    return {"training_ids": [row["id"] for row in rows], "training_normalized_text_sha256": [hashlib.sha256(text.encode()).hexdigest() for text in normalized], "training_row_signatures": {row["id"]: signature(row) for row in rows}, "normalization": "Unicode NFKC, casefold, whitespace collapse", "request_sha256": sha(path), "synthetic_facts_in_production_evidence": False}


def metrics(y, probabilities) -> dict:
    predicted = np.argmax(probabilities, axis=1)
    return {"rows": len(y), "correct": int(np.sum(predicted == y)),
            "accuracy": float(accuracy_score(y, predicted)),
            "macro_f1": float(f1_score(y, predicted, labels=[0, 1, 2], average="macro", zero_division=0)),
            "balanced_accuracy": float(recall_score(y, predicted, labels=[0, 1, 2], average="macro", zero_division=0)),
            "log_loss": float(log_loss(y, probabilities, labels=[0, 1, 2])),
            "confusion": confusion_matrix(y, predicted, labels=[0, 1, 2]).tolist()}


def target_labels(base: Path, partition: str, rows: list[dict]) -> np.ndarray:
    labels = {r["id"]: r["label"] for r in json.loads((base / "targets" / f"{partition}.json").read_text(encoding="utf-8"))}
    return np.array([LABELS.index(labels[r["id"]]) for r in rows], dtype=np.int64)


def select_features(row: dict, ablation: str) -> dict:
    result = row["features"]
    if ablation == "all":
        return result
    if ablation == "evidence":
        return {k: v for k, v in result.items() if k.startswith("atom.") or k in ("row.facts", "row.empty", "row.distinct_properties")}
    if ablation == "no_lexical":
        return {k: v for k, v in result.items() if not k.startswith(("lex.", "cue."))}
    if ablation == "lexical":
        return {k: v for k, v in result.items() if k.startswith(("lex.", "cue.", "row."))}
    if ablation == "no_property_priors":
        return {k: v for k, v in result.items() if "property.label" not in k and not k.startswith(("slot.", "subject.", "attribute."))}
    raise ValueError(ablation)


def candidates():
    for depth in (2, 3):
        for leaf in (8, 20):
            yield f"gbt-d{depth}-l{leaf}", GradientBoostingClassifier(n_estimators=120, learning_rate=0.045, max_depth=depth, min_samples_leaf=leaf, subsample=1.0, random_state=417)
    for leaf in (4, 12):
        yield f"rf-l{leaf}", RandomForestClassifier(n_estimators=256, max_depth=12, min_samples_leaf=leaf, max_features=0.5, random_state=417, n_jobs=2)
        yield f"extra-l{leaf}", ExtraTreesClassifier(n_estimators=256, max_depth=12, min_samples_leaf=leaf, max_features=0.7, random_state=417, n_jobs=2)
    for c in (0.03, 0.3):
        yield f"logistic-c{c}", make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=1200, random_state=417))


def export_gbt(model, vectorizer: DictVectorizer, provenance: dict) -> dict:
    # sklearn's multiclass exponential loss uses the log-prior initial estimator.
    zero = np.zeros((1, len(vectorizer.feature_names_)), dtype=np.float32)
    initial = model._raw_predict_init(zero)[0].tolist()
    trees = []
    for iteration in model.estimators_:
        for class_index, estimator in enumerate(iteration):
            tree = estimator.tree_
            nodes = []
            for i in range(tree.node_count):
                leaf = tree.children_left[i] == -1
                nodes.append({"feature": int(max(0, tree.feature[i])), "threshold": float(tree.threshold[i]),
                              "left": int(max(0, tree.children_left[i])), "right": int(max(0, tree.children_right[i])),
                              "value": float(tree.value[i, 0, 0]), "leaf": bool(leaf)})
            trees.append({"class": class_index, "nodes": nodes})
    return {"schema_version": 1, "labels": LABELS, "feature_names": vectorizer.feature_names_,
            "initial_logits": initial, "learning_rate": model.learning_rate,
            "trees": trees, "provenance": provenance}


def predict_portable(model: dict, rows: list[dict], ablation: str) -> np.ndarray:
    result = []
    for row in rows:
        features = select_features(row, ablation)
        logits = np.array(model["initial_logits"])
        for tree in model["trees"]:
            index = 0
            while True:
                node = tree["nodes"][index]
                if node["leaf"]:
                    logits[tree["class"]] += model["learning_rate"] * node["value"]
                    break
                value = float(np.float32(features.get(model["feature_names"][node["feature"]], 0.0)))
                index = node["left"] if value <= node["threshold"] else node["right"]
        exp = np.exp(logits - max(logits))
        result.append(exp / sum(exp))
    return np.array(result)


def run(args):
    base = args.directory
    feature_base = args.features or base / "features"
    started = time.monotonic()
    partitions = {name: load(feature_base / f"{name}-{args.mode}.jsonl") for name in ("fit", "validation", "refit", "practice390")}
    labels = {name: target_labels(base, name, rows) for name, rows in partitions.items()}
    comparisons = []
    trained = {}
    for ablation in ([] if args.reuse_grid else args.ablations.split(",")):
        vectorizer = DictVectorizer(sparse=False, dtype=np.float32)
        x = vectorizer.fit_transform([select_features(r, ablation) for r in partitions["fit"]])
        validation_x = vectorizer.transform([select_features(r, ablation) for r in partitions["validation"]])
        for name, model in candidates():
            model.fit(x, labels["fit"])
            score = metrics(labels["validation"], model.predict_proba(validation_x))
            key = ablation + "/" + name
            comparisons.append({"candidate": key, "validation": score})
            trained[key] = (model, vectorizer)
            print(json.dumps(comparisons[-1]), flush=True)
    if args.reuse_grid:
        raw_log = args.reuse_grid.read_bytes()
        for line in raw_log.decode("utf-16" if raw_log.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig").splitlines():
            if line.startswith('{"candidate":'):
                comparisons.append(json.loads(line))
        if not comparisons:
            raise ValueError("No candidate measurements in grid log")
    suffix = "-" + args.tag if args.tag else ""
    (base / f"grid-{args.mode}{suffix}.json").write_text(json.dumps(comparisons, indent=2), encoding="utf-8")
    # No outer diagnostic outcome influences candidate selection.
    comparisons.sort(key=lambda r: (r["validation"]["accuracy"], r["validation"]["macro_f1"], -r["validation"]["log_loss"]), reverse=True)
    winner = comparisons[0]["candidate"]
    best_tree = next(row["candidate"] for row in comparisons if "/gbt-" in row["candidate"])
    report = {"mode": args.mode, "label_order": LABELS, "selection": "inner validation accuracy; tie macro-F1 then log loss", "independent_final_evaluation": False,
              "outer_evaluation_status": "diagnostic only; parser selection already exposed these rows", "winner": winner, "best_portable_gbt": best_tree,
              "candidates": comparisons, "runtime": {"sklearn": sklearn.__version__, "numpy": np.__version__, "python": platform.python_version(), "threads": 2},
              "inputs": {str(feature_base / f"{name}-{args.mode}.jsonl"): sha(feature_base / f"{name}-{args.mode}.jsonl") for name in partitions}}
    exported = {}
    for key in dict.fromkeys([winner, best_tree]):
        ablation, _ = key.split("/", 1)
        model = dict(candidates())[key.split("/", 1)[1]]
        vectorizer = DictVectorizer(sparse=False, dtype=np.float32)
        x = vectorizer.fit_transform([select_features(r, ablation) for r in partitions["refit"]])
        model.fit(x, labels["refit"])
        outer_x = vectorizer.transform([select_features(r, ablation) for r in partitions["practice390"]])
        probabilities = model.predict_proba(outer_x)
        report.setdefault("refit_models", {})[key] = metrics(labels["practice390"], probabilities)
        if isinstance(model, GradientBoostingClassifier):
            source_manifest = args.source_manifest or base / "baseline-source.json"
            artifact = export_gbt(model, vectorizer, {"training_partition": "1507 practice rows excluding paired390 IDs and normalized texts", "selection_partition": "inner validation only", "mode": args.mode, "ablation": ablation, "features_input_hashes": report["inputs"], "feature_source_manifest_sha256": sha(source_manifest), "contains_synthetic_truth_evidence": False, **partition_provenance(base,"refit",args.mode)})
            portable = predict_portable(artifact, partitions["practice390"], ablation)
            error = float(np.max(np.abs(portable - probabilities)))
            if error > 1e-10:
                raise AssertionError(f"Portable tree parity failed: {error}")
            report["refit_models"][key]["python_portable_max_probability_error"] = error
            model_path = base / "models" / f"{args.mode}-{ablation}-gbt{suffix}.json"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
            exported[key] = {"path": str(model_path), "sha256": sha(model_path), "bytes": model_path.stat().st_size}
        errors = []
        for row, gold, probs in zip(partitions["practice390"], labels["practice390"], probabilities):
            guess = int(np.argmax(probs))
            if guess != gold:
                errors.append({"id": row["id"], "text": row["baseline"]["text"], "gold": LABELS[gold], "predicted": LABELS[guess], "probabilities": probs.tolist(), "facts": row["feature_facts"], "baseline_label": row["baseline"]["label"]})
        report.setdefault("errors", {})[key] = errors
    baseline_probs = np.array([[r["baseline"]["probabilities"][label] for label in LABELS] for r in partitions["practice390"]])
    report["engine_baseline"] = metrics(labels["practice390"], baseline_probs)
    majority = np.argmax(np.bincount(labels["refit"], minlength=3))
    report["majority_baseline"] = metrics(labels["practice390"], np.full((len(labels["practice390"]), 3), 0.01) + np.eye(3)[np.full(len(labels["practice390"]), majority)] * 0.97)
    report["exported"] = exported
    report["seconds"] = time.monotonic() - started
    output = base / f"training-{args.mode}{suffix}.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("winner", "refit_models", "engine_baseline", "majority_baseline", "exported", "seconds")}, indent=2))


def production(args):
    base = args.directory
    selection = json.loads(args.selection_report.read_text(encoding="utf-8"))
    selected = selection["best_portable_gbt"]
    ablation, model_name = selected.split("/", 1)
    rows = load((args.features or base / "features") / "production-inferred.jsonl")
    request = json.loads((base / "inputs/production-inferred.json").read_text(encoding="utf-8"))
    labels = {row["id"]: LABELS.index(row["label"]) for row in request["training"]}
    y = np.array([labels[row["id"]] for row in rows])
    vectorizer = DictVectorizer(sparse=False, dtype=np.float32)
    x = vectorizer.fit_transform([select_features(row, ablation) for row in rows])
    model = dict(candidates())[model_name]
    if not isinstance(model, GradientBoostingClassifier):
        raise TypeError("Production portable model must be the preselected GBT")
    model.fit(x, y)
    source_manifest = args.source_manifest or base / "baseline-source.json"
    artifact = export_gbt(model, vectorizer, {"training_partition": "ALL public practice rows; production only", "evaluation_policy": "NEVER use on any practice holdout split", "selection_report_sha256": sha(args.selection_report), "selected_hyperparameters": selected, "features_input_sha256": sha((args.features or base / "features") / "production-inferred.jsonl"), "feature_source_manifest_sha256": sha(source_manifest), "mode": "inferred", "ablation": ablation, **partition_provenance(base,"production","inferred")})
    probabilities = model.predict_proba(x[:30])
    portable = predict_portable(artifact, rows[:30], ablation)
    error = float(np.max(np.abs(probabilities - portable)))
    if error > 1e-10:
        raise AssertionError(f"Production tree export parity failed: {error}")
    output = base / "models/PRODUCTION-all-practice-gbt.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact,separators=(",",":")), encoding="utf-8")
    report = {"path": str(output), "sha256": sha(output), "bytes": output.stat().st_size, "training_rows": len(rows), "selected_hyperparameters": selected, "evaluation": "No heldout score: all public practice labels used", "python_tree_probability_max_error": error}
    (base / "production-model.json").write_text(json.dumps(report,indent=2), encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/verifier-lab"))
    parser.add_argument("--mode", choices=["inferred", "oracle"], default="inferred")
    parser.add_argument("--ablations", default="all,evidence,no_lexical,lexical,no_property_priors")
    parser.add_argument("--reuse-grid", type=Path, help="Reuse unchanged candidate measurements to repeat export/parity")
    parser.add_argument("--features", type=Path, help="Separate feature directory for a frozen core ablation")
    parser.add_argument("--tag", default="", help="Keep separate model/report files when reusing the selected configuration")
    parser.add_argument("--source-manifest", type=Path, help="Byte hashes of the frozen Rust feature/kernel source")
    parser.add_argument("--production", action="store_true", help="Fit all public practice using the already selected configuration; never evaluate it on holdouts")
    parser.add_argument("--selection-report", type=Path, default=Path("artifacts/verifier-lab/training-inferred.json"))
    arguments = parser.parse_args()
    production(arguments) if arguments.production else run(arguments)
