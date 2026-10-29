//! Experimental verifier features and portable tree inference, never runtime evidence.
//! The caller must compile a separate index per training/evidence partition.
use crate::{
    knowledge::KnowledgeGraph,
    model::{Fact, InputRow},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

pub type Features = BTreeMap<String, f64>;

#[derive(Clone)]
struct Observation {
    row: InputRow,
    fact: Fact,
}

pub struct FeatureIndex {
    graph: KnowledgeGraph,
    observations: BTreeMap<(String, String), Vec<Observation>>,
}

fn class(label: &str) -> Option<usize> {
    match label {
        "true" => Some(0),
        "false" => Some(1),
        "unsure" => Some(2),
        _ => None,
    }
}

fn ordinal(text: &str) -> Option<i32> {
    let mut parts = text.split('-');
    let y: i32 = parts.next()?.parse().ok()?;
    let m: usize = parts.next()?.parse().ok()?;
    let d: i32 = parts.next()?.parse().ok()?;
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    let before = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][m - 1];
    let leap = m > 2 && (y % 4 == 0 && (y % 100 != 0 || y % 400 == 0));
    Some(365 * (y - 1) + (y - 1) / 4 - (y - 1) / 100 + (y - 1) / 400 + before + d + i32::from(leap))
}

fn terms(text: &str) -> BTreeSet<String> {
    text.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect()
}

fn fnv(text: &str) -> u64 {
    text.bytes().fold(0xcbf29ce484222325, |h, b| {
        (h ^ u64::from(b)).wrapping_mul(0x100000001b3)
    })
}

fn numeric(value: &Value) -> Option<f64> {
    value["value"].as_f64()
}

fn comparable(a: &Value, b: &Value) -> bool {
    a["kind"] == b["kind"]
        && ["unit", "currency", "per"]
            .iter()
            .all(|k| a.get(*k) == b.get(*k))
}

fn relation(query: &Value, observed: &Value, negative: bool) -> [f64; 3] {
    match crate::knowledge::entails(query, observed, negative) {
        Some(true) => [1.0, 0.0, 0.0],
        Some(false) => [0.0, 1.0, 0.0],
        None => [0.0, 0.0, 1.0],
    }
}

fn insert_relation(
    out: &mut Features,
    prefix: &str,
    query: &Value,
    observed: &Value,
    negative: bool,
) {
    for (name, value) in ["support", "contradict", "incomparable"]
        .iter()
        .zip(relation(query, observed, negative))
    {
        out.insert(format!("{prefix}.{name}"), value);
    }
    out.insert(format!("{prefix}.exact"), f64::from(query == observed));
    if comparable(query, observed)
        && let (Some(a), Some(b)) = (numeric(query), numeric(observed))
    {
        out.insert(
            format!("{prefix}.relative_delta"),
            ((a - b) / (b.abs() + 1.0)).clamp(-20.0, 20.0),
        );
        out.insert(
            format!("{prefix}.relative_distance"),
            ((a - b).abs() / (b.abs() + 1.0)).min(20.0),
        );
    }
}

impl FeatureIndex {
    pub fn compile(rows: &[InputRow]) -> Self {
        let mut observations = BTreeMap::<(String, String), Vec<Observation>>::new();
        for row in rows.iter().filter(|r| class(&r.label).is_some()) {
            for fact in &row.form {
                observations
                    .entry((fact.subject.clone(), fact.attribute.clone()))
                    .or_default()
                    .push(Observation {
                        row: row.clone(),
                        fact: fact.clone(),
                    });
            }
        }
        for values in observations.values_mut() {
            values.sort_by(|a, b| a.row.date.cmp(&b.row.date).then(a.row.id.cmp(&b.row.id)));
        }
        Self {
            graph: KnowledgeGraph::compile(rows),
            observations,
        }
    }

