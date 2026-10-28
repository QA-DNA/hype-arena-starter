use std::{
    env,
    error::Error,
    fs,
    path::{Path, PathBuf},
    process::ExitCode,
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use veridyct_core::{Engine, generate_claims, output_csv, read_csv};

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
    let rows = read_csv(
        &fs::read_to_string(&input).map_err(|e| format!("Cannot read {}: {e}", input.display()))?,
    )?;
    let lexicon: serde_json::Value = serde_json::from_str(&fs::read_to_string(&lexicon)?)?;
    let practice = read_csv(include_str!("../../../data/practice.csv"))?;
    eprintln!(
        "Loaded {} runtime rows; {} require labels. CPU forest; no network or runtime LLM.",
        rows.len(),
        rows.iter().filter(|row| row.label.is_empty()).count()
    );
    let engine = Engine::new(&practice, &lexicon)?;
    deadline_check()?;
    let predictions = engine.predict(&rows);
    eprintln!(
        "Classification complete in {:.3}s; constructing evidenced claims.",
        started.elapsed().as_secs_f64()
    );
    let mut generation_rows = practice;
    generation_rows.extend(rows.iter().cloned());
    let generation = generate_claims(&generation_rows, &predictions, &lexicon, 1_000)?;
    let csv = output_csv(&predictions, &generation.claims)?;
    atomic_write(&output, csv.as_bytes())?;
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
        "VERIDYCT · evidence before verdict\n\n  info             Workspace and solver status as JSON\n  run              Read /universe, write /output/output.csv\n                   [--input PATH] [--lexicon PATH] [--output PATH]\n"
    );
}
