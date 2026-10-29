"""Collect measured parity/container receipts and exact source hashes (no gold)."""
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    read = lambda name: json.loads((here / "artifacts" / name).read_text(encoding="utf-8"))
    parity = read("parity/parity-report.json")
    padding = read("padding/padding-report.json")
    cli = read("cli-tests/cli-test-report.json")
    benchmark = read("benchmark-20000/benchmark.json")
    if not parity["passed"] or not cli["passed"]:
        raise ValueError("Refusing to collect failed validation")
    if any(n != padding["rows"] for n in padding["native_python_form_matches"].values()):
        raise ValueError("Padding policy parity failed")
    parity.pop("mismatches", None)
    crate = root / "crates" / "extractor"
    files = [root / "Dockerfile.native-extractor", crate / "Cargo.toml", crate / "Cargo.lock"]
    for directory in (crate / "src", crate / "tests", crate / "examples"):
        files += sorted(p for p in directory.rglob("*") if p.is_file())
    files += sorted(p for p in here.iterdir() if p.is_file() and p.suffix in (".py", ".ps1", ".json") and p.name != "validation.json")
    hashes = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    receipt = dict(source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                   code_uncommitted=True, scope="Native frozen-v2 extraction port; prediction parity and resource measurements only",
                   parity=parity, padding=padding, cli=cli, benchmark_20000=benchmark,
                   source_sha256=hashes,
                   runtime_provenance=json.loads((here / "provenance.json").read_text(encoding="utf-8")),
                   no_sealed_or_calibration_gold_read=True)
    path = here / "validation.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(report=str(path), source_files=len(hashes), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
