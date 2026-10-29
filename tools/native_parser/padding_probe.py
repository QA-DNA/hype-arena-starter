"""Measure frozen-model padding sensitivity using public text only, never gold.

Reference mode runs inside the Python oracle image. --compare runs on the host
after the corresponding native CLI runs have produced native-*.json files.
"""
import argparse
import collections
import json
import random
import subprocess
import sys
import time
from pathlib import Path

CONFIGS = [("batch1", 1, False, False), ("batch48", 48, False, False),
           ("shuffled48", 48, False, True), ("exact-length", 48, True, False),
           ("shuffled-exact-length", 48, True, True)]


def compare(out):
    read = lambda prefix, key: json.loads((out / f"{prefix}-{key}.json").read_text(encoding="utf-8"))
    index = lambda rows: {r["id"]: r["form"] for r in rows}
    reference = {key: index(read("python", key)) for key, *_ in CONFIGS}
    native = {key: index(read("native", key)) for key, *_ in CONFIGS}
    changes = lambda a, b: [key for key in a if a[key] != b[key]]
    report = dict(rows=len(reference["batch1"]),
                  native_python_form_matches={key: sum(native[key][i] == form for i, form in values.items()) for key, values in reference.items()},
                  batch1_vs_batch48_changed_ids=changes(reference["batch1"], reference["batch48"]),
                  original_vs_shuffled48_changed_ids=changes(reference["batch48"], reference["shuffled48"]),
                  batch1_vs_exact_length_changed_ids=changes(reference["batch1"], reference["exact-length"]),
                  original_vs_shuffled_exact_length_changed_ids=changes(reference["exact-length"], reference["shuffled-exact-length"]),
                  timing=json.loads((out / "python-timing.json").read_text(encoding="utf-8")),
                  native_timing={key: json.loads((out / f"native-{key}-report.json").read_text(encoding="utf-8"))["seconds_including_preprocessing"] for key, *_ in CONFIGS},
                  scope="Padding sensitivity and port parity on public practice only; no accuracy evaluation or sealed gold")
    (out / "padding-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(n != report["rows"] for n in report["native_python_form_matches"].values()):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--native-image", help="Host-only: run each native Docker policy and compare")
    args = parser.parse_args()
    if args.compare:
        compare(args.out)
        return
    if args.native_image:
        for key, batch, exact, shuffle in CONFIGS:
            source=(args.out / "shuffled-input.json") if shuffle else args.input
            argv=["docker", "run", "--rm", "--network", "none", "--read-only", "--cpus", "2", "--memory", "6g", "--user", "10001",
                  "--mount", f"type=bind,source={source.resolve()},target=/input/rows.json,readonly",
                  "--mount", f"type=bind,source={args.out.resolve()},target=/io", args.native_image,
                  "--input", "/input/rows.json", "--output", f"/io/native-{key}.json", "--report", f"/io/native-{key}-report.json",
                  "--batch-size", str(batch), "--batching", "exact-length" if exact else "padded"]
            run=subprocess.run(argv,capture_output=True,text=True,encoding="utf-8")
            if run.returncode:
                raise RuntimeError(f"Native {key} failed: {run.stderr}")
            print(json.dumps(dict(config=key, native=True)),flush=True)
        compare(args.out)
        return
    if args.root is None or args.input is None:
        parser.error("--root and --input are required in reference mode")
    sys.path.insert(0, str(args.root / "frozen"))
    from runtime import CpuExtractor, encode_input
    engine = CpuExtractor(args.root / "model", threads=2)
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("This comparison requires unique IDs")
    args.out.mkdir(parents=True, exist_ok=True)
    shuffled = list(rows)
    random.Random(20261029).shuffle(shuffled)
    (args.out / "shuffled-input.json").write_text(json.dumps(shuffled, ensure_ascii=False), encoding="utf-8")
    timing = {}
    for key, batch, exact, shuffle in CONFIGS:
        selected = shuffled if shuffle else rows
        output = [dict(r, form=[]) for r in selected]
        start = time.monotonic()
        for lo in range(0, len(selected), 512):
            encoded = [(i, encode_input(r["text"], "", engine.meta, engine.grammar, r["id"])) for i, r in enumerate(selected[lo:lo+512], lo)]
            encoded.sort(key=lambda item: len(item[1]["tokens"]))
            groups = collections.defaultdict(list)
            if exact:
                for item in encoded:
                    groups[len(item[1]["tokens"])].append(item)
            else:
                groups[0] = encoded
            for group in groups.values():
                for start_batch in range(0, len(group), batch):
                    part = group[start_batch:start_batch+batch]
                    for (index, _), assertions in zip(part, engine.predict_encoded([r for _, r in part])):
                        output[index]["form"] = [a["atom"] for a in assertions]
        timing[key] = time.monotonic() - start
        (args.out / f"python-{key}.json").write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(json.dumps(dict(config=key, seconds=timing[key])), flush=True)
    (args.out / "python-timing.json").write_text(json.dumps(timing), encoding="utf-8")


if __name__ == "__main__":
    main()
