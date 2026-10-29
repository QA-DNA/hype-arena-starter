#!/usr/bin/env python3
"""
scripts/build_hooly_world.py - Builds the canonical "Hooly World" representation
from data/practice.csv and data/lexicon.json.

Outputs:
1. data/hooly_world.json: Complete structured Knowledge Graph of the universe
   (entities, as-of 2026-10-29 ground truth facts, temporal histories, events, links, comparisons).
2. data/hooly_world_facts.csv: Tabular view of all as-of facts for easy querying and inspection.
"""

import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime

AS_OF_DATE = "2026-10-29"

# Categorize subjects based on lexicon attributes
def categorize_entity(name, attrs, events):
    if name in events:
        return "event"
    person_attrs = {"joined", "previous_employer", "team_size", "chairs", "independent_director", "facilities_team", "desks_managed", "offices_run"}
    if any(a in person_attrs for a in attrs):
        return "person"
    if name in ["Quayside Hall", "Rheinhalle", "Hooly Berlin Office"]:
        return "facility"
    if name in ["Hooly", "Hooly Board", "Hooly Devices", "Brightline Labs", "Meridian Health", "Hooly Hiring Programme"]:
        return "organization"
    return "product"


def format_value_text(val):
    """Formats a claimed_value dict into human-readable text conforming to value-forms.md."""
    if not isinstance(val, dict):
        return str(val)
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