    fn atom(&self, row: &InputRow, fact: &Fact) -> Features {
        let mut out = Features::new();
        for (i, v) in self
            .graph
            .features(row, std::slice::from_ref(fact))
            .into_iter()
            .enumerate()
        {
            out.insert(format!("graph.{i}"), v);
        }
        out.insert(
            format!("kind.{}", fact.value["kind"].as_str().unwrap_or("missing")),
            1.0,
        );
        out.insert(
            format!("op.{}", fact.value["op"].as_str().unwrap_or("eq")),
            1.0,
        );
        for key in ["per", "unit", "currency"] {
            if let Some(value) = fact.value[key].as_str() {
                out.insert(format!("{key}.{value}"), 1.0);
            }
        }
        if let Some(n) = numeric(&fact.value) {
            out.insert("numeric.log_magnitude".into(), n.abs().ln_1p());
            out.insert("numeric.negative".into(), f64::from(n < 0.0));
        }
        let date = ordinal(&row.date).unwrap_or(0);
        let observations: Vec<_> = self
            .observations
            .get(&(fact.subject.clone(), fact.attribute.clone()))
            .into_iter()
            .flatten()
            .filter(|o| o.row.id != row.id && !o.row.text.eq_ignore_ascii_case(&row.text))
            .collect();
        out.insert(
            "property.observations".into(),
            (observations.len() as f64).ln_1p(),
        );
        let mut counts = [0.0; 3];
        for o in &observations {
            if let Some(c) = class(&o.row.label) {
                counts[c] += 1.0;
            }
        }
        for (i, c) in counts.into_iter().enumerate() {
            out.insert(
                format!("property.label.{i}"),
                (c + 1.0) / (observations.len() as f64 + 3.0),
            );
        }
        out.insert(
            "property.false_compounds".into(),
            observations
                .iter()
                .filter(|o| o.row.label == "false" && o.row.form.len() > 1)
                .count() as f64,
        );
        let positives: Vec<_> = observations
            .iter()
            .copied()
            .filter(|o| o.row.label == "true")
            .collect();
        let negatives: Vec<_> = observations
            .iter()
            .copied()
            .filter(|o| o.row.label == "false" && o.row.form.len() == 1)
            .collect();
        for (prefix, pool, negate) in [
            ("positive", positives, false),
            ("negative", negatives, true),
        ] {
            let prior: Vec<_> = pool
                .iter()
                .copied()
                .filter(|o| o.row.date <= row.date)
                .collect();
            let future: Vec<_> = pool
                .iter()
                .copied()
                .filter(|o| o.row.date > row.date)
                .collect();
            out.insert(format!("{prefix}.count"), (pool.len() as f64).ln_1p());
            out.insert(
                format!("{prefix}.prior_count"),
                (prior.len() as f64).ln_1p(),
            );
            out.insert(
                format!("{prefix}.future_count"),
                (future.len() as f64).ln_1p(),
            );
            let nearest = pool
                .iter()
                .min_by_key(|o| (ordinal(&o.row.date).unwrap_or(0) - date).abs());
            for (name, source) in [
                ("previous", prior.last().copied()),
                ("next", future.first().copied()),
                ("nearest", nearest.copied()),
            ] {
                let p = format!("{prefix}.{name}");
                out.insert(format!("{p}.missing"), f64::from(source.is_none()));
                if let Some(o) = source {
                    let gap = (ordinal(&o.row.date).unwrap_or(0) - date).abs() as f64;
                    out.insert(format!("{p}.gap"), (gap / 366.0).min(5.0));
                    out.insert(format!("{p}.same_day"), f64::from(gap == 0.0));
                    insert_relation(&mut out, &p, &fact.value, &o.fact.value, negate);
                }
            }
            for (i, label) in ["support", "contradict", "incomparable"].iter().enumerate() {
                let count = pool
                    .iter()
                    .filter(|o| relation(&fact.value, &o.fact.value, negate)[i] > 0.5)
                    .count();
                out.insert(format!("{prefix}.any.{label}"), f64::from(count > 0));
                out.insert(
                    format!("{prefix}.fraction.{label}"),
                    count as f64 / pool.len().max(1) as f64,
                );
                let nearest = pool
                    .iter()
                    .filter(|o| relation(&fact.value, &o.fact.value, negate)[i] > 0.5)
                    .map(|o| (ordinal(&o.row.date).unwrap_or(0) - date).abs())
                    .min();
                out.insert(
                    format!("{prefix}.gap.{label}"),
                    nearest.map_or(5.0, |g| (f64::from(g) / 366.0).min(5.0)),
                );
            }
            if let (Some(a), Some(b)) = (prior.last(), future.first()) {
                out.insert(
                    format!("{prefix}.bracket_equal"),
                    f64::from(a.fact.value == b.fact.value),
                );
            }
        }
        out
    }

