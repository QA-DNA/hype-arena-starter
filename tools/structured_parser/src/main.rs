use serde::Deserialize;
use serde_json::{Value, json};
use std::{env, fs, process, time::Instant};
use veridyct_core::Fact;
use veridyct_structured_parser_tools::structured::{SchemaParser, ValueCandidate};

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
    let started = Instant::now();
    let args: Vec<_> = env::args().collect();
    if !(4..=5).contains(&args.len()) {
        return Err("usage: veridyct-structured-parser-tools LEXICON ROWS OUTPUT [METRICS]".into());
    }
    let lexicon: Value = serde_json::from_slice(&fs::read(&args[1])?)?;
    let parser = SchemaParser::compile(&lexicon)?;
    let rows: Vec<Row> = serde_json::from_slice(&fs::read(&args[2])?)?;
    let prepared_seconds = started.elapsed().as_secs_f64();
    let parsing = Instant::now();
    let result: Vec<_> = rows
        .iter()
        .map(|r| json!({"id":r.id,"parsed":parser.parse(&r.text,&r.candidates,&r.neural)}))
        .collect();
    let parse_seconds = parsing.elapsed().as_secs_f64();
    fs::write(&args[3], serde_json::to_vec(&result)?)?;
    let peak_rss_kib = fs::read_to_string("/proc/self/status").ok().and_then(|s| {
        s.lines()
            .find(|s| s.starts_with("VmHWM:"))
            .and_then(|line| line.split_whitespace().nth(1))
            .and_then(|s| s.parse::<u64>().ok())
    });
    let metrics = json!({"rows":rows.len(),"seconds_prepared":prepared_seconds,"seconds_parse":parse_seconds,"seconds_total":started.elapsed().as_secs_f64(),"peak_process_rss_kib":peak_rss_kib,"parser_threads":1,"scope":"schema binding only; excludes neural candidate preparation"});
    if let Some(path) = args.get(4) {
        fs::write(path, serde_json::to_vec_pretty(&metrics)?)?;
    }
    eprintln!("{metrics}");
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        process::exit(2);
    }
}
