"""Native Docker adapter regressions using public/synthetic text, no gold."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="veridyct-native-extractor:selected-v2")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)

    def write(name, rows):
        (root / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def run(name, *extra, expected=0):
        output = root / f"{name}-output.json"
        if output.exists():
            output.unlink()
        argv = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cpus", "2", "--memory", "6g", "--user", "10001",
                "--mount", f"type=bind,source={root},target=/io", args.image,
                "--input", f"/io/{name}.json", "--output", f"/io/{name}-output.json", *extra]
        process = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
        if process.returncode != expected:
            raise AssertionError(f"{name}: {process.returncode}, expected {expected}: {process.stderr}")
        if expected:
            assert not output.exists(), f"{name} left a partial output"
            return process.stderr
        return json.loads(output.read_text(encoding="utf-8"))

    row = dict(id="duplicate", text="Hooly AI Pro costs €79 per month.", date="2026-10-29", label="")
    known = dict(row, form=[dict(opaque="kept")], extra=dict(retain=True))
    altered = dict(row, id="other", date="1900-01-01", label="false", gold=dict(arbitrary=99), previous_text="Hooly Workspace.")
    write("valid", [row, altered, known, dict(row, text="word " * 400), dict(row, text="\n"), dict(row, text=""), row])
    rows = run("valid")
    assert rows[0]["form"] and rows[0]["form"] == rows[1]["form"] == rows[-1]["form"]
    assert rows[1]["date"] == "1900-01-01" and rows[1]["gold"] == altered["gold"] and rows[1]["label"] == "false"
    assert rows[2] == known
    assert all(r["form"] == [] for r in rows[3:6])
    write("invalid", [dict(id="x", date="2026-01-01")])
    assert "requires string text" in run("invalid", expected=2)
    write("threads", [row])
    assert "CPU threads" in run("threads", "--threads", "3", expected=2)
    write("tampered", [row])
    bad = root / "bad-bundle"
    bad.mkdir(exist_ok=True)
    (bad / "model.onnx").write_bytes(b"changed frozen weights")
    assert "SHA256 mismatch: model.onnx" in run("tampered", "--bundle", "/io/bad-bundle", expected=2)
    original = root / "same.json"
    write("same", [row])
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    process = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "10001",
                              "--mount", f"type=bind,source={root},target=/io", args.image,
                              "--input", "/io/same.json", "--output", "/io/same.json"], capture_output=True)
    assert process.returncode == 2 and hashlib.sha256(original.read_bytes()).hexdigest() == before
    receipt = dict(passed=True, scenarios=5, checks="row metadata/forms/order, unsupported isolation, schema error, thread bounds, weight tampering, atomic same-path refusal")
    (root / "cli-test-report.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
