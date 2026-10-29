//! Label-free assertion consistency, exclusively statistical verdict features.
//! This module never creates Evidence, accepted facts, or generation candidates.
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use unicode_normalization::UnicodeNormalization;
use veridyct_core::{Fact, InputRow, boosted::Features, knowledge::entails};

pub fn normalize(text: &str) -> String {
    text.nfkc()
        .collect::<String>()
        .to_lowercase()
        .replace('\u{df}', "ss")
        .replace('\u{3c2}', "\u{3c3}")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn tokens(text: &str) -> Vec<String> {
    normalize(text)
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect()
}

/// Public lexical delexicalization; never reads gold template or form metadata.
#[derive(Clone)]
pub struct Families {
    aliases: Vec<Vec<String>>,
}

impl Families {
    pub fn new(lexicon: &Value) -> Self {
        let mut aliases = BTreeSet::new();
        for subject in lexicon["subjects"].as_array().into_iter().flatten() {
            for text in subject["name"].as_str().into_iter().chain(
                subject["aliases"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str),
            ) {
                let t = tokens(text);
                if !t.is_empty() {
                    aliases.insert(t);
                }
            }
        }
        let mut aliases: Vec<_> = aliases.into_iter().collect();
        aliases.sort_by(|a, b| b.len().cmp(&a.len()).then(a.cmp(b)));
        Self { aliases }
    }

    pub fn key(&self, row: &InputRow) -> String {
        let text = tokens(&row.text);
        let mut replacements = self.aliases.clone();
        for fact in &row.form {
            if let Some(value) = fact.value["value"].as_str() {
                let t = tokens(value);
                if !t.is_empty() {
                    replacements.push(t);
                }
            }
        }
        replacements.sort_by(|a, b| b.len().cmp(&a.len()).then(a.cmp(b)));
        replacements.dedup();
        let mut out = Vec::new();
        let mut i = 0;
        while i < text.len() {
            if let Some(alias) = replacements.iter().find(|a| text[i..].starts_with(a)) {
                out.push("$value".to_owned());
                i += alias.len();
            } else {
                let word = &text[i];
                let number = word.chars().any(|c| c.is_ascii_digit());
                let month = [
                    "january",
                    "february",
                    "march",
                    "april",
                    "may",
                    "june",
                    "july",
                    "august",
                    "september",
                    "october",
                    "november",
                    "december",
                    "jan",
                    "feb",
                    "mar",
                    "apr",
                    "jun",
                    "jul",
                    "aug",
                    "sep",
                    "sept",
                    "oct",
                    "nov",
                    "dec",
                ]
                .contains(&word.as_str());
                out.push(if number {
                    "$number".into()
                } else if month {
                    "$month".into()
                } else {
                    word.clone()
                });
                i += 1;
            }
        }
        out.join(" ")
    }
}

fn day(date: &str) -> Option<i32> {
    let parts: Vec<_> = date.split('-').collect();
    if parts.len() != 3 {
        return None;
    }
    let y: i32 = parts[0].parse().ok()?;
    let m: usize = parts[1].parse().ok()?;
    let d: i32 = parts[2].parse().ok()?;
    if !(1..=12).contains(&m) {
        return None;
    }
    let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    let max = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][m - 1];
    if d < 1 || d > max {
        return None;
    }
    let before = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][m - 1];
    Some(
        365 * (y - 1) + (y - 1) / 4 - (y - 1) / 100
            + (y - 1) / 400
            + before
            + d
            + i32::from(leap && m > 2),
    )
}

/// Keys retain all typed dimensions. Incompatible currencies/units never vote.
fn property(fact: &Fact) -> String {
    serde_json::to_string(&(
        &fact.subject,
        &fact.attribute,
        &fact.value["kind"],
        &fact.value["unit"],
        &fact.value["currency"],
        &fact.value["per"],
    ))
    .expect("JSON values serialize")
}

#[derive(Clone)]
struct Assertion {
    id: String,
    text: String,
    family: String,
    day: Option<i32>,
    value: Value,
    value_key: String,
    // A repeated compound is no stronger than an independent singleton.
    reliability: f64,
}

pub struct ClusterIndex {
    assertions: BTreeMap<String, Vec<Assertion>>,
    families: Families,
}

