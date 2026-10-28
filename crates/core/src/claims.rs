//! Evidence-backed candidate construction and deterministic maximal marginal relevance.
//!
//! Observation dates establish ordering, never exact transition boundaries. Current-date
//! claims are restricted to immutable historical dates; mutable values are used only
//! for historical changes or an event whose exact date has independent evidence.
use crate::model::{Claim, Evidence, GenerationReport, InputRow, Prediction};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

const AS_OF: &str = "2026-10-29";

struct Candidate {
    claim: Claim,
    fingerprint: u128,
    redundancy: f64,
    selected: bool,
}

pub fn generate_claims(
    rows: &[InputRow],
    predictions: &[Prediction],
    lexicon: &Value,
    limit: usize,
) -> Result<GenerationReport, String> {
    if limit > 1_000 {
        return Err("At most 1,000 generated claims are supported".into());
    }
    let subjects = lexicon["subjects"]
        .as_array()
        .ok_or("Lexicon has no subjects array")?;
    let mut names = BTreeMap::new();
    let mut attributes = BTreeMap::<String, BTreeSet<String>>::new();
    for subject in subjects {
        let name = subject["name"]
            .as_str()
            .ok_or("Lexicon subject has no name")?;
        names.insert(name.to_lowercase(), name.to_string());
        if let Some(aliases) = subject["aliases"].as_array() {
            for alias in aliases.iter().filter_map(Value::as_str) {
                names.insert(alias.to_lowercase(), name.to_string());
            }
        }
        attributes.insert(
            name.to_string(),
            subject["attributes"]
                .as_array()
                .ok_or("Lexicon subject has no attributes")?
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect(),
        );
    }
    let mut observations = BTreeMap::<String, Evidence>::new();
    let mut insert = |mut evidence: Evidence| {
        if evidence.label != "true" || evidence.date.as_str() > AS_OF {
            return;
        }
        let Some(name) = names.get(&evidence.fact.subject.to_lowercase()) else {
            return;
        };
        if !attributes
            .get(name)
            .is_some_and(|a| a.contains(&evidence.fact.attribute))
        {
            return;
        }
        let Some(value) = exact_value(&evidence.fact.value) else {
            return;
        };
        evidence.fact.subject.clone_from(name);
        evidence.fact.value = value;
        let key = format!(
            "{}\0{}\0{}\0{}",
            evidence.row_id, name, evidence.fact.attribute, evidence.fact.value
        );
        observations.entry(key).or_insert(evidence);
    };
    for row in rows.iter().filter(|row| row.label == "true") {
        for fact in &row.form {
            insert(Evidence {
                row_id: row.id.clone(),
                text: row.text.clone(),
                date: row.date.clone(),
                label: "true".into(),
                fact: fact.clone(),
            });
        }
    }
    for prediction in predictions {
        // Only supplied known labels can license newly extracted evidence. Model
        // predictions alone never turn into trusted facts.
        if prediction.known_label.as_deref() == Some("true") {
            for fact in &prediction.facts {
                insert(Evidence {
                    row_id: prediction.id.clone(),
                    text: prediction.text.clone(),
                    date: prediction.date.clone(),
                    label: "true".into(),
                    fact: fact.clone(),
                });
            }
        }
        for evidence in &prediction.evidence {
            insert(evidence.clone());
        }
    }
    let mut groups = BTreeMap::<(String, String), Vec<Evidence>>::new();
    for evidence in observations.into_values() {
        groups
            .entry((
                evidence.fact.subject.clone(),
                evidence.fact.attribute.clone(),
            ))
            .or_default()
            .push(evidence);
    }
    for values in groups.values_mut() {
        values.sort_by(|a, b| (&a.date, &a.row_id).cmp(&(&b.date, &b.row_id)));
    }
    let source_texts: BTreeSet<String> = rows
        .iter()
        .map(|row| row.text.trim().to_lowercase())
        .collect();
    let mut forms = BTreeSet::new();
    let mut texts = BTreeSet::new();
    let mut candidates = Vec::new();
    let mut add =
        |kind: &str, text: String, form: Value, evidence: Vec<Evidence>, confidence: f64| {
            if text.chars().count() > 300 || source_texts.contains(&text.trim().to_lowercase()) {
                return;
            }
            let key = format!("{kind}\0{form}");
            if !forms.insert(key) || !texts.insert(text.clone()) {
                return;
            }
            let fingerprint = fingerprint(&text, kind);
            candidates.push(Candidate {
                claim: Claim {
                    id: String::new(),
                    kind: kind.to_string(),
                    text,
                    form,
                    confidence,
                    evidence,
                },
                fingerprint,
                redundancy: 0.0,
                selected: false,
            });
        };

    // A historical change says only that one exact value held and another held
    // later. It makes no assumption about the day of the transition.
    for ((subject, attribute), observations) in &groups {
        for (i, first) in observations.iter().enumerate() {
            for second in &observations[i + 1..] {
                if first.date >= second.date
                    || same_value(&first.fact.value, &second.fact.value)
                    || !compatible(&first.fact.value, &second.fact.value)
                {
                    continue;
                }
                // Conflicting values on the same page date cannot prove a transition.
                if has_day_conflict(observations, first) || has_day_conflict(observations, second) {
                    continue;
                }
                let (Some(from), Some(to)) = (
                    render_value(&first.fact.value),
                    render_value(&second.fact.value),
                ) else {
                    continue;
                };
                let words = attribute.replace('_', " ");
                let text = if first.fact.value["kind"] == "boolean" {
                    format!("{subject} changed {words} from {from} {words} to {to} {words}.")
                } else {
                    format!("{subject} changed {words} from {from} to {to}.")
                };
                add(
                    "change",
                    text,
                    json!({"subject":subject,"attribute":attribute,"from":first.fact.value,"to":second.fact.value}),
                    vec![first.clone(), second.clone()],
                    0.92,
                );
            }
        }
    }

    let immutable: Vec<Evidence> = groups
        .iter()
        .filter_map(|((subject, attribute), values)| {
            immutable_observation(subject, attribute, values, lexicon)
        })
        .collect();
    for evidence in &immutable {
        let fact = &evidence.fact;
        let Some(value) = render_value(&fact.value) else {
            continue;
        };
        add(
            "fact",
            format!(
                "{} {} is {value}.",
                fact.subject,
                fact.attribute.replace('_', " ")
            ),
            json!({"subject":fact.subject,"attribute":fact.attribute,"value":fact.value}),
            vec![evidence.clone()],
            0.96,
        );
    }
    // Each unordered pair is emitted once: reversing a comparison is not used
    // as padding. Immutable historical dates remain valid on the as-of date.
    for (i, left) in immutable.iter().enumerate() {
        for right in &immutable[i + 1..] {
            let a = left.fact.value["value"].as_str().unwrap_or_default();
            let b = right.fact.value["value"].as_str().unwrap_or_default();
            if a.len() != b.len() {
                continue;
            }
            let (op, phrase) = match a.cmp(b) {
                std::cmp::Ordering::Less => ("lt", "is earlier than"),
                std::cmp::Ordering::Greater => ("gt", "is later than"),
                std::cmp::Ordering::Equal => ("eq", "is on the same day as"),
            };
            add(
                "compare",
                format!(
                    "{} {} {phrase} {} {}.",
                    left.fact.subject,
                    left.fact.attribute.replace('_', " "),
                    right.fact.subject,
                    right.fact.attribute.replace('_', " ")
                ),
                json!({"left":{"subject":left.fact.subject,"attribute":left.fact.attribute},"right":{"subject":right.fact.subject,"attribute":right.fact.attribute},"op":op}),
                vec![left.clone(), right.clone()],
                0.95,
            );
        }
    }

    // Event dates must have happened and be confirmed by a later observation.
    let event_names: BTreeSet<&str> = lexicon["events"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect();
    for event_date in immutable
        .iter()
        .filter(|e| e.fact.attribute == "date" && event_names.contains(e.fact.subject.as_str()))
    {
        let Some(date) = event_date.fact.value["value"]
            .as_str()
            .filter(|d| d.len() == 10)
        else {
            continue;
        };
        for observations in groups.values() {
            for evidence in observations.iter().filter(|e| e.date == date) {
                if has_day_conflict(observations, evidence)
                    || evidence.fact.subject == event_date.fact.subject
                {
                    continue;
                }
                // A value which names another date would add an independent date
                // to the sentence; omit it under the strict one-date rule.
                if evidence.fact.value["kind"] == "date" {
                    continue;
                }
                let Some(value) = render_value(&evidence.fact.value) else {
                    continue;
                };
                let attribute = evidence.fact.attribute.replace('_', " ");
                let value_text = if evidence.fact.value["kind"] == "boolean" {
                    format!("{value} {attribute}")
                } else {
                    value
                };
                add(
                    "at_event",
                    format!(
                        "{} {attribute} was {value_text} at {}.",
                        evidence.fact.subject, event_date.fact.subject
                    ),
                    json!({"subject":evidence.fact.subject,"attribute":evidence.fact.attribute,"event":event_date.fact.subject,"value":evidence.fact.value}),
                    vec![evidence.clone(), event_date.clone()],
                    0.94,
                );
            }
        }
    }

    // Relations are proven at a shared observation date. No guessed validity
    // interval connects unrelated observations.
    for observations in groups.values() {
        for link in observations
            .iter()
            .filter(|e| e.fact.value["kind"] == "name")
        {
            let Some(target_name) = link.fact.value["value"]
                .as_str()
                .and_then(|v| names.get(&v.to_lowercase()))
            else {
                continue;
            };
            for target_observations in groups.values() {
                for target in target_observations
                    .iter()
                    .filter(|e| &e.fact.subject == target_name && e.date == link.date)
                {
                    if has_day_conflict(observations, link)
                        || has_day_conflict(target_observations, target)
                    {
                        continue;
                    }
                    let Some(value) = render_value(&target.fact.value) else {
                        continue;
                    };
                    let attribute = target.fact.attribute.replace('_', " ");
                    let value_text = if target.fact.value["kind"] == "boolean" {
                        format!("{value} {attribute}")
                    } else {
                        value
                    };
                    add(
                        "relation",
                        format!(
                            "The {} of {} has {attribute} {value_text}.",
                            link.fact.attribute.replace('_', " "),
                            link.fact.subject
                        ),
                        json!({"subject":link.fact.subject,"link":link.fact.attribute,"target":target_name,"attribute":target.fact.attribute,"value":target.fact.value}),
                        vec![link.clone(), target.clone()],
                        0.93,
                    );
                }
            }
        }
    }

    let candidate_count = candidates.len();
    let mut claims = Vec::with_capacity(limit.min(candidate_count));
    let reserved: BTreeSet<&str> = rows.iter().map(|r| r.id.as_str()).collect();
    let mut counter = 1;
    for _ in 0..limit.min(candidate_count) {
        let best = candidates
            .iter()
            .enumerate()
            .filter(|(_, c)| !c.selected)
            .max_by(|(ia, a), (ib, b)| {
                let score_a = 0.78 * a.claim.confidence - 0.22 * a.redundancy;
                let score_b = 0.78 * b.claim.confidence - 0.22 * b.redundancy;
                score_a.total_cmp(&score_b).then_with(|| ib.cmp(ia))
            })
            .map(|(i, _)| i)
            .ok_or("MMR selection exhausted candidates")?;
        candidates[best].selected = true;
        let selected_fingerprint = candidates[best].fingerprint;
        let mut claim = candidates[best].claim.clone();
        loop {
            claim.id = format!("jev-claim-{counter:04}");
            counter += 1;
            if !reserved.contains(claim.id.as_str()) {
                break;
            }
        }
        claims.push(claim);
        for candidate in candidates.iter_mut().filter(|c| !c.selected) {
            let union = (candidate.fingerprint | selected_fingerprint).count_ones();
            let similarity = if union == 0 {
                0.0
            } else {
                (candidate.fingerprint & selected_fingerprint).count_ones() as f64 / union as f64
            };
            candidate.redundancy = candidate.redundancy.max(similarity);
        }
    }
    let mut notes = vec![
        "MMR uses 0.78 evidence confidence and 0.22 maximum token redundancy; deterministic selection, no runtime LLM.".into(),
        "Only labelled-true observations license candidates. Model-predicted true rows are not trusted generation evidence.".into(),
        "Current facts and comparisons use confirmed immutable historical dates. Mutable values use ordered historical observations or independently dated events; page dates do not establish exact change boundaries.".into(),
        "Confidence values are engineering estimates, not independently calibrated probabilities or a guarantee of the hidden referee's truth judgement.".into(),
    ];
    if claims.len() < limit {
        notes.push(format!("Only {} distinct evidenced claims available; requested {limit}. No duplicate or unsupported padding was added.",claims.len()));
    }
    Ok(GenerationReport {
        claims,
        candidate_count,
        notes,
    })
}

fn exact_value(value: &Value) -> Option<Value> {
    let object = value.as_object()?;
    if object
        .get("op")
        .and_then(Value::as_str)
        .is_some_and(|op| op != "eq")
    {
        return None;
    }
    let mut value = value.clone();
    value.as_object_mut()?.remove("op");
    render_value(&value)?;
    Some(value)
}

fn immutable_observation(
    subject: &str,
    attribute: &str,
    observations: &[Evidence],
    lexicon: &Value,
) -> Option<Evidence> {
    let is_event = lexicon["events"]
        .as_array()
        .is_some_and(|v| v.iter().any(|e| e == subject));
    let historical = [
        "joined",
        "launched",
        "founded",
        "opened",
        "announced",
        "released",
        "beta_date",
        "general_availability_date",
        "training_data_cutoff",
    ];
    if !(historical.contains(&attribute) || attribute == "date" && is_event) {
        return None;
    }
    let dates: Vec<&Evidence> = observations
        .iter()
        .filter(|e| e.fact.value["kind"] == "date")
        .collect();
    let selected = dates
        .iter()
        .filter(|e| {
            let date = e.fact.value["value"].as_str().unwrap_or_default();
            // A forecast does not prove the historical occurrence. Partial dates are
            // allowed only if the whole interval precedes the observation's day.
            !date.is_empty()
                && date <= e.date.as_str()
                && date <= AS_OF
                && (date.len() == 10 || !e.date.starts_with(date))
        })
        .max_by(|a, b| {
            a.fact.value["value"]
                .as_str()
                .unwrap_or_default()
                .len()
                .cmp(&b.fact.value["value"].as_str().unwrap_or_default().len())
                .then_with(|| a.date.cmp(&b.date))
        })?;
    let chosen_date = selected.fact.value["value"].as_str()?;
    // Earlier forecasts may differ; actual past observations must agree at all
    // precisions. An actual conflicting past date excludes the key entirely.
    if dates.iter().any(|other| {
        let date = other.fact.value["value"].as_str().unwrap_or_default();
        date <= other.date.as_str()
            && !date.starts_with(chosen_date)
            && !chosen_date.starts_with(date)
    }) {
        return None;
    }
    Some((*selected).clone())
}

fn has_day_conflict(observations: &[Evidence], current: &Evidence) -> bool {
    observations
        .iter()
        .any(|e| e.date == current.date && !same_value(&e.fact.value, &current.fact.value))
}

fn compatible(left: &Value, right: &Value) -> bool {
    left["kind"] == right["kind"]
        && left["currency"] == right["currency"]
        && left["per"] == right["per"]
        && (left["unit"] == right["unit"]
            || numeric_value(left)
                .zip(numeric_value(right))
                .is_some_and(|(a, b)| a.0 == b.0))
}

fn same_value(left: &Value, right: &Value) -> bool {
    if left == right {
        return true;
    }
    if left["kind"] == "date"
        && right["kind"] == "date"
        && let (Some(a), Some(b)) = (left["value"].as_str(), right["value"].as_str())
    {
        return a.starts_with(b) || b.starts_with(a);
    }
    numeric_value(left)
        .zip(numeric_value(right))
        .is_some_and(|(a, b)| a.0 == b.0 && a.1 == b.1)
}

fn numeric_value(value: &Value) -> Option<(String, f64)> {
    let number = value["value"].as_f64()?;
    let kind = value["kind"].as_str()?;
    let unit = value["unit"].as_str().unwrap_or_default();
    let (dimension, multiplier) = match (kind, unit) {
        ("quantity", "B") => ("data", 1.0),
        ("quantity", "KB") => ("data", 1_000.0),
        ("quantity", "MB") => ("data", 1_000_000.0),
        ("quantity", "GB") => ("data", 1_000_000_000.0),
        ("quantity", "TB") => ("data", 1_000_000_000_000.0),
        ("duration", "ms") => ("time", 0.001),
        ("duration", "s") => ("time", 1.0),
        ("duration", "min") => ("time", 60.0),
        ("duration", "h") => ("time", 3600.0),
        ("duration", "day") => ("time", 86400.0),
        ("duration", "week") => ("time", 604800.0),
        _ => (unit, 1.0),
    };
    Some((
        format!("{kind}:{dimension}:{}:{}", value["currency"], value["per"]),
        number * multiplier,
    ))
}

fn render_value(value: &Value) -> Option<String> {
    let kind = value["kind"].as_str()?;
    let numeric = || value["value"].as_number().map(ToString::to_string);
    match kind {
        "quantity" => Some(format!(
            "{} {}",
            group_number(&numeric()?),
            value["unit"].as_str()?
        )),
        "duration" => Some(format!("{} {}", numeric()?, value["unit"].as_str()?)),
        "money" => Some(format!(
            "{} {}{}",
            value["currency"].as_str()?,
            numeric()?,
            value["per"]
                .as_str()
                .map(|p| format!(" per {p}"))
                .unwrap_or_default()
        )),
        "percent" => Some(format!("{}%", numeric()?)),
        "date" => value["value"].as_str().map(str::to_string),
        "version" => value["value"].as_str().map(|v| format!("v{v}")),
        "name" => value["value"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
            .map(str::to_string),
        "boolean" => value["value"]
            .as_bool()
            .map(|v| if v { "yes" } else { "not" }.to_string()),
        _ => None,
    }
}

fn group_number(value: &str) -> String {
    let (integer, fraction) = value.split_once('.').map_or((value, ""), |(a, b)| (a, b));
    let mut output = String::new();
    for (i, c) in integer.chars().enumerate() {
        if i > 0 && (integer.len() - i).is_multiple_of(3) {
            output.push(',');
        }
        output.push(c);
    }
    if !fraction.is_empty() {
        output.push('.');
        output.push_str(fraction);
    }
    output
}

fn fingerprint(text: &str, kind: &str) -> u128 {
    text.split(|c: char| !c.is_alphanumeric())
        .chain(std::iter::once(kind))
        .filter(|s| s.len() > 2)
        .fold(0, |bits, token| {
            let hash = token.bytes().fold(1469598103934665603_u64, |hash, b| {
                (hash ^ b.to_ascii_lowercase() as u64).wrapping_mul(1099511628211)
            });
            bits | (1_u128 << (hash % 128))
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Fact;
    fn row(id: &str, date: &str, label: &str, value: f64) -> InputRow {
        InputRow {
            id: id.into(),
            text: format!("source {id}"),
            date: date.into(),
            label: label.into(),
            form: vec![Fact {
                subject: "A".into(),
                attribute: "users".into(),
                value: json!({"kind":"quantity","value":value,"unit":"user"}),
            }],
        }
    }
    fn lexicon() -> Value {
        json!({"subjects":[{"name":"A","aliases":[],"attributes":["users"]}],"events":[]})
    }
    #[test]
    fn changes_require_true_evidence_and_strict_chronology() {
        let rows = vec![
            row("a", "2026-01-01", "true", 1.0),
            row("b", "2026-02-01", "true", 2.0),
            row("c", "2026-03-01", "false", 3.0),
        ];
        let report = generate_claims(&rows, &[], &lexicon(), 1000).unwrap();
        assert_eq!(report.claims.len(), 1);
        assert_eq!(report.claims[0].kind, "change");
        assert_eq!(report.claims[0].evidence.len(), 2);
        assert!(report.claims[0].evidence.iter().all(|e| e.label == "true"));
    }
    #[test]
    fn conflicting_same_day_values_do_not_prove_a_change() {
        let rows = vec![
            row("a", "2026-01-01", "true", 1.0),
            row("b", "2026-01-01", "true", 2.0),
            row("c", "2026-02-01", "true", 3.0),
        ];
        assert!(
            generate_claims(&rows, &[], &lexicon(), 1000)
                .unwrap()
                .claims
                .is_empty()
        );
    }
    #[test]
    fn equivalent_units_and_partial_dates_do_not_count_as_changes() {
        assert!(same_value(
            &json!({"kind":"quantity","value":1,"unit":"TB"}),
            &json!({"kind":"quantity","value":1000,"unit":"GB"})
        ));
        assert!(same_value(
            &json!({"kind":"date","value":"2026-01"}),
            &json!({"kind":"date","value":"2026-01-12"})
        ));
        assert_eq!(group_number("2026"), "2,026");
    }

    #[test]
    fn practice_produces_one_thousand_distinct_evidenced_claims() {
        let rows = crate::io::read_csv(include_str!("../../../data/practice.csv")).unwrap();
        let lexicon = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
        let report = generate_claims(&rows, &[], &lexicon, 1_000).unwrap();
        assert_eq!(report.claims.len(), 1_000);
        let forms: BTreeSet<_> = report
            .claims
            .iter()
            .map(|c| format!("{}:{}", c.kind, c.form))
            .collect();
        assert_eq!(forms.len(), 1_000);
        assert!(
            report
                .claims
                .iter()
                .all(|c| !c.evidence.is_empty() && c.evidence.iter().all(|e| e.label == "true"))
        );
        let original: BTreeSet<_> = rows.iter().map(|r| r.text.as_str()).collect();
        assert!(
            report
                .claims
                .iter()
                .all(|c| !original.contains(c.text.as_str()))
        );
    }
}
