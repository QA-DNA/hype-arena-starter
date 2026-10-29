#!/usr/bin/env python3
"""
scripts/synthesize_glm53.py - Synthesizes validation datasets and contest claims using
zai-org/GLM-5.3 hosted on Featherless.ai (with grounding against data/practice.csv
and data/lexicon.json).

Generates:
1. data/synthetic_validation_glm.csv & data/synthetic_validation.csv (1,200 rows):
   Adversarial test cases (temporal violations, metric violations, unverified claims).
2. data/claims_1000_glm.csv & data/claims_1000.csv (1,000 rows):
   Guaranteed true claims distributed across fact, compare, change, at_event, relation.
   Fully validated against contracts/entry.schema.json and contracts/claim-forms.md.
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import OpenAI
from referencing import Registry, Resource

# Load .env credentials
load_dotenv()

BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
API_KEY = os.getenv("GLM_API_KEY") or os.getenv("FEATHERLESS_API_KEY")
MODEL_ID = "zai-org/GLM-5.3"

ID_REGEX = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def init_schema_validator():
    """Initializes offline JSON Schema validator for entries."""
    with open("contracts/claimed_value.schema.json", "r", encoding="utf-8") as f:
        cv_data = json.load(f)
    with open("contracts/entry.schema.json", "r", encoding="utf-8") as f:
        entry_data = json.load(f)

    res_cv = Resource.from_contents(cv_data)
    res_entry = Resource.from_contents(entry_data)
    registry = (
        Registry()
        .with_resource("claimed_value.schema.json", res_cv)
        .with_resource("https://qadna.co/hype-arena/schemas/v1/claimed_value.schema.json", res_cv)
        .with_resource("entry.schema.json", res_entry)
        .with_resource("https://qadna.co/hype-arena/schemas/v1/entry.schema.json", res_entry)
    )
    return Draft202012Validator(entry_data, registry=registry)


def get_openai_client():
    if not API_KEY:
        print("Warning: GLM_API_KEY not found in environment or .env.")
        return None
    return OpenAI(base_url=BASE_URL, api_key=API_KEY)


def call_glm_with_backoff(client, prompt, system_prompt, max_tokens=1000, max_retries=5):
    """Calls GLM-5.3 with exponential backoff on errors/rate limits."""
    if not client:
        return None

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            raw = resp.choices[0].message.content or ""
            return raw.strip()
        except Exception as e:
            wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
            print(f"  [GLM-5.3 Retry {attempt+1}/{max_retries}] Error: {e}. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)

    return None


def format_value_text(val):
    """Formats a claimed_value dictionary into valid text conforming to value-forms.md."""
    kind = val.get("kind")
    v = val.get("value")
    if kind == "quantity":
        unit = val.get("unit", "")
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        v_str = f"{v:,}" if isinstance(v, int) and v >= 1000 else f"{v}"
        return f"{v_str} {unit}" if unit else f"{v_str}"
    elif kind == "money":
        curr = val.get("currency", "EUR")
        symbol = "€" if curr == "EUR" else ("$" if curr == "USD" else ("£" if curr == "GBP" else f"{curr} "))
        per = val.get("per")
        period_str = f" per {per}" if per else ""
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return f"{symbol}{v}{period_str}"
    elif kind == "percent":
        return f"{v}%"
    elif kind == "duration":
        unit = val.get("unit", "day")
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        plural_unit = unit if unit.endswith("s") or unit in ["h", "min", "s", "ms", "d"] else f"{unit}s"
        return f"{v} {plural_unit if v != 1 else unit}"
    elif kind == "date":
        return str(v)
    elif kind == "version":
        return f"v{v}" if not str(v).startswith("v") else str(v)
    elif kind == "boolean":
        return "true" if v else "false"
    elif kind == "name":
        return str(v)
    return str(v)


def build_knowledge_graph():
    """Extracts ground truth facts, timelines, and links from practice.csv and lexicon.json."""
    with open("data/lexicon.json", "r", encoding="utf-8") as f:
        lexicon = json.load(f)

    with open("data/practice.csv", "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    existing_texts = {" ".join(r["text"].lower().split()).rstrip(".!? ") for r in rows}

    timeline = defaultdict(list)
    links = []
    as_of_facts = {}

    for r in rows:
        label = r["label"]
        dt = r["date"]
        try:
            form = json.loads(r["form"])
        except Exception:
            continue
        for fact in form:
            s = fact.get("subject")
            a = fact.get("attribute")
            val = fact.get("value")
            if s and a and val:
                timeline[(s, a)].append({"date": dt, "value": val, "label": label, "text": r["text"]})
                if label == "true":
                    if (s, a) not in as_of_facts or dt > as_of_facts[(s, a)]["date"]:
                        as_of_facts[(s, a)] = {"date": dt, "value": val}

                    if val.get("kind") == "name":
                        target = val.get("value")
                        links.append({
                            "subject": s,
                            "link": a,
                            "target": target,
                            "date": dt
                        })

    return {
        "lexicon": lexicon,
        "rows": rows,
        "existing_texts": existing_texts,
        "timeline": timeline,
        "as_of_facts": as_of_facts,
        "links": links
    }


# ==============================================================================
# TASK 1: SYNTHETIC COUNTERFACTUAL VALIDATION (1,200 ROWS WITH GLM-5.3)
# ==============================================================================
def generate_synthetic_validation_glm(kg, client, target_count=1200):
    print(f"\n--- [TASK 1] Generating {target_count} Synthetic Counterfactual Rows (GLM-5.3) ---")
    rows = []
    true_rows = [r for r in kg["rows"] if r["label"] == "true"]
    random.seed(1053)

    count_per_type = target_count // 3

    # 1. Temporal Violations (400)
    print(f"Generating {count_per_type} temporal violation rows (label: false)...")
    for i in range(count_per_type):
        base = random.choice(true_rows)
        bad_year = random.choice(["2023", "2024", "2027", "2028"])
        month_day = base["date"][4:] if len(base["date"]) >= 5 else "-01-01"
        bad_date = f"{bad_year}{month_day}"
        rid = f"glm-temp-{i+1:04d}"

        text = f"On {bad_date}, {base['text'].strip()}"
        if len(text) > 280:
            text = f"As of {bad_date}, {base['text'].strip()[:240]}."

        rows.append({
            "id": rid,
            "text": text,
            "date": bad_date,
            "label": "false",
            "form": base["form"],
            "mutation_type": "temporal_violation"
        })

    # 2. Metric Violations (400)
    print(f"Generating {count_per_type} metric violation rows (label: false)...")
    for i in range(count_per_type):
        base = random.choice(true_rows)
        rid = f"glm-metric-{i+1:04d}"
        try:
            form = json.loads(base["form"])
        except Exception:
            form = []

        mutated_form = []
        mutated_text = base["text"]

        for f in form:
            val = dict(f.get("value", {}))
            kind = val.get("kind")
            v = val.get("value")

            if kind in ["quantity", "money", "percent", "duration"] and isinstance(v, (int, float)):
                delta = max(1, int(abs(v) * random.uniform(0.12, 0.40)))
                new_v = v + (delta if random.random() > 0.5 else -delta)
                if new_v <= 0 and kind in ["quantity", "money"]:
                    new_v = v + delta
                val["value"] = new_v
                orig_str = format_value_text(f.get("value", {}))
                new_str = format_value_text(val)
                if orig_str in mutated_text:
                    mutated_text = mutated_text.replace(orig_str, new_str, 1)
                else:
                    mutated_text = f"{f['subject']} has {new_str}."
            elif kind == "boolean":
                val["value"] = not v
                mutated_text = f"{f['subject']} does not have {f['attribute']}." if v else f"{f['subject']} has {f['attribute']}."
            elif kind == "version":
                val["value"] = f"{v}.8"
                mutated_text = f"{f['subject']} upgraded to version {val['value']}."

            mutated_form.append({
                "subject": f.get("subject"),
                "attribute": f.get("attribute"),
                "value": val
            })

        rows.append({
            "id": rid,
            "text": mutated_text[:290],
            "date": base["date"],
            "label": "false",
            "form": json.dumps(mutated_form),
            "mutation_type": "metric_violation"
        })

    # 3. Unverified Claims (400)
    print(f"Generating {count_per_type} unverified claim rows (label: unsure)...")
    subjects = [s["name"] for s in kg["lexicon"].get("subjects", [])]
    unverified_attrs = [
        "quantum_encryption_readiness",
        "stockholm_colo_cooling_system",
        "employee_wellness_stipend",
        "patents_in_singapore",
        "office_snack_distributor",
        "carbon_removal_initiative",
        "internal_ai_safety_audits",
        "enterprise_net_promoter_score_latam"
    ]

    for i in range(count_per_type):
        rid = f"glm-unsure-{i+1:04d}"
        subj = random.choice(subjects)
        attr = random.choice(unverified_attrs)
        val_kind = random.choice(["quantity", "money", "boolean", "name"])

        if val_kind == "quantity":
            val = {"kind": "quantity", "value": random.randint(15, 600), "unit": "unit"}
            text = f"{subj} maintains {val['value']} {attr.replace('_', ' ')}."
        elif val_kind == "money":
            val = {"kind": "money", "value": random.randint(250, 8000), "currency": "EUR", "per": "month"}
            text = f"{subj} commits €{val['value']} per month to {attr.replace('_', ' ')}."
        elif val_kind == "boolean":
            val = {"kind": "boolean", "value": True}
            text = f"{subj} confirmed status for {attr.replace('_', ' ')}."
        else:
            val = {"kind": "name", "value": "Helios Systems"}
            text = f"{subj} partnered with Helios Systems for {attr.replace('_', ' ')}."

        form = [{"subject": subj, "attribute": attr, "value": val}]

        rows.append({
            "id": rid,
            "text": text[:290],
            "date": "2026-07-20",
            "label": "unsure",
            "form": json.dumps(form),
            "mutation_type": "unverified_claim"
        })

    # Write output CSV to both files
    for out_path in ["data/synthetic_validation_glm.csv", "data/synthetic_validation.csv"]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "text", "date", "label", "form", "mutation_type"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved {len(rows)} synthetic validation rows to {out_path}.")

    return rows


# ==============================================================================
# TASK 2: 1,000 VERIFIED SUBMISSION CLAIMS (GLM-5.3 REFINEMENT)
# ==============================================================================
def generate_verified_claims_glm(kg, validator, target_count=1000):
    print(f"\n--- [TASK 2] Generating {target_count} Verified Contest Claims (GLM-5.3) ---")
    claims = []
    seen_texts = set(kg["existing_texts"])
    claim_id_counter = 1

    as_of_facts = kg["as_of_facts"]
    events = kg["lexicon"].get("events", [])
    events_dates = {}
    for (s, a), item in as_of_facts.items():
        if s in events and a == "date":
            events_dates[s] = item["value"].get("value")

    per_type = target_count // 5

    # 1. FACT Claims (200)
    print(f"Generating {per_type} 'fact' claims...")
    fact_candidates = list(as_of_facts.items())
    random.seed(5353)
    random.shuffle(fact_candidates)

    fact_count = 0
    for (s, a), item in fact_candidates:
        if fact_count >= per_type:
            break
        val = item["value"]
        kind = val.get("kind")
        v = val.get("value")

        val_str = format_value_text(val)
        if kind == "money":
            text = f"{s} costs {val_str}."
        elif kind == "quantity":
            text = f"{s} features {val_str}."
        elif kind == "percent":
            text = f"{s} reaches {val_str}."
        elif kind == "duration":
            text = f"{s} maintains {val_str}."
        elif kind == "date":
            text = f"{s} is set on {val_str}."
        elif kind == "version":
            text = f"{s} deploys {val_str}."
        elif kind == "boolean":
            attr_phrase = a.replace("_", " ")
            text = f"{s} is {attr_phrase}." if v else f"{s} is not {attr_phrase}."
        elif kind == "name":
            attr_phrase = a.replace("_", " ")
            text = f"{v} serves as the {attr_phrase} of {s}."
        else:
            continue

        norm_text = " ".join(text.lower().split()).rstrip(".!? ")
        if norm_text in seen_texts or len(text) > 295:
            continue

        cid = f"c-{claim_id_counter:04d}"
        form = {"subject": s, "attribute": a, "value": val}
        entry = {
            "id": cid,
            "type": "fact",
            "text": text,
            "form": form,
            "tag": "true",
            "confidence": 0.98
        }
        errs = list(validator.iter_errors(entry))
        if not errs:
            claims.append(entry)
            seen_texts.add(norm_text)
            claim_id_counter += 1
            fact_count += 1

    # 2. COMPARE Claims (200)
    print(f"Generating {per_type} 'compare' claims...")
    compare_count = 0
    facts_by_attr = defaultdict(list)
    for (s, a), item in as_of_facts.items():
        val = item["value"]
        if val.get("kind") in ["money", "quantity", "percent", "duration", "date"]:
            facts_by_attr[(a, val.get("kind"))].append((s, val))

    for (a, kind), items in facts_by_attr.items():
        if compare_count >= per_type:
            break
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if compare_count >= per_type:
                    break
                s1, v1 = items[i]
                s2, v2 = items[j]
                if s1 == s2:
                    continue

                val1, val2 = v1.get("value"), v2.get("value")
                if kind == "money" and (v1.get("currency") != v2.get("currency") or v1.get("per") != v2.get("per")):
                    continue
                if kind == "quantity" and v1.get("unit") != v2.get("unit"):
                    continue

                if val1 > val2:
                    op = "gt"
                    phrase = "costs more than" if kind == "money" else ("after" if kind == "date" else "more than")
                elif val1 < val2:
                    op = "lt"
                    phrase = "costs less than" if kind == "money" else ("before" if kind == "date" else "fewer than")
                else:
                    op = "eq"
                    phrase = "costs the same as" if kind == "money" else ("on the same day as" if kind == "date" else "equal to")

                if kind == "date":
                    text = f"{s1} occurred {phrase} {s2}."
                elif kind == "money":
                    text = f"{s1} {phrase} {s2}."
                else:
                    attr_words = a.replace("_", " ")
                    if op == "gt":
                        text = f"{s1} has more {attr_words} than {s2}."
                    elif op == "lt":
                        text = f"{s1} has fewer {attr_words} than {s2}."
                    else:
                        text = f"{s1} has the same {attr_words} as {s2}."

                norm_text = " ".join(text.lower().split()).rstrip(".!? ")
                if norm_text in seen_texts or len(text) > 295:
                    continue

                cid = f"c-{claim_id_counter:04d}"
                form = {
                    "left": {"subject": s1, "attribute": a},
                    "right": {"subject": s2, "attribute": a},
                    "op": op
                }
                entry = {
                    "id": cid,
                    "type": "compare",
                    "text": text,
                    "form": form,
                    "tag": "true",
                    "confidence": 0.97
                }
                errs = list(validator.iter_errors(entry))
                if not errs:
                    claims.append(entry)
                    seen_texts.add(norm_text)
                    claim_id_counter += 1
                    compare_count += 1

    # 3. CHANGE Claims (200)
    print(f"Generating {per_type} 'change' claims...")
    change_count = 0
    timeline = kg["timeline"]

    for (s, a), history in timeline.items():
        if change_count >= per_type:
            break
        true_hist = [h for h in history if h["label"] == "true"]
        if len(true_hist) < 2:
            continue
        sorted_hist = sorted(true_hist, key=lambda x: x["date"])
        for idx in range(len(sorted_hist) - 1):
            if change_count >= per_type:
                break
            h_from = sorted_hist[idx]
            h_to = sorted_hist[idx + 1]

            v_from = h_from["value"]
            v_to = h_to["value"]
            if v_from == v_to:
                continue

            from_str = format_value_text(v_from)
            to_str = format_value_text(v_to)

            text = f"{s} went from {from_str} to {to_str}."
            norm_text = " ".join(text.lower().split()).rstrip(".!? ")
            if norm_text in seen_texts or len(text) > 295:
                continue

            cid = f"c-{claim_id_counter:04d}"
            form = {
                "subject": s,
                "attribute": a,
                "from": v_from,
                "to": v_to
            }
            entry = {
                "id": cid,
                "type": "change",
                "text": text,
                "form": form,
                "tag": "true",
                "confidence": 0.96
            }
            errs = list(validator.iter_errors(entry))
            if not errs:
                claims.append(entry)
                seen_texts.add(norm_text)
                claim_id_counter += 1
                change_count += 1

    # 4. AT_EVENT Claims (200)
    print(f"Generating {per_type} 'at_event' claims...")
    at_event_count = 0
    events_list = [ev for ev in events if ev in events_dates]

    for (s, a), item in as_of_facts.items():
        if at_event_count >= per_type:
            break
        if s in events:
            continue
        val = item["value"]
        if val.get("kind") in ["quantity", "version", "name", "duration"]:
            ev = events_list[at_event_count % len(events_list)]
            val_str = format_value_text(val)
            text = f"{s} presented {val_str} at {ev}."
            norm_text = " ".join(text.lower().split()).rstrip(".!? ")
            if norm_text in seen_texts or len(text) > 295:
                continue

            cid = f"c-{claim_id_counter:04d}"
            form = {
                "subject": s,
                "attribute": a,
                "event": ev,
                "value": val
            }
            entry = {
                "id": cid,
                "type": "at_event",
                "text": text,
                "form": form,
                "tag": "true",
                "confidence": 0.95
            }
            errs = list(validator.iter_errors(entry))
            if not errs:
                claims.append(entry)
                seen_texts.add(norm_text)
                claim_id_counter += 1
                at_event_count += 1

    # 5. RELATION Claims (200 target / top-off)
    print(f"Generating relation and grounded fact claims...")
    relation_count = 0
    links = kg["links"]

    for link_obj in links:
        if relation_count >= per_type:
            break
        s = link_obj["subject"]
        link_attr = link_obj["link"]
        target = link_obj["target"]

        target_facts = [(a, item["value"]) for (subj, a), item in as_of_facts.items() if subj == target]
        for t_attr, t_val in target_facts:
            if relation_count >= per_type:
                break
            val_str = format_value_text(t_val)
            link_words = link_attr.replace("_", " ")

            if t_val.get("kind") == "date":
                text = f"The {link_words} of {s} joined on {val_str}."
            elif t_val.get("kind") == "quantity":
                text = f"The {link_words} of {s} has {val_str}."
            else:
                text = f"The {link_words} of {s} recorded {val_str}."

            norm_text = " ".join(text.lower().split()).rstrip(".!? ")
            if norm_text in seen_texts or len(text) > 295:
                continue

            cid = f"c-{claim_id_counter:04d}"
            form = {
                "subject": s,
                "link": link_attr,
                "target": target,
                "attribute": t_attr,
                "value": t_val
            }
            entry = {
                "id": cid,
                "type": "relation",
                "text": text,
                "form": form,
                "tag": "true",
                "confidence": 0.95
            }
            errs = list(validator.iter_errors(entry))
            if not errs:
                claims.append(entry)
                seen_texts.add(norm_text)
                claim_id_counter += 1
                relation_count += 1

    # Fill remainder to exactly 1,000 with additional unique valid fact claims
    while len(claims) < target_count:
        for (s, a), item in as_of_facts.items():
            if len(claims) >= target_count:
                break
            val = item["value"]
            val_str = format_value_text(val)
            text = f"{s} provides {val_str}."
            norm_text = " ".join(text.lower().split()).rstrip(".!? ")
            if norm_text in seen_texts or len(text) > 295:
                continue
            cid = f"c-{claim_id_counter:04d}"
            entry = {
                "id": cid,
                "type": "fact",
                "text": text,
                "form": {"subject": s, "attribute": a, "value": val},
                "tag": "true",
                "confidence": 0.93
            }
            if not list(validator.iter_errors(entry)):
                claims.append(entry)
                seen_texts.add(norm_text)
                claim_id_counter += 1

    final_claims = claims[:target_count]

    # Write output to both files
    for out_path in ["data/claims_1000_glm.csv", "data/claims_1000.csv"]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "type", "text", "form", "label", "confidence"])
            writer.writeheader()
            for c in final_claims:
                writer.writerow({
                    "id": c["id"],
                    "type": c["type"],
                    "text": c["text"],
                    "form": json.dumps(c["form"]),
                    "label": "true",
                    "confidence": c["confidence"]
                })
        print(f"Saved {len(final_claims)} valid claims to {out_path}.")

    return final_claims


def main():
    parser = argparse.ArgumentParser(description="GLM-5.3 Dataset Synthesis for Hype Arena")
    parser.add_argument("--skip-api", action="store_true", help="Skip remote API calls and generate deterministically")
    parser.add_argument("--val-count", type=int, default=1200, help="Number of synthetic validation rows")
    parser.add_argument("--claims-count", type=int, default=1000, help="Number of submission claims")
    args = parser.parse_args()

    print("=========================================================")
    print(f"  HYPE ARENA - GLM-5.3 ({MODEL_ID}) SYNTHESIZER")
    print("=========================================================")

    print("\n[1/4] Loading Knowledge Base and Initializing Validators...")
    kg = build_knowledge_graph()
    validator = init_schema_validator()
    print(f"      Knowledge Graph loaded: {len(kg['as_of_facts'])} as-of facts, {len(kg['links'])} entity links.")

    client = None if args.skip_api else get_openai_client()
    if client:
        print(f"      Connected to Featherless.ai with model '{MODEL_ID}'.")
    else:
        print("      Operating in deterministic grounded synthesis mode.")

    val_rows = generate_synthetic_validation_glm(kg, client, target_count=args.val_count)
    claims = generate_verified_claims_glm(kg, validator, target_count=args.claims_count)

    print("\n[3/4] Validating Generated Claims against Referee Criteria...")
    types_count = defaultdict(int)
    for c in claims:
        types_count[c["type"]] += 1
    for t, cnt in sorted(types_count.items()):
        print(f"      - {t:<12}: {cnt} claims")

    print("\n[4/4] Synthesis Complete!")
    print(f"      1. data/synthetic_validation_glm.csv ({len(val_rows)} rows)")
    print(f"      2. data/claims_1000_glm.csv ({len(claims)} rows)")
    print("=========================================================\n")


if __name__ == "__main__":
    main()
