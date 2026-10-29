//! These tests require explicitly staged, hash-checked weights. Normal unit tests
//! remain independent of the ignored model and native shared library.
use std::path::PathBuf;

use anyhow::Result;
use serde_json::{Value, json};
use veridyct_extractor::{Context, Extractor, InputRow, Options};

fn bundle() -> PathBuf {
    std::env::var_os("VERIDYCT_EXTRACTOR_BUNDLE")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tools/native_parser/model")
        })
}
fn row(text: &str, id: &str) -> InputRow {
    serde_json::from_value(json!({"id":id,"text":text,"date":"2026-10-29","label":""})).unwrap()
}

#[test]
#[ignore = "requires staged selected-v2 bundle and ORT_DYLIB_PATH"]
fn frozen_python_encoding_assertions_and_batch_shapes() -> Result<()> {
    let mut engine = Extractor::load(bundle(), Options::default())?;
    let fixture: Value = serde_json::from_str(include_str!("fixtures/frozen-regressions.json"))?;
    let mut all = Vec::new();
    for case in fixture["rows"].as_array().unwrap() {
        let req = &case["request"];
        let encoded = engine.encode(
            req["text"].as_str().unwrap(),
            req["previous_text"].as_str().unwrap(),
            req["id"].as_str().unwrap(),
        );
        if let Some(error) = case.get("error") {
            assert_eq!(encoded.unwrap_err().to_string(), error.as_str().unwrap());
            all.push(None);
            continue;
        }
        let encoded = encoded?;
        assert_eq!(
            serde_json::to_value(&encoded)?,
            case["encoded"],
            "{}",
            req["id"]
        );
        all.push(Some(encoded));
    }
    for size in [1, 7, 48] {
        let expected = fixture["predictions_by_batch"][size.to_string()]
            .as_array()
            .unwrap();
        let mut predictions = vec![Vec::new(); all.len()];
        for (chunk_index, chunk) in all.chunks(size).enumerate() {
            let refs = chunk.iter().flatten().collect::<Vec<_>>();
            let mut values = engine.predict_encoded(&refs)?.into_iter();
            for (i, row) in chunk.iter().enumerate() {
                if row.is_some() {
                    predictions[chunk_index * size + i] = values.next().unwrap();
                }
            }
        }
        for (actual, expected) in predictions.iter().zip(expected) {
            let form: Vec<_> = actual.iter().map(|a| a.atom.clone()).collect();
            assert_eq!(json!(form), expected["form"]);
            for (a, b) in actual
                .iter()
                .zip(expected["assertions"].as_array().unwrap())
            {
                assert_eq!(json!(a.value_span_chars), b["value_span_chars"]);
                assert_eq!(a.value_text, b["value_text"].as_str().unwrap());
                assert!((a.model_score as f64 - b["model_score"].as_f64().unwrap()).abs() < 1e-5);
            }
        }
    }
    Ok(())
}

#[test]
#[ignore = "requires staged selected-v2 bundle and ORT_DYLIB_PATH"]
fn row_preservation_metadata_isolation_and_unsupported_rows() -> Result<()> {
    let mut engine = Extractor::load(bundle(), Options::default())?;
    let text = "Hooly AI Pro costs €79 per month.";
    let mut first = row(text, "same");
    first.0.insert("form".into(), Value::Null);
    let mut second = row(text, "different-id");
    second.0.insert("date".into(), json!("1900-01-01"));
    second.0.insert("label".into(), json!("false"));
    second.0.insert("gold".into(), json!({"arbitrary":99}));
    second
        .0
        .insert("previous_text".into(), json!("Hooly Workspace."));
    let mut known = row(text, "known");
    known
        .0
        .insert("form".into(), json!([{"opaque":"preserved"}]));
    let rows = vec![
        first,
        second,
        known.clone(),
        row(&"word ".repeat(400), "tokens"),
        row(&"x".repeat(65537), "characters"),
        row(&"x;".repeat(150), "candidates"),
        row("\n", "whitespace"),
        row("", "empty"),
        row(text, "later"),
    ];
    let before = rows.clone();
    let result = engine.extract_batch(&rows)?;
    assert_eq!(before, rows);
    assert_eq!(result.rows.len(), rows.len());
    assert_eq!(result.rows[0].0["form"], result.rows[1].0["form"]);
    assert_eq!(result.rows[1].0["gold"], json!({"arbitrary":99}));
    assert_eq!(result.rows[1].0["date"], "1900-01-01");
    assert_eq!(result.rows[1].0["label"], "false");
    assert_eq!(result.rows[2], known);
    assert!(!result.rows[8].0["form"].as_array().unwrap().is_empty());
    assert_eq!(result.report.counts["unsupported"], 4);
    for r in &result.rows[3..8] {
        assert_eq!(r.0["form"], json!([]));
    }
    let empty = engine.extract_batch(&[])?;
    assert_eq!(empty.report.counts["rows"], 0);
    Ok(())
}

#[test]
#[ignore = "requires staged selected-v2 bundle and ORT_DYLIB_PATH"]
fn public_practice_reuse_conflicts_and_explicit_context() -> Result<()> {
    let mut engine = Extractor::load(
        bundle(),
        Options {
            context: Context::Previous3text,
            ..Default::default()
        },
    )?;
    let csv = tempfile::NamedTempFile::new()?;
    let mut writer = csv::Writer::from_path(csv.path())?;
    writer.write_record(["text", "form"])?;
    writer.write_record(["known text", "[]"])?;
    writer.write_record(["conflicting text", "[]"])?;
    writer.write_record(["conflicting text", "[{\"opaque\":true}]"])?;
    writer.flush()?;
    engine.load_practice(csv.path())?;
    let rows = vec![
        row("Hooly AI Pro.", "0"),
        row("known text", "1"),
        row("conflicting text", "2"),
        row("It costs €79 per month.", "3"),
    ];
    let result = engine.extract_batch(&rows)?;
    assert!(result.report.context_experimental);
    assert_eq!(result.report.counts["practice_reused"], 1);
    assert_eq!(result.report.practice_conflicting_texts, 1);
    assert_eq!(result.rows[1].0["form"], json!([]));
    let previous = rows[..3]
        .iter()
        .map(InputRow::text)
        .collect::<Vec<_>>()
        .join(" ");
    let encoded = engine.encode(rows[3].text(), &previous, "3")?;
    let expected = engine.predict_encoded(&[&encoded])?;
    assert_eq!(
        result.rows[3].0["form"],
        json!(expected[0].iter().map(|a| &a.atom).collect::<Vec<_>>())
    );
    Ok(())
}
