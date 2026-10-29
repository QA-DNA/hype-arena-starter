use std::{
    collections::HashMap,
    env,
    fs::File,
    io::{BufReader, BufWriter, Read, Write},
    path::{Path, PathBuf},
    time::Instant,
};

use anyhow::{Context as _, Result, bail, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use veridyct_extractor::{
    Batching, Context, Extractor, InputRow, Options,
    encode::{Metadata, encode_input},
    grammar::Grammar,
    runtime::{sha256, verify_bundle},
};

const HELP: &str = "veridyct-extractor --bundle DIR --input rows.json --output filled.json [--report report.json]\n\
  --threads 1|2                 CPU intra-op threads (default 2; inter-op 1)\n\
  --batch-size 1..64             Rows per batch (default 48)\n\
  --context none|previous3text   Only explicit input-order text context (default none)\n\
  --batching padded|exact-length Experimental same-length batching (batch mode only)\n\
  --practice-csv FILE            Optional exact public practice form reuse\n\
  --mode batch|requests|encode   Default batch: InputRow array; requests/encode: explicit\n\
                                [{id?, text, previous_text?}] for parity/library diagnostics\n\
Model, metadata and lexicon hashes are checked before use. No truth verdict is produced.";

#[derive(Deserialize)]
struct Request {
    #[serde(default)]
    id: String,
    text: String,
    #[serde(default)]
    previous_text: String,
}

fn read_json(path: &Path) -> Result<Value> {
    let file = File::open(path)?;
    ensure!(
        file.metadata()?.len() <= 128 * 1024 * 1024,
        "Input JSON exceeds 128 MiB"
    );
    let mut bytes = Vec::new();
    file.take(128 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() <= 128 * 1024 * 1024,
        "Input JSON exceeds 128 MiB"
    );
    let bytes = bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(&bytes);
    Ok(serde_json::from_slice(bytes)?)
}

fn atomic_json(path: &Path, value: &impl serde::Serialize) -> Result<()> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let mut temp = tempfile::NamedTempFile::new_in(parent)?;
    {
        let mut writer = BufWriter::with_capacity(65536, &mut temp);
        serde_json::to_writer(&mut writer, value)?;
        writer.write_all(b"\n")?;
        writer.flush()?;
    }
    temp.as_file().sync_all()?;
    temp.persist(path)?;
    Ok(())
}

fn main() -> std::process::ExitCode {
    match run() {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(e) => {
            eprintln!(
                "{}",
                json!({"event":"extraction_failed","reason":format!("{e:#}")})
            );
            std::process::ExitCode::from(2)
        }
    }
}

