//! Safe Rust adapter for the frozen ONNX ensemble and InputRow batch contract.
use std::{
    collections::{BTreeMap, HashMap, HashSet},
    fs::File,
    io::{BufReader, Read},
    path::Path,
    time::Instant,
};

use anyhow::{Context as _, Result, ensure};
use ort::{
    execution_providers::CPUExecutionProvider,
    session::{Session, builder::GraphOptimizationLevel},
    value::Tensor,
};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

use crate::{
    encode::{self, EncodedRow, MAX_ASSERTIONS, MAX_CHARS, MAX_TEXT_CHARS, Metadata, Tensors},
    grammar::{Grammar, canonical},
    python::Text,
};

pub const MODEL_SHA256: &str = "98eebdb851849f689c60499a9f4b2514305d520a523816b0505e98bba4523b6f";
pub const BUNDLE_HASHES: [(&str, &str); 3] = [
    ("model.onnx", MODEL_SHA256),
    (
        "meta.json",
        "3ab93d76b178bb714bd4c5ac665da2de0d97c29a46d32597ca43be3e52c08567",
    ),
    (
        "lexicon.json",
        "40d591b7e0345172f2822742c1d1b2cda69619c564ff23dd306d11984756747c",
    ),
];

pub fn sha256(path: &Path) -> Result<String> {
    let mut file =
        BufReader::new(File::open(path).with_context(|| format!("Opening {}", path.display()))?);
    let mut hash = Sha256::new();
    let mut buffer = [0_u8; 65536];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

pub fn verify_bundle(bundle: &Path) -> Result<()> {
    for (name, expected) in BUNDLE_HASHES {
        ensure!(
            sha256(&bundle.join(name))? == expected,
            "Frozen artifact SHA256 mismatch: {name}"
        );
    }
    Ok(())
}

/// Retains fields verbatim, including omitted labels, null forms, and extra keys.
/// Only `id`, `text`, and `date` are required strings; only text becomes a feature.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct InputRow(pub Map<String, Value>);
impl InputRow {
    pub fn text(&self) -> &str {
        self.0["text"].as_str().expect("validated InputRow")
    }
    pub fn id(&self) -> &str {
        self.0["id"].as_str().expect("validated InputRow")
    }
    pub fn validate(&self, index: usize) -> Result<()> {
        for key in ["id", "text", "date"] {
            ensure!(
                self.0.get(key).is_some_and(Value::is_string),
                "Row {index} requires string {key}"
            );
        }
        ensure!(
            self.0
                .get("form")
                .is_none_or(|f| f.is_null() || f.is_array()),
            "Row {index} form must be an array or null"
        );
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Context {
    #[default]
    None,
    Previous3text,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Batching {
    #[default]
    Padded,
    ExactLength,
}

#[derive(Debug, Clone)]
pub struct Options {
    pub threads: usize,
    pub batch_size: usize,
    pub context: Context,
    pub batching: Batching,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            threads: 2,
            batch_size: 48,
            context: Context::None,
            batching: Batching::Padded,
        }
    }
}
impl Options {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            (1..=2).contains(&self.threads),
            "CPU threads must be 1 or 2"
        );
        ensure!(
            (1..=64).contains(&self.batch_size),
            "Batch size must be between 1 and 64"
        );
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Assertion {
    pub atom: Value,
    pub model_score: f32,
    pub value_span_chars: [usize; 2],
    pub value_text: String,
}
#[derive(Debug, Serialize)]
pub struct Diagnostic {
    pub event: &'static str,
    pub index: usize,
    pub id: String,
    pub code: &'static str,
    pub reason: String,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub counts: BTreeMap<&'static str, usize>,
    pub unsupported: Vec<Diagnostic>,
    pub practice_conflicting_texts: usize,
    pub context: Context,
    pub context_experimental: bool,
    pub batching: Batching,
    pub batching_experimental: bool,
    pub cpu_threads: usize,
    pub batch_size: usize,
    pub seconds_including_preprocessing: f64,
    pub model_sha256: &'static str,
    pub scope: &'static str,
}
impl Report {
    fn count(&mut self, key: &'static str, n: usize) {
        *self.counts.entry(key).or_default() += n;
    }
}
#[derive(Debug, Serialize)]
pub struct BatchOutput {
    pub rows: Vec<InputRow>,
    pub report: Report,
}

/// Serializes inference on a reusable CPU session. No custom unsafe code or FFI.
pub struct Extractor {
    pub meta: Metadata,
    pub grammar: Grammar,
    session: Session,
    options: Options,
    practice: HashMap<String, Value>,
    conflicts: HashSet<String>,
}

impl Extractor {
    pub fn load(bundle: impl AsRef<Path>, options: Options) -> Result<Self> {
        options.validate()?;
        let bundle = bundle.as_ref();
        verify_bundle(bundle)?;
        let meta: Metadata =
            serde_json::from_reader(BufReader::new(File::open(bundle.join("meta.json"))?))?;
        ensure!(
            meta.pairs.len() == 514,
            "Expected frozen 514 subject-attribute pairs"
        );
        let lexicon: Value =
            serde_json::from_reader(BufReader::new(File::open(bundle.join("lexicon.json"))?))?;
        let grammar = Grammar::new(&lexicon, &meta.extra_names)?;
        ort::init()
            .with_name("veridyct-native-extractor")
            .commit()?;
        let session = Session::builder()?
            .with_intra_threads(options.threads)?
            .with_inter_threads(1)?
            .with_parallel_execution(false)?
            .with_optimization_level(GraphOptimizationLevel::Level3)?
            .with_execution_providers([CPUExecutionProvider::default().build()])?
            .commit_from_file(bundle.join("model.onnx"))?;
        let names: HashSet<_> = session.inputs.iter().map(|i| i.name.as_str()).collect();
        ensure!(
            names == HashSet::from(["words", "chars", "spans", "clauses", "kinds"]),
            "Unexpected model inputs"
        );
        Ok(Self {
            meta,
            grammar,
            session,
            options,
            practice: HashMap::new(),
            conflicts: HashSet::new(),
        })
    }

    /// Optional explicit public practice CSV; literal text reuse only, conflicts refused.
    /// This never derives a feature from a label, date, ID, or form.
    pub fn load_practice(&mut self, path: impl AsRef<Path>) -> Result<()> {
        let mut reader = csv::Reader::from_path(path)?;
        let headers = reader.headers()?.clone();
        let text = headers
            .iter()
            .position(|s| s.trim_start_matches('\u{feff}') == "text")
            .context("Practice requires text")?;
        let form = headers
            .iter()
            .position(|s| s == "form")
            .context("Practice requires form")?;
        let mut practice = HashMap::new();
        let mut conflicts = HashSet::new();
        for row in reader.records() {
            let row = row?;
            let value: Value = serde_json::from_str(row.get(form).context("Practice form cell")?)?;
            ensure!(value.is_array(), "Practice form must be an array");
            let text = row.get(text).context("Practice text cell")?.to_owned();
            if let Some(prior) = practice.insert(text.clone(), value.clone())
                && prior != value
            {
                conflicts.insert(text);
            }
        }
        for key in &conflicts {
            practice.remove(key);
        }
        self.practice = practice;
        self.conflicts = conflicts;
        Ok(())
    }

    /// Explicit context API used by parity tooling; ordinary InputRows cannot set this.
    pub fn encode(&self, text: &str, previous: &str, id: &str) -> Result<EncodedRow> {
        encode::encode_input(text, previous, &self.meta, &self.grammar, id)
    }

    pub fn predict_encoded(&mut self, rows: &[&EncodedRow]) -> Result<Vec<Vec<Assertion>>> {
        if rows.is_empty() {
            return Ok(Vec::new());
        }
        let Tensors {
            b,
            t,
            c,
            words,
            chars,
            spans,
            clauses,
            kinds,
        } = Tensors::from_rows(rows)?;
        let outputs = self.session.run(ort::inputs! {
            "words"=>Tensor::from_array(([b,t],words))?,
            "chars"=>Tensor::from_array(([b,t,MAX_CHARS],chars))?,
            "spans"=>Tensor::from_array(([b,c,t],spans))?,
            "clauses"=>Tensor::from_array(([b,c,t],clauses))?,
            "kinds"=>Tensor::from_array(([b,c],kinds))?,
        })?;
        let (shape, logits) = outputs[0].try_extract_tensor::<f32>()?;
        ensure!(
            **shape == [b as i64, c as i64, 515],
            "Unexpected model output dimensions"
        );
        decode(rows, logits, c, &self.meta.pairs)
    }

    pub fn extract_batch(&mut self, rows: &[InputRow]) -> Result<BatchOutput> {
        self.extract_batch_with_metadata(rows, false)
    }

    pub fn extract_batch_with_metadata(
        &mut self,
        rows: &[InputRow],
        metadata: bool,
    ) -> Result<BatchOutput> {
        for (i, row) in rows.iter().enumerate() {
            row.validate(i)?;
        }
        let start = Instant::now();
        let mut out = BatchOutput {
            rows: rows.to_vec(),
            report: Report {
                counts: BTreeMap::from([("rows", rows.len())]),
                unsupported: Vec::new(),
                practice_conflicting_texts: self.conflicts.len(),
                context: self.options.context,
                context_experimental: self.options.context != Context::None,
                batching: self.options.batching,
                batching_experimental: self.options.batching != Batching::Padded,
                cpu_threads: self.options.threads,
                batch_size: self.options.batch_size,
                seconds_including_preprocessing: 0.,
                model_sha256: MODEL_SHA256,
                scope: "typed extraction only; native Rust/ONNX CPU, no LLM or truth score",
            },
        };
        for lo in (0..rows.len()).step_by(512) {
            let mut encoded = Vec::new();
            for index in lo..(lo + 512).min(rows.len()) {
                let row = &rows[index];
                if row
                    .0
                    .get("form")
                    .and_then(Value::as_array)
                    .is_some_and(|f| !f.is_empty())
                {
                    out.report.count("preserved", 1);
                    continue;
                }
                if let Some(form) = self.practice.get(row.text()) {
                    out.rows[index].0.insert("form".into(), form.clone());
                    out.report.count("practice_reused", 1);
                    continue;
                }
                if row.text().chars().count() > MAX_TEXT_CHARS {
                    reject(
                        &mut out,
                        rows,
                        index,
                        "text_size",
                        format!("Text exceeds {MAX_TEXT_CHARS} characters"),
                    );
                    continue;
                }
                let previous = if self.options.context == Context::Previous3text {
                    rows[index.saturating_sub(3)..index]
                        .iter()
                        .map(|r| {
                            let t = Text::new(r.text());
                            t.slice(t.len().saturating_sub(MAX_TEXT_CHARS), t.len())
                                .to_owned()
                        })
                        .collect::<Vec<_>>()
                        .join(" ")
                } else {
                    String::new()
                };
                match self.encode(row.text(), &previous, row.id()) {
                    Ok(item) if item.candidates.is_empty() => {
                        out.rows[index].0.insert("form".into(), json!([]));
                        out.report.count("no_candidates", 1);
                    }
                    Ok(item) => encoded.push((index, item)),
                    Err(e) => reject(&mut out, rows, index, "preprocessing", e.to_string()),
                }
            }
            encoded.sort_by_key(|(_, r)| r.tokens.len());
            if self.options.batching == Batching::Padded {
                for chunk in encoded.chunks(self.options.batch_size) {
                    self.infer_chunk(chunk, rows, &mut out, metadata);
                }
            } else {
                let mut start = 0;
                while start < encoded.len() {
                    let length = encoded[start].1.tokens.len();
                    let end = start
                        + encoded[start..]
                            .iter()
                            .take_while(|(_, r)| r.tokens.len() == length)
                            .count();
                    for chunk in encoded[start..end].chunks(self.options.batch_size) {
                        self.infer_chunk(chunk, rows, &mut out, metadata);
                    }
                    start = end;
                }
            }
        }
        out.report.seconds_including_preprocessing = start.elapsed().as_secs_f64();
        Ok(out)
    }

    fn infer_chunk(
        &mut self,
        selected: &[(usize, EncodedRow)],
        rows: &[InputRow],
        out: &mut BatchOutput,
        metadata: bool,
    ) {
        if selected.is_empty() {
            return;
        }
        let refs: Vec<_> = selected.iter().map(|(_, r)| r).collect();
        match self.predict_encoded(&refs) {
            Ok(predictions) => {
                for ((index, _), atoms) in selected.iter().zip(predictions) {
                    if atoms.len() > MAX_ASSERTIONS {
                        reject(
                            out,
                            rows,
                            *index,
                            "assertion_count",
                            format!("Input exceeds {MAX_ASSERTIONS} predicted assertions"),
                        );
                        continue;
                    }
                    out.report.count("predicted", 1);
                    out.report.count("predicted_atoms", atoms.len());
                    if atoms.is_empty() {
                        out.report.count("empty_predictions", 1);
                    }
                    if metadata && let Ok(assertions) = serde_json::to_value(&atoms) {
                        out.rows[*index]
                            .0
                            .insert("_extractor_assertions".into(), assertions);
                    }
                    out.rows[*index].0.insert(
                        "form".into(),
                        Value::Array(atoms.into_iter().map(|a| a.atom).collect()),
                    );
                }
            }
            Err(_) if selected.len() > 1 => {
                let mid = selected.len() / 2;
                self.infer_chunk(&selected[..mid], rows, out, metadata);
                self.infer_chunk(&selected[mid..], rows, out, metadata);
            }
            Err(e) => reject(out, rows, selected[0].0, "inference", e.to_string()),
        }
    }
}

fn reject(
    out: &mut BatchOutput,
    rows: &[InputRow],
    index: usize,
    code: &'static str,
    reason: String,
) {
    out.rows[index].0.insert("form".into(), json!([]));
    out.report.count("unsupported", 1);
    out.report.unsupported.push(Diagnostic {
        event: "unsupported_extraction",
        index,
        id: rows[index].id().into(),
        code,
        reason,
    });
}

/// NumPy uses pairwise summation on the contiguous last float32 axis.
fn pairwise_sum(a: &[f32]) -> f32 {
    if a.len() < 8 {
        return a.iter().fold(-0.0, |s, x| s + x);
    }
    if a.len() <= 128 {
        let mut sums: [f32; 8] = a[..8].try_into().unwrap();
        let end = a.len() / 8 * 8;
        for chunk in a[8..end].chunks_exact(8) {
            for j in 0..8 {
                sums[j] += chunk[j];
            }
        }
        let mut sum = ((sums[0] + sums[1]) + (sums[2] + sums[3]))
            + ((sums[4] + sums[5]) + (sums[6] + sums[7]));
        for v in &a[end..] {
            sum += v;
        }
        return sum;
    }
    let mid = (a.len() / 2) / 8 * 8;
    pairwise_sum(&a[..mid]) + pairwise_sum(&a[mid..])
}

fn decode(
    rows: &[&EncodedRow],
    logits: &[f32],
    max_candidates: usize,
    pairs: &[[String; 2]],
) -> Result<Vec<Vec<Assertion>>> {
    let labels = pairs.len() + 1;
    let mut result = Vec::with_capacity(rows.len());
    for (i, row) in rows.iter().enumerate() {
        let mut pred = Vec::new();
        let mut seen = HashSet::new();
        let text = Text::new(&row.text);
        for (j, candidate) in row.candidates.iter().enumerate() {
            let values =
                &logits[(i * max_candidates + j) * labels..(i * max_candidates + j + 1) * labels];
            ensure!(values.iter().all(|v| v.is_finite()), "Non-finite logits");
            let mut label = 0;
            for n in 1..labels {
                if values[n] > values[label] {
                    label = n;
                }
            }
            if label == 0 {
                continue;
            }
            let max = values[label];
            let prob: Vec<_> = values.iter().map(|v| (v - max).exp()).collect();
            let score = prob[label] / pairwise_sum(&prob);
            if score < 0.5 {
                continue;
            }
            let [subject, attribute] = &pairs[label - 1];
            if !seen.insert((subject, attribute, canonical(&candidate.value))) {
                continue;
            }
            pred.push(Assertion {
                atom: json!({"subject":subject,"attribute":attribute,"value":candidate.value}),
                model_score: score,
                value_span_chars: [candidate.start, candidate.end],
                value_text: text.slice(candidate.start, candidate.end).into(),
            });
        }
        result.push(pred);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_metadata_without_interpreting_it() -> Result<()> {
        let row: InputRow = serde_json::from_value(
            json!({"id":"same","text":"","date":"opaque","label":"false","gold":{"x":1},"form":null}),
        )?;
        row.validate(0)?;
        assert_eq!(row.0["gold"], json!({"x":1}));
        let bad: InputRow = serde_json::from_value(json!({"id":"x","date":"2026-01-01"}))?;
        assert!(bad.validate(0).is_err());
        assert!(
            Options {
                threads: 3,
                ..Default::default()
            }
            .validate()
            .is_err()
        );
        Ok(())
    }
    #[test]
    fn numpy_summation_is_bounded() {
        assert_eq!(pairwise_sum(&vec![1.; 515]), 515.);
    }
}
