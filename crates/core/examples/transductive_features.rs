//! Statistical-only transductive verification research over a frozen current core.
//! Build via tools/transductive_verifier/stage.py; this checkout's older core is
//! deliberately unchanged. No reserved gold or frozen neural extractor is read.
#[path = "../../../tools/transductive_verifier/cluster.rs"]
mod cluster;

use cluster::{ClusterIndex, Families, normalize};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    io::{BufRead, BufReader, BufWriter, Write},
    path::{Path, PathBuf},
    time::Instant,
};
use veridyct_core::{
    Engine, InputRow,
    boosted::{BoostedVerifier, FeatureIndex, Features},
};

#[derive(Deserialize)]
struct Request {
    training: Vec<InputRow>,
    queries: Vec<InputRow>,
    corpus: Vec<InputRow>,
    split: String,
    crossfit_folds: usize,
}

fn hide(row: &InputRow) -> InputRow {
    InputRow {
        id: row.id.clone(),
        text: row.text.clone(),
        date: row.date.clone(),
        label: String::new(),
        form: Vec::new(),
    }
}

fn fnv(text: &str) -> u64 {
    text.bytes().fold(0xcbf29ce484222325, |h, b| {
        (h ^ u64::from(b)).wrapping_mul(0x100000001b3)
    })
}

fn validate(request: &Request) -> Result<(), String> {
    if request.training.is_empty()
        || request.queries.is_empty()
        || !(2..=10).contains(&request.crossfit_folds)
    {
        return Err("Need nonempty train/test and 2..10 crossfit folds".into());
    }
    if request
        .queries
        .iter()
        .chain(&request.corpus)
        .any(|r| !r.label.is_empty() || !r.form.is_empty())
    {
        return Err("Query/corpus labels and gold forms must be blank".into());
    }
    if request
        .training
        .iter()
        .any(|r| !["true", "false", "unsure"].contains(&r.label.as_str()))
    {
        return Err("Training rows need public labels".into());
    }
    let query_ids: BTreeSet<_> = request.queries.iter().map(|r| &r.id).collect();
    let query_text: BTreeSet<_> = request.queries.iter().map(|r| normalize(&r.text)).collect();
    if request
        .training
        .iter()
        .any(|r| query_ids.contains(&r.id) || query_text.contains(&normalize(&r.text)))
    {
        return Err("Outer training contains a query ID or normalized duplicate".into());
    }
    let corpus_ids: BTreeSet<_> = request.corpus.iter().map(|r| &r.id).collect();
    if corpus_ids.len() != request.corpus.len() || query_ids.len() != request.queries.len() {
        return Err("Corpus/query IDs must be unique".into());
    }
    if request
        .training
        .iter()
        .chain(&request.queries)
        .any(|r| !corpus_ids.contains(&r.id))
    {
        return Err("Every train/test text must occur in the permitted public corpus".into());
    }
    Ok(())
}

fn export_partition(
    training: &[InputRow],
    queries: &[InputRow],
    corpus: &[InputRow],
    lexicon: &Value,
    role: &str,
    fold: Option<usize>,
    writer: &mut impl Write,
) -> Result<Value, Box<dyn std::error::Error>> {
    let start = Instant::now();
    let forbidden: BTreeSet<_> = queries.iter().map(|r| normalize(&r.text)).collect();
    let forbidden_ids: BTreeSet<_> = queries.iter().map(|r| &r.id).collect();
    if training
        .iter()
        .any(|r| forbidden_ids.contains(&r.id) || forbidden.contains(&normalize(&r.text)))
    {
        return Err("Crossfit source contains a query or duplicate".into());
    }
    let engine = Engine::new(training, lexicon)?;
    let accepted = FeatureIndex::compile(training);
    let families = Families::new(lexicon);
    let mut parsed = Vec::with_capacity(corpus.len());
    for source in corpus {
        let mut input = hide(source);
        // Actual inferred assertions; no supplied target forms, labels, IDs as
        // model features, world identifiers, proof IDs or neural sidecars.
        input.form = engine.extract(&input);
        parsed.push(input);
    }
    let index = ClusterIndex::compile(&parsed, families.clone())?;
    let mut shuffled = parsed.clone();
    // Deterministic nontrivial shuffle. No input order becomes a factor weight.
    let mut state = 0xd1b54a32d192ed03_u64;
    for i in (1..shuffled.len()).rev() {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        shuffled.swap(i, state as usize % (i + 1));
    }
    let shuffled_index = ClusterIndex::compile(&shuffled, families.clone())?;
    let parsed_by_id: BTreeMap<_, _> = parsed.iter().map(|r| (&r.id, r)).collect();
    let mut empty = 0;
    let mut has_family_votes = 0;
    let mut ambiguous = 0;
    for source in queries {
        let query = parsed_by_id
            .get(&source.id)
            .ok_or("Missing query in corpus")?;
        if query.text != source.text || query.date != source.date {
            return Err("Query/corpus text/date mismatch".into());
        }
        let statistics = index.features(query);
        if statistics != shuffled_index.features(query) {
            return Err(format!(
                "Corpus shuffle changed statistical features for {}",
                query.id
            )
            .into());
        }
        let mut features = accepted.features(query, &query.form);
        features.extend(statistics);
        if features.values().any(|v| !v.is_finite()) {
            return Err("Nonfinite feature".into());
        }
        empty += usize::from(query.form.is_empty());
        has_family_votes += usize::from(
            features
                .get("stat.atom.max.global.families")
                .copied()
                .unwrap_or(0.0)
                > 0.0,
        );
        ambiguous += usize::from(
            features
                .get("stat.atom.max.near30.ambiguity")
                .copied()
                .unwrap_or(0.0)
                > 0.0,
        );
        writeln!(
            writer,
            "{}",
            json!({"id":query.id,"text":query.text,"date":query.date,"role":role,"fold":fold,
            "feature_facts":query.form,"family":families.key(query),"features":features,
            "statistical_estimates_only":true,"extraction":"fresh pure-Rust Engine; query ID/text excluded"})
        )?;
    }
    Ok(
        json!({"role":role,"fold":fold,"training":training.len(),"queries":queries.len(),"empty_parses":empty,
        "rows_with_eligible_family_votes":has_family_votes,"rows_with_near30_conflicts":ambiguous,
        "corpus_shuffle_feature_equality":true,"seconds":start.elapsed().as_secs_f64()}),
    )
}

