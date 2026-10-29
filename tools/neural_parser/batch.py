"""Fill InputRow forms using the frozen, non-LLM selected-v2 CPU extractor.

The CLI reads/writes JSON arrays. Labels and dates are preserved but never passed
to the network. No training, remote access, gold loading or truth lookup occurs.
"""

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent
MAX_TEXT_CHARS = 65536
MAX_CANDIDATES = 256
MAX_ASSERTIONS = 64


def verify_artifacts(bundle):
    manifest = json.loads((ROOT / "provenance.json").read_text(encoding="utf-8"))
    for directory, key in [(ROOT / "frozen", "frozen_sources"), (Path(bundle), "bundle")]:
        for name, expected in manifest[key].items():
            actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Frozen artifact SHA256 mismatch: {name}")
    return manifest


def load_runtime():
    # Preserve the frozen source bytes and its absolute imports without exposing
    # generic grammar/prepare/runtime modules to the embedding application.
    saved = {name: sys.modules.get(name) for name in ("grammar", "prepare", "runtime")}
    try:
        for name in saved:
            spec = importlib.util.spec_from_file_location(name, ROOT / "frozen" / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return sys.modules["runtime"]
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def practice_forms(path):
    """Reuse only literal public practice texts whose forms are unambiguous."""
    if path is None:
        return {}, set()
    result, conflicts = {}, set()
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            form = json.loads(row["form"])
            if not isinstance(form, list):
                raise ValueError("Practice form must be an array")
            text = row["text"]
            if text in result and result[text] != form:
                conflicts.add(text)
            result[text] = form
    for text in conflicts:
        result.pop(text, None)
    return result, conflicts


class BatchExtractor:
    """Reusable model session; callers should serialize calls on one instance."""

    def __init__(self, bundle, threads=2, batch_size=48, context="none", practice_csv=None):
        if threads not in (1, 2):
            raise ValueError("CPU threads must be 1 or 2")
        if not 1 <= batch_size <= 64:
            raise ValueError("Batch size must be between 1 and 64")
        if context not in ("none", "previous3text"):
            raise ValueError("Unsupported context policy")
        self.provenance = verify_artifacts(bundle)
        self.runtime = load_runtime()
        self.engine = self.runtime.CpuExtractor(bundle, threads=threads)
        self.threads, self.batch_size, self.context = threads, batch_size, context
        self.practice, self.practice_conflicts = practice_forms(practice_csv)

    def extract_rows(self, rows, diagnostic=None):
        if not isinstance(rows, list):
            raise ValueError("Input must be a JSON array of InputRow objects")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"Row {i} must be an object")
            for key in ("id", "text", "date"):
                if not isinstance(row.get(key), str):
                    raise ValueError(f"Row {i} requires string {key}")
            if row.get("form") is not None and not isinstance(row["form"], list):
                raise ValueError(f"Row {i} form must be an array or null")
        start = time.monotonic()
        output = [dict(row) for row in rows]
        counts = collections.Counter(rows=len(rows))
        unsupported = []

        def reject(index, code, error):
            output[index]["form"] = []
            event = {"event": "unsupported_extraction", "index": index,
                     "id": rows[index]["id"], "code": code, "reason": str(error)}
            unsupported.append(event)
            counts["unsupported"] += 1
            if diagnostic:
                diagnostic(event)

        def infer(selected):
            if not selected:
                return
            try:
                predictions = self.engine.predict_encoded([item for _, item in selected])
            except Exception as error:
                # A troublesome row cannot make all later rows disappear.
                if len(selected) > 1:
                    mid = len(selected) // 2
                    infer(selected[:mid])
                    infer(selected[mid:])
                else:
                    reject(selected[0][0], "inference", error)
                return
            for (index, _), atoms in zip(selected, predictions):
                if len(atoms) > MAX_ASSERTIONS:
                    reject(index, "assertion_count", f"Input exceeds {MAX_ASSERTIONS} predicted assertions")
                    continue
                output[index]["form"] = [item["atom"] for item in atoms]
                counts["predicted"] += 1
                counts["predicted_atoms"] += len(atoms)
                if not atoms:
                    counts["empty_predictions"] += 1

        # Bounded windows limit encoded candidates and padded tensors. Sorting
        # changes batching only; indices restore original order, including IDs.
        for lo in range(0, len(rows), 512):
            encoded = []
            for index in range(lo, min(lo + 512, len(rows))):
                row = rows[index]
                if row.get("form"):
                    counts["preserved"] += 1
                    continue
                if row["text"] in self.practice:
                    output[index]["form"] = self.practice[row["text"]]
                    counts["practice_reused"] += 1
                    continue
                text = row["text"]
                if len(text) > MAX_TEXT_CHARS:
                    reject(index, "text_size", f"Text exceeds {MAX_TEXT_CHARS} characters")
                    continue
                previous = ""
                if self.context == "previous3text":
                    # Public input order only, no annotations, forms or labels.
                    previous = " ".join(r["text"][-MAX_TEXT_CHARS:]
                                        for r in rows[max(0, index - 3):index])
                try:
                    item = self.runtime.encode_input(text, previous, self.engine.meta,
                                                     self.engine.grammar, row["id"])
                    if len(item["candidates"]) > MAX_CANDIDATES:
                        raise ValueError(f"Input exceeds {MAX_CANDIDATES} value candidates")
                    if not item["candidates"]:
                        output[index]["form"] = []
                        counts["no_candidates"] += 1
                    else:
                        encoded.append((index, item))
                except Exception as error:
                    reject(index, "preprocessing", error)
            encoded.sort(key=lambda item: len(item[1]["tokens"]))
            for lo_batch in range(0, len(encoded), self.batch_size):
                infer(encoded[lo_batch:lo_batch + self.batch_size])

        report = {"counts": dict(counts), "unsupported": unsupported,
                  "practice_conflicting_texts": len(self.practice_conflicts),
                  "context": self.context, "context_experimental": self.context != "none",
                  "cpu_threads": self.threads, "batch_size": self.batch_size,
                  "seconds_including_preprocessing": time.monotonic() - start,
                  "platform": platform.platform(),
                  "model_sha256": self.provenance["bundle"]["model.onnx"],
                  "scope": "typed extraction only; Python/ONNX adapter, no LLM or truth score"}
        try:
            import resource
            report["peak_process_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except ImportError:
            pass
        return output, report


def write_json_atomic(path, value):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=os.environ.get("VERIDYCT_EXTRACTOR_BUNDLE", "/opt/veridyct-extractor/model"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--practice-csv")
    parser.add_argument("--threads", type=int, choices=(1, 2), default=2)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--context", choices=("none", "previous3text"), default="none")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        with Path(args.input).open(encoding="utf-8-sig") as stream:
            rows = json.load(stream)
        extractor = BatchExtractor(args.bundle, args.threads, args.batch_size,
                                   args.context, args.practice_csv)
        output, report = extractor.extract_rows(rows, lambda event: print(json.dumps(event), file=sys.stderr))
        report["seconds_total"] = time.monotonic() - started
        report["input_sha256"] = hashlib.sha256(Path(args.input).read_bytes()).hexdigest()
        if args.report:
            write_json_atomic(args.report, report)
        write_json_atomic(args.output, output)
        print(json.dumps({"event": "extraction_complete", **{k: v for k, v in report.items() if k != "unsupported"}}), file=sys.stderr)
        return 0
    except Exception as error:
        print(json.dumps({"event": "extraction_failed", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