    pub fn features(&self, row: &InputRow, facts: &[Fact]) -> Features {
        let mut out = Features::new();
        let words = terms(&row.text);
        out.insert("row.facts".into(), facts.len() as f64);
        out.insert("row.empty".into(), f64::from(facts.is_empty()));
        out.insert(
            "row.chars".into(),
            (row.text.chars().count() as f64 / 200.0).min(10.0),
        );
        out.insert("row.words".into(), words.len() as f64 / 30.0);
        out.insert(
            "row.digits".into(),
            row.text.chars().filter(char::is_ascii_digit).count() as f64 / 20.0,
        );
        out.insert(
            "row.clauses".into(),
            row.text.matches(';').count() as f64 + row.text.matches(" and ").count() as f64,
        );
        out.insert(
            "row.numeric_facts".into(),
            facts.iter().filter(|f| numeric(&f.value).is_some()).count() as f64,
        );
        let distinct: BTreeSet<_> = facts.iter().map(|f| (&f.subject, &f.attribute)).collect();
        out.insert("row.distinct_properties".into(), distinct.len() as f64);
        for word in [
            "not",
            "never",
            "no",
            "without",
            "before",
            "after",
            "until",
            "since",
            "from",
            "through",
            "or",
            "and",
            "reportedly",
            "rumor",
            "perhaps",
            "might",
        ] {
            out.insert(format!("cue.{word}"), f64::from(words.contains(word)));
        }
        for word in &words {
            *out.entry(format!("lex.{}", fnv(word) % 128)).or_default() +=
                1.0 / (words.len().max(1) as f64).sqrt();
        }
        for f in facts {
            *out.entry(format!("subject.{}", f.subject)).or_default() += 1.0;
            *out.entry(format!("attribute.{}", f.attribute)).or_default() += 1.0;
            *out.entry(format!("slot.{}|{}", f.subject, f.attribute))
                .or_default() += 1.0;
        }
        let atoms: Vec<_> = facts.iter().map(|f| self.atom(row, f)).collect();
        let names: BTreeSet<_> = atoms.iter().flat_map(|a| a.keys().cloned()).collect();
        for name in names {
            let values: Vec<_> = atoms
                .iter()
                .map(|a| a.get(&name).copied().unwrap_or(0.0))
                .collect();
            let mean = values.iter().sum::<f64>() / values.len().max(1) as f64;
            let min = values.iter().copied().fold(f64::INFINITY, f64::min);
            let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            out.insert(format!("atom.mean.{name}"), mean);
            out.insert(format!("atom.min.{name}"), min);
            out.insert(format!("atom.max.{name}"), max);
        }
        out
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub struct TreeNode {
    pub feature: usize,
    pub threshold: f64,
    pub left: usize,
    pub right: usize,
    pub value: f64,
    pub leaf: bool,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct BoostedTree {
    pub class: usize,
    pub nodes: Vec<TreeNode>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct BoostedVerifier {
    pub schema_version: usize,
    pub labels: Vec<String>,
    pub feature_names: Vec<String>,
    pub initial_logits: Vec<f64>,
    pub learning_rate: f64,
    pub trees: Vec<BoostedTree>,
    pub provenance: Value,
}

impl BoostedVerifier {
    pub fn from_json(text: &str) -> Result<Self, String> {
        // With arbitrary_precision, Value retains decimal lexemes and its number
        // deserializer rounds directly to f64. Direct struct deserialization can
        // shift an exact split threshold by one ULP without float_roundtrip.
        let value: Value =
            serde_json::from_str(text).map_err(|e| format!("Invalid verifier JSON: {e}"))?;
        let model: Self =
            serde_json::from_value(value).map_err(|e| format!("Invalid verifier model: {e}"))?;
        model.validate()?;
        Ok(model)
    }

    /// Reject an accidentally reused production or other-split checkpoint.
    /// FNV signatures are an identity guard; archive/model SHA256 is recorded by
    /// the training harness separately. Row forms are not a source of truth here.
    pub fn validate_training_partition(&self, rows: &[InputRow]) -> Result<(), String> {
        let expected = self.provenance["training_row_signatures"]
            .as_object()
            .ok_or("Model lacks training partition signatures")?;
        let actual: BTreeMap<_, _> = rows
            .iter()
            .filter(|r| class(&r.label).is_some())
            .map(|r| {
                let signature = fnv(&format!("{}\0{}\0{}\0{}", r.id, r.date, r.label, r.text));
                (r.id.as_str(), format!("{signature:016x}"))
            })
            .collect();
        if expected.len() != actual.len()
            || expected.iter().any(|(id, signature)| {
                let Some(signature) = signature.as_str() else {
                    return true;
                };
                actual.get(id.as_str()).map(String::as_str) != Some(signature)
            })
        {
            return Err("Verifier checkpoint does not match the supplied training IDs, texts, dates and labels".into());
        }
        Ok(())
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1
            || self.labels != ["true", "false", "unsure"]
            || self.initial_logits.len() != 3
            || !self.learning_rate.is_finite()
        {
            return Err("Unsupported verifier schema or labels".into());
        }
        if !self.initial_logits.iter().all(|x| x.is_finite()) {
            return Err("Non-finite initial logits".into());
        }
        for tree in &self.trees {
            if tree.class >= 3 || tree.nodes.is_empty() {
                return Err("Invalid tree class or empty tree".into());
            }
            for (i, n) in tree.nodes.iter().enumerate() {
                if !n.value.is_finite()
                    || !n.threshold.is_finite()
                    || (!n.leaf
                        && (n.feature >= self.feature_names.len()
                            || n.left <= i
                            || n.right <= i
                            || n.left >= tree.nodes.len()
                            || n.right >= tree.nodes.len()))
                {
                    return Err("Invalid or cyclic verifier node".into());
                }
            }
        }
        Ok(())
    }

    pub fn predict_logits(&self, features: &Features) -> Result<[f64; 3], String> {
        self.validate()?;
        let mut logits: [f64; 3] = self
            .initial_logits
            .as_slice()
            .try_into()
            .map_err(|_| "Invalid logits")?;
        for tree in &self.trees {
            let mut i = 0;
            loop {
                let node = &tree.nodes[i];
                if node.leaf {
                    logits[tree.class] += self.learning_rate * node.value;
                    break;
                }
                // sklearn tree traversal casts input to float32 before comparing.
                let x = f64::from(
                    features
                        .get(&self.feature_names[node.feature])
                        .copied()
                        .unwrap_or(0.0) as f32,
                );
                if !x.is_finite() {
                    return Err("Non-finite verifier feature".into());
                }
                i = if x <= node.threshold {
                    node.left
                } else {
                    node.right
                };
            }
        }
        Ok(logits)
    }

    /// Scores already use observed training class frequencies. Do not apply
    /// balanced-forest prior restoration to these logits or probabilities.
    pub fn predict(&self, features: &Features) -> Result<[f64; 3], String> {
        let logits = self.predict_logits(features)?;
        let maximum = logits.into_iter().fold(f64::NEG_INFINITY, f64::max);
        let exps = logits.map(|l| (l - maximum).exp());
        let sum: f64 = exps.iter().sum();
        Ok(exps.map(|p| p / sum))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn excluded_self_cannot_supply_evidence() {
        let row = InputRow {
            id: "one".into(),
            text: "A has 10".into(),
            date: "2026-01-01".into(),
            label: "true".into(),
            form: vec![Fact {
                subject: "A".into(),
                attribute: "count".into(),
                value: json!({"kind":"quantity","value":10,"unit":"item"}),
            }],
        };
        let features = FeatureIndex::compile(std::slice::from_ref(&row)).features(&row, &row.form);
        assert_eq!(features["atom.max.property.observations"], 0.0);
        assert_eq!(features["atom.max.positive.count"], 0.0);
    }

    #[test]
    fn conjunction_keeps_contradiction_maximum() {
        let a = Fact {
            subject: "A".into(),
            attribute: "count".into(),
            value: json!({"kind":"quantity","value":10,"unit":"item"}),
        };
        let row = InputRow {
            id: "anchor".into(),
            text: "Known 10".into(),
            date: "2026-01-01".into(),
            label: "true".into(),
            form: vec![a.clone()],
        };
        let mut wrong = a.clone();
        wrong.value["value"] = json!(11);
        let query = InputRow {
            id: "query".into(),
            text: "10 and 11".into(),
            date: row.date.clone(),
            label: String::new(),
            form: vec![],
        };
        let f = FeatureIndex::compile(&[row]).features(&query, &[a, wrong]);
        assert_eq!(f["atom.max.graph.2"], 1.0);
        assert_eq!(f["atom.mean.graph.2"], 0.5);
    }

    #[test]
    fn malformed_tree_is_rejected() {
        let model = BoostedVerifier {
            schema_version: 1,
            labels: vec!["true".into(), "false".into(), "unsure".into()],
            feature_names: vec!["x".into()],
            initial_logits: vec![0.0; 3],
            learning_rate: 0.1,
            trees: vec![BoostedTree {
                class: 0,
                nodes: vec![TreeNode {
                    feature: 0,
                    threshold: 0.0,
                    left: 0,
                    right: 0,
                    value: 0.0,
                    leaf: false,
                }],
            }],
            provenance: json!({}),
        };
        assert!(model.predict(&Features::new()).is_err());
    }
}
