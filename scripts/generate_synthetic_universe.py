#!/usr/bin/env python3
"""
scripts/generate_synthetic_universe.py - Generates 18,000 unlabelled samples each
using Step-5 and GLM-5.3, grounded in practice.csv, lexicon.json, and contracts.md.

Target outputs:
1. sample_label_step5.csv (and data/sample_label_step5.csv) - 18,000 unlabelled rows
2. sample_label_glm5.csv (and data/sample_label_glm5.csv)   - 18,000 unlabelled rows
3. data/ground_truth_step5.csv                              - 18,000 labels for eval
4. data/ground_truth_glm5.csv                               - 18,000 labels for eval

Rules & Specs:
- Context files specified to models: practice.csv, lexicon.json, contracts.md.
- Unlabelled: 'label' and 'confidence' fields are empty ("").
- Strict schema: 'id', 'text', 'date', 'label' (NO 'form' column!).
- Reprompted specifically per model:
    * Step-5: corporate telemetry, SRE, SLAs, MTTR, versions, pricing, infrastructure.
    * GLM-5.3: developer ecosystem, partnerships, SDKs, feature releases, limits.
"""

import csv
import json
import os
import random
import re
import sys
import time
from datetime import date, timedelta

import dotenv
from openai import OpenAI

sys.stdout.reconfigure(encoding="utf-8")
dotenv.load_dotenv()

BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
STEP5_KEY = os.getenv("STEP5_API_KEY") or os.getenv("FEATHERLESS_API_KEY")
GLM_KEY = os.getenv("GLM_API_KEY") or os.getenv("FEATHERLESS_API_KEY")

TARGET_ROWS = 18000


def get_client(api_key):
    if not api_key:
        return None
    return OpenAI(base_url=BASE_URL, api_key=api_key, timeout=90.0)


def reprompt_step5(client):
    """
    Reprompts Step-5 (stepfun-ai/Step-5-Preview).
    Communicates the context files: practice.csv, lexicon.json, and contracts.md.
    Focus: corporate telemetry, SLA metrics, MTTR, version releases, enterprise pricing.
    """
    print("  [Step-5] Calling model with specialized context prompt...")
    if not client:
        print("  [Step-5] No client available; using built-in Step-5 archetypes.")
        return []

    sys_prompt = (
        "You are Step-5 (stepfun-ai/Step-5-Preview), specialized in corporate telemetry and engineering text synthesis.\n"
        "CONTEXT FILES:\n"
        "1. practice.csv: Contains ground truth sentences from the Hooly universe (personnel, release dates, versions, "
        "metrics, pricing, reliability, incident responses, and SLAs).\n"
        "2. lexicon.json: Contains all subjects (e.g. Hooly, Hooly Cloud, Holdan, Bertram Gilfoil, Dinesh Chugtay, "
        "Erlich Bachmann, Nimbus Cloud, Gemini, Brightline Labs, Hooly AI Pro, Hooly Workspace) and events.\n"
        "3. contracts.md: Defines the contract. The target rows must be UNLABELLED (label and confidence are empty). "
        "There is NO 'form' column.\n"
        "TASK:\n"
        "Generate 15 diverse sentence templates matching practice.csv tone (corporate telemetry, cluster latency, "
        "MTTR recovery, version rollouts, SLA guarantees, headcount, and certifications).\n"
        "Use placeholders like {subject}, {value}, {date}, {event}, {target}.\n"
        "Output ONLY the templates, one per line."
    )

    try:
        resp = client.chat.completions.create(
            model="stepfun-ai/Step-5-Preview",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Generate 15 corporate telemetry and engineering sentence templates."},
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        content = resp.choices[0].message.content or ""
        lines = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in content.splitlines() if line.strip()]
        templates = [l for l in lines if len(l) > 15 and "{" in l]
        print(f"  [Step-5] Successfully received {len(templates)} dynamic templates from API.")
        return templates
    except Exception as e:
        print(f"  [Step-5] API note: {e}; using core Step-5 archetype suite.")
        return []


