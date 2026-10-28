use std::{env, error::Error, process::ExitCode};

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
    match args.as_slice() {
        [] => help(),
        [command] if command == "--help" || command == "help" || command == "-h" => help(),
        [command] if command == "info" => {
            println!(
                "{}",
                serde_json::to_string_pretty(&veridyct_core::workspace_info())?
            );
        }
        [command] if command == "run" => {
            return Err("The solver is not implemented. No output.csv was created. Use info to check the workspace.".into());
        }
        [command, ..]
            if matches!(
                command.as_str(),
                "lexicon" | "normalize" | "split" | "parse"
            ) =>
        {
            preprocessing::run(&args)?;
        }
        _ => return Err("Unknown command or arguments. Run veridyct --help.".into()),
    }
    Ok(())
}

fn help() {
    println!(
        "VERIDYCT · evidence before verdict\n\n  info             Workspace status as JSON\n  run              Reserved for the future competition solver\n  lexicon compile  --input lexicon.json --output index.json [--aliases reviewed.json]\n  normalize        --index index.json --input rows.csv --output normalized.csv\n  split            --index index.json --input normalized.csv --output assertions.csv [--summary rows.csv]\n  parse            --index index.json --input rows.csv --output assertions.csv [--summary rows.csv]\n\nPreprocessing keeps assertion text, not typed values or truth verdicts.\n"
    );
}
