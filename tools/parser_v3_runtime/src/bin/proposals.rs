//! Independent diagnostic: dump raw proposals and actual parser results.
use serde_json::{Value, json};
use std::{
    env,
    fs::File,
    io::{BufRead, BufReader, BufWriter, Write},
    process,
};
use veridyct_core::{
    claim_parsing::ClaimParser,
    claim_program::ProgramParser,
    structured::{SchemaParser, ValueCandidate},
};
use veridyct_extractor::grammar::Grammar;
use veridyct_parser_v3_runtime::Input;

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 4 {
        return Err("usage: proposals LEXICON INPUT_JSONL OUTPUT_JSONL".into());
    }
    let lexicon: Value = serde_json::from_reader(BufReader::new(File::open(&args[1])?))?;
    let grammar = Grammar::new(&lexicon, &[])?;
    let schema = SchemaParser::compile(&lexicon)?;
    let program = ProgramParser::compile(&lexicon)?;
    let mut shared = ClaimParser::compile(&lexicon)?;
    let mut output = BufWriter::new(File::create_new(&args[3])?);
    for line in BufReader::new(File::open(&args[2])?).lines() {
        let line = line?;
        if line.len() > 2 * 1024 * 1024 {
            return Err("line limit".into());
        }
        let input: Input = serde_json::from_str(&line)?;
        let candidates: Vec<_> = grammar
            .binding_candidates(&input.text)?
            .into_iter()
            .map(|c| ValueCandidate {
                start: c.start,
                end: c.end,
                value: c.value,
            })
            .collect();
        shared.reset();
        let compiled = shared.parse(
            None,
            "diagnostic",
            "2000-01-01",
            &input.text,
            &candidates,
            &[],
        )?;
        let result = json!({"id":input.id,"text":input.text,"raw_candidates":candidates,
            "schema":schema.parse(&input.text,&candidates,&[]),
            "program":program.parse(&input.text,&candidates,&[]),"shared":compiled});
        serde_json::to_writer(&mut output, &result)?;
        output.write_all(b"\n")?;
    }
    output.flush()?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        process::exit(2);
    }
}