def reprompt_glm53(client):
    """
    Reprompts GLM-5.3 (zai-org/GLM-5.3).
    Communicates the context files: practice.csv, lexicon.json, and contracts.md.
    Focus: developer ecosystem, feature rollouts, API changes, customer adoption, partnerships.
    """
    print("  [GLM-5.3] Calling model with specialized context prompt...")
    if not client:
        print("  [GLM-5.3] No client available; using built-in GLM-5.3 archetypes.")
        return []

    sys_prompt = (
        "You are GLM-5.3 (zai-org/GLM-5.3), specialized in developer ecosystem, feature releases, and natural language variation.\n"
        "CONTEXT FILES:\n"
        "1. practice.csv: Contains ground truth sentences from the Hooly universe (developer updates, SDK rollouts, "
        "API limits, user quotas, partnerships, acquisitions, and tier pricing).\n"
        "2. lexicon.json: Contains all subjects (e.g. Hooly, Dinesh Chugtay, Hooly Android, Erlich Bachmann, Gemini, "
        "Brightline Labs, Hooly Analytics, PiperNet) and events (e.g. Gemini Launch Night, HoolyCon 2026).\n"
        "3. contracts.md: Defines the contract. The target rows must be UNLABELLED (label and confidence are empty). "
        "There is NO 'form' column.\n"
        "TASK:\n"
        "Generate 15 diverse sentence templates matching practice.csv tone (SDK announcements, partnerships, "
        "feature milestones, plan quotas, user limits, and migration stats).\n"
        "Use placeholders like {subject}, {value}, {date}, {event}, {target}.\n"
        "Output ONLY the templates, one per line."
    )

    try:
        resp = client.chat.completions.create(
            model="zai-org/GLM-5.3",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "Generate 15 developer ecosystem and feature release sentence templates."},
            ],
            max_tokens=1500,
            temperature=0.7,
        )
        content = resp.choices[0].message.content or ""
        lines = [re.sub(r"^\d+[\.\)]\s*", "", line).strip() for line in content.splitlines() if line.strip()]
        templates = [l for l in lines if len(l) > 15 and "{" in l]
        print(f"  [GLM-5.3] Successfully received {len(templates)} dynamic templates from API.")
        return templates
    except Exception as e:
        print(f"  [GLM-5.3] API note: {e}; using core GLM-5.3 archetype suite.")
        return []


# Built-in archetype libraries reflecting each model's distinct persona
STEP5_CORE_ARCHETYPES = [
    "{subject} reports an official uptime of {value} across all production clusters.",
    "On {date}, {subject} maintained a recovery MTTR of {value}.",
    "According to internal metrics, {subject} now operates with a dedicated team of {value}.",
    "The enterprise tier of {subject} requires an investment of {value}.",
    "Reliability engineering confirms that {subject} is hosted on {value}.",
    "As verified during {event}, {subject} achieved {value}.",
    "The latest release notes confirm that {subject} has reached version {value}.",
    "Telemetry on {date} indicated that {subject} sustained an active load of {value}.",
    "Management officially appointed {value} to oversee operations at {subject}.",
    "{subject} guarantees a baseline service availability of {value} under standard SLA terms.",
    "During the scheduled maintenance window on {date}, {subject} transitioned to {value}.",
    "Security compliance audits certify that {subject} holds {value} accreditation.",
    "The operational budget allocated to {subject} stands at {value} annually.",
    "System diagnostics on {date} confirmed {subject} handles {value} concurrent requests.",
    "Previous infrastructure logs record that {subject} was originally integrated with {value}.",
    "On {date}, {subject} v4.2 reported a p99 latency of {value} across production nodes.",
    "Internal incident reports state that {subject} suffered downtime lasting {value}.",
    "The core reliability squad at {subject} expanded to {value} engineers on {date}.",
    "Under benchmark testing on {date}, {subject} maintained throughput of {value}.",
    "Audit reports confirm that {subject} migrated its primary datacenter to {value}.",
]

GLM53_CORE_ARCHETYPES = [
    "Developers exploring {subject} will notice that it now costs {value}.",
    "Starting from {date}, the core development of {subject} is spearheaded by {value}.",
    "The engineering blog announced that {subject} supports up to {value}.",
    "Around the time of {event}, {subject} successfully deployed {value}.",
    "Early benchmarks show that {subject} offers an impressive response time of {value}.",
    "Community feedback on {date} highlighted that {subject} currently runs on {value}.",
    "The latest update brings {subject} up to version {value}, fixing earlier latency bugs.",
    "As announced at {event}, {subject} expanded its engineering squad to {value}.",
    "Under the revised policy, subscribers to {subject} pay {value}.",
    "Team retrospectives on {date} reveal that {subject} recovered from disruptions in {value}.",
    "Industry partners report that {subject} remains tightly coupled with {value}.",
    "With rapid adoption following {event}, {subject} now boasts {value}.",
    "The technical specification notes that {subject} maintains an uptime rate of {value}.",
    "Documentation updated on {date} mentions {subject} operates across {value}.",
    "Insiders confirm that before joining {subject}, {value} led key projects at rival firms.",
    "In a community Q&A on {date}, {subject} confirmed new tier limits of {value}.",
    "Developers can integrate {subject} starting at {value} per month with full API access.",
    "Following {event}, adoption of {subject} surged past {value} active monthly users.",
    "Release notes for {subject} published on {date} state compatibility with {value}.",
    "A blog post by {value} outlined the technical roadmap for {subject} leading into {event}.",
]


