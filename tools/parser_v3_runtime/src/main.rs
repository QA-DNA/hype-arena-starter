use serde_json::{Value, json};
use std::{
    env,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, BufWriter, Read, Write},
    process,
    time::Instant,
};
use veridyct_parser_v3_runtime::{Adapter, Backend, Input};

const MAX_LINE_BYTES: usize = 2 * 1024 * 1024;
const MAX_LEXICON_BYTES: u64 = 16 * 1024 * 1024;

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let mut flags = std::collections::BTreeMap::new();
    while let Some(key) = args.next() {
        if ![
            "--lexicon",
            "--input",
            "--output",
            "--metrics",
            "--backend",
            "--variant",
            "--model",
        ]
        .contains(&key.as_str())
        {
            return Err(format!("unknown option {key}").into());
        }
        let value = args.next().ok_or("missing option value")?;
        if flags.insert(key, value).is_some() {
            return Err("duplicate option".into());
        }
    }
    let required = |key: &str| flags.get(key).ok_or_else(|| format!("required {key}"));
    let lexicon_file = File::open(required("--lexicon")?)?;
    if lexicon_file.metadata()?.len() > MAX_LEXICON_BYTES {
        return Err("lexicon size limit".into());
    }
    let lexicon: Value = serde_json::from_reader(BufReader::new(lexicon_file))?;
    let backend = match flags
        .get("--backend")
        .map(String::as_str)
        .unwrap_or("program")
    {
        "program" => Backend::Program,
        "schema" => Backend::Schema,
        #[cfg(feature = "frozen-baseline")]
        "frozen-schema" => Backend::FrozenSchema,
        _ => return Err("unknown backend".into()),
    };
    let variant = flags.get("--variant").map(String::as_str).unwrap_or("none");
    let started = Instant::now();
    let mut adapter = Adapter::compile(
        &lexicon,
        backend,
        variant,
        flags.get("--model").map(String::as_str),
    )?;
    let seconds_initialize = started.elapsed().as_secs_f64();
    let input = File::open(required("--input")?)?;
    let mut reader = BufReader::new(input);
    let output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(required("--output")?)?;
    let mut writer = BufWriter::new(output);
    let mut rows = 0usize;
    let mut line = Vec::new();
    let processing = Instant::now();
    loop {
        line.clear();
        let n = reader
            .by_ref()
            .take((MAX_LINE_BYTES + 1) as u64)
            .read_until(b'\n', &mut line)?;
        if n == 0 {
            break;
        }
        if n > MAX_LINE_BYTES {
            return Err("JSONL line size limit".into());
        }
        if line.iter().all(u8::is_ascii_whitespace) {
            continue;
        }
        if rows >= 100_000 {
            return Err("row count limit".into());
        }
        let row: Input = serde_json::from_slice(&line)?;
        serde_json::to_writer(&mut writer, &adapter.parse(row))?;
        writer.write_all(b"\n")?;
        rows += 1;
    }
    writer.flush()?;
    let peak_rss = fs::read_to_string("/proc/self/status").ok().and_then(|s| {
        s.lines()
            .find(|l| l.starts_with("VmHWM:"))
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|n| n.parse::<u64>().ok())
    });
    let metrics = json!({"rows":rows,"seconds_initialize":seconds_initialize,"seconds_processing":processing.elapsed().as_secs_f64(),"seconds_total":started.elapsed().as_secs_f64(),"peak_process_rss_kib":peak_rss,"parser_threads":1,"native_threads":if flags.contains_key("--model") {1} else {0},"candidate_grammar":"frozen-selected-v2-public-lexicon-only","backend":format!("{backend:?}"),"variant":variant,"native_model":flags.contains_key("--model"),"frozen_baseline_commit":option_env!("RUNTIME_BASELINE_COMMIT"),"scope":"initialization + JSONL IO + candidate generation + explicit context + actual Rust parser + serialization; native inference included when selected"});
    if let Some(path) = flags.get("--metrics") {
        let output = OpenOptions::new().write(true).create_new(true).open(path)?;
        serde_json::to_writer_pretty(output, &metrics)?;
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