def main():
    print("=========================================================")
    print("  BUILDING THE HOOLY WORLD MODEL (SEED OF ALL CLAIMS)")
    print("=========================================================")

    with open("data/lexicon.json", "r", encoding="utf-8") as f:
        lexicon = json.load(f)

    with open("data/practice.csv", "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    events_set = set(lexicon.get("events", []))
    subjects_lexicon = {s["name"]: s for s in lexicon.get("subjects", [])}

    print(f"Loaded {len(subjects_lexicon)} lexicon subjects and {len(rows)} practice rows.")

    # 1. Collect all true observations grouped by (subject, attribute)
    timeline = defaultdict(list)
    links = []

    for r in rows:
        if r.get("label") != "true" or not r.get("form"):
            continue
        try:
            atoms = json.loads(r["form"])
        except Exception:
            continue

        dt = r["date"]
        rid = r["id"]
        sentence = r["text"]

        for atom in atoms:
            s = atom.get("subject")
            a = atom.get("attribute")
            val = atom.get("value")
            if s and a and val:
                timeline[(s, a)].append({
                    "date": dt,
                    "value": val,
                    "row_id": rid,
                    "sentence": sentence
                })
                # Check for entity links
                if val.get("kind") == "name" and val.get("value") in subjects_lexicon:
                    links.append({
                        "subject": s,
                        "link": a,
                        "target": val.get("value"),
                        "established_date": dt,
                        "row_id": rid
                    })

    # Deduplicate links
    unique_links_dict = {}
    for l in links:
        key = (l["subject"], l["link"], l["target"])
        if key not in unique_links_dict or l["established_date"] < unique_links_dict[key]["established_date"]:
            unique_links_dict[key] = l
    unique_links = list(unique_links_dict.values())

    # 2. Compute canonical intervals & as-of state for each track
    as_of_facts = {}
    transitions = []
    entities_data = {}

    for s_name, s_meta in subjects_lexicon.items():
        cat = categorize_entity(s_name, s_meta.get("attributes", []), events_set)
        entities_data[s_name] = {
            "name": s_name,
            "category": cat,
            "aliases": s_meta.get("aliases", []),
            "lexicon_attributes": s_meta.get("attributes", []),
            "as_of_2026_10_29": {},
            "history": {}
        }

    for (s, a), obs_list in timeline.items():
        if s not in entities_data:
            cat = categorize_entity(s, [a], events_set)
            entities_data[s] = {
                "name": s,
                "category": cat,
                "aliases": [],
                "lexicon_attributes": [a],
                "as_of_2026_10_29": {},
                "history": {}
            }

        # Sort chronologically
        obs_list.sort(key=lambda x: x["date"])

        # Collapse contiguous identical values into intervals
        intervals = []
        for obs in obs_list:
            v_key = json.dumps(obs["value"], sort_keys=True)
            if intervals and intervals[-1]["v_key"] == v_key:
                intervals[-1]["support_count"] += 1
                intervals[-1]["last_seen_date"] = obs["date"]
            else:
                if intervals:
                    intervals[-1]["valid_until"] = obs["date"]
                intervals.append({
                    "start_date": obs["date"],
                    "valid_until": "2026-10-29",
                    "value": obs["value"],
                    "formatted": format_value_text(obs["value"]),
                    "v_key": v_key,
                    "support_count": 1,
                    "first_source_id": obs["row_id"],
                    "sample_sentence": obs["sentence"]
                })

        # Save history
        entities_data[s]["history"][a] = [
            {k: v for k, v in iv.items() if k != "v_key"} for iv in intervals
        ]

        # Latest observation on or before AS_OF_DATE
        valid_obs = [o for o in obs_list if o["date"] <= AS_OF_DATE]
        latest_obs = valid_obs[-1] if valid_obs else obs_list[-1]
        latest_iv = intervals[-1]

        as_of_fact = {
            "subject": s,
            "category": entities_data[s]["category"],
            "attribute": a,
            "value": latest_obs["value"],
            "formatted": format_value_text(latest_obs["value"]),
            "effective_date": latest_iv["start_date"],
            "support_count": latest_iv["support_count"],
            "source_id": latest_obs["row_id"],
            "sample_sentence": latest_obs["sentence"]
        }
        entities_data[s]["as_of_2026_10_29"][a] = as_of_fact
        as_of_facts[(s, a)] = as_of_fact

        # State transitions (for change claims)
        if len(intervals) > 1:
            for i in range(len(intervals) - 1):
                from_iv = intervals[i]
                to_iv = intervals[i + 1]
                if from_iv["value"] != to_iv["value"]:
                    transitions.append({
                        "subject": s,
                        "attribute": a,
                        "from_value": from_iv["value"],
                        "from_formatted": from_iv["formatted"],
                        "to_value": to_iv["value"],
                        "to_formatted": to_iv["formatted"],
                        "changed_on_or_before": to_iv["start_date"],
                        "from_source_id": from_iv["first_source_id"],
                        "to_source_id": to_iv["first_source_id"]
                    })

    # 3. Extract event details
    events_data = {}
    for ev_name in events_set:
        ev_attrs = entities_data.get(ev_name, {}).get("as_of_2026_10_29", {})
        events_data[ev_name] = {
            "name": ev_name,
            "date": ev_attrs.get("date", {}).get("formatted"),
            "city": ev_attrs.get("city", {}).get("formatted"),
            "venue": ev_attrs.get("venue", {}).get("formatted"),
            "facts": {a: item["formatted"] for a, item in ev_attrs.items()}
        }

    # 4. Compute comparable metric pairs
    comparisons = []
    facts_by_dim = defaultdict(list)
    for (s, a), fact in as_of_facts.items():
        val = fact["value"]
        kind = val.get("kind")
        if kind in ["money", "quantity", "percent", "duration", "date"]:
            dim_key = (a, kind, val.get("unit"), val.get("currency"), val.get("per"))
            facts_by_dim[dim_key].append((s, val.get("value"), fact["formatted"]))

    for dim_key, s_list in facts_by_dim.items():
        a, kind = dim_key[0], dim_key[1]
        if len(s_list) >= 2:
            for i in range(len(s_list)):
                for j in range(i + 1, len(s_list)):
                    s1, v1, f1 = s_list[i]
                    s2, v2, f2 = s_list[j]
                    if s1 == s2 or v1 == v2:
                        continue
                    if v1 > v2:
                        comparisons.append({
                            "left": {"subject": s1, "attribute": a, "value": f1},
                            "op": "gt",
                            "right": {"subject": s2, "attribute": a, "value": f2},
                            "dimension": kind
                        })
                    else:
                        comparisons.append({
                            "left": {"subject": s1, "attribute": a, "value": f1},
                            "op": "lt",
                            "right": {"subject": s2, "attribute": a, "value": f2},
                            "dimension": kind
                        })

    # Build Master JSON
    hooly_world = {
        "meta": {
            "title": "The Hooly Universe Ground Truth World Model",
            "as_of_date": AS_OF_DATE,
            "source": "data/practice.csv & data/lexicon.json",
            "generated_at": datetime.now().isoformat(),
            "total_entities": len(entities_data),
            "total_as_of_facts": len(as_of_facts),
            "total_state_transitions": len(transitions),
            "total_events": len(events_data),
            "total_links": len(unique_links),
            "total_comparable_pairs": len(comparisons)
        },
        "entities": entities_data,
        "events": events_data,
        "entity_links": unique_links,
        "state_transitions": transitions,
        "comparisons_preview": comparisons[:50]
    }

    # Write data/hooly_world.json
    json_path = "data/hooly_world.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(hooly_world, f, indent=2, ensure_ascii=False)
    print(f"\n[1/2] Wrote complete Knowledge Graph -> {json_path}")

    # Write data/hooly_world_facts.csv
    csv_path = "data/hooly_world_facts.csv"
    csv_cols = [
        "subject", "category", "attribute", "value_kind", "value_raw",
        "unit_or_currency", "period", "formatted_value", "effective_date",
        "support_count", "source_row_id", "sample_sentence"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols)
        writer.writeheader()
        for fact in as_of_facts.values():
            val = fact["value"]
            kind = val.get("kind")
            unit_or_curr = val.get("unit") or val.get("currency") or ""
            period = val.get("per") or ""
            writer.writerow({
                "subject": fact["subject"],
                "category": fact["category"],
                "attribute": fact["attribute"],
                "value_kind": kind,
                "value_raw": val.get("value"),
                "unit_or_currency": unit_or_curr,
                "period": period,
                "formatted_value": fact["formatted"],
                "effective_date": fact["effective_date"],
                "support_count": fact["support_count"],
                "source_row_id": fact["source_id"],
                "sample_sentence": fact["sample_sentence"]
            })
    print(f"[2/2] Wrote tabular facts table     -> {csv_path}")

    print("\n--- HOOLY WORLD SUMMARY ---")
    print(f"  • Total Canonical Entities   : {len(entities_data)}")
    print(f"  • As-Of Facts (2026-10-29)   : {len(as_of_facts)}")
    print(f"  • Temporal State Transitions : {len(transitions)} (seed for 'change' claims)")
    print(f"  • Established Entity Links   : {len(unique_links)} (seed for 'relation' claims)")
    print(f"  • Events with Fixed Dates    : {len(events_data)} (seed for 'at_event' claims)")
    print(f"  • Comparable Entity Pairs    : {len(comparisons)} (seed for 'compare' claims)")
    print("=========================================================\n")


if __name__ == "__main__":
    main()