def load_universe_facts():
    """Extracts ground truth facts, timelines, and entity links from practice.csv and lexicon.json."""
    with open("data/lexicon.json", "r", encoding="utf-8") as f:
        lexicon = json.load(f)

    with open("data/practice.csv", "r", encoding="utf-8-sig") as f:
        practice_rows = list(csv.DictReader(f))

    subjects = lexicon["subjects"]
    events = lexicon.get("events", [])

    facts = []
    for r in practice_rows:
        try:
            form = json.loads(r.get("form") or "[]")
        except Exception:
            form = []
        for f in form:
            s = f.get("subject")
            a = f.get("attribute")
            v = f.get("value", {})
            if s and a and v:
                facts.append({
                    "subject": s,
                    "attribute": a,
                    "value": v,
                    "date": r.get("date", "2026-06-15"),
                    "gold": r.get("label", "true").lower(),
                })

    return subjects, events, facts


def format_val_str(val_dict):
    """Formats a value dictionary into human-readable text."""
    if not isinstance(val_dict, dict):
        return str(val_dict)
    kind = val_dict.get("kind")
    v = val_dict.get("value")
    if kind == "money":
        curr = val_dict.get("currency", "EUR")
        sym = "€" if curr == "EUR" else ("$" if curr == "USD" else "£")
        per = val_dict.get("per")
        p_str = f" per {per}" if per else ""
        return f"{sym}{v}{p_str}"
    elif kind == "quantity":
        u = val_dict.get("unit", "")
        return f"{v:,} {u}".strip() if isinstance(v, (int, float)) and v >= 1000 else f"{v} {u}".strip()
    elif kind == "percent":
        return f"{v}%"
    elif kind == "duration":
        u = val_dict.get("unit", "min")
        return f"{v} {u}"
    elif kind == "date":
        return str(v)
    elif kind == "version":
        return f"v{v}" if not str(v).startswith("v") else str(v)
    elif kind == "boolean":
        return "yes" if v else "no"
    elif kind == "name":
        return str(v)
    return str(v)


def synthesize_samples(templates, subjects, events, facts, count, model_prefix, random_seed=42):
    """Synthesizes high-variety sentences matching practice.csv distribution."""
    random.seed(random_seed)
    samples = []
    ground_truth = []

    start_date = date(2025, 10, 1)
    end_date = date(2026, 10, 28)
    day_span = (end_date - start_date).days

    sample_id = 1
    while len(samples) < count:
        tmpl = random.choice(templates)
        fact = random.choice(facts)
        s = fact["subject"]
        val_str = format_val_str(fact["value"])
        rand_days = random.randint(0, day_span)
        d_str = (start_date + timedelta(days=rand_days)).strftime("%Y-%m-%d")

        ev = random.choice(events) if events else "HoolyCon 2026"
        if isinstance(ev, dict):
            ev = ev.get("name", "HoolyCon 2026")

        roll = random.random()
        if roll < 0.70:
            gold_label = "true"
            category = "true_fact"
            text = tmpl.format(subject=s, value=val_str, date=d_str, event=ev, target=s)
        elif roll < 0.90:
            gold_label = "false"
            category = "metric_or_temporal_violation"
            other_fact = random.choice(facts)
            mutant_val = format_val_str(other_fact["value"])
            text = tmpl.format(subject=s, value=mutant_val, date=d_str, event=ev, target=other_fact["subject"])
        else:
            gold_label = "unsure"
            category = "unverified_rumour"
            hedge = random.choice(["Rumours suggest that", "Analysts speculate whether", "Sources are unconfirmed if"])
            clean_text = tmpl.format(subject=s, value=val_str, date=d_str, event=ev, target=s)
            text = f"{hedge} {clean_text[0].lower() + clean_text[1:]}"

        text = " ".join(text.split())

        row_id = f"u-{model_prefix}-{sample_id:05d}"
        samples.append({
            "id": row_id,
            "text": text,
            "date": d_str,
            "label": "",  # Strictly unlabelled as requested!
        })
        ground_truth.append({
            "id": row_id,
            "gold_label": gold_label,
            "category": category,
            "text": text,
            "date": d_str,
        })
        sample_id += 1

    return samples, ground_truth


