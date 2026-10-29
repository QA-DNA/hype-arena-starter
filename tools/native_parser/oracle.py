"""Run only frozen Python preprocessing/inference on public parity requests.

Development tool; never copied into the native runtime image.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--requests", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--batch-size", default=48, type=int)
    parser.add_argument("--fixture", type=Path, help="Also save shape-matched 1/7/48 regression fixtures")
    args = parser.parse_args()
    manifest = json.loads((args.root / "provenance.json").read_text(encoding="utf-8"))
    for directory, section in [(args.root / "frozen", "frozen_sources"), (args.root / "model", "bundle")]:
        for name, expected in manifest[section].items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Hash mismatch: {name}")
    sys.path.insert(0, str(args.root / "frozen"))
    from runtime import CpuExtractor, encode_input
    engine = CpuExtractor(args.root / "model", threads=2)
    requests = json.loads(args.requests.read_text(encoding="utf-8"))
    start = time.monotonic()
    encoded = []
    for r in requests:
        try:
            encoded.append(dict(encoded=encode_input(r["text"], r.get("previous_text", ""), engine.meta, engine.grammar, r.get("id", ""))))
        except Exception as error:
            encoded.append(dict(id=r.get("id", ""), error=str(error)))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "python-encoded.json").write_text(json.dumps(encoded, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    def predict(batch_size):
        predictions = [dict(id=r.get("id", ""), form=[], assertions=[]) for r in requests]
        for lo in range(0, len(encoded), batch_size):
            valid = [(i, item["encoded"]) for i, item in enumerate(encoded[lo:lo+batch_size], lo) if "encoded" in item]
            if valid:
                for (index, _), pred in zip(valid, engine.predict_encoded([r for _, r in valid])):
                    predictions[index] = dict(id=requests[index].get("id", ""), form=[a["atom"] for a in pred], assertions=pred)
            for index in range(lo, min(lo+batch_size, len(encoded))):
                if "error" in encoded[index]:
                    predictions[index]["error"] = encoded[index]["error"]
        return predictions
    predictions = predict(args.batch_size)
    (args.out / "python-predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.fixture:
        by_batch = {str(size): predictions if size == args.batch_size else predict(size) for size in (1, 7, 48)}
        fixture = dict(provenance="Frozen selected-v2 Python 3.11 CPU outputs; shape-matched regression tests, not training material or truth labels",
                       model_sha256=manifest["bundle"]["model.onnx"],
                       oracle_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       rows=[dict(request=r, **e) for r, e in zip(requests, encoded)], predictions_by_batch=by_batch)
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(dict(rows=len(requests), seconds=time.monotonic()-start, batch_size=args.batch_size)))


if __name__ == "__main__":
    main()
