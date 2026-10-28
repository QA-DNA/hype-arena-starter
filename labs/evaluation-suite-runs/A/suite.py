"""Shared world registry and public-file readers (no gold access here)."""
import csv
import json
import os

DATA = os.environ.get("EVAL_DATA", "/Users/mogaeduard/Downloads/evaluation-data")
OUT = "/tmp/veridyct-evalsuite"

WORLDS = {
    "dev": "realistic-v1/development-20000",
    "cal": "realistic-v1/calibration-20000",
    "sealed": "realistic-v1/sealed-20000",
    "diag": "realistic-v1/diagnostic-6000",
    "pilot": "realistic-v1/pilot-500",
    "prac": "realistic-v1/practice-1897",
    "extdev": "realistic-v1/external-development",
    "extcal": "realistic-v1/external-calibration",
    "extsealed": "realistic-v1/external-sealed",
    "synth": "realistic-synthetic-20000",
    "clean": "realistic-clean-input",
}
# clean has public/ only; ablation.json: gold_reference = development-20000, same ids/forms/labels.
GOLD_OF = {"clean": "dev"}


def public_path(world, name):
    return os.path.join(DATA, WORLDS[world], "public", name)


def gold_path(world, name):
    return os.path.join(DATA, WORLDS[GOLD_OF.get(world, world)], "gold", name)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_universe(world):
    """Public rows: id, text, date, label ('' for hidden targets)."""
    return read_csv(public_path(world, "universe.csv"))


def read_lexicon(world):
    with open(public_path(world, "lexicon.json"), encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
