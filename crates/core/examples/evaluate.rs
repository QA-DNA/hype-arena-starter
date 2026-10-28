//! Run: cargo run --release -p veridyct-core --example evaluate
use serde_json::{Value, json};
use std::{error::Error, fs, path::Path, time::Instant};
use veridyct_core::{engine::{Engine, evaluate_holdout}, model::InputRow};

fn main() -> Result<(), Box<dyn Error>> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut reader = csv::Reader::from_path(root.join("data/practice.csv"))?;
    let mut practice = Vec::new();
    for record in reader.records() {
        let record = record?;
        practice.push(InputRow {
            id: record[0].into(), text: record[1].into(), date: record[2].into(),
            label: record[3].into(), form: serde_json::from_str(&record[4])?,
        });
    }
    let lexicon: Value = serde_json::from_str(&fs::read_to_string(root.join("data/lexicon.json"))?)?;
    let start = Instant::now();
    let engine = Engine::new(&practice, &lexicon)?;
    let training_seconds = start.elapsed().as_secs_f64();
    let rows: Vec<InputRow> = (0..20_000).map(|index| {
        let source = &practice[index % practice.len()];
        InputRow {
            id: format!("load-{index}"),
            text: if index < practice.len() {source.text.clone()} else {format!("{} Additional record {index}.", source.text)},
            date: source.date.clone(),
            label: if index < practice.len() {source.label.clone()} else {String::new()},
            form: Vec::new(),
        }
    }).collect();
    let start = Instant::now();
    let predictions = engine.predict(&rows);
    let prediction_seconds = start.elapsed().as_secs_f64();
    let peak_rss = fs::read_to_string("/proc/self/status").unwrap_or_default().lines()
        .find(|line| line.starts_with("VmHWM:")).unwrap_or("unavailable on this platform").to_owned();
    let hardware = fs::read_to_string("/proc/cpuinfo").unwrap_or_default().lines()
        .find(|line| line.starts_with("model name")).map(str::to_owned)
        .unwrap_or_else(|| std::env::var("PROCESSOR_IDENTIFIER").unwrap_or_default());
    let benchmark = json!({
        "profile": if cfg!(debug_assertions) {"debug"} else {"release"},
        "source_commit": std::env::var("VERIDYCT_BENCH_COMMIT").unwrap_or_else(|_|"record git rev-parse HEAD separately".into()),
        "hardware": hardware,
        "available_cpus": std::thread::available_parallelism().map(|n|n.get()).unwrap_or(1),
        "compute_threads": 1,
        "rows": rows.len(), "unknown_rows": rows.iter().filter(|row|row.label.is_empty()).count(),
        "form_column": false, "training_seconds": training_seconds,
        "prediction_seconds": prediction_seconds, "total_seconds": training_seconds+prediction_seconds,
        "peak_rss": peak_rss, "trees": engine.tree_count(),
        "labels": {
            "true": predictions.iter().filter(|p|p.label=="true").count(),
            "false": predictions.iter().filter(|p|p.label=="false").count(),
            "unsure": predictions.iter().filter(|p|p.label=="unsure").count()
        },
        "note": "Synthetic near-template load: 1897 known rows plus 18103 practice-derived texts with an extra unique sentence, all without forms. Timing is not accuracy evidence. Run under --cpus 2 --memory 6g for resource parity."
    });
    drop(predictions); drop(engine);
    let start = Instant::now();
    let holdout = evaluate_holdout(&practice, &lexicon)?;
    let report = json!({"benchmark":benchmark,"holdout":holdout,"holdout_seconds":start.elapsed().as_secs_f64()});
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}
