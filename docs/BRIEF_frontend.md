# Brief: frontend teammate (branch `frontend`)

You own `web/`: **the Polygraph console**. Paste this whole file into your AI tool as context.

## What the judges need to see (from the rules)

- A page that shows **the architecture of our system as a diagram**.
- The same page **runs the system live** on rows you give it, in particular the 20 rows of `sample/sample.csv` (published 09:00 on 29 Oct).

Our video (due 11:00 on 29 Oct) records this page, and the finalists pitch it on stage at 17:00.

## The concept: "Polygraph", a lie detector for Hooly's hype

**Look:** dark noir + neon.
- Near-black background (`#07080a`).
- Neon green `#39ff88` = true, neon red `#ff3b5c` = false/hype, amber `#ffb020` = unsure.
- Monospace readouts (JetBrains Mono / IBM Plex Mono), subtle CRT scanlines.

**Screens:**
1. **Live architecture diagram** (React Flow is a good fit). The 6 stages come from `GET /api/architecture`. During a run, each stage node lights up in order and shows its `count` and `ms` from the trace's `stages`.
2. **Run panel.** A "Load sample" button (`GET /api/sample`), a textarea or CSV upload for your own rows, and a RUN button that calls `POST /api/run`. Each row then gets a polygraph needle that wobbles and settles, and a stamp: TRUE / FALSE / UNSURE plus a confidence gauge.
3. **Evidence board** (click a row). Show the sentence with each extracted fact highlighted (`facts[].span`). For each fact, draw its **timeline** from `timelines["Subject|attribute"]`:
   - a step chart over Oct 2025 → Oct 2026;
   - every mention as a dot (green true / red false);
   - this row's dot highlighted;
   - the `status` explained in words:
     - `agrees`: the value holds on this date.
     - `stale`: it was true before.
     - `premature`: only later.
     - `invented`: never true.
     - `unknown`: no evidence.
4. **Claim Forge tab.** The claims from `GET /api/claims`, filterable by type (fact / compare / change / at_event / relation), each with its confidence and the facts it connects (`sources`).
5. Optional fun: a **"Hype meter"** of which speakers lie most (rows starting `Gavin:` are the hype CEO).

## Start NOW with the mock, no backend needed

`web/public/mock/trace.json` is a real response of `POST /api/run`, plus an `architecture` key with the `GET /api/architecture` response. Build everything against it first.

## The API (run it with the backend teammate or captain)

```powershell
.venv\Scripts\Activate.ps1
uvicorn server.app:app --reload --port 8000
```

| Call | Returns |
| --- | --- |
| `GET /api/health` | `{"ok": true}` |
| `GET /api/architecture` | `{"stages": [{id, name, what}], "edges": [[from, to]]}` |
| `GET /api/sample` | `{"rows": [{id, text, date}]}` (empty until 09:00 on 29 Oct) |
| `POST /api/run` body `{"rows": [{id, text, date}], "include_claims": false}` | The trace (below) for those rows |
| `GET /api/claims` | `{"claims": [...]}` the 1,000 claims |

### The trace JSON

```jsonc
{
  "stages": [{"name": "reader", "ms": 1.2, "count": 40}],      // one per pipeline stage, in order
  "rows": [{
    "id": "s-1", "text": "Hooly Jules works in 8 languages.", "date": "2026-09-08", "page": 12,
    "given_label": null,                      // the input's label if it had one
    "verdict": "false", "confidence": 0.86,   // confidence is null when verdict is "unsure"
    "why": "stale: Hooly Jules programming_languages",
    "facts": [{"subject": "Hooly Jules", "attribute": "programming_languages",
               "value": {"kind": "quantity", "value": 8, "unit": "language"},
               "span": [21, 32],              // character offsets in text, or null
               "status": "stale"}]            // agrees | stale | premature | invented | unknown
  }],
  "timelines": {
    "Hooly Jules|programming_languages": {
      "steps": [{"from": "2026-04-17", "to": "2026-08-18", "value": {...}, "confidence": 1, "support": 5}],
      "mentions": [{"date": "2026-04-15", "value": {...}, "row_id": "p-412", "verdict": "false"}]
    }
  },
  "claims": [{"id": "c0001-fact", "type": "fact", "text": "...", "form": {...}, "confidence": 0.93,
              "sources": [{"subject": "...", "attribute": "..."}]}]
}
```

A `value` is a dict with a `kind`: quantity / money / percent / date / version / duration / name / boolean. Write a small `formatValue()`: e.g. money gives `€59 / month`, quantity gives `8 languages`.

## How it's started (part of the submission)

The PR must contain "what starts the frontend". Build to `web/dist` (`npm run build`). The API serves `web/dist` at `/` automatically, so the whole demo is one command: `uvicorn server.app:app --port 8000`, then open http://localhost:8000. During development, point Vite's proxy at `http://localhost:8000` for `/api`.

## Done when

- The sample's 20 rows run live in under ~5 s with the animation.
- The diagram lights up per stage.
- Clicking a FALSE row shows a timeline that makes the lie obvious.
- It looks great in a 1080p screen recording.