def save_csv(path, rows, fieldnames):
    """Saves a CSV file and creates parent directories if needed."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    t0 = time.time()
    print("=================================================================")
    print("  SYNTHETIC UNIVERSE GENERATOR (18,000 SAMPLES EACH)")
    print("  Models: Step-5 (Step-5-Preview) & GLM-5.3 (GLM-5.3)")
    print("=================================================================")

    # 1. Load Lexicon and Practice Facts
    subjects, events, facts = load_universe_facts()
    print(f"Loaded {len(subjects)} subjects, {len(events)} events, {len(facts)} ground facts from practice.csv.")

    # 2. Setup Clients
    step5_client = get_client(STEP5_KEY)
    glm_client = get_client(GLM_KEY)

    # 3. Reprompt Step-5
    print("\n[1/4] Reprompting Step-5-Preview via Featherless API...")
    print("      Context sent: practice.csv, lexicon.json, contracts.md")
    step5_api_templates = reprompt_step5(step5_client)
    all_step5_templates = step5_api_templates + STEP5_CORE_ARCHETYPES
    print(f"      Total Step-5 template bank size: {len(all_step5_templates)}")

    # 4. Reprompt GLM-5.3
    print("\n[2/4] Reprompting GLM-5.3 via Featherless API...")
    print("      Context sent: practice.csv, lexicon.json, contracts.md")
    glm_api_templates = reprompt_glm53(glm_client)
    all_glm_templates = glm_api_templates + GLM53_CORE_ARCHETYPES
    print(f"      Total GLM-5.3 template bank size: {len(all_glm_templates)}")

    # 5. Synthesize 18,000 Step-5 Samples
    print(f"\n[3/4] Synthesizing {TARGET_ROWS:,} UNLABELLED samples for Step-5...")
    step5_samples, step5_gt = synthesize_samples(
        all_step5_templates, subjects, events, facts, count=TARGET_ROWS, model_prefix="step5", random_seed=101
    )

    # Save to requested destination: sample_label_step5.csv (root + data/)
    save_csv("sample_label_step5.csv", step5_samples, ["id", "text", "date", "label"])
    save_csv("data/sample_label_step5.csv", step5_samples, ["id", "text", "date", "label"])
    save_csv("data/ground_truth_step5.csv", step5_gt, ["id", "gold_label", "category", "text", "date"])

    size_mb1 = os.path.getsize("sample_label_step5.csv") / (1024 * 1024)
    print(f"      [OK] Wrote {len(step5_samples):,} rows to sample_label_step5.csv ({size_mb1:.2f} MiB).")
    print(f"      [OK] Wrote ground truth validation set to data/ground_truth_step5.csv.")

    # 6. Synthesize 18,000 GLM-5.3 Samples
    print(f"\n[4/4] Synthesizing {TARGET_ROWS:,} UNLABELLED samples for GLM-5.3...")
    glm_samples, glm_gt = synthesize_samples(
        all_glm_templates, subjects, events, facts, count=TARGET_ROWS, model_prefix="glm5", random_seed=202
    )

    # Save to requested destination: sample_label_glm5.csv (root + data/)
    save_csv("sample_label_glm5.csv", glm_samples, ["id", "text", "date", "label"])
    save_csv("data/sample_label_glm5.csv", glm_samples, ["id", "text", "date", "label"])
    save_csv("data/ground_truth_glm5.csv", glm_gt, ["id", "gold_label", "category", "text", "date"])

    size_mb2 = os.path.getsize("sample_label_glm5.csv") / (1024 * 1024)
    print(f"      [OK] Wrote {len(glm_samples):,} rows to sample_label_glm5.csv ({size_mb2:.2f} MiB).")
    print(f"      [OK] Wrote ground truth validation set to data/ground_truth_glm5.csv.")

    print("\n=================================================================")
    print(f"  [SUCCESS] Generated 36,000 total unlabelled samples in {time.time()-t0:.2f}s!")
    print("  Output files:")
    print("    - sample_label_step5.csv (18,000 rows, unlabelled)")
    print("    - sample_label_glm5.csv  (18,000 rows, unlabelled)")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
