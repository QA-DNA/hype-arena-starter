use std::{
    env,
    error::Error,
    fs,
    path::{Path, PathBuf},
    process::ExitCode,
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use veridyct_core::{Engine, generate_claims, output_csv, read_csv};
mod parser;
mod preprocessing;

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("veridyct: {error}");
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        None | Some("--help" | "help" | "-h") => {
            help();
            Ok(())
        }
        Some("info") if args.len() == 1 => {
            println!(
                "{}",
                serde_json::to_string_pretty(&veridyct_core::workspace_info())?
            );
            Ok(())
        }
        Some("run") => arena(&args[1..]),
        Some("lexicon" | "normalize" | "split" | "parse") => preprocessing::run(&args),
        _ => Err("Unknown command or arguments. Run veridyct --help.".into()),
    }
}

fn arena(args: &[String]) -> Result<(), Box<dyn Error>> {
    let mut input = PathBuf::from("/universe/universe.csv");
    let mut lexicon = PathBuf::from("/universe/lexicon.json");
    let mut output = PathBuf::from("/output/output.csv");
    if !args.len().is_multiple_of(2) {
        return Err("Options require values: --input PATH --lexicon PATH --output PATH".into());
    }
    for pair in args.chunks_exact(2) {
        match pair[0].as_str() {
            "--input" => input = PathBuf::from(&pair[1]),
            "--lexicon" => lexicon = PathBuf::from(&pair[1]),
            "--output" => output = PathBuf::from(&pair[1]),
            _ => return Err(format!("Unknown run option: {}", pair[0]).into()),
        }
    }
    deadline_check()?;
    let started = Instant::now();
    let mut rows = read_csv(
        &fs::read_to_string(&input).map_err(|e| format!("Cannot read {}: {e}", input.display()))?,
    )?;
    let lexicon: serde_json::Value = serde_json::from_str(&fs::read_to_string(&lexicon)?)?;
    let practice = read_csv(include_str!("../../../data/practice.csv"))?;
    // Embedded public forms take precedence over optional statistical extraction.
    let exact: std::collections::BTreeMap<_, _> = practice
        .iter()
        .map(|r| (r.text.as_str(), r.form.as_slice()))
        .collect();
    for row in &mut rows {
        if let Some(form) = exact.get(row.text.as_str()) {
            row.form = form.to_vec();
        }
    }
    let extraction_hints = parser::enrich(
        &mut rows,
        output.parent().unwrap_or(Path::new("/output")),
        &lexicon,
    )?;
    eprintln!(
        "Loaded {} runtime rows; {} require labels. CPU forest; no network or runtime LLM.",
        rows.len(),
        rows.iter().filter(|row| row.label.is_empty()).count()
    );
    let mut engine = Engine::new(&practice, &lexicon)?;
    if let Some(path) = env::var_os("VERIDYCT_VERIFIER_MODEL") {
        engine = engine.with_boosted(&fs::read_to_string(path)?)?;
        eprintln!(
            "Partition-validated gradient-boosted verifier loaded; original class proportions, no extra prior correction."
        );
    }
    eprintln!(
        "Embedded training graph: {}",
        serde_json::to_string(engine.knowledge_summary())?
    );
    deadline_check()?;
    let canonical_seed = engine.canonical_seed_present(&rows);
    eprintln!(
        "Canonical seed present in runtime universe: {canonical_seed}; only supplied-world evidence licenses runtime proofs."
    );
    let predictions = engine.predict_universe_with_hints(&rows, &extraction_hints);
    eprintln!(
        "Classification complete in {:.3}s; constructing evidenced claims.",
        started.elapsed().as_secs_f64()
    );
    let mut generation_rows = if canonical_seed { practice } else { Vec::new() };
    generation_rows.extend(rows.iter().cloned());
    let generation = generate_claims(&generation_rows, &predictions, &lexicon, 1_000)?;
    let mut predictions = predictions;
    if env::var("VERIDYCT_KB_CHAIN").is_ok_and(|v| v == "1") {
        // Off by default. Relabels only the unlabelled rows; claims were already built above.
        let chain_started = Instant::now();
        let practice = read_csv(include_str!("../../../data/practice.csv"))?;
        match veridyct_core::kb_chain::relabel(&rows, &mut predictions, &lexicon, &practice) {
            Some(n) => eprintln!(
                "KB temporal chain relabelled {n} rows in {:.3}s.",
                chain_started.elapsed().as_secs_f64()
            ),
            None => eprintln!("KB temporal chain: no two-class fit; engine labels kept."),
        }
    }
    let csv = output_csv(&predictions, &generation.claims)?;
    atomic_write(&output, csv.as_bytes())?;
    if env::var("VERIDYCT_DIAGNOSTICS").is_ok_and(|v| v == "1") {
        let diagnostic = serde_json::to_vec(
            &serde_json::json!({"canonical_seed":canonical_seed,"extraction_hints":&extraction_hints,"predictions":&predictions,"generation":&generation}),
        )?;
        atomic_write(&output.with_extension("diagnostics.json"), &diagnostic)?;
    }
    eprintln!(
        "Wrote {} bytes with {} predictions and {} claims selected from {} candidates in {:.3}s.",
        csv.len(),
        predictions
            .iter()
            .filter(|p| p.known_label.is_none())
            .count(),
        generation.claims.len(),
        generation.candidate_count,
        started.elapsed().as_secs_f64()
    );
    for note in generation.notes {
        eprintln!("{note}");
    }
    if generation.claims.len() != 1_000 {
        return Err("Fewer than 1,000 evidenced claims; partial output was preserved and is not contest-complete".into());
    }
    Ok(())
}

fn deadline_check() -> Result<(), Box<dyn Error>> {
    if let Ok(value) = env::var("ARENA_DEADLINE") {
        let deadline: u64 = value
            .parse()
            .map_err(|_| "ARENA_DEADLINE must be Unix seconds")?;
        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
        if now.saturating_add(2) >= deadline {
            return Err("Arena deadline reached before next processing stage".into());
        }
    }
    Ok(())
}

fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), Box<dyn Error>> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let name = path
        .file_name()
        .ok_or("Output path needs a filename")?
        .to_string_lossy();
    let temporary = parent.join(format!(".{name}.{}.tmp", std::process::id()));
    fs::write(&temporary, bytes)?;
    if let Err(error) = fs::rename(&temporary, path) {
        let _ = fs::remove_file(&temporary);
        return Err(format!("Cannot publish {}: {error}", path.display()).into());
    }
    Ok(())
}

fn help() {
    println!(
        "Preprocessing: lexicon compile --input lexicon.json --output index.json [--aliases reviewed.json]\n  normalize --index index.json --input rows.csv --output normalized.csv\n  split --index index.json --input normalized.csv --output assertions.csv [--summary rows.csv] [--context previous|off]\n  parse --index index.json --input rows.csv --output assertions.csv [--summary rows.csv] [--context previous|off]\n"
    );
    println!(
        "VERIDYCT · evidence before verdict\n\n  info             Workspace and solver status as JSON\n  run              Read /universe, write /output/output.csv\n                   [--input PATH] [--lexicon PATH] [--output PATH]\n"
    );
}