impl ClusterIndex {
    pub fn compile(corpus: &[InputRow], families: Families) -> Result<Self, String> {
        if corpus.iter().any(|r| !r.label.is_empty()) {
            return Err("Statistical corpus must have blank labels".into());
        }
        // Choose a deterministic representative for normalized duplicate texts.
        // The query's whole normalized-text group is removed again at lookup.
        let mut ordered: Vec<_> = corpus.iter().collect();
        ordered.sort_by_key(|r| (normalize(&r.text), r.date.clone(), r.id.clone()));
        let mut seen = BTreeSet::new();
        let mut assertions = BTreeMap::<String, Vec<Assertion>>::new();
        for row in ordered {
            let text = normalize(&row.text);
            if !seen.insert(text.clone()) {
                continue;
            }
            let family = families.key(row);
            let mut values = BTreeSet::new();
            for fact in &row.form {
                if !fact.value["kind"].is_string()
                    || !values.insert((property(fact), fact.value.to_string()))
                {
                    continue;
                }
                assertions
                    .entry(property(fact))
                    .or_default()
                    .push(Assertion {
                        id: row.id.clone(),
                        text: text.clone(),
                        family: family.clone(),
                        day: day(&row.date),
                        value: fact.value.clone(),
                        value_key: fact.value.to_string(),
                        reliability: 1.0 / (row.form.len().max(1) as f64).sqrt(),
                    });
            }
        }
        // JSON decimal spelling is not a typed value identity. Use the core's
        // exact comparison boundary, including version spelling and dimensions,
        // rather than rounding through f64 or splitting 12 from 12.0.
        for pool in assertions.values_mut() {
            let raw: BTreeMap<_, _> = pool
                .iter()
                .map(|a| (a.value.to_string(), a.value.clone()))
                .collect();
            let mut representatives = Vec::<(String, Value)>::new();
            let mut canonical = BTreeMap::new();
            for (key, value) in raw {
                let equivalent = representatives.iter().find(|(_, candidate)| {
                    entails(&value, candidate, false) == Some(true)
                        && entails(candidate, &value, false) == Some(true)
                });
                let identity = if let Some((identity, _)) = equivalent {
                    identity.clone()
                } else {
                    representatives.push((key.clone(), value));
                    key.clone()
                };
                canonical.insert(key, identity);
            }
            for assertion in pool {
                assertion.value_key = canonical[&assertion.value_key].clone();
            }
        }
        Ok(Self {
            assertions,
            families,
        })
    }

    fn atom(&self, query: &InputRow, fact: &Fact) -> Features {
        let mut out = Features::new();
        let text = normalize(&query.text);
        let family = self.families.key(query);
        let query_day = day(&query.date);
        let pool: Vec<_> = self
            .assertions
            .get(&property(fact))
            .into_iter()
            .flatten()
            .filter(|a| a.id != query.id && a.text != text && a.family != family)
            .collect();
        out.insert("no_date".into(), f64::from(query_day.is_none()));
        for window in [
            "global",
            "same_day",
            "near30",
            "near180",
            "past365",
            "future365",
            "decay90",
        ] {
            let mut groups = BTreeMap::<&str, Vec<(&Assertion, f64)>>::new();
            for assertion in &pool {
                let gap = query_day.zip(assertion.day).map(|(q, a)| a - q);
                let weight = match (window, gap) {
                    ("global", _) => Some(1.0),
                    ("same_day", Some(0)) => Some(1.0),
                    ("near30", Some(d)) if d.abs() <= 30 => Some(1.0),
                    ("near180", Some(d)) if d.abs() <= 180 => Some(1.0),
                    ("past365", Some(d)) if (-365..=0).contains(&d) => Some(1.0),
                    ("future365", Some(d)) if (1..=365).contains(&d) => Some(1.0),
                    ("decay90", Some(d)) => Some((-(d.abs() as f64) / 90.0).exp()),
                    _ => None,
                };
                if let Some(w) = weight {
                    groups
                        .entry(&assertion.family)
                        .or_default()
                        .push((assertion, w));
                }
            }
            let mut relation = [0.0_f64; 3];
            let mut values = BTreeMap::<String, f64>::new();
            let mut family_conflict = 0.0;
            for group in groups.values() {
                // Collapse repeated inferred typed values inside one family.
                // Rewording a common template cannot multiply its total mass.
                let mut distinct = BTreeMap::<String, (&Assertion, f64)>::new();
                for &(assertion, w) in group {
                    let key = assertion.value_key.clone();
                    let candidate = distinct.entry(key).or_insert((assertion, w));
                    if w * assertion.reliability > candidate.1 * candidate.0.reliability {
                        *candidate = (assertion, w);
                    }
                }
                let divisor = distinct.len().max(1) as f64;
                family_conflict += f64::from(distinct.len() > 1);
                for (key, (assertion, w)) in distinct {
                    let weight = w * assertion.reliability / divisor;
                    let index = match entails(&fact.value, &assertion.value, false) {
                        Some(true) => 0,
                        Some(false) => 1,
                        None => 2,
                    };
                    relation[index] += weight;
                    *values.entry(key).or_default() += weight;
                }
            }
            let total = relation.iter().sum::<f64>();
            let max = values.values().copied().fold(0.0_f64, f64::max);
            let entropy = values
                .values()
                .filter(|&&w| w > 0.0 && total > 0.0)
                .map(|&w| -(w / total) * (w / total).ln())
                .sum::<f64>();
            let (a, b) = (relation[0], relation[1]);
            for (key, value) in [
                ("families", (groups.len() as f64).ln_1p()),
                ("mass", total.ln_1p()),
                ("missing", f64::from(groups.is_empty())),
                ("support", a / total.max(1e-12)),
                ("contradict", b / total.max(1e-12)),
                ("incomparable", relation[2] / total.max(1e-12)),
                ("margin", (a - b) / total.max(1e-12)),
                ("ambiguity", a.min(b) / (a + b).max(1e-12)),
                ("value_entropy", entropy),
                ("value_dominance", max / total.max(1e-12)),
                ("distinct_values", (values.len() as f64).ln_1p()),
                (
                    "within_family_conflict",
                    family_conflict / groups.len().max(1) as f64,
                ),
                // A simple soft consistency objective; never a proof of truth.
                ("consistency_gap", (max - a) / total.max(1e-12)),
            ] {
                out.insert(format!("{window}.{key}"), value);
            }
        }
        for (name, supporting) in [("support", true), ("contradict", false)] {
            let gap = pool
                .iter()
                .filter(|a| entails(&fact.value, &a.value, false) == Some(supporting))
                .filter_map(|a| query_day.zip(a.day).map(|(q, d)| (d - q).abs()))
                .min();
            out.insert(format!("nearest.{name}.missing"), f64::from(gap.is_none()));
            out.insert(
                format!("nearest.{name}.gap"),
                gap.map_or(5.0, |g| (g as f64 / 366.0).min(5.0)),
            );
        }
        out
    }

