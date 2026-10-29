"""Frozen five-split, pure-Rust pipeline evaluation; no model search or reserved data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("random", "bundle_group", "template_group", "forward_time", "every_fifth")
LABELS = ["true", "false", "unsure"]
PARAMETERS = dict(n_estimators=120, learning_rate=0.045, max_depth=2,
                  min_samples_leaf=20, subsample=1.0, random_state=417)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path: Path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]


def git(*args) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def snapshot(args, base: Path) -> None:
    """Keep original bytes and source hashes, deriving only workspace membership."""
    integration = args.integration.resolve()
    sources = sorted((integration / "crates/core/src").glob("*.rs"))
    sources += [integration / p for p in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "crates/core/Cargo.toml")]
    manifest = {}
    for source in sources:
        relative = source.relative_to(integration)
        target = base / "current" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        target.write_bytes(content)
        if source.read_bytes() != content:
            raise RuntimeError(f"Concurrent source modification while snapshotting {source}")
        manifest[relative.as_posix()] = dict(source=str(source), sha256=sha(target))
    # Recheck the whole source set after copying, not merely individual files.
    for relative, row in manifest.items():
        if sha(integration / relative) != row["sha256"]:
            raise RuntimeError(f"Source snapshot changed concurrently: {relative}; retry stage")
    for name in ("current", "original"):
        snap = base / name
        if name == "original":
            original_files = git("ls-tree", "-r", "--name-only", "HEAD", "crates/core").decode().splitlines()
            original_files += ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml"]
            original_manifest = {}
            for relative in original_files:
                target = snap / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(git("show", f"HEAD:{relative}"))
                original_manifest[relative] = {"sha256": sha(target), "source": "git HEAD:" + relative}
            write(base / "original-source-sha256.json", original_manifest)
        cargo = snap / "Cargo.toml"
        (snap / "Cargo.toml.original").write_bytes(cargo.read_bytes())
        (snap / "Cargo.lock.original").write_bytes((snap / "Cargo.lock").read_bytes())
        cargo.write_text(re.sub(r'(?m)^members = \[.*\]$', 'members = ["crates/core"]', cargo.read_text(encoding="utf-8")), encoding="utf-8")
        (snap / "data").mkdir(exist_ok=True)
        for relative in ("data/practice.csv", "data/lexicon.json"):
            shutil.copyfile(ROOT / relative, snap / relative)
        examples = snap / "crates/core/examples"
        examples.mkdir(parents=True, exist_ok=True)
        if name == "current":
            shutil.copyfile(ROOT / "crates/core/examples/evaluate_boosted.rs", examples / "evaluate_boosted.rs")
        else:
            shutil.copyfile(ROOT / "tools/verifier_folds/original_rf.rs", examples / "original_rf.rs")
    write(base / "current-source-sha256.json", manifest)
    lab = args.lab.resolve()
    for name in ("train.py", "parity.py", "snapshot.py", "requirements-research.txt"):
        target = base / "lab" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lab / name, target)
    write(base / "lab-source-sha256.json", {p.name: sha(p) for p in (base / "lab").iterdir() if p.is_file()})
    if args.seed_cargo and not (base / "cargo-home/registry").exists():
        shutil.copytree(args.seed_cargo / "registry", base / "cargo-home/registry")


def partition_rows(rows, assignments, split):
    chosen = [a for a in assignments if a["split"] == split]
    by_id = {a["id"]: a["partition"] for a in chosen}
    if len(by_id) != len(chosen) or set(by_id) != {r["id"] for r in rows}:
        raise ValueError(f"{split}: assignments must name every source ID exactly once")
    if set(by_id.values()) != {"train", "test"}:
        raise ValueError(f"{split}: expected nonempty train/test partitions")
    test = [r for r in rows if by_id[r["id"]] == "test"]
    provided = [r for r in rows if by_id[r["id"]] == "train"]
    test_ids = {r["id"] for r in test}
    test_texts = {normalize(r["text"]) for r in test}
    train = [r for r in provided if r["id"] not in test_ids and normalize(r["text"]) not in test_texts]
    if not train:
        raise ValueError(f"{split}: no clean training rows")
    return train, test, provided


def stage(args, base: Path):
    if (base / "protocol.json").exists():
        raise ValueError("Snapshot already exists; use a new --output directory to freeze another source revision")
    base.mkdir(parents=True, exist_ok=True)
    snapshot(args, base)
    practice = ROOT / "data/practice.csv"
    assignments_path = ROOT / "analysis/practice/outputs/split_assignments.csv"
    with practice.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["form"] = json.loads(row["form"] or "[]")
        if row["label"] not in LABELS:
            raise ValueError("Practice labels must be known")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate practice IDs")
    with assignments_path.open(encoding="utf-8-sig", newline="") as f:
        assignments = list(csv.DictReader(f))
    partitions = {}
    for split in SPLITS:
        train, test, provided = partition_rows(rows, assignments, split)
        queries = [dict(id=r["id"], text=r["text"], date=r["date"], label="", form=[]) for r in test]
        fit_folds = {r["id"]: int(hashlib.sha256(normalize(r["text"]).encode()).hexdigest(), 16) % 5 for r in train}
        request = dict(split=split, training=train, queries=queries, fit_folds=fit_folds)
        write(base / "requests" / f"{split}.json", request)
        write(base / "targets" / f"{split}.json", test)
        train_texts = {normalize(r["text"]) for r in train}
        test_texts = {normalize(r["text"]) for r in test}
        partitions[split] = dict(provided_training_rows=len(provided), training_rows=len(train), test_rows=len(test),
            excluded_training_rows=len(provided)-len(train), training_ids=[r["id"] for r in train],
            test_ids=[r["id"] for r in test], normalized_text_overlap=len(train_texts & test_texts),
            id_overlap=len({r["id"] for r in train} & {r["id"] for r in test}),
            parser_fit_fold_counts=[sum(v == i for v in fit_folds.values()) for i in range(5)])
    write(base / "protocol.json", dict(schema_version=1, label_order=LABELS, fixed_parameters=PARAMETERS,
        ablation="no_lexical: no lex.* or cue.*", class_balancing=False, calibration="none",
        selection="Fixed before opening these fold results: original paired390 experiment inner307 validation only; no new search",
        parser="same-engine Rust template extractor only, fit parses crossfit5 by SHA256(NFKC/casefold/whitespace text) modulo 5",
        fit_features="full cleaned training evidence minus query ID and ALL normalized-text copies; supplied train forms allowed",
        prediction="Engine::predict including production graph and confidence overrides; no hints, gold forms, or neural parser",
        source_commit=git("rev-parse", "HEAD").decode().strip(), originalRF="checked-in MVP at source_commit",
        source_manifest_sha256=sha(base / "current-source-sha256.json"),
        data={str(p.relative_to(ROOT)): sha(p) for p in (practice, ROOT / "data/lexicon.json", assignments_path)},
        reserved_worlds_opened=[], partitions=partitions))
    print(json.dumps({s: {k: v for k, v in p.items() if not k.endswith("ids")} for s, p in partitions.items()}, indent=2))


def docker(args, base: Path, command, log_name: str, expected=0):
    relative = base.relative_to(ROOT).as_posix()
    argv = ["docker", "run", "--rm", "--user", "0", "--network", "none", "--cpus", "2", "--memory", "6g",
            "-v", f"{ROOT}:/work", "-w", "/work", "-e", f"CARGO_HOME=/work/{relative}/cargo-home",
            "-e", f"CARGO_TARGET_DIR=/work/{relative}/target", args.image, *command]
    started = time.monotonic()
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
    path = base / "logs" / log_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout + result.stderr, encoding="utf-8")
    record = dict(argv=argv, exit_code=result.returncode, elapsed_seconds=time.monotonic()-started, log=str(path.relative_to(ROOT)))
    with (base / "commands.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
    if result.returncode != expected:
        print(result.stderr[-8000:])
        raise RuntimeError(f"{log_name}: expected exit {expected}, got {result.returncode}")
    return result


def build(args, base):
    rel = base.relative_to(ROOT).as_posix()
    for snap, example in (("current", "evaluate_boosted"), ("original", "original_rf")):
        evaluator = ROOT / ("crates/core/examples/evaluate_boosted.rs" if snap == "current" else "tools/verifier_folds/original_rf.rs")
        shutil.copyfile(evaluator, base / snap / "crates/core/examples" / f"{example}.rs")
        # Core-only workspaces legitimately derive a new lockfile from frozen source manifests.
        docker(args, base, ["cargo", "build", "--offline", "--release", "--manifest-path", f"{rel}/{snap}/Cargo.toml",
                            "-p", "veridyct-core", "--example", example], f"build-{snap}.log")
    write(base / "build-sha256.json", {snap: {
        "derived_manifest_sha256":sha(base / snap / "Cargo.toml"), "derived_lock_sha256":sha(base / snap / "Cargo.lock"),
        "evaluator_sha256":sha(base / snap / "crates/core/examples" / f"{example}.rs"),
        "binary_sha256":sha(base / "target/release/examples" / example)}
        for snap, example in (("current", "evaluate_boosted"), ("original", "original_rf"))})


def export_features(args, base):
    rel = base.relative_to(ROOT).as_posix()
    for split in SPLITS:
        docker(args, base, [f"{rel}/target/release/examples/evaluate_boosted", "features", f"{rel}/requests/{split}.json",
                            "data/lexicon.json", f"{rel}/features/{split}.jsonl"], f"features-{split}.log")


def lab_module(base, name):
    spec = importlib.util.spec_from_file_location(f"frozen_lab_{name}", base / "lab" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signature(row):
    result = 0xcbf29ce484222325
    for byte in "\0".join(row[k] for k in ("id", "date", "label", "text")).encode():
        result = ((result ^ byte) * 0x100000001b3) & ((1 << 64) - 1)
    return f"{result:016x}"


def train(args, base):
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
    import numpy as np
    import sklearn
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.feature_extraction import DictVectorizer
    lab = lab_module(base, "train")
    for split in SPLITS:
        started = time.monotonic()
        request = load(base / "requests" / f"{split}.json")
        features = lines(base / "features" / f"{split}.jsonl")
        fit = [r["row"] for r in features if r["partition"] == "fit"]
        test = [r["row"] for r in features if r["partition"] == "test"]
        training = request["training"]
        if [r["id"] for r in fit] != [r["id"] for r in training]:
            raise AssertionError("Fit order/membership changed")
        vectorizer = DictVectorizer(sparse=False, dtype=np.float32)
        x = vectorizer.fit_transform([lab.select_features(r, "no_lexical") for r in fit])
        y = np.array([LABELS.index(r["label"]) for r in training])
        model = GradientBoostingClassifier(**PARAMETERS)
        model.fit(x, y)
        provenance = dict(training_partition=split, training_ids=[r["id"] for r in training],
            training_row_signatures={r["id"]: signature(r) for r in training},
            training_normalized_text_sha256=[hashlib.sha256(normalize(r["text"]).encode()).hexdigest() for r in training],
            request_sha256=sha(base / "requests" / f"{split}.json"),
            features_sha256=sha(base / "features" / f"{split}.jsonl"),
            feature_source_manifest_sha256=sha(base / "current-source-sha256.json"),
            protocol_sha256=sha(base / "protocol.json"), fixed_parameters=PARAMETERS,
            mode="rust_crossfit5", ablation="no_lexical", normalization="Unicode NFKC, casefold, whitespace collapse",
            selection_partition="original paired390 inner307 only; no tuning on the five evaluated splits",
            class_balancing=False, calibration="none", contains_synthetic_truth=False)
        artifact = lab.export_gbt(model, vectorizer, provenance)
        if any(n.startswith(("lex.", "cue.")) for n in artifact["feature_names"]):
            raise AssertionError("Forbidden lexical feature")
        test_x = vectorizer.transform([lab.select_features(r, "no_lexical") for r in test])
        probabilities = model.predict_proba(test_x)
        portable = lab.predict_portable(artifact, test, "no_lexical")
        error = float(np.max(np.abs(portable - probabilities)))
        if error > 1e-12:
            raise AssertionError(f"sklearn export parity failed: {error}")
        path = base / "models" / f"{split}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
        write(base / "sklearn" / f"{split}.json", [dict(id=r["id"], probabilities=p.tolist()) for r, p in zip(test, probabilities)])
        report = dict(split=split, training_rows=len(fit), feature_count=x.shape[1], model_sha256=sha(path),
            sklearn_portable_probability_max_error=error, seconds=time.monotonic()-started,
            runtime=dict(python=platform.python_version(), numpy=np.__version__, sklearn=sklearn.__version__, threads=2))
        write(base / "training" / f"{split}.json", report)
        print(json.dumps(report), flush=True)


def predict(args, base):
    rel = base.relative_to(ROOT).as_posix()
    (base / "predictions").mkdir(exist_ok=True)
    for split in SPLITS:
        docker(args, base, [f"{rel}/target/release/examples/original_rf", f"{rel}/requests/{split}.json",
                            "data/lexicon.json", f"{rel}/predictions/{split}-originalRF.jsonl"], f"originalRF-{split}.log")
        for name, model in (("currentRF", []), ("newGBT", [f"{rel}/models/{split}.json"])):
            docker(args, base, [f"{rel}/target/release/examples/evaluate_boosted", "predict", f"{rel}/requests/{split}.json",
                                "data/lexicon.json", f"{rel}/predictions/{split}-{name}.jsonl", *model], f"{name}-{split}.log")


def classification(gold, predictions, probabilities):
    import numpy as np
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
    confusion = confusion_matrix(gold, predictions, labels=[0, 1, 2])
    precision, recall, f1, support = precision_recall_fscore_support(gold, predictions, labels=[0, 1, 2], zero_division=0)
    p = np.asarray(probabilities)
    if not np.all(np.isfinite(p)) or np.any(p < 0) or not np.allclose(p.sum(axis=1), 1, atol=1e-12):
        raise AssertionError("Invalid full Engine probabilities")
    return dict(rows=len(gold), correct=int(np.sum(np.asarray(gold) == predictions)),
        accuracy=float(accuracy_score(gold, predictions)), macro_f1=float(f1_score(gold, predictions, labels=[0, 1, 2], average="macro", zero_division=0)),
        coverage=float(np.mean(np.asarray(predictions) != 2)),
        log_loss=float(-np.log(np.clip(p[np.arange(len(gold)), gold], 1e-15, 1)).mean()),
        brier=float(np.mean(np.sum((p - np.eye(3)[gold]) ** 2, axis=1))), confusion=confusion.tolist(),
        per_class={label:dict(support=int(support[i]), predicted=int(confusion[:, i].sum()), precision=float(precision[i]), recall=float(recall[i]), f1=float(f1[i])) for i, label in enumerate(LABELS)})


def report(args, base):
    """First phase to open heldout targets; no subsequent search/refit decisions."""
    import numpy as np
    lab = lab_module(base, "parity")
    protocol = load(base / "protocol.json")
    reports = {}
    for split in SPLITS:
        request = load(base / "requests" / f"{split}.json")
        targets = load(base / "targets" / f"{split}.json")
        if [r["id"] for r in targets] != [r["id"] for r in request["queries"]]:
            raise AssertionError("Target membership changed")
        gold = [LABELS.index(r["label"]) for r in targets]
        training_counts = np.bincount([LABELS.index(r["label"]) for r in request["training"]], minlength=3)
        prior = training_counts / training_counts.sum()
        majority = int(np.argmax(prior))
        split_report = dict(training=protocol["partitions"][split], training_label_counts=training_counts.tolist(),
            majority_probability_policy="empirical cleaned-train class frequencies; majority label from argmax, tie true,false,unsure",
            majority=classification(gold, np.full(len(gold), majority), np.tile(prior, (len(gold), 1))))
        reference = [r["row"] for r in lines(base / "features" / f"{split}.jsonl") if r["partition"] == "test"]
        model = load(base / "models" / f"{split}.json")
        sklearn_rows = load(base / "sklearn" / f"{split}.json")
        parity = dict(feature_max_absolute_error=0.0, logit_max_absolute_error=0.0, probability_max_absolute_error=0.0, sklearn_probability_max_absolute_error=0.0)
        current_facts = None
        for name in ("originalRF", "currentRF", "newGBT"):
            rows = lines(base / "predictions" / f"{split}-{name}.jsonl")
            if [r["id"] for r in rows] != [r["id"] for r in targets]:
                raise AssertionError("Prediction order changed")
            predictions = [LABELS.index(r["prediction"]["label"]) for r in rows]
            probabilities = [[r["prediction"]["probabilities"][label] for label in LABELS] for r in rows]
            result = classification(gold, np.asarray(predictions), probabilities)
            result["prediction_sha256"] = sha(base / "predictions" / f"{split}-{name}.jsonl")
            result["errors"] = [dict(id=g["id"], text=g["text"], gold=g["label"], predicted=r["prediction"]["label"], facts=r["prediction"]["facts"], reason=r["prediction"]["reason"]) for g, r in zip(targets, rows) if g["label"] != r["prediction"]["label"]]
            if name == "currentRF":
                current_facts = [r["prediction"]["facts"] for r in rows]
                if any(r["prediction"] != f["baseline"] for r, f in zip(rows, reference)):
                    raise AssertionError("CurrentRF changed from frozen feature export")
            if name == "newGBT":
                if [r["prediction"]["facts"] for r in rows] != current_facts:
                    raise AssertionError("GBT altered the parser")
                train_ids = set(model["provenance"]["training_ids"])
                test_ids = {r["id"] for r in targets}
                test_text_hashes = {hashlib.sha256(normalize(r["text"]).encode()).hexdigest() for r in targets}
                if train_ids & test_ids or set(model["provenance"]["training_normalized_text_sha256"]) & test_text_hashes:
                    raise AssertionError("Artifact partition leakage")
                raw_probabilities = []
                for reference_row, actual, sklearn_row in zip(reference, rows, sklearn_rows):
                    if reference_row["features"].keys() != actual["features"].keys():
                        raise AssertionError("Features changed")
                    feature_error = max((abs(v-actual["features"][k]) for k, v in reference_row["features"].items()), default=0)
                    logits = lab.logits(model, actual["features"])
                    exp = np.exp(logits - max(logits))
                    raw = exp / exp.sum()
                    if int(np.argmax(raw)) != int(np.argmax(actual["boosted_scores"])) or int(np.argmax(raw)) != int(np.argmax(sklearn_row["probabilities"])):
                        raise AssertionError("Portable classifier labels differ")
                    raw_probabilities.append(raw)
                    for key, error in (("feature_max_absolute_error", feature_error),
                        ("logit_max_absolute_error", np.max(np.abs(logits-actual["boosted_logits"]))),
                        ("probability_max_absolute_error", np.max(np.abs(raw-actual["boosted_scores"]))),
                        ("sklearn_probability_max_absolute_error", np.max(np.abs(raw-sklearn_row["probabilities"])) )):
                        parity[key] = max(parity[key], float(error))
                if parity["feature_max_absolute_error"] != 0 or any(v > 1e-12 for v in parity.values()):
                    raise AssertionError(f"Portable parity failed: {parity}")
                parity.update(predicted_classes_identical=True, rows=len(rows), training_test_id_overlap=0, training_test_normalized_text_overlap=0)
                raw_predictions = np.argmax(raw_probabilities, axis=1)
                result["raw_fallback_diagnostic"] = classification(gold, raw_predictions, raw_probabilities)
                result["routing_changed_raw_argmax"] = int(np.sum(raw_predictions != predictions))
                result["model_sha256"] = sha(base / "models" / f"{split}.json")
                result["parity"] = parity
            split_report[name] = result
        reports[split] = split_report
    commands = lines(base / "commands.jsonl")
    cpuinfo = subprocess.check_output(["docker", "run", "--rm", "--user", "0", "--network", "none", args.image, "cat", "/proc/cpuinfo"], text=True)
    hardware = next((s.split(":", 1)[1].strip() for s in cpuinfo.splitlines() if s.startswith("model name")), platform.processor())
    summary = dict(schema_version=1, protocol=protocol, label_order=LABELS,
        confusion_orientation="rows gold, columns predicted", brier_definition="mean over rows of sum over three classes (p-y)^2",
        log_loss_clip=1e-15, macro_f1_policy="all three labels, undefined class F1 zero", splits=reports,
        runtime=dict(hardware=hardware, host_processor=platform.processor(), rust_image=args.image,
            image_id=subprocess.check_output(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"], text=True).strip(),
            cpu_limit=2, memory_limit="6g", network="none", rust_compute_threads=1, commands=commands),
        independent_final_evaluation=False,
        limitations=["Practice-derived folds, with overlapping facts; fixed model selection used a separate practice partition and is not independent of every fold's examples.",
                    "No neural parser is used; pure Rust extraction quality remains a bottleneck.",
                    "Fit parser crossfitting uses 80% of each cleaned train partition versus full train for outer prediction.",
                    "No calibration fit or hyperparameter retuning was performed; Engine graph scores retain production heuristics.",
                    "No sealed or fresh synthetic world was opened."])
    write(base / "results.json", summary)
    artifact_files = [p for folder in ("models", "features", "requests", "targets", "predictions", "training", "sklearn", "guards") for p in (base / folder).rglob("*") if p.is_file()]
    artifact_files += [base / name for name in ("protocol.json", "results.json", "build-sha256.json", "current-source-sha256.json", "original-source-sha256.json", "lab-source-sha256.json", "verification.json", "error-audit.json") if (base / name).exists()]
    write(base / "artifact-sha256.json", {p.relative_to(base).as_posix():sha(p) for p in sorted(artifact_files)})
    harness = base / "harness"
    harness.mkdir(exist_ok=True)
    for p in (ROOT / "tools/verifier_folds").iterdir():
        if p.is_file():
            shutil.copyfile(p, harness / p.name)
    shutil.copyfile(ROOT / "crates/core/examples/evaluate_boosted.rs", harness / "evaluate_boosted.rs")
    write(base / "harness-sha256.json", {p.name:sha(p) for p in harness.iterdir() if p.is_file()})
    for split, values in reports.items():
        print(split, json.dumps({name: {k: row[k] for k in ("correct", "accuracy", "macro_f1", "coverage", "log_loss", "brier")} for name, row in values.items() if name in ("majority", "originalRF", "currentRF", "newGBT")}))


def guards(args, base):
    rel = base.relative_to(ROOT).as_posix()
    output = base / "guards" / "should-not-exist.jsonl"
    output.parent.mkdir(exist_ok=True)
    if output.exists():
        raise AssertionError("Guard output already exists; choose new output to recheck")
    binary = f"{rel}/target/release/examples/evaluate_boosted"
    request_path = f"{rel}/requests/random.json"
    mismatched = docker(args, base, [binary, "predict", request_path, "data/lexicon.json",
        f"{rel}/guards/should-not-exist.jsonl", f"{rel}/models/bundle_group.json"], "guard-wrong-partition.log", expected=2)
    if output.exists() or "does not match" not in mismatched.stderr:
        raise AssertionError("Wrong partition was not rejected before output creation")
    request = load(base / "requests/random.json")
    request["queries"][0]["label"] = "true"
    write(base / "guards" / "labelled-query.json", request)
    labelled = docker(args, base, [binary, "predict", f"{rel}/guards/labelled-query.json", "data/lexicon.json",
        f"{rel}/guards/should-not-exist.jsonl", f"{rel}/models/random.json"], "guard-labelled-query.log", expected=2)
    if output.exists() or "must be blank" not in labelled.stderr:
        raise AssertionError("Labelled query was not rejected before output creation")
    write(base / "guards" / "results.json", dict(wrong_partition_rejected_before_output=True, labelled_query_rejected_before_output=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["stage", "build", "features", "train", "predict", "report", "guards", "all"])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verifier-folds")
    parser.add_argument("--integration", type=Path, default=ROOT.parent / "evidence-graph-runtime")
    parser.add_argument("--lab", type=Path, default=ROOT.parent / "evidence-graph-runtime/tools/verifier_lab")
    parser.add_argument("--seed-cargo", type=Path)
    parser.add_argument("--image", default="veridyct:dev")
    arguments = parser.parse_args()
    destination = arguments.output.resolve()
    destination.relative_to(ROOT)  # Mounts and outputs must remain in this isolated checkout.
    phases = ("stage", "build", "features", "train", "predict", "guards", "report") if arguments.phase == "all" else [arguments.phase]
    functions = dict(stage=stage, build=build, features=export_features, train=train, predict=predict, report=report, guards=guards)
    for phase in phases:
        if phase not in ("stage",):
            protocol = load(destination / "protocol.json")
            for relative, expected in protocol["data"].items():
                if sha(ROOT / relative) != expected:
                    raise RuntimeError(f"Input data changed after staging: {relative}")
            for kind in ("current", "original"):
                for relative, info in load(destination / f"{kind}-source-sha256.json").items():
                    path = destination / kind / relative
                    if relative in ("Cargo.toml", "Cargo.lock"):
                        path = path.with_name(path.name + ".original")
                    if sha(path) != info["sha256"]:
                        raise RuntimeError(f"Frozen source changed: {path}")
        functions[phase](arguments, destination)
