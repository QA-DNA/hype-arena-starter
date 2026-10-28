use std::{env, error::Error, process::ExitCode};

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
        _ => return Err("Unknown command or arguments. Run veridyct --help.".into()),
    }
    Ok(())
}

fn help() {
    println!(
        "VERIDYCT · evidence before verdict\n\n  info             Workspace status as JSON\n  run              Reserved for the future competition solver\n"
    );
}
