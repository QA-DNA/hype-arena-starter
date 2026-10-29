//! Export the exact public evidence index, without adding model-generated facts.
use std::{error::Error, fs};
use veridyct_core::{knowledge::KnowledgeGraph, read_csv};
fn main() -> Result<(), Box<dyn Error>> {
    let rows = read_csv(include_str!("../../../data/practice.csv"))?;
    let graph = KnowledgeGraph::compile(&rows);
    let output = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "artifacts/compiled-universe.json".into());
    if let Some(parent) = std::path::Path::new(&output).parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&output, serde_json::to_vec_pretty(&graph.snapshot())?)?;
    eprintln!(
        "Compiled {}: {}",
        output,
        serde_json::to_string(graph.summary())?
    );
    Ok(())
}
