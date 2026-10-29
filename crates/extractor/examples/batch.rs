//! cargo run --example batch -- /path/to/selected-v2 < rows.json > filled.json
//! Set ORT_DYLIB_PATH to the verified ONNX Runtime 1.23.2 shared library.
use std::{
    io::{self, BufReader, BufWriter},
    path::PathBuf,
};

use anyhow::{Context, Result};
use veridyct_extractor::{Extractor, InputRow, Options};

fn main() -> Result<()> {
    let bundle = PathBuf::from(
        std::env::args_os()
            .nth(1)
            .context("Pass the frozen model bundle directory")?,
    );
    let rows: Vec<InputRow> = serde_json::from_reader(BufReader::new(io::stdin().lock()))?;
    let mut extractor = Extractor::load(bundle, Options::default())?;
    let output = extractor.extract_batch(&rows)?;
    serde_json::to_writer(BufWriter::new(io::stdout().lock()), &output.rows)?;
    eprintln!("{}", serde_json::to_string(&output.report)?);
    Ok(())
}
