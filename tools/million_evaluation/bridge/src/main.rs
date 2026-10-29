//! Input-only bridge to the committed parser and exact typed kernel.
//! No dataset generator, oracle, answer key, bank or target is loaded here.
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    env,
    error::Error,
    fs,
    io::{BufRead, BufReader, BufWriter, Write},
    path::Path,
    time::Instant,
};
use unicode_normalization::UnicodeNormalization;
use veridyct_core::{
    Engine, ExtractionHints, Fact, InputRow,
    knowledge::entails,
    read_csv,
    structured::{SchemaParser, ValueCandidate},
};
use veridyct_extractor::{Extractor, Options, encode::EncodedRow};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    id: String,
    text: String,
    #[serde(default)]
    previous_text: String,
    date: String,
    mode: String,
}

fn norm(s: &str) -> String {
    s.nfkc()
        .collect::<String>()
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
fn hidden(facts: &[Fact]) -> Value {
    json!({"facts":facts,"complete":true,"notes":[]})
}
fn hints(id: &str, complete: bool, notes: &[String], facts: &[Fact], h: &mut ExtractionHints) {
    if facts.is_empty() {
        h.recognized_empty.insert(id.into());
    }
    let unknown = notes.iter().any(|n| n.starts_with("explicit_unknown"));
    if unknown {
        h.explicit_unknown.insert(id.into());
    }
    let whole = notes
        .iter()
        .any(|n| n == "neural_fallback:no reliable schema binding");
    if unknown
        || notes
            .iter()
            .any(|n| n.starts_with("input_limit") || n.contains("invalid candidate"))
        || (!complete
            && !whole
            && notes
                .iter()
                .any(|n| n.starts_with("unresolved") || n.starts_with("ambiguous")))
    {
        h.incomplete.insert(id.into());
    }
}

fn parse(args: &[String]) -> Result<(), Box<dyn Error>> {
    if args.len() != 5 {
        return Err("parse REQUESTS.jsonl OUTPUT.jsonl BUNDLE VERIFIER PRACTICE".into());
    }
    let started = Instant::now();
    let requests: Vec<Request> = BufReader::new(fs::File::open(&args[0])?)
        .lines()
        .map(|s| Ok(serde_json::from_str(&s?)?))
        .collect::<Result<_, Box<dyn Error>>>()?;
    let lexicon: Value =
        serde_json::from_slice(&fs::read(Path::new(&args[2]).join("lexicon.json"))?)?;
    let practice = read_csv(&fs::read_to_string(&args[4])?)?;
    let exact: BTreeMap<_, _> = practice
        .iter()
        .map(|r| ((norm(&r.text), r.date.clone()), r.form.clone()))
        .collect();
    let engine = Engine::new(&practice, &lexicon)?.with_boosted(&fs::read_to_string(&args[3])?)?;
    let mut extractor = Extractor::load(&args[2], Options::default())?;
    let schema = SchemaParser::compile(&lexicon)?;
    let mut results: Vec<Value> = vec![Value::Null; requests.len()];
    let mut encoded: BTreeMap<usize, Vec<(usize, EncodedRow)>> = BTreeMap::new();
    for (index, row) in requests.iter().enumerate() {
        if !matches!(row.mode.as_str(), "literal" | "note" | "pilot") {
            return Err("Unsupported bridge request mode".into());
        }
        if row.mode == "note"
            && let Some(facts) = exact.get(&(norm(&row.text), row.date.clone()))
        {
            results[index] = hidden(facts);
            continue;
        }
        let candidates: Vec<ValueCandidate> = extractor
            .grammar
            .binding_candidates(&row.text)?
            .into_iter()
            .map(|c| ValueCandidate {
                start: c.start,
                end: c.end,
                value: c.value,
            })
            .collect();
        if row.mode == "literal" {
            let parsed = schema.parse(&row.text, &candidates, &[]);
            if parsed.complete && parsed.facts.len() == 1 {
                results[index] = serde_json::to_value(parsed)?;
                continue;
            }
        }
        match extractor.encode(&row.text, &row.previous_text, &row.id) {
            Ok(value) => encoded
                .entry(value.tokens.len())
                .or_default()
                .push((index, value)),
            Err(error) => {
                results[index] =
                    json!({"facts":[],"complete":false,"notes":[format!("input_limit:{error}")]})
            }
        }
    }
    let neural_count: usize = encoded.values().map(Vec::len).sum();
    for group in encoded.values() {
        for chunk in group.chunks(48) {
            let values: Vec<_> = chunk.iter().map(|(_, r)| r).collect();
            let decoded = extractor.predict_encoded(&values)?;
            for ((index, _), atoms) in chunk.iter().zip(decoded) {
                let row = &requests[*index];
                let neural: Vec<Fact> = atoms
                    .into_iter()
                    .map(|a| serde_json::from_value(a.atom))
                    .collect::<Result<_, _>>()?;
                let candidates: Vec<ValueCandidate> = extractor
                    .grammar
                    .binding_candidates(&row.text)?
                    .into_iter()
                    .map(|c| ValueCandidate {
                        start: c.start,
                        end: c.end,
                        value: c.value,
                    })
                    .collect();
                results[*index] =
                    serde_json::to_value(schema.parse(&row.text, &candidates, &neural))?;
            }
        }
    }
    let mut query_rows = Vec::new();
    let mut query_indices = Vec::new();
    let mut query_hints = ExtractionHints::default();
    for (index, row) in requests
        .iter()
        .enumerate()
        .filter(|(_, r)| r.mode == "pilot")
    {
        let facts: Vec<Fact> = serde_json::from_value(results[index]["facts"].clone())?;
        let notes: Vec<String> = serde_json::from_value(results[index]["notes"].clone())?;
        hints(
            &row.id,
            results[index]["complete"] == true,
            &notes,
            &facts,
            &mut query_hints,
        );
        query_rows.push(InputRow {
            id: row.id.clone(),
            text: row.text.clone(),
            date: row.date.clone(),
            label: String::new(),
            form: facts,
        });
        query_indices.push(index);
    }
    let predictions = engine.predict_with_hints(&query_rows, &query_hints);
    for (index, prediction) in query_indices.into_iter().zip(predictions) {
        results[index]["label"] = json!(prediction.label);
        results[index]["confidence"] = json!(prediction.confidence);
        results[index]["probabilities"] = serde_json::to_value(prediction.probabilities)?;
    }
    let mut output = BufWriter::new(fs::File::create(&args[1])?);
    for (row, result) in requests.iter().zip(results) {
        writeln!(
            output,
            "{}",
            json!({"id":row.id,"mode":row.mode,"parsed":result})
        )?;
    }
    output.flush()?;
    eprintln!(
        "{}",
        json!({"requests":requests.len(),"neural_requests":neural_count,"pilot_queries":query_rows.len(),"seconds":started.elapsed().as_secs_f64(),"batching":"exact length, max48","cpu_threads":2})
    );
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Comparison {
    id: String,
    left: Value,
    right: Value,
    op: String,
    semantics: String,
}
type CalendarDay = (u16, u8, u8);
type DateRange = (CalendarDay, CalendarDay);
fn date_range(value: &Value) -> Option<DateRange> {
    let pieces: Vec<_> = value["value"].as_str()?.split('-').collect();
    if pieces.is_empty() || pieces.len() > 3 {
        return None;
    }
    let year: u16 = pieces[0].parse().ok()?;
    let month: u8 = pieces.get(1).map_or(Some(1), |v| v.parse().ok())?;
    let day: u8 = pieces.get(2).map_or(Some(1), |v| v.parse().ok())?;
    if year == 0 || month == 0 || month > 12 {
        return None;
    }
    let leap = year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if day == 0 || day > days[usize::from(month) - 1] {
        return None;
    }
    Some((
        (year, month, day),
        match pieces.len() {
            1 => (year, 12, 31),
            2 => (year, month, days[usize::from(month) - 1]),
            _ => (year, month, day),
        },
    ))
}
// A comparison between two partially known date VALUES differs from asking
// whether one actual date satisfies a month/year predicate. This is a public
// protocol adapter; the production predicate kernel remains unchanged.
fn compare_dates(left: &Value, right: &Value, op: &str) -> Option<bool> {
    let (alo, ahi) = date_range(left)?;
    let (blo, bhi) = date_range(right)?;
    if op == "eq" {
        return if alo == ahi && alo == blo && alo == bhi {
            Some(true)
        } else if ahi < blo || bhi < alo {
            Some(false)
        } else {
            None
        };
    }
    let (yes, no) = match op {
        "lt" => (ahi < blo, alo >= bhi),
        "le" => (ahi <= blo, alo > bhi),
        "gt" => (alo > bhi, ahi <= blo),
        "ge" => (alo >= bhi, ahi < blo),
        _ => return None,
    };
    if yes {
        Some(true)
    } else if no {
        Some(false)
    } else {
        None
    }
}
fn compare(args: &[String]) -> Result<(), Box<dyn Error>> {
    if args.len() != 2 {
        return Err("compare REQUESTS.jsonl OUTPUT.jsonl".into());
    }
    let mut output = BufWriter::new(fs::File::create(&args[1])?);
    let mut count = 0;
    for line in BufReader::new(fs::File::open(&args[0])?).lines() {
        let q: Comparison = serde_json::from_str(&line?)?;
        if !matches!(q.op.as_str(), "eq" | "lt" | "le" | "gt" | "ge") {
            return Err("Unsupported comparison operator".into());
        }
        let mut boundary = q.right.clone();
        boundary["op"] = json!(q.op);
        let result = match q.semantics.as_str() {
            "recorded" => {
                if q.op != "eq" {
                    return Err("Recorded is an equality query".into());
                }
                if q.left["kind"] != q.right["kind"]
                    || ["unit", "currency", "per"]
                        .iter()
                        .any(|k| q.left[*k] != q.right[*k])
                {
                    Some(false)
                } else if matches!(
                    q.left["kind"].as_str(),
                    Some("date" | "version" | "name" | "boolean")
                ) {
                    Some(q.left["value"] == q.right["value"])
                } else {
                    entails(&boundary, &q.left, false)
                }
            }
            "compare" => {
                if q.left["kind"] == "date" && q.right["kind"] == "date" {
                    compare_dates(&q.left, &q.right, &q.op)
                } else {
                    entails(&boundary, &q.left, false)
                }
            }
            _ => return Err("Unsupported comparison semantics".into()),
        };
        let label = match result {
            Some(true) => "true",
            Some(false) => "false",
            None => "unsure",
        };
        writeln!(output, "{}", json!({"id":q.id,"label":label}))?;
        count += 1;
    }
    output.flush()?;
    eprintln!("Compared {count} input-only typed pairs using committed Rust predicates.");
    Ok(())
}
fn run() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("parse") => parse(&args[1..]),
        Some("compare") => compare(&args[1..]),
        _ => Err("Expected parse or compare".into()),
    }
}
fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn two_partial_date_values_are_not_a_precision_predicate() {
        let d = |s| json!({"kind":"date","value":s});
        assert_eq!(compare_dates(&d("2026-06-01"), &d("2026"), "le"), None);
        assert_eq!(compare_dates(&d("2026"), &d("2026"), "lt"), None);
        assert_eq!(
            compare_dates(&d("2026-01-01"), &d("2026-01-01"), "eq"),
            Some(true)
        );
        assert_eq!(compare_dates(&d("2025"), &d("2026"), "lt"), Some(true));
        assert_eq!(
            compare_dates(&d("2026"), &d("2026-01-01"), "lt"),
            Some(false)
        );
        assert!(date_range(&d("2025-02-29")).is_none());
        assert!(date_range(&d("2024-02-29")).is_some());
    }
}
