//! Partition-guarded full-pipeline evaluation of externally inferred assertions.
//! Gold belongs in a separate scoring process and is never read by this example.
use serde::Deserialize;
use serde_json::Value;
use std::{collections::BTreeSet, env, fs, path::Path};
use unicode_normalization::UnicodeNormalization;
use veridyct_core::{Engine, ExtractionHints, InputRow};

#[derive(Deserialize)]
struct Request {
    training: Vec<InputRow>,
    queries: Vec<InputRow>,
    #[serde(default)]
    hints: ExtractionHints,
}

fn normalize(text: &str) -> String {
    text.nfkc()
        .collect::<String>()
        .to_lowercase()
        .replace('\u{df}', "ss")
        .replace('\u{3c2}', "\u{3c3}")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if !(3..=4).contains(&args.len()) {
        return Err(
            "evaluate_parsed REQUEST.json LEXICON.json OUTPUT.json [PARTITION_MODEL.json]".into(),
        );
    }
    let request: Request = serde_json::from_slice(&fs::read(&args[0])?)?;
    let ids: BTreeSet<_> = request.queries.iter().map(|r| r.id.as_str()).collect();
    let texts: BTreeSet<_> = request.queries.iter().map(|r| normalize(&r.text)).collect();
    if ids.len() != request.queries.len() || request.queries.iter().any(|r| !r.label.is_empty()) {
        return Err("Queries require unique IDs and blank labels".into());
    }
    if request
        .training
        .iter()
        .any(|r| ids.contains(r.id.as_str()) || texts.contains(&normalize(&r.text)))
    {
        return Err("Training overlaps a query ID or normalized text".into());
    }
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let mut engine = Engine::new(&request.training, &lexicon)?;
    if let Some(path) = args.get(3) {
        engine = engine.with_boosted(&fs::read_to_string(path)?)?;
    }
    let predictions = engine.predict_with_hints(&request.queries, &request.hints);
    let train_ids: BTreeSet<_> = request.training.iter().map(|r| r.id.as_str()).collect();
    if predictions
        .iter()
        .flat_map(|p| &p.evidence)
        .any(|e| !train_ids.contains(e.row_id.as_str()))
    {
        return Err("Prediction cites evidence outside its training partition".into());
    }
    let output = Path::new(&args[2]);
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(output, serde_json::to_vec(&predictions)?)?;
    eprintln!(
        "Completed {} parsed queries against {} clean training rows; boosted={}.",
        predictions.len(),
        request.training.len(),
        args.len() == 4
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
