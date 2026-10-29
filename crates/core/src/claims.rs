//! Evidence-backed candidate construction and deterministic maximal marginal relevance.
//!
//! Observation dates establish ordering, never exact transition boundaries. Current-date
//! claims are restricted to immutable historical dates; mutable values are used only
//! for historical changes or an event whose exact date has independent evidence.
use crate::model::{Claim, Evidence, GenerationReport, InputRow, Prediction};
use crate::temporal::explicit_scope;
use crate::typed::numeric;
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
        if evidence.label != "true" || effective_window(&evidence).is_none() {
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
    let windows: BTreeMap<_, _> = groups
        .values()
        .flatten()
        .filter_map(|e| effective_window(e).map(|w| (e.row_id.clone(), w)))
        .collect();
    for values in groups.values_mut() {
        values.sort_by(|a, b| {
            window_start(a, &windows)
                .cmp(window_start(b, &windows))
                .then(a.row_id.cmp(&b.row_id))
        });
    }
    let source_texts: BTreeSet<String> = rows
        .iter()
        .map(|row| normalize_claim_text(&row.text))
        .chain(
            predictions
                .iter()
                .map(|row| normalize_claim_text(&row.text)),
        )
        .collect();
    let mut forms = BTreeSet::new();
    let mut texts = BTreeSet::new();
    let mut candidates = Vec::new();
    let mut add =
        |kind: &str, text: String, form: Value, evidence: Vec<Evidence>, confidence: f64| {
            if text.chars().count() > 300 || source_texts.contains(&normalize_claim_text(&text)) {
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
                if window_end(first, &windows) >= window_start(second, &windows)
                    || same_value(&first.fact.value, &second.fact.value)
                    || !compatible(&first.fact.value, &second.fact.value)
                {
                    continue;
                }
                // Conflicting values on the same page date cannot prove a transition.
                if has_window_conflict(observations, first, &windows)
                    || has_window_conflict(observations, second, &windows)
                {
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
                    // The full attribute is required in the sentence. Keep it
                    // outside the value sides: names such as end_to_end must not
                    // introduce another change delimiter inside those sides.
                    format!("{subject} {words} changed from {from} to {to}.")
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
    let mut current: BTreeMap<(String, String, String), Evidence> = immutable
        .iter()
        .map(|e| {
            (
                (
                    e.fact.subject.clone(),
                    e.fact.attribute.clone(),
                    String::new(),
                ),
                e.clone(),
            )
        })
        .collect();
    for (key, observations) in &groups {
        for evidence in observations.iter().filter(|e| {
            window_end(e, &windows) == AS_OF && !has_window_conflict(observations, e, &windows)
        }) {
            let channel = if evidence.fact.value["kind"] == "money" {
                format!(
                    "{}:{}",
                    evidence.fact.value["currency"], evidence.fact.value["per"]
                )
            } else {
                String::new()
            };
            current
                .entry((key.0.clone(), key.1.clone(), channel))
                .or_insert_with(|| evidence.clone());
        }
    }
    let current: Vec<_> = current.into_values().collect();
    let mut reference_channels: BTreeMap<(&str, &str), usize> = BTreeMap::new();
    for e in &current {
        *reference_channels
            .entry((&e.fact.subject, &e.fact.attribute))
            .or_default() += 1;
    }
    for evidence in &current {
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
    for (i, left) in current.iter().enumerate() {
        for right in &current[i + 1..] {
            // Reference-only comparisons cannot choose between several active
            // currency/period offers. Value-bearing facts remain unambiguous.
            if reference_channels
                .get(&(left.fact.subject.as_str(), left.fact.attribute.as_str()))
                .copied()
                .unwrap_or(0)
                > 1
                || reference_channels
                    .get(&(right.fact.subject.as_str(), right.fact.attribute.as_str()))
                    .copied()
                    .unwrap_or(0)
                    > 1
            {
                continue;
            }
            let Some((op, phrase)) = comparison_phrase(&left.fact.value, &right.fact.value) else {
                continue;
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
    for event_date in current
        .iter()
        .filter(|e| e.fact.attribute == "date" && event_names.contains(e.fact.subject.as_str()))
    {
        let Some(date) = event_date.fact.value["value"]
            .as_str()
            .filter(|d| d.len() == 10 && *d <= AS_OF)
        else {
            continue;
        };
        for observations in groups.values() {
            for evidence in observations
                .iter()
                .filter(|e| window_start(e, &windows) <= date && date <= window_end(e, &windows))
            {
                if has_window_conflict(observations, evidence, &windows)
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
                for target in target_observations.iter().filter(|e| {
                    &e.fact.subject == target_name && windows_overlap(e, link, &windows)
                }) {
                    if has_window_conflict(observations, link, &windows)
                        || has_window_conflict(target_observations, target, &windows)
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
    let reserved: BTreeSet<&str> = rows
        .iter()
        .map(|r| r.id.as_str())
        .chain(predictions.iter().map(|r| r.id.as_str()))
        .collect();
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
        "Current facts and comparisons require an explicit validity window covering the as-of date or a confirmed immutable historical date. Historical joins and changes use validity windows; page dates alone do not establish exact change boundaries.".into(),
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

fn normalize_claim_text(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
        .trim_end_matches(['.', '!', '?', ' '])
        .to_string()
}

fn immutable_observation(
    subject: &str,
    attribute: &str,
    observations: &[Evidence],
    lexicon: &Value,
) -> Option<Evidence> {
    // A scoped statement cannot license persistence outside its declared range,
    // even for a field whose name often denotes an immutable historical date.
    if observations
        .iter()
        .any(|e| explicit_scope(&e.text).is_some())
    {
        return None;
    }
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

type Windows = BTreeMap<String, (String, String)>;

fn effective_window(evidence: &Evidence) -> Option<(String, String)> {
    let (start, end) = if let Some(scope) = explicit_scope(&evidence.text) {
        (scope.start_inclusive, scope.end_inclusive)
    } else {
        (evidence.date.clone(), evidence.date.clone())
    };
    if start.as_str() > AS_OF {
        return None;
    }
    Some((start, end.as_str().min(AS_OF).to_owned()))
}
fn window_start<'a>(e: &'a Evidence, windows: &'a Windows) -> &'a str {
    windows
        .get(&e.row_id)
        .map_or(e.date.as_str(), |w| w.0.as_str())
}
fn window_end<'a>(e: &'a Evidence, windows: &'a Windows) -> &'a str {
    windows
        .get(&e.row_id)
        .map_or(e.date.as_str(), |w| w.1.as_str())
}
fn windows_overlap(a: &Evidence, b: &Evidence, windows: &Windows) -> bool {
    window_start(a, windows) <= window_end(b, windows)
        && window_start(b, windows) <= window_end(a, windows)
}
fn has_window_conflict(observations: &[Evidence], current: &Evidence, windows: &Windows) -> bool {
    observations.iter().any(|e| {
        windows_overlap(e, current, windows)
            && !same_value(&e.fact.value, &current.fact.value)
            && !(e.fact.value["kind"] == "money"
                && current.fact.value["kind"] == "money"
                && (e.fact.value["currency"] != current.fact.value["currency"]
                    || e.fact.value["per"] != current.fact.value["per"]))
    })
}

fn comparison_phrase(left: &Value, right: &Value) -> Option<(&'static str, &'static str)> {
    if left["kind"] != right["kind"] {
        return None;
    }
    let kind = left["kind"].as_str()?;
    // A comparison form carries references only, so preserve the precision of
    // both dated values rather than rendering a year as a particular day.
    if kind == "date" && left["value"].as_str()?.len() != right["value"].as_str()?.len() {
        return None;
    }
    let order = if let Some((a, b)) = numeric(left).zip(numeric(right)) {
        if a.dimension != b.dimension {
            return None;
        }
        a.amount.cmp(&b.amount)
    } else if matches!(kind, "date" | "version") {
        if left["value"] == right["value"] {
            if kind == "date" && left["value"].as_str()?.len() != 10 {
                return None;
            }
            std::cmp::Ordering::Equal
        } else {
            let mut bound = right.clone();
            bound["op"] = json!("gt");
            if crate::knowledge::entails(&bound, left, false) == Some(true) {
                std::cmp::Ordering::Greater
            } else {
                bound["op"] = json!("lt");
                if crate::knowledge::entails(&bound, left, false) == Some(true) {
                    std::cmp::Ordering::Less
                } else {
                    return None;
                }
            }
        }
    } else {
        return None;
    };
    Some(match (kind, order) {
        ("date", std::cmp::Ordering::Less) => ("lt", "is earlier than"),
        ("date", std::cmp::Ordering::Greater) => ("gt", "is later than"),
        ("date", std::cmp::Ordering::Equal) => ("eq", "is on the same day as"),
        (_, std::cmp::Ordering::Less) => ("lt", "is less than"),
        (_, std::cmp::Ordering::Greater) => ("gt", "is greater than"),
        (_, std::cmp::Ordering::Equal) => ("eq", "is equal to"),
    })
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
    if let Some((a, b)) = numeric(left).zip(numeric(right)) {
        return a.dimension == b.dimension && a.amount == b.amount;
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
    fn version_comparisons_use_actual_numeric_components_and_date_precision() {
        let version = |v| json!({"kind":"version","value":v});
        assert_eq!(
            comparison_phrase(&version("14.0.0"), &version("4.21.10.2"))
                .unwrap()
                .0,
            "gt"
        );
        assert_eq!(
            comparison_phrase(&version("2.9"), &version("2.10"))
                .unwrap()
                .0,
            "lt"
        );
        assert_eq!(
            comparison_phrase(&version("2.3"), &version("2.3.0"))
                .unwrap()
                .0,
            "lt"
        );
        let date = |v| json!({"kind":"date","value":v});
        assert!(comparison_phrase(&date("2024"), &date("2025-02-03")).is_none());
        assert_eq!(
            comparison_phrase(&date("2024-02-03"), &date("2025-02-03"))
                .unwrap()
                .0,
            "lt"
        );
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
    fn explicit_validity_orders_changes_independently_of_publication_dates() {
        let mut first = row("first", "2026-09-01", "true", 1.0);
        first.text = "From January 1, 2026 through January 31, 2026, A has 1 user.".into();
        let mut second = row("second", "2025-12-01", "true", 2.0);
        second.text = "From February 1, 2026 through February 28, 2026, A has 2 users.".into();
        let report = generate_claims(&[first, second], &[], &lexicon(), 1000).unwrap();
        let change = report.claims.iter().find(|c| c.kind == "change").unwrap();
        assert_eq!(change.form["from"]["value"], json!(1.0));
        assert_eq!(change.form["to"]["value"], json!(2.0));
        assert_eq!(change.evidence[0].date, "2026-09-01"); // Source date is preserved.
        assert!(report.claims.iter().all(|c| c.kind != "fact"));
    }
    #[test]
    fn mutable_current_facts_require_explicit_coverage_and_comparisons_convert_units() {
        let mut a = row("a", "2025-12-01", "true", 1.2);
        a.text = "From October 1, 2026 through October 29, 2026, A has 1.2 GB of storage.".into();
        a.form[0].value = json!({"kind":"quantity","value":1.2,"unit":"GB"});
        let mut b = row("b", "2026-10-01", "true", 1200.0);
        b.text = "From October 1, 2026 through October 29, 2026, B has 1200 MB of storage.".into();
        b.form[0].subject = "B".into();
        b.form[0].value = json!({"kind":"quantity","value":1200,"unit":"MB"});
        let mut lex = lexicon();
        lex["subjects"]
            .as_array_mut()
            .unwrap()
            .push(json!({"name":"B","aliases":[],"attributes":["users"]}));
        let report = generate_claims(&[a, b], &[], &lex, 1000).unwrap();
        assert_eq!(report.claims.iter().filter(|c| c.kind == "fact").count(), 2);
        assert!(
            report
                .claims
                .iter()
                .any(|c| c.kind == "compare" && c.form["op"] == "eq")
        );
    }
    #[test]
    fn multiple_price_periods_license_facts_and_changes_but_not_ambiguous_compares() {
        let mut rows = Vec::new();
        for (id, start, end, per, value) in [
            ("m1", "2026-01-01", "2026-06-30", "month", 79),
            ("m2", "2026-07-01", "2026-10-29", "month", 95),
            ("y1", "2026-01-01", "2026-06-30", "year", 790),
            ("y2", "2026-07-01", "2026-10-29", "year", 950),
        ] {
            let mut r = row(id, start, "true", 1.0);
            r.text = format!("From {start} through {end}, A has a price of EUR{value} per {per}.");
            r.form[0].attribute = "price".into();
            r.form[0].value = json!({"kind":"money","value":value,"currency":"EUR","per":per});
            rows.push(r);
        }
        let lex =
            json!({"subjects":[{"name":"A","aliases":[],"attributes":["price"]}],"events":[]});
        let report = generate_claims(&rows, &[], &lex, 1000).unwrap();
        assert_eq!(report.claims.iter().filter(|c| c.kind == "fact").count(), 2);
        assert_eq!(
            report.claims.iter().filter(|c| c.kind == "change").count(),
            2
        );
        assert!(!report.claims.iter().any(|c| c.kind == "compare"));
    }
    #[test]
    fn overlapping_conflicting_scopes_do_not_license_current_values_or_changes() {
        let mut a = row("a", "2026-01-01", "true", 1.0);
        a.text = "From October 1, 2026 through October 29, 2026, A has 1 user.".into();
        let mut b = row("b", "2026-02-01", "true", 2.0);
        b.text = "From October 1, 2026 through October 29, 2026, A has 2 users.".into();
        assert!(
            generate_claims(&[a, b], &[], &lexicon(), 1000)
                .unwrap()
                .claims
                .is_empty()
        );
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
    fn newness_ignores_whitespace_case_and_trailing_punctuation() {
        assert_eq!(
            normalize_claim_text("  A  changed users from 1 user to 2 user!\n"),
            normalize_claim_text("a changed users from 1 user to 2 user.")
        );
        let mut rows = vec![
            row("a", "2026-01-01", "true", 1.0),
            row("b", "2026-02-01", "true", 2.0),
        ];
        rows.push(InputRow {
            id: "already-present".into(),
            text: " A  changed users from 1.0 user to 2.0 user! ".into(),
            date: "2026-02-01".into(),
            label: String::new(),
            form: vec![],
        });
        assert!(
            generate_claims(&rows, &[], &lexicon(), 1000)
                .unwrap()
                .claims
                .is_empty()
        );
    }

    #[test]
    fn changing_model_cutoff_is_not_assumed_current() {
        let mut evidence = Evidence {
            row_id: "e".into(),
            text: "source".into(),
            date: "2026-10-01".into(),
            label: "true".into(),
            fact: Fact {
                subject: "A".into(),
                attribute: "training_data_cutoff".into(),
                value: json!({"kind":"date","value":"2025-06"}),
            },
        };
        assert!(
            immutable_observation("A", "training_data_cutoff", &[evidence.clone()], &lexicon())
                .is_none()
        );
        evidence.fact.attribute = "joined".into();
        assert!(immutable_observation("A", "joined", &[evidence], &lexicon()).is_some());
    }

    #[test]
    fn boolean_change_keeps_attribute_outside_value_sides() {
        let mut rows = vec![
            row("a", "2026-01-01", "true", 1.0),
            row("b", "2026-02-01", "true", 2.0),
        ];
        for (r, value) in rows.iter_mut().zip([false, true]) {
            r.form[0].attribute = "end_to_end_encryption".into();
            r.form[0].value = json!({"kind":"boolean","value":value});
        }
        let lexicon = json!({"subjects":[{"name":"A","aliases":[],"attributes":["end_to_end_encryption"]}],"events":[]});
        let report = generate_claims(&rows, &[], &lexicon, 1000).unwrap();
        assert_eq!(report.claims.len(), 1);
        assert_eq!(
            report.claims[0].text,
            "A end to end encryption changed from not to yes."
        );
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
