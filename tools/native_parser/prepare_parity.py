"""Build parity requests from public practice and frozen development predictions.

No sealed/calibration data is opened. Development targets, labels, dates, IDs and
precomputed candidates are not used to construct model features.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def regressions():
    texts = [
        "Hooly AI Pro costs €79 per month.", "Hooly AI Pro costs €71 per month.",
        "Hooly has 500 employees.", "Hooly is not SOC 2 certified.",
        "Holdan started at Hooly on 12 January 2026.", "Its version is no newer than 20.0.",
        "It replies in under a second.", "Growth is at least -26.62%.",
        "It reaches 35 m down.", "It serves 536 teams.", "Hooly Docs 2.0",
        "Cold start measures 1.9 s.", "It closed after 3 days.",
        "It occupies 4 data centre sites.", "Its venue is Ringsend Forum.",
        "€49 was mentioned; joined no earlier than the 25th of April 2025.",
        "The plan costs 1,234.56 euros per user per month and lasts 7 days.",
        "It costs CHF 39 annually; growth is 24.5 percent, and it has 4,000 teams.",
        "It goes up to 99.9% SLA.", "It has at least 99.9% SLA.",
        "Version v0.11.5 is newer than ver. 0.10.1.",
        "It started in Sept. 2026, September 7th, 2026 and 2025-03.",
        "It has twenty-one meetings and a dozen teams.",
        "It has 2 million users and 3M users and 35 m down.",
        "It has 1.5bn users and 2 thousand employees and 4k teams.",
        "It has four data-centre sites and 12 people and 15 persons.",
        "Unrelated café Straße €49.99, Łódź, 東京; Hooly has 200 employees.",
        "Éva pays £49.99 per year. Hooly AI Pro costs $79 monthly!",
        "e\u0301 €79 per month; Hooly AI Pro has 3 employees.",
        "It has ١٢ teams and １２ employees and ٢٫٥ teams.",
        "It has 2 teams\n", "It has 2\u001cpeople.",
        "It costs 79 EUR/seat/month.", "It costs $79/seat per month.",
        "Its version is 20.0. It has no more than 400 users.",
        "From 2026-01-01 through 2026-02-01: Hooly AI Pro costs €79 per month.",
        "Anyway, that is unrelated text with no numeric value.",
        "", "...", "\n", "Hooly has 35 ms latency and 2 W power.",
        "Hooly uses 12 GB of storage and 2 gigabytes.",
        "A price is under €79. A duration is within 3 days.",
        "It has 9007199254740993 employees.",
        "It has 18446744073709551616 teams.",
        "It has 0000042 teams.",
        "It has 18446744073709551616.00 teams.",
        "It has 100000000000 billion users.",
        "It costs €0.00000000051 per month.",
    ]
    for op in ["at least", "no less than", "not less than", "at most", "no more than",
               "not more than", "up to", "within", "more than", "greater than", "over",
               "above", "less than", "fewer than", "under", "below", ">=", "≥", "<=", "≤"]:
        texts.append(f"It costs {op} €49.99 per month.")
    for unit in ["ms", "millisecond", "s", "sec", "second", "min", "minutes", "h", "hr", "hours",
                 "d", "days", "wk", "weeks", "mo", "months", "yr", "years", "GB", "MB", "TB", "KB",
                 "bytes", "mAh", "watts", "grams", "kg", "km", "metres", "inches", "Hz", "GHz", "MHz"]:
        texts.append(f"It uses 12 {unit}.")
    for currency in ["EUR", "USD", "GBP", "CHF", "RON", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK", "JPY", "CNY", "INR", "CAD", "AUD"]:
        texts.extend([f"It costs {currency} 12 per year.", f"It costs 12 {currency} per month."])
    for i, text in enumerate(texts):
        yield dict(id=f"regression:{i}", text=text, previous_text="", group="regression")
    for i, previous in enumerate(["Hooly AI Pro.", "Hooly Workspace. Hooly.", "word " * 150]):
        yield dict(id=f"context:{i}", text="It costs €79 per month.", previous_text=previous, group="context")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--practice", required=True)
    parser.add_argument("--frozen-predictions", required=True)
    parser.add_argument("--synthetic-dev", help="Optional unsealed first-round development inputs")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((Path(__file__).parent / "provenance.json").read_text(encoding="utf-8"))
    frozen_path = Path(args.frozen_predictions)
    if hashlib.sha256(frozen_path.read_bytes()).hexdigest() != manifest["frozen_predictions"]["cpu-dev-predictions.jsonl"]:
        raise ValueError("Frozen prediction hash changed")
    with Path(args.practice).open(encoding="utf-8-sig", newline="") as stream:
        # Deliberately ignore form and label: the only oracle here is predictions.
        public = [{k: row[k] for k in ("id", "text", "date")} for row in csv.DictReader(stream)]
    frozen = [json.loads(line) for line in frozen_path.read_text(encoding="utf-8").splitlines()]
    by_id = {r["id"]: (i, r) for i, r in enumerate(public)}
    frozen_official = [r for r in frozen if r["id"] in by_id]
    if len(frozen_official) != 390:
        raise ValueError(f"Expected frozen official 390, got {len(frozen_official)}")
    requests = [dict(id=r["id"], text=r["text"], previous_text="", group="practice") for r in public]
    official = []
    for pred in frozen_official:
        i, row = by_id[pred["id"]]
        official.append(dict(id=row["id"], text=row["text"], previous_text=" ".join(r["text"] for r in public[max(0, i-3):i]), group="frozen_official390"))
    requests += official
    synthetic = []
    if args.synthetic_dev:
        for line in Path(args.synthetic_dev).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            synthetic.append(dict(id=r["id"], text=r["text"], previous_text=r["previous_text"], group="frozen_synthetic8088"))
        if len(synthetic) != 8088:
            raise ValueError("Expected 8088 unsealed synthetic development inputs")
        requests += synthetic
    regression = list(regressions())
    requests += regression
    write(out / "requests.json", requests)
    write(out / "regression-requests.json", regression)
    write(out / "frozen-official-predictions.json", frozen_official)
    write(out / "frozen-predictions.json", frozen)
    write(out / "batch-input.json", [dict(r, label="") for r in public])
    write(out / "benchmark-input.json", [dict(public[i % len(public)], id=f"bench:{i}", label="") for i in range(20000)])
    write(out / "sources.json", dict(practice_sha256=hashlib.sha256(Path(args.practice).read_bytes()).hexdigest(),
                                   frozen_predictions_sha256=hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
                                   synthetic_dev_sha256=hashlib.sha256(Path(args.synthetic_dev).read_bytes()).hexdigest() if args.synthetic_dev else None,
                                   requests=len(requests), sealed_or_calibration_data_read=False))
    print(json.dumps(dict(requests=len(requests), practice=len(public), official390=len(official), synthetic8088=len(synthetic), regression=len(regression))))


if __name__ == "__main__":
    main()
