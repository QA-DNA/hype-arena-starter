"""Check Rust feature/logit/probability parity and explicit partition exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

import numpy as np


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def logits(model, features):
    result = [float(x) for x in model["initial_logits"]]
    for tree in model["trees"]:
        node_index = 0
        while True:
            node = tree["nodes"][node_index]
            if node["leaf"]:
                result[tree["class"]] += model["learning_rate"] * node["value"]
                break
            value = float(np.float32(features.get(model["feature_names"][node["feature"]], 0.0)))
            node_index = node["left"] if value <= node["threshold"] else node["right"]
    return np.array(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--reference-features", type=Path, required=True)
    parser.add_argument("--rust-output", type=Path, required=True)
    parser.add_argument("--test-targets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = json.loads(args.model.read_text(encoding="utf-8"))
    reference = read_jsonl(args.reference_features)
    actual = read_jsonl(args.rust_output)
    if len(reference) != len(actual):
        raise AssertionError("Different Rust output length")
    max_feature_error = max_logit_error = max_probability_error = 0.0
    predictions_equal = True
    for expected, rust in zip(reference, actual):
        if expected["id"] != rust["id"]:
            raise AssertionError("Rust row order changed")
        if expected["features"].keys() != rust["features"].keys():
            raise AssertionError("Rust feature names changed")
        feature_error = max((abs(value - rust["features"][key]) for key, value in expected["features"].items()), default=0.0)
        max_feature_error = max(max_feature_error, feature_error)
        expected_logits = logits(model, expected["features"])
        exp = np.exp(expected_logits - np.max(expected_logits))
        probabilities = exp / np.sum(exp)
        max_logit_error = max(max_logit_error, float(np.max(np.abs(expected_logits - rust["boosted_logits"]))))
        max_probability_error = max(max_probability_error, float(np.max(np.abs(probabilities - rust["boosted_scores"]))))
        predictions_equal &= int(np.argmax(probabilities)) == int(np.argmax(rust["boosted_scores"]))
    targets = json.loads(args.test_targets.read_text(encoding="utf-8"))
    target_ids = {row["id"] for row in targets}
    target_text_hashes = {hashlib.sha256(" ".join(unicodedata.normalize("NFKC", row["text"]).casefold().split()).encode()).hexdigest() for row in targets}
    overlap_ids = set(model["provenance"]["training_ids"]) & target_ids
    overlap_texts = set(model["provenance"]["training_normalized_text_sha256"]) & target_text_hashes
    if max_feature_error != 0.0 or max_logit_error > 1e-12 or max_probability_error > 1e-12 or not predictions_equal or overlap_ids or overlap_texts:
        raise AssertionError(f"Rust/model parity or partition exclusion failed: feature={max_feature_error} logit={max_logit_error} probability={max_probability_error} classes_equal={predictions_equal} overlap_ids={overlap_ids} overlap_texts={overlap_texts}")
    result = {"rows":len(actual),"model_sha256":hashlib.sha256(args.model.read_bytes()).hexdigest(),"feature_max_absolute_error":max_feature_error,"logit_max_absolute_error":max_logit_error,"probability_max_absolute_error":max_probability_error,"predicted_classes_identical":predictions_equal,"training_ids_overlapping_test":sorted(overlap_ids),"training_normalized_text_hashes_overlapping_test":sorted(overlap_texts),"passed":True}
    args.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
