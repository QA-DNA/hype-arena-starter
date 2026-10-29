//! Research harness over a byte-hashed read-only integration snapshot.
//! Stage with tools/verifier_lab/stage.py first. No snapshot belongs in Git.
#![allow(dead_code)]
use veridyct_core::{boosted, engine, model};

use model::InputRow;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    env, fs,
    io::{BufWriter, Write},
    path::Path,
    time::Instant,
};

#[derive(Deserialize)]
struct Request {
    training: Vec<InputRow>,
    queries: Vec<InputRow>,
    mode: String,
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() < 3 {
        return Err("verifier_features REQUEST.json LEXICON.json OUTPUT.jsonl [MODEL.json]".into());
    }
    let request: Request = serde_json::from_slice(&fs::read(&args[0])?)?;
    if request.queries.iter().any(|r| !r.label.is_empty()) {
        return Err("Query labels must be blank".into());
    }
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let started = Instant::now();
    let engine = engine::Engine::new(&request.training, &lexicon)?;
    let index = boosted::FeatureIndex::compile(&request.training);
    let verifier: Option<boosted::BoostedVerifier> = args
        .get(3)
        .map(|p| -> Result<_, Box<dyn std::error::Error>> {
            Ok(boosted::BoostedVerifier::from_json(&fs::read_to_string(
                p,
            )?)?)
        })
        .transpose()?;
    if let Some(model) = &verifier {
        model.validate()?;
        model.validate_training_partition(&request.training)?;
    }
    let output = Path::new(&args[2]);
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut writer = BufWriter::new(fs::File::create(output)?);
    let predictions = engine.predict(&request.queries);
    for (row, prediction) in request.queries.iter().zip(predictions) {
        // Inferred empty forms stay empty here. The Engine's template fallback can
        // recover a familiar training form and would leak parse quality into fit.
        let facts = if request.mode == "template" {
            &prediction.facts
        } else {
            &row.form
        };
        let features = index.features(row, facts);
        let scores = verifier
            .as_ref()
            .map(|m| m.predict(&features))
            .transpose()?;
        let logits = verifier
            .as_ref()
            .map(|m| m.predict_logits(&features))
            .transpose()?;
        writeln!(
            writer,
            "{}",
            serde_json::to_string(
                &json!({"id":row.id,"features":features,"feature_facts":facts,"baseline":prediction,"mode":request.mode,"boosted_scores":scores,"boosted_logits":logits})
            )?
        )?;
    }
    writer.flush()?;
    eprintln!(
        "{}",
        json!({"training":request.training.len(),"queries":request.queries.len(),"mode":request.mode,"seconds":started.elapsed().as_secs_f64(),"tree_count":engine.tree_count()})
    );
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(2);
    }
}
