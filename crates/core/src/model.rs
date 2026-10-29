//! Shared MVP interface; probabilities are model scores, not certified truth.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeSet;

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct ExtractionHints {
    /// A parser intentionally returned no assertions; do not invent a fallback.
    pub recognized_empty: BTreeSet<String>,
    /// At least one asserted clause remains unresolved. False still dominates;
    /// matching only the parsed subset cannot establish a true conjunction.
    pub incomplete: BTreeSet<String>,
    /// The text explicitly says a value is unknown, independently of extraction
    /// coverage. Statistical fallback must not turn that into a factual value.
    pub explicit_unknown: BTreeSet<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct InputRow {
    pub id: String,
    pub text: String,
    pub date: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub form: Vec<Fact>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Fact {
    pub subject: String,
    pub attribute: String,
    pub value: Value,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Evidence {
    pub row_id: String,
    pub text: String,
    pub date: String,
    pub label: String,
    pub fact: Fact,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Probabilities {
    #[serde(rename = "true")]
    pub p_true: f64,
    #[serde(rename = "false")]
    pub p_false: f64,
    #[serde(rename = "unsure")]
    pub p_unsure: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Prediction {
    pub id: String,
    pub text: String,
    pub date: String,
    pub known_label: Option<String>,
    pub label: String,
    pub probabilities: Probabilities,
    pub confidence: Option<f64>,
    pub facts: Vec<Fact>,
    pub evidence: Vec<Evidence>,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Claim {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub text: String,
    pub form: Value,
    pub confidence: f64,
    pub evidence: Vec<Evidence>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GenerationReport {
    pub claims: Vec<Claim>,
    pub candidate_count: usize,
    pub notes: Vec<String>,
}
