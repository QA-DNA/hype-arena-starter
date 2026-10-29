//! Gold-free feature export and full Engine prediction for partition-local GBTs.
//! See tools/verifier_folds/README.md; build against a hashed integration snapshot.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    io::{BufWriter, Write},
    path::Path,
    time::Instant,
};
use unicode_normalization::UnicodeNormalization;
use veridyct_core::{
    Engine, InputRow, Prediction,
    boosted::{BoostedVerifier, FeatureIndex},
};

#[derive(Deserialize)]
struct Request {
    split: String,
    training: Vec<InputRow>,
    queries: Vec<InputRow>,
    fit_folds: BTreeMap<String, usize>,
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

fn hidden(row: &InputRow) -> InputRow {
    InputRow {
        id: row.id.clone(),
        text: row.text.clone(),
        date: row.date.clone(),
        label: String::new(),
        form: Vec::new(),
    }
}

fn check_request(request: &Request) -> Result<(), String> {
    if request.training.is_empty() || request.queries.is_empty() {
        return Err("Both training and queries must be nonempty".into());
    }
    let ids: BTreeSet<_> = request.training.iter().map(|r| r.id.as_str()).collect();
    let texts: BTreeSet<_> = request
        .training
        .iter()
        .map(|r| normalize(&r.text))
        .collect();
    if ids.len() != request.training.len() || request.fit_folds.len() != ids.len() {
        return Err("Training IDs/fold assignments must be complete and unique".into());
    }
    let mut text_folds = BTreeMap::new();
    for row in &request.training {
        if !["true", "false", "unsure"].contains(&row.label.as_str()) {
            return Err("Training rows need known labels".into());
        }
        let fold = *request.fit_folds.get(&row.id).ok_or("Missing fit fold")?;
        if fold >= 5 {
            return Err("Fit folds must lie in 0..5".into());
        }
        if let Some(old) = text_folds.insert(normalize(&row.text), fold)
            && old != fold
        {
            return Err("Normalized copies must share one fit fold".into());
        }
    }
    let query_ids: BTreeSet<_> = request.queries.iter().map(|r| &r.id).collect();
    if query_ids.len() != request.queries.len() {
        return Err("Query IDs must be unique".into());
    }
    for row in &request.queries {
        if !row.label.is_empty() || !row.form.is_empty() {
            return Err("Query labels and forms must be blank".into());
        }
        if ids.contains(row.id.as_str()) || texts.contains(&normalize(&row.text)) {
            return Err("Query ID or normalized text overlaps training".into());
        }
    }
    Ok(())
}

fn check_predictions(predictions: &[Prediction], training: &[InputRow]) -> Result<(), String> {
    let ids: BTreeSet<_> = training.iter().map(|r| r.id.as_str()).collect();
    for p in predictions {
        if p.known_label.is_some() || p.evidence.iter().any(|e| !ids.contains(e.row_id.as_str())) {
            return Err("Prediction exposed a label or non-training evidence".into());
        }
    }
    Ok(())
}

fn runtime(started: Instant) -> Value {
    let status = fs::read_to_string("/proc/self/status").unwrap_or_default();
    let find = |prefix: &str| {
        status
            .lines()
            .find(|s| s.starts_with(prefix))
            .map(str::to_owned)
    };
    json!({"seconds": started.elapsed().as_secs_f64(), "compute_threads": 1,
        "profile": if cfg!(debug_assertions) {"debug"} else {"release"},
        "peak_rss": find("VmHWM:"), "threads": find("Threads:")})
}

fn features(request: &Request, lexicon: &Value, output: &Path) -> Result<(), String> {
    let started = Instant::now();
    let mut fit = BTreeMap::new();
    for fold in 0..5 {
        let parser_training: Vec<_> = request
            .training
            .iter()
            .filter(|r| request.fit_folds[&r.id] != fold)
            .cloned()
            .collect();
        let queries: Vec<_> = request
            .training
            .iter()
            .filter(|r| request.fit_folds[&r.id] == fold)
            .map(hidden)
            .collect();
        if queries.is_empty() {
            continue;
        }
        let engine = Engine::new(&parser_training, lexicon)?;
        let predictions = engine.predict(&queries);
        check_predictions(&predictions, &parser_training)?;
        for (query, prediction) in queries.iter().zip(predictions) {
            // The index is physically partitioned here: Unicode-normalized copies
            // cannot supply graph or observation features, even under other IDs.
            let text = normalize(&query.text);
            let evidence: Vec<_> = request
                .training
                .iter()
                .filter(|r| r.id != query.id && normalize(&r.text) != text)
                .cloned()
                .collect();
            let index = FeatureIndex::compile(&evidence);
            let row = json!({"id":query.id, "features":index.features(query,&prediction.facts),
                "feature_facts":prediction.facts, "mode":"rust_crossfit5",
                "parser_training_rows":parser_training.len(), "feature_evidence_rows":evidence.len(),
                "excluded_query_id_and_normalized_text":true, "parser_fold":fold});
            fit.insert(query.id.clone(), row);
        }
        eprintln!("{}: completed parser fit block {fold}", request.split);
    }
    let engine = Engine::new(&request.training, lexicon)?;
    let index = FeatureIndex::compile(&request.training);
    let predictions = engine.predict(&request.queries);
    check_predictions(&predictions, &request.training)?;
    let mut writer = create_writer(output)?;
    for row in &request.training {
        write_json(
            &mut writer,
            &json!({"partition":"fit", "row":fit.remove(&row.id).ok_or("Missing fit row")?}),
        )?;
    }
    for (row, prediction) in request.queries.iter().zip(predictions) {
        write_json(
            &mut writer,
            &json!({"partition":"test", "row":{
            "id":row.id,"features":index.features(row,&prediction.facts),
            "feature_facts":prediction.facts,"baseline":prediction,"mode":"rust_full_training"}}),
        )?;
    }
    writer.flush().map_err(|e| e.to_string())?;
    eprintln!(
        "{}",
        json!({"split":request.split,"phase":"features","runtime":runtime(started)})
    );
    Ok(())
}

fn create_writer(path: &Path) -> Result<BufWriter<fs::File>, String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    Ok(BufWriter::new(
        fs::File::create(path).map_err(|e| e.to_string())?,
    ))
}