fn run() -> Result<()> {
    let start = Instant::now();
    let mut args = env::args().skip(1);
    let mut flags = HashMap::new();
    while let Some(key) = args.next() {
        if key == "--help" || key == "-h" {
            println!("{HELP}");
            return Ok(());
        }
        if key == "--version" {
            println!("veridyct-extractor {}", env!("CARGO_PKG_VERSION"));
            return Ok(());
        }
        ensure!(
            [
                "--bundle",
                "--input",
                "--output",
                "--report",
                "--threads",
                "--batch-size",
                "--context",
                "--batching",
                "--practice-csv",
                "--mode",
                "--export-candidates"
            ]
            .contains(&key.as_str()),
            "Unknown option {key}"
        );
        let value = args
            .next()
            .with_context(|| format!("Missing value for {key}"))?;
        ensure!(!flags.contains_key(&key), "Duplicate option {key}");
        flags.insert(key, value);
    }
    let required = |key: &str| -> Result<PathBuf> {
        Ok(PathBuf::from(
            flags
                .get(key)
                .with_context(|| format!("Required {key}; use --help"))?,
        ))
    };
    let bundle = flags
        .get("--bundle")
        .cloned()
        .or_else(|| env::var("VERIDYCT_EXTRACTOR_BUNDLE").ok())
        .unwrap_or("/opt/veridyct-extractor/model".into());
    let input = required("--input")?;
    let output = required("--output")?;
    ensure!(input != output, "Input and output paths must differ");
    let options = Options {
        threads: flags
            .get("--threads")
            .map(|s| s.parse())
            .transpose()?
            .unwrap_or(2),
        batch_size: flags
            .get("--batch-size")
            .map(|s| s.parse())
            .transpose()?
            .unwrap_or(48),
        context: match flags.get("--context").map(String::as_str).unwrap_or("none") {
            "none" => Context::None,
            "previous3text" => Context::Previous3text,
            _ => bail!("Unsupported context policy"),
        },
        batching: match flags
            .get("--batching")
            .map(String::as_str)
            .unwrap_or("padded")
        {
            "padded" => Batching::Padded,
            "exact-length" => Batching::ExactLength,
            _ => bail!("Unsupported batching policy"),
        },
    };
    options.validate()?;
    let value = read_json(&input)?;
    let mode = flags.get("--mode").map(String::as_str).unwrap_or("batch");
    if mode == "encode" {
        verify_bundle(Path::new(&bundle))?;
        let meta: Metadata = serde_json::from_reader(BufReader::new(File::open(
            Path::new(&bundle).join("meta.json"),
        )?))?;
        let lexicon: Value = serde_json::from_reader(BufReader::new(File::open(
            Path::new(&bundle).join("lexicon.json"),
        )?))?;
        let grammar = Grammar::new(&lexicon, &meta.extra_names)?;
        let requests: Vec<Request> = serde_json::from_value(value)?;
        let encoded: Vec<_> = requests
            .iter()
            .map(
                |r| match encode_input(&r.text, &r.previous_text, &meta, &grammar, &r.id) {
                    Ok(row) => json!({"encoded":row}),
                    Err(e) => json!({"id":r.id,"error":e.to_string()}),
                },
            )
            .collect();
        atomic_json(&output, &encoded)?;
        return Ok(());
    }
    let mut engine = Extractor::load(&bundle, options.clone())?;
    if let Some(practice) = flags.get("--practice-csv") {
        engine.load_practice(practice)?;
    }
    if mode == "requests" {
        ensure!(
            options.context == Context::None
                && options.batching == Batching::Padded
                && !flags.contains_key("--practice-csv"),
            "requests mode uses only explicit request context"
        );
        let requests: Vec<Request> = serde_json::from_value(value)?;
        let mut predictions = Vec::new();
        for chunk in requests.chunks(options.batch_size) {
            let mut selected = Vec::new();
            let mut filled: Vec<Value> = chunk
                .iter()
                .map(|r| json!({"id":r.id,"form":[],"assertions":[]}))
                .collect();
            for (index, request) in chunk.iter().enumerate() {
                match engine.encode(&request.text, &request.previous_text, &request.id) {
                    Ok(row) => selected.push((index, row)),
                    Err(e) => filled[index]["error"] = json!(e.to_string()),
                }
            }
            for ((index, _), assertions) in selected
                .iter()
                .zip(engine.predict_encoded(&selected.iter().map(|(_, r)| r).collect::<Vec<_>>())?)
            {
                let form: Vec<_> = assertions.iter().map(|a| &a.atom).collect();
                filled[*index] = json!({"id":chunk[*index].id,"form":form,"assertions":assertions});
            }
            predictions.extend(filled);
        }
        atomic_json(&output, &predictions)?;
        eprintln!(
            "{}",
            json!({"event":"requests_complete","rows":predictions.len(),"seconds_total":start.elapsed().as_secs_f64()})
        );
        return Ok(());
    }
    ensure!(mode == "batch", "Unknown mode {mode}");
    let rows: Vec<InputRow> =
        serde_json::from_value(value).context("Input must be a JSON array of InputRow objects")?;
    let export_candidates = match flags
        .get("--export-candidates")
        .map(String::as_str)
        .unwrap_or("false")
    {
        "true" => true,
        "false" => false,
        _ => bail!("--export-candidates must be true or false"),
    };
    let mut result = engine.extract_batch_with_metadata(&rows, export_candidates)?;
    if export_candidates {
        for (row, input) in result.rows.iter_mut().zip(&rows) {
            if input.text().chars().count() > 65536 {
                continue;
            }
            match engine.grammar.binding_candidates(input.text()) {
                Ok(mut candidates) => {
                    if candidates.len() > 256 {
                        candidates.truncate(256);
                        row.0
                            .insert("_extractor_candidate_truncated".into(), json!(true));
                    }
                    row.0.insert(
                        "_extractor_candidates".into(),
                        serde_json::to_value(candidates)?,
                    );
                }
                Err(error) => {
                    row.0.insert(
                        "_extractor_candidate_error".into(),
                        json!(error.to_string()),
                    );
                }
            }
        }
    }
    for event in &result.report.unsupported {
        eprintln!("{}", serde_json::to_string(event)?);
    }
    let mut report = serde_json::to_value(&result.report)?;
    report["seconds_total"] = json!(start.elapsed().as_secs_f64());
    report["input_sha256"] = json!(sha256(&input)?);
    report["platform"] = json!(format!("{}-{}", env::consts::OS, env::consts::ARCH));
    if let Ok(status) = std::fs::read_to_string("/proc/self/status")
        && let Some(line) = status.lines().find(|s| s.starts_with("VmHWM:"))
    {
        report["peak_process_rss_kib"] = json!(
            line.split_whitespace()
                .nth(1)
                .unwrap_or("0")
                .parse::<u64>()?
        );
    }
    if let Some(path) = flags.get("--report") {
        ensure!(
            Path::new(path) != input && Path::new(path) != output,
            "Report path must differ from input/output"
        );
        atomic_json(Path::new(path), &report)?;
    }
    atomic_json(&output, &result.rows)?;
    report.as_object_mut().unwrap().remove("unsupported");
    report["event"] = json!("extraction_complete");
    eprintln!("{report}");
    Ok(())
}
