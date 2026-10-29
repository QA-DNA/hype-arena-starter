use regex::Regex;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    env,
    error::Error,
    fs,
    path::{Path, PathBuf},
    process::{Command, ExitCode},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn main() -> ExitCode {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    match run(root, &env::args().skip(1).collect::<Vec<_>>()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("xtask: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run(root: &Path, args: &[String]) -> Result<()> {
    let command = args.first().map(String::as_str).unwrap_or("help");
    if !matches!(command, "context") && args.len() > 1 {
        return Err(format!("{command} does not accept additional arguments").into());
    }
    match command {
        "help" | "--help" | "-h" => println!(
            "VERIDYCT tasks\n\n  doctor       Inspect local prerequisites\n  setup        Fetch locked dependencies\n  dev          Run the local workbench at 127.0.0.1:8787\n  check        Format, lint, docs, graph and upstream integrity\n  test         Run workspace tests\n  build        Build release binaries\n  docs         Validate documentation, graph and original files\n  graph        Export a fingerprinted map to artifacts/project-graph.json\n  context      --scope core|cli|api|web|qa|native|tooling [--task ID] [--max-chars N]\n  arena-check  Run the official checker on Linux (solver still required)"
        ),
        "doctor" => doctor(root)?,
        "setup" => {
            exec(root, "cargo", &["fetch", "--locked"])?;
            println!("Dependencies ready. Next: cargo xtask doctor, then cargo xtask dev.");
        }
        "dev" => exec(
            root,
            "cargo",
            &["run", "--locked", "--package", "veridyct-api"],
        )?,
        "check" => {
            exec(root, "cargo", &["fmt", "--all", "--", "--check"])?;
            exec(
                root,
                "cargo",
                &[
                    "clippy",
                    "--locked",
                    "--workspace",
                    "--all-targets",
                    "--",
                    "-D",
                    "warnings",
                ],
            )?;
            validate_docs(root)?;
        }
        "test" => exec(root, "cargo", &["test", "--locked", "--workspace"])?,
        "build" => exec(
            root,
            "cargo",
            &["build", "--locked", "--release", "--workspace"],
        )?,
        "docs" => validate_docs(root)?,
        "graph" => {
            let graph = graph_snapshot(root)?;
            fs::create_dir_all(root.join("artifacts"))?;
            fs::write(
                root.join("artifacts/project-graph.json"),
                format!("{}\n", serde_json::to_string_pretty(&graph)?),
            )?;
            println!(
                "Wrote artifacts/project-graph.json (curated relations + extracted Cargo dependencies)."
            );
        }
        "context" => context(root, &args[1..])?,
        "arena-check" => {
            if !cfg!(target_os = "linux") {
                return Err("The official checker requires Linux. Use WSL2 or a Linux host with Docker and Python 3.".into());
            }
            eprintln!(
                "The organizer checker verifies output format; semantic quality requires independent evaluation."
            );
            exec(root, "sh", &["scripts/check.sh"])?;
        }
        other => return Err(format!("Unknown task {other:?}; use cargo xtask help").into()),
    }
    Ok(())
}

fn exec(root: &Path, program: &str, args: &[&str]) -> Result<()> {
    eprintln!("→ {program} {}", args.join(" "));
    let status = Command::new(program)
        .args(args)
        .current_dir(root)
        .status()
        .map_err(|e| format!("Cannot start {program}: {e}"))?;
    if !status.success() {
        return Err(format!("{program} failed ({status})").into());
    }
    Ok(())
}

fn capture(root: &Path, program: &str, args: &[&str]) -> Result<String> {
    let output = Command::new(program)
        .args(args)
        .current_dir(root)
        .output()?;
    if !output.status.success() {
        return Err(format!(
            "{program} failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )
        .into());
    }
    Ok(String::from_utf8(output.stdout)?)
}

fn doctor(root: &Path) -> Result<()> {
    println!("VERIDYCT / {} / {}", env::consts::OS, env::consts::ARCH);
    for program in ["rustc", "cargo", "git"] {
        println!("[ok] {}", capture(root, program, &["--version"])?.trim());
    }
    for (program, args, purpose) in [
        ("python3", vec!["--version"], "official checker (Python 3)"),
        (
            "docker",
            vec!["info", "--format", "{{.ServerVersion}}"],
            "container verification",
        ),
    ] {
        match capture(root, program, &args) {
            Ok(version) => println!("[ok] {purpose}: {}", version.trim()),
            Err(_) => println!("[optional] {purpose} unavailable here; required for arena-check"),
        }
    }
    println!(
        "Bind address: {}",
        env::var("VERIDYCT_ADDR").unwrap_or_else(|_| "127.0.0.1:8787".into())
    );
    println!("No API keys, NVIDIA GPU, Node runtime, or network inference needed.");
    println!("A successful doctor checks tools, not solver correctness.");
    Ok(())
}

fn source_path(root: &Path, relative: &str) -> Result<PathBuf> {
    let relative = Path::new(relative);
    if relative.is_absolute() {
        return Err("Expected a repository-relative path".into());
    }
    let canonical_root = root.canonicalize()?;
    let resolved = root.join(relative).canonicalize()?;
    if !resolved.starts_with(&canonical_root) {
        return Err("Source path escapes the repository".into());
    }
    Ok(resolved)
}

fn graph_source(root: &Path) -> Result<Value> {
    let graph: Value =
        serde_json::from_str(&fs::read_to_string(root.join("docs/knowledge/graph.json"))?)?;
    validate_graph(root, &graph)?;
    Ok(graph)
}

fn field<'a>(value: &'a Value, name: &str) -> Result<&'a str> {
    value[name]
        .as_str()
        .ok_or_else(|| format!("Missing string field: {name}").into())
}

fn validate_graph(root: &Path, graph: &Value) -> Result<()> {
    let nodes = graph["nodes"].as_array().ok_or("Missing nodes")?;
    let edges = graph["edges"].as_array().ok_or("Missing edges")?;
    let mut ids = BTreeSet::new();
    for node in nodes {
        let id = field(node, "id")?;
        if !ids.insert(id) {
            return Err(format!("Duplicate node ID: {id}").into());
        }
        if ![
            "existing",
            "written",
            "proposed",
            "planned",
            "deferred",
            "implemented",
            "foundation",
        ]
        .contains(&field(node, "status")?)
        {
            return Err(format!("Unknown node status: {id}").into());
        }
        source_path(root, field(node, "path")?)?;
    }
    for edge in edges {
        if !ids.contains(field(edge, "from")?) || !ids.contains(field(edge, "to")?) {
            return Err("Graph has a dangling edge".into());
        }
        if ![
            "constrained_by",
            "follows",
            "governed_by",
            "depends_on",
            "calls",
            "explains",
            "verified_by",
        ]
        .contains(&field(edge, "relation")?)
        {
            return Err("Unknown graph relationship".into());
        }
        source_path(root, field(edge, "source")?)?;
    }
    Ok(())
}

fn project_files(root: &Path) -> Result<Vec<String>> {
    let files = capture(
        root,
        "git",
        &[
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
    )?;
    Ok(files
        .split('\0')
        .filter(|p| !p.is_empty())
        .map(str::to_owned)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect())
}

fn validate_docs(root: &Path) -> Result<()> {
    let graph = graph_source(root)?;
    let links = Regex::new(r"\[[^\]]+\]\(([^)]+)\)")?;
    let mut checked = 0;
    for file in project_files(root)?.iter().filter(|p| p.ends_with(".md")) {
        let path = source_path(root, file)?;
        for captures in links.captures_iter(&fs::read_to_string(&path)?) {
            let link = &captures[1];
            if link.starts_with("https://")
                || link.starts_with("http://")
                || link.starts_with('#')
                || link.starts_with("mailto:")
            {
                continue;
            }
            let local = link.split('#').next().unwrap_or_default();
            if local.is_empty() {
                continue;
            }
            let target = path.parent().unwrap().join(local);
            if !target.exists() {
                return Err(format!("Broken link in {file}: {link}").into());
            }
            checked += 1;
        }
    }
    let manifest: Value =
        serde_json::from_str(&fs::read_to_string(root.join("docs/upstream-files.json"))?)?;
    for entry in manifest["files"]
        .as_array()
        .ok_or("Missing upstream manifest files")?
    {
        let path = field(entry, "path")?;
        // Git may check out CRLF; the organizer's text is normalized to LF before hashing.
        let bytes = fs::read(source_path(root, path)?)?;
        let normalized = String::from_utf8(bytes)?.replace("\r\n", "\n");
        let actual = format!("{:x}", Sha256::digest(normalized.as_bytes()));
        if actual != field(entry, "sha256")? {
            return Err(format!("Organizer file changed: {path}").into());
        }
    }
    println!(
        "Docs valid: {checked} local links, {} graph nodes, {} relationships; organizer files match the recorded snapshot.",
        graph["nodes"].as_array().unwrap().len(),
        graph["edges"].as_array().unwrap().len()
    );
    Ok(())
}

fn fingerprint(root: &Path) -> Result<String> {
    let mut hash = Sha256::new();
    for file in project_files(root)? {
        let extension = Path::new(&file)
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or_default();
        if ![
            "rs", "md", "toml", "json", "lock", "html", "css", "js", "yml", "yaml",
        ]
        .contains(&extension)
            && ![
                "Dockerfile",
                ".gitignore",
                ".dockerignore",
                ".gitattributes",
            ]
            .contains(&file.as_str())
        {
            continue;
        }
        // The allowlist deliberately excludes .env, keys, binaries and ignored artifacts.
        let path = source_path(root, &file)?;
        if !path.is_file() {
            continue;
        }
        hash.update(file.as_bytes());
        hash.update([0]);
        hash.update(fs::read(path)?);
        hash.update([0]);
    }
    Ok(format!("{hash:x}", hash = hash.finalize()))
}

fn graph_snapshot(root: &Path) -> Result<Value> {
    let graph = graph_source(root)?;
    let metadata: Value = serde_json::from_str(&capture(
        root,
        "cargo",
        &["metadata", "--no-deps", "--locked", "--format-version", "1"],
    )?)?;
    let packages = metadata["packages"]
        .as_array()
        .ok_or("Cargo metadata has no packages")?;
    let names: BTreeSet<&str> = packages.iter().filter_map(|p| p["name"].as_str()).collect();
    let cargo_packages: Vec<Value> = packages
        .iter()
        .map(|package| {
            let dependencies: Vec<&str> = package["dependencies"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|d| d["name"].as_str())
                .filter(|name| names.contains(name))
                .collect();
            json!({"name": package["name"], "workspace_dependencies": dependencies})
        })
        .collect();
    Ok(json!({
        "provenance": {"commit": capture(root, "git", &["rev-parse", "HEAD"])?.trim(), "source_fingerprint": fingerprint(root)?, "extraction": "Cargo workspace dependencies; other relations are curated"},
        "project": graph,
        "cargo_packages": cargo_packages
    }))
}

fn context(root: &Path, args: &[String]) -> Result<()> {
    let mut scope = "core";
    let mut task = None;
    let mut budget = 12_000usize;
    let mut index = 0;
    while index < args.len() {
        let value = args
            .get(index + 1)
            .ok_or("Context options require values")?;
        match args[index].as_str() {
            "--scope" => scope = value,
            "--task" => task = Some(value.as_str()),
            "--max-chars" => budget = value.parse()?,
            _ => return Err(format!("Unknown context option: {}", args[index]).into()),
        }
        index += 2;
    }
    if !(1000..=100_000).contains(&budget) {
        return Err("--max-chars must be between 1000 and 100000".into());
    }
    let scoped = match scope {
        "core" => "crates/core/AGENTS.md",
        "cli" => "crates/cli/AGENTS.md",
        "api" => "crates/api/AGENTS.md",
        "web" => "apps/web/AGENTS.md",
        "qa" => "tests/AGENTS.md",
        "native" => "native/AGENTS.md",
        "tooling" => "xtask/AGENTS.md",
        _ => return Err("Unknown scope; use core, cli, api, web, qa, native, or tooling".into()),
    };
    let graph = graph_source(root)?;
    let mut paths = vec!["AGENTS.md".to_string(), scoped.into()];
    if let Some(task) = task {
        if task.is_empty()
            || !task
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        {
            return Err(
                "Task IDs may contain only letters, digits, hyphens and underscores".into(),
            );
        }
        let path = format!("docs/handoffs/{task}.md");
        source_path(root, &path).map_err(|_| format!("No handoff found for task {task}"))?;
        paths.push(path);
    }
    paths.extend([
        "docs/architecture.md".into(),
        "docs/agents.md".into(),
        "docs/decisions/0001-cpu-first.md".into(),
    ]);
    let id = if scope == "qa" {
        "scope:qa".to_string()
    } else {
        format!("module:{scope}")
    };
    let edges: Vec<&Value> = graph["edges"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|edge| edge["from"] == id || edge["to"] == id)
        .collect();
    let mut output = format!(
        "# VERIDYCT context / {scope}\nCommit: {}\nSource fingerprint: {}\n\nRelations: {}\n",
        capture(root, "git", &["rev-parse", "HEAD"])?.trim(),
        fingerprint(root)?,
        serde_json::to_string(&edges)?
    );
    for path in paths {
        output.push_str(&format!(
            "\n## {path}\n{}\n",
            fs::read_to_string(source_path(root, &path)?)?
        ));
    }
    if output.chars().count() > budget {
        let suffix = "\n[TRUNCATED: increase --max-chars or read the linked files.]\n";
        output = output
            .chars()
            .take(budget - suffix.chars().count())
            .collect();
        output.push_str(suffix);
    }
    print!("{output}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn graph_rejects_dangling_relations_and_duplicate_ids() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        let node = json!({"id": "a", "status": "written", "path": "AGENTS.md"});
        assert!(
            validate_graph(
                root,
                &json!({"nodes": [node.clone(), node.clone()], "edges": []})
            )
            .is_err()
        );
        assert!(validate_graph(root, &json!({"nodes": [node], "edges": [{"from": "a", "to": "missing", "relation": "calls", "source": "AGENTS.md"}]})).is_err());
    }

    #[test]
    fn sources_cannot_escape_the_repository() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
        assert!(source_path(root, "../").is_err());
        assert!(source_path(root, "AGENTS.md").is_ok());
    }
}
