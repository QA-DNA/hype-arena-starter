//! Gold-free adapter compiled against the checked-in original MVP core.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    env, fs,
    io::{BufWriter, Write},
    time::Instant,
};
use veridyct_core::{Engine, InputRow};

#[derive(Deserialize)]
struct Request {
    training: Vec<InputRow>,
    queries: Vec<InputRow>,
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    if args.len() != 3 {
        return Err("original_rf REQUEST LEXICON OUTPUT".into());
    }
    let request: Request = serde_json::from_slice(&fs::read(&args[0])?)?;
    if request
        .queries
        .iter()
        .any(|r| !r.label.is_empty() || !r.form.is_empty())
    {
        return Err("Test labels/forms must be hidden".into());
    }
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let started = Instant::now();
    let engine = Engine::new(&request.training, &lexicon)?;
    let predictions = engine.predict(&request.queries);
    let ids: std::collections::BTreeSet<_> =
        request.training.iter().map(|r| r.id.as_str()).collect();
    if predictions.iter().any(|p| {
        p.known_label.is_some() || p.evidence.iter().any(|e| !ids.contains(e.row_id.as_str()))
    }) {
        return Err("Original RF exposed hidden labels or nontraining evidence".into());
    }
    let mut writer = BufWriter::new(fs::File::create(&args[2])?);
    for prediction in predictions {
        writeln!(
            writer,
            "{}",
            json!({"id":prediction.id,"prediction":prediction})
        )?;
    }
    writer.flush()?;
    let status = fs::read_to_string("/proc/self/status").unwrap_or_default();
    eprintln!(
        "{}",
        json!({"phase":"original_rf","seconds":started.elapsed().as_secs_f64(),"compute_threads":1,
        "peak_rss":status.lines().find(|s|s.starts_with("VmHWM:"))})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("original_rf: {error}");
        std::process::exit(2);
    }
}
