#!/usr/bin/env python3
"""
Frontend for the Hype Arena system: shows the architecture diagram and runs the
real system (src/label_rows.py + generate_claims.py, the same code the Docker
image runs) live on rows you paste or upload.

    python frontend/server.py            # then open http://localhost:8000
    PORT=9000 python frontend/server.py

Standard library HTTP server; the system needs numpy, pandas, scipy, scikit-learn.
"""
import csv
import io
import json
import os
import sys
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from entrypoint import read_practice  # noqa: E402
from generate_claims import Generator  # noqa: E402
from label_rows import predict_labels  # noqa: E402

PRACTICE = ROOT / "data" / "practice.csv"
LEXICON = ROOT / "data" / "lexicon.json"
SAMPLE = ROOT / "datasets" / "sample.csv"
MAX_BODY = 8 * 1024 * 1024


def run_system(csv_text):
    """Label every unlabelled row of csv_text and generate the 1,000 claims."""
    rows = [r for r in csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
            if (r.get("id") or "").strip() and (r.get("text") or "").strip()]
    unlabelled = [r for r in rows if not (r.get("label") or "").strip()]
    if not unlabelled:
        raise ValueError("no rows to label: expected a header id,text,date,label and rows with an empty label")
    practice = read_practice(PRACTICE)
    lexicon = json.loads(LEXICON.read_text(encoding="utf-8"))

    t0 = time.time()
    preds = predict_labels(practice, unlabelled, str(LEXICON))
    t1 = time.time()
    gen = Generator(practice, lexicon).generate(target=1000)
    t2 = time.time()

    labels = []
    for r in unlabelled:
        label, conf = preds.get(r["id"].strip(), ("unsure", ""))
        labels.append({"id": r["id"], "date": r.get("date", ""), "text": r["text"],
                       "label": label, "confidence": conf})
    return {
        "labels": labels,
        "claims": gen["claims"],
        "by_type": Counter(c["type"] for c in gen["claims"]),
        "seconds": {"label": round(t1 - t0, 2), "generate": round(t2 - t1, 2)},
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path  # ignore ?theme= and other query strings
        if path in ("/", "/index.html"):
            self._send(200, (Path(__file__).parent / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/sample.csv":
            self._send(200, SAMPLE.read_bytes(), "text/csv; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if urlsplit(self.path).path != "/run":
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self._send(400, json.dumps({"error": "send a CSV body up to 8 MiB"}), "application/json")
        try:
            result = run_system(self.rfile.read(n).decode("utf-8"))
        except ValueError as e:  # bad input: say what is wrong
            return self._send(400, json.dumps({"error": str(e)}), "application/json")
        except Exception as e:  # show the failure in the page instead of a dropped connection
            return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}), "application/json")
        self._send(200, json.dumps(result, ensure_ascii=False), "application/json")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Hype Arena frontend on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