fn feature_export(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    if args.len() != 3 {
        return Err("transductive_features REQUEST.json LEXICON.json OUTPUT_DIR".into());
    }
    let request: Request =
        serde_json::from_value(serde_json::from_slice::<Value>(&fs::read(&args[0])?)?)?;
    validate(&request)?;
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let directory = Path::new(&args[2]);
    fs::create_dir_all(directory)?;
    let mut writer = BufWriter::new(fs::File::create(
        directory.join(format!("{}-train.jsonl", request.split)),
    )?);
    let mut audit = Vec::new();
    for fold in 0..request.crossfit_folds {
        let in_fold =
            |r: &&InputRow| fnv(&normalize(&r.text)) as usize % request.crossfit_folds == fold;
        let queries: Vec<_> = request.training.iter().filter(in_fold).map(hide).collect();
        let forbidden: BTreeSet<_> = queries.iter().map(|r| normalize(&r.text)).collect();
        let train: Vec<_> = request
            .training
            .iter()
            .filter(|r| !forbidden.contains(&normalize(&r.text)))
            .cloned()
            .collect();
        if queries.is_empty() || train.is_empty() {
            return Err("Empty crossfit fold".into());
        }
        let row = export_partition(
            &train,
            &queries,
            &request.corpus,
            &lexicon,
            "crossfit_train",
            Some(fold),
            &mut writer,
        )?;
        eprintln!("{row}");
        audit.push(row);
    }
    writer.flush()?;
    let mut writer = BufWriter::new(fs::File::create(
        directory.join(format!("{}-test.jsonl", request.split)),
    )?);
    let row = export_partition(
        &request.training,
        &request.queries,
        &request.corpus,
        &lexicon,
        "outer_test",
        None,
        &mut writer,
    )?;
    writer.flush()?;
    eprintln!("{row}");
    audit.push(row);
    fs::write(
        directory.join(format!("{}-audit.json", request.split)),
        serde_json::to_string_pretty(&json!({"split":request.split,
        "accepted_labelled_evidence_is_separate":true,"corpus_labels_and_gold_forms_removed":true,"no_evidence_or_generation_output":true,
        "partition_audits":audit}))?,
    )?;
    Ok(())
}

#[derive(Deserialize)]
struct FeatureRow {
    id: String,
    features: Features,
}

fn score(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    if args.len() != 4 {
        return Err("transductive_features --score REQUEST.json FEATURES.jsonl MODEL_MANIFEST.json OUTPUT.jsonl".into());
    }
    let request: Request =
        serde_json::from_value(serde_json::from_slice::<Value>(&fs::read(&args[0])?)?)?;
    validate(&request)?;
    let paths: BTreeMap<String, PathBuf> = serde_json::from_slice(&fs::read(&args[2])?)?;
    let mut models = BTreeMap::new();
    for (name, path) in paths {
        let model = BoostedVerifier::from_json(&fs::read_to_string(path)?)?;
        // This is mandatory even for research. Never reuse an all-practice or
        // another-split checkpoint, or restore RF priors a second time.
        model.validate_training_partition(&request.training)?;
        models.insert(name, model);
    }
    let mut result = Vec::new();
    for line in BufReader::new(fs::File::open(&args[1])?).lines() {
        let value: Value = serde_json::from_str(&line?)?;
        let row: FeatureRow = serde_json::from_value(value)?;
        let mut probabilities = BTreeMap::new();
        let mut logits = BTreeMap::new();
        for (name, model) in &models {
            probabilities.insert(name, model.predict(&row.features)?);
            logits.insert(name, model.predict_logits(&row.features)?);
        }
        result.push(json!({"id":row.id,"probabilities":probabilities,"logits":logits,"statistical_estimates_only":true}));
    }
    let output = Path::new(&args[3]);
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut writer = BufWriter::new(fs::File::create(output)?);
    for row in result {
        writeln!(writer, "{row}")?;
    }
    writer.flush()?;
    Ok(())
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args: Vec<_> = env::args().skip(1).collect();
    if args.first().is_some_and(|a| a == "--score") {
        args.remove(0);
        score(&args)
    } else {
        feature_export(&args)
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_gold_forms_labels_and_duplicate_text_leakage() {
        let training = InputRow {
            id: "a".into(),
            text: "Ａ statement".into(),
            date: "2026-01-01".into(),
            label: "true".into(),
            form: Vec::new(),
        };
        let query = InputRow {
            id: "q".into(),
            text: "A   STATEMENT".into(),
            date: "2026-01-02".into(),
            label: String::new(),
            form: Vec::new(),
        };
        let mut request = Request {
            training: vec![training],
            queries: vec![query.clone()],
            corpus: vec![query],
            split: "test".into(),
            crossfit_folds: 2,
        };
        assert!(validate(&request).unwrap_err().contains("duplicate"));
        request.training[0].text = "Distinct source".into();
        request.corpus.push(hide(&request.training[0]));
        request.corpus[0].label = "false".into();
        assert!(validate(&request).unwrap_err().contains("blank"));
    }
}
