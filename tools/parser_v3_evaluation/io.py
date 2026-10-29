"""Immutable bundle I/O and digest helpers."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    # Preserve written decimal precision rather than rounding through a float.
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_float=str)


def load_jsonl(path):
    result = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank JSONL line {line_number}")
        item = json.loads(line, parse_float=str)
        if not isinstance(item, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        result.append(item)
    return result


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def public_hashes(bundle):
    public = Path(bundle) / "public"
    return {path.relative_to(public).as_posix(): digest(path) for path in sorted(public.rglob("*")) if path.is_file()}


def public_digest(bundle):
    payload = json.dumps(public_hashes(bundle), sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def verify_public(bundle):
    manifest = load_json(Path(bundle) / "manifest.json")
    if public_hashes(bundle) != manifest["public_sha256"]:
        raise ValueError("public input hash mismatch")
    if public_digest(bundle) != manifest["public_bundle_sha256"]:
        raise ValueError("public bundle digest mismatch")
    return manifest


def require_artifacts(path):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / "artifacts").resolve()):
        raise ValueError("generated datasets and reports must stay below ignored artifacts/")
    return path
