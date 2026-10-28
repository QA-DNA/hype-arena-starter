# Brief: backend teammate (branch `forge`)

You own **the 1,000 claims**: `polygraph/forge.py` + `polygraph/validate.py` (+ `polygraph/render.py`), and the API in `server/app.py`. Paste this whole file into your AI tool as context.

## The goal in one paragraph

Our system must write exactly 1,000 new claims about Hooly, and **every one must be true and readable by the referee**. An invalid or false claim still uses up one of the 1,000 slots. The referee is strict and deterministic: read `contracts/claim-forms.md` and `contracts/value-forms.md` fully, since every rule there is a way a claim can fail. Quality beats quantity here: a claim we're not sure about is worse than a duller, safer one.

## What already works

`python scripts/eval.py --gold-extraction` prints the claims section:

```
== claims: 1000 (target exactly 1000)
  by type: {'fact': 350, 'compare': 400, 'change': 98, 'at_event': 150, 'relation': 2}
  validator problems: none
```

**How it works:**
- `forge.generate(kb, input_texts)` builds candidates of all 5 types from the knowledge base, validates them, ranks them by confidence with per-type quotas, and keeps 1,000.
- The KB (`polygraph/kb.py`) is each fact's timeline as Steps (start, end, value, support).
- Until the engine is ready, the KB comes from the organizers' gold facts (`KB.from_gold`), so you can work now. Later the engine fills the **same interface**, and your code doesn't change.
- `render.py` writes values exactly as the referee reads them (`€59 per month`, `2,048 customers`, `1 July 2026`).

## Your tasks, in priority order

1. **Make every claim certainly valid.** In `validate.py`, add the text checks from `claim-forms.md` for each type:
   - the subject is named in the same sentence as the value;
   - no other value of the same kind is in that sentence;
   - no negation unless the value is a yes/no;
   - for `compare`, no number at all, and exactly one op phrase;
   - for `relation`, the link's words are present.

   Once the reader lands (`reader.IMPLEMENTED = True`, coming from the engine branch), read every claim text back with `reader.parse_values(text)` and require that it finds exactly the form's value. Until then, write these checks with regexes.
2. **Make claims safer.** Prefer facts with high `support` (many mentions) whose last step was seen recently, since the as-of date is 29 Oct 2026. Drop facts whose newest mention is old, because they may have changed since. Tune the confidences so they mean something: 0.95 should be right 95% of the time.
3. **Better wording.** The templates are clunky ("The joined of Holdan is..."). Write per-attribute phrasings in `polygraph/artifacts/templates.json`, e.g. `{"price": "{subject} costs {value}", "joined": "{subject} joined on {value}"}`. You may use an LLM to draft these for all ~500 attributes in `data/lexicon.json`; that's allowed at build time. Every template must still pass `validate()`.
4. **Fix the type mix.** `relation` only yields 2 claims. Look at `kb.links()` (attributes whose value names another entity: ceo, cto, headquarters, series_a_lead, lead, city...) and why so few pass. Per the README, claims that *connect* facts (compare, change, at_event, relation) are the point of the challenge.
5. **Compare with unit conversion.** `14 days` vs `2 weeks`, `1 GB` vs `1,000 MB` (see value-forms.md "Units convert").
6. **`server/app.py`**: keep the API working for the frontend teammate (contract in `docs/BRIEF_frontend.md`), and make `/api/run` fast (cache what doesn't change).

## How you know you're done

- `python -m pytest`: everything passes (`tests/test_pipeline.py` checks all 1,000 claims pass `validate`).
- `python scripts/eval.py --gold-extraction`: 1,000 claims, `validator problems: none`, and a good mix of types.
- `python scripts/run_local.py` ends with `the format checks pass`.
- Spot-check 30 random claims by hand against `contracts/claim-forms.md`.

## Don't touch (to avoid merge conflicts)

`reader.py`, `linker.py`, `attributor.py`, `truth.py`, `judge.py`, `pipeline.py` and `run.py` are the engine branch's. If you need a change there, tell the captain.

## Setup

See `START_HERE.md`. Your branch is `forge`:

```powershell
git checkout forge
python scripts/eval.py --gold-extraction
```