fn write_json(writer: &mut impl Write, value: &Value) -> Result<(), String> {
    writeln!(
        writer,
        "{}",
        serde_json::to_string(value).map_err(|e| e.to_string())?
    )
    .map_err(|e| e.to_string())
}

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() < 4 || args.len() > 5 || !["features", "predict"].contains(&args[0].as_str()) {
        return Err(
            "evaluate_boosted features|predict REQUEST.json LEXICON.json OUTPUT.jsonl [MODEL.json]"
                .into(),
        );
    }
    let read = |p: &str| fs::read_to_string(p).map_err(|e| format!("{p}: {e}"));
    let request: Request = serde_json::from_str(&read(&args[1])?).map_err(|e| e.to_string())?;
    check_request(&request)?;
    let lexicon: Value = serde_json::from_str(&read(&args[2])?).map_err(|e| e.to_string())?;
    if args[0] == "features" {
        return features(&request, &lexicon, Path::new(&args[3]));
    }
    let started = Instant::now();
    let artifact = args.get(4).map(|p| read(p)).transpose()?;
    let verifier = artifact
        .as_deref()
        .map(BoostedVerifier::from_json)
        .transpose()?;
    if let Some(model) = &verifier {
        model.validate_training_partition(&request.training)?;
    }
    let engine = Engine::new(&request.training, &lexicon)?;
    let engine = if let Some(artifact) = &artifact {
        engine.with_boosted(artifact)?
    } else {
        engine
    };
    let index = FeatureIndex::compile(&request.training);
    let predictions = engine.predict(&request.queries);
    check_predictions(&predictions, &request.training)?;
    // Complete every guard before creating output (including model partition).
    let mut writer = create_writer(Path::new(&args[3]))?;
    for (row, prediction) in request.queries.iter().zip(predictions) {
        let features = index.features(row, &prediction.facts);
        let logits = verifier
            .as_ref()
            .map(|m| m.predict_logits(&features))
            .transpose()?;
        let scores = verifier
            .as_ref()
            .map(|m| m.predict(&features))
            .transpose()?;
        write_json(
            &mut writer,
            &json!({"id":row.id,"features":features,
            "feature_facts":prediction.facts,"boosted_logits":logits,
            "boosted_scores":scores,"prediction":prediction}),
        )?;
    }
    writer.flush().map_err(|e| e.to_string())?;
    eprintln!(
        "{}",
        json!({"split":request.split,"phase":"predict","boosted":artifact.is_some(),"runtime":runtime(started)})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("evaluate_boosted: {error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unicode_copies_cannot_cross_the_evidence_partition() {
        let train = InputRow {
            id: "a".into(),
            text: "  STRA\u{df}E \u{ff21} ".into(),
            date: "2026-01-01".into(),
            label: "true".into(),
            form: vec![],
        };
        let query = InputRow {
            id: "b".into(),
            text: "strasse a".into(),
            ..hidden(&train)
        };
        let request = Request {
            split: "test".into(),
            training: vec![train],
            queries: vec![query],
            fit_folds: BTreeMap::from([("a".into(), 0)]),
        };
        assert!(check_request(&request).unwrap_err().contains("overlaps"));
    }

    #[test]
    fn labelled_or_annotated_queries_are_rejected_before_prediction() {
        let train = InputRow {
            id: "a".into(),
            text: "train".into(),
            date: "2026-01-01".into(),
            label: "true".into(),
            form: vec![],
        };
        let mut query = InputRow {
            id: "b".into(),
            text: "query".into(),
            ..hidden(&train)
        };
        query.label = "false".into();
        let mut request = Request {
            split: "test".into(),
            training: vec![train],
            queries: vec![query],
            fit_folds: BTreeMap::from([("a".into(), 0)]),
        };
        assert!(check_request(&request).is_err());
        request.queries[0].label.clear();
        request.queries[0].form=serde_json::from_value(json!([{"subject":"secret","attribute":"hidden","value":{"kind":"number","value":999}}])).unwrap();
        assert!(check_request(&request).is_err());
    }
}
