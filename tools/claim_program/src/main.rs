use serde::Deserialize;
use serde_json::{Value, json};
use std::{env, fs, process, time::Instant};
use veridyct_claim_program_tools::{claim_program::ProgramParser, structured::ValueCandidate};
use veridyct_core::Fact;

#[derive(Deserialize)]
struct Row {
    id: String,
    text: String,
    #[serde(default, alias = "_extractor_candidates")]
    candidates: Vec<ValueCandidate>,
    #[serde(default, alias = "form")]
    neural: Vec<Fact>,
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if !(4..=5).contains(&args.len()) {
        return Err("usage: veridyct-claim-program-tools LEXICON ROWS OUTPUT [METRICS]".into());
    }
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let parser = ProgramParser::compile(&lexicon)?;
    // The boundary deserializes text/proposals only; unrelated input metadata
    // (labels, observation dates, gold, world pointers) never reaches parsing.
    let rows: Vec<Row> = serde_json::from_slice(&fs::read(&args[2])?)?;
    let started = Instant::now();
    let result: Vec<_> = rows
        .iter()
        .map(|row| {
            let program = parser.parse(&row.text, &row.candidates, &row.neural);
            json!({"id":row.id,"legacy_facts":program.legacy_facts(),"program":program})
        })
        .collect();
    let seconds = started.elapsed().as_secs_f64();
    fs::write(&args[3], serde_json::to_vec(&result)?)?;
    let peak_rss_kib = fs::read_to_string("/proc/self/status").ok().and_then(|s| {
        s.lines()
            .find(|line| line.starts_with("VmHWM:"))
            .and_then(|line| line.split_whitespace().nth(1))
            .and_then(|n| n.parse::<u64>().ok())
    });
    let metrics = json!({"rows":rows.len(),"seconds_parse":seconds,"peak_process_rss_kib":peak_rss_kib,"parser_threads":1,"scope":"program parsing only; excludes neural candidate preparation"});
    if let Some(path) = args.get(4) {
        fs::write(path, serde_json::to_vec_pretty(&metrics)?)?;
    }
    eprintln!("{metrics}");
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        process::exit(2);
    }
}