    pub fn features(&self, query: &InputRow) -> Features {
        let mut out = Features::new();
        out.insert("stat.empty".into(), f64::from(query.form.is_empty()));
        let atoms: Vec<_> = query.form.iter().map(|f| self.atom(query, f)).collect();
        let names: BTreeSet<_> = atoms.iter().flat_map(|a| a.keys().cloned()).collect();
        for name in names {
            let values: Vec<_> = atoms
                .iter()
                .map(|a| a.get(&name).copied().unwrap_or(0.0))
                .collect();
            out.insert(
                format!("stat.atom.mean.{name}"),
                values.iter().sum::<f64>() / values.len() as f64,
            );
            out.insert(
                format!("stat.atom.min.{name}"),
                values.iter().copied().fold(f64::INFINITY, f64::min),
            );
            out.insert(
                format!("stat.atom.max.{name}"),
                values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            );
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn row(id: &str, text: &str, number: i32, date: &str) -> InputRow {
        InputRow {
            id: id.into(),
            text: text.into(),
            date: date.into(),
            label: String::new(),
            form: vec![Fact {
                subject: "Widget".into(),
                attribute: "users".into(),
                value: json!({"kind":"quantity","value":number,"unit":"user","op":"eq"}),
            }],
        }
    }

    fn families() -> Families {
        Families::new(&json!({"subjects":[{"name":"Widget","aliases":[]}]}))
    }

    #[test]
    fn excludes_self_normalized_duplicates_and_query_template_family() {
        let q = row("q", "Widget has 20 users", 20, "2026-01-02");
        let corpus = [
            q.clone(),
            row("copy", "Ｗｉｄｇｅｔ HAS ２０ USERS", 20, "2026-01-02"),
            row("family", "Widget has 90 users", 90, "2026-01-02"),
        ];
        let f = ClusterIndex::compile(&corpus, families())
            .unwrap()
            .features(&q);
        assert_eq!(f["stat.atom.mean.global.families"], 0.0);
        assert_eq!(f["stat.atom.mean.global.mass"], 0.0);
    }

    #[test]
    fn correlated_repetition_is_capped_and_order_does_not_matter() {
        let q = row("q", "Widget has 20 users", 20, "2026-01-02");
        let a = row("a", "Users on Widget total 20", 20, "2026-01-02");
        let b = row("b", "Widget user census reports 90", 90, "2026-01-02");
        let original = ClusterIndex::compile(&[a.clone(), b.clone()], families())
            .unwrap()
            .features(&q);
        let mut copies = vec![a.clone(), b];
        for i in 0..200 {
            let mut c = a.clone();
            c.id = format!("copy-{i}");
            copies.push(c);
        }
        for i in 1..80 {
            let mut c = a.clone();
            c.id = format!("surface-{i}");
            c.text = format!("Users on Widget total {}20", "0".repeat(i));
            copies.push(c);
        }
        copies.reverse();
        let repeated = ClusterIndex::compile(&copies, families())
            .unwrap()
            .features(&q);
        assert_eq!(original, repeated);
        assert_eq!(original["stat.atom.mean.global.support"], 0.5);
        assert_eq!(original["stat.atom.mean.global.contradict"], 0.5);
        assert_eq!(original["stat.atom.mean.global.ambiguity"], 0.5);
    }

    #[test]
    fn typed_dimensions_and_temporal_windows_stay_separate() {
        let q = row("q", "Widget has 20 users", 20, "2026-01-02");
        let before = row("a", "Users on Widget total 20", 20, "2026-01-01");
        let after = row("b", "Widget user census reports 90", 90, "2026-02-01");
        let mut incompatible = row(
            "c",
            "Another measurement for Widget is 20",
            20,
            "2026-01-02",
        );
        incompatible.form[0].value["unit"] = json!("kg");
        let f = ClusterIndex::compile(&[before, after, incompatible], families())
            .unwrap()
            .features(&q);
        assert_eq!(f["stat.atom.mean.same_day.families"], 0.0);
        assert_eq!(f["stat.atom.mean.past365.support"], 1.0);
        assert_eq!(f["stat.atom.mean.future365.contradict"], 1.0);
        assert!((f["stat.atom.mean.global.families"] - 3.0_f64.ln()).abs() < 1e-12);
    }

    #[test]
    fn no_labels_or_missing_parses_can_create_votes() {
        let mut q = row("q", "Widget has 20 users", 20, "2026-01-02");
        q.label = "true".into();
        assert!(ClusterIndex::compile(&[q.clone()], families()).is_err());
        q.label.clear();
        q.form.clear();
        let f = ClusterIndex::compile(&[], families()).unwrap().features(&q);
        assert_eq!(f, Features::from([("stat.empty".into(), 1.0)]));
    }

    #[test]
    fn numeric_equivalence_does_not_split_clusters_or_merge_large_integers() {
        let q = row("q", "Widget has 20 users", 20, "2026-01-02");
        let a = row("a", "Users on Widget total 20", 20, "2026-01-02");
        let mut b = row("b", "Widget census says 20", 20, "2026-01-02");
        b.form[0].value["value"] = serde_json::from_str("20.0").unwrap();
        let f = ClusterIndex::compile(&[a, b], families())
            .unwrap()
            .features(&q);
        assert_eq!(f["stat.atom.mean.global.support"], 1.0);
        assert_eq!(f["stat.atom.mean.global.value_entropy"], 0.0);
        assert_eq!(f["stat.atom.mean.global.distinct_values"], 1.0_f64.ln_1p());

        let mut huge = row("huge", "A huge Widget census", 20, "2026-01-02");
        huge.form[0].value["value"] = serde_json::from_str("9007199254740992").unwrap();
        let mut neighbor = row(
            "neighbor",
            "Separate Widget users counted",
            20,
            "2026-01-02",
        );
        neighbor.form[0].value["value"] = serde_json::from_str("9007199254740993").unwrap();
        let f = ClusterIndex::compile(&[huge, neighbor], families())
            .unwrap()
            .features(&q);
        assert!((f["stat.atom.mean.global.distinct_values"] - 3.0_f64.ln()).abs() < 1e-12);
    }

    #[test]
    fn exact_version_spellings_keep_separate_clusters() {
        let mut q = row("q", "Widget ships version 2.3", 0, "2026-01-02");
        q.form[0].value = json!({"kind":"version","value":"2.3"});
        let mut a = row("a", "The Widget release is 2.3", 0, "2026-01-02");
        a.form[0].value = json!({"kind":"version","value":"2.3"});
        let mut b = row("b", "Widget release number: 2.3.0", 0, "2026-01-02");
        b.form[0].value = json!({"kind":"version","value":"2.3.0"});
        let f = ClusterIndex::compile(&[a, b], families())
            .unwrap()
            .features(&q);
        assert_eq!(f["stat.atom.mean.global.support"], 0.5);
        assert_eq!(f["stat.atom.mean.global.contradict"], 0.5);
    }
}
