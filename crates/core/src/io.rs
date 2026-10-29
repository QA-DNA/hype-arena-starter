//! Strict, bounded arena CSV adapters shared by CLI and HTTP.
use crate::model::{Claim, InputRow, Prediction};
use std::collections::BTreeSet;

pub fn read_csv(text: &str) -> Result<Vec<InputRow>, String> {
    if text.len() > 64 * 1024 * 1024 {
        return Err("CSV exceeds 64 MiB".into());
    }
    let text = text.trim_start_matches('\u{feff}');
    let first_line = text.lines().next().unwrap_or_default();
    let delimiter = if first_line.matches(';').count() > first_line.matches(',').count() {
        b';'
    } else {
        b','
    };
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(delimiter)
        .from_reader(text.as_bytes());
    let headers = reader
        .headers()
        .map_err(|e| format!("CSV header: {e}"))?
        .clone();
    let column = |name: &str| headers.iter().position(|s| s.trim() == name);
    let required = ["id", "text", "date", "label"];
    for name in required {
        if column(name).is_none() {
            return Err(format!("Missing required CSV column: {name}"));
        }
        if headers.iter().filter(|h| h.trim() == name).count() != 1 {
            return Err(format!("Duplicate CSV column: {name}"));
        }
    }
    let indices: Vec<usize> = required.iter().filter_map(|name| column(name)).collect();
    let form_column = column("form");
    let mut rows = Vec::new();
    let mut ids = BTreeSet::new();
    for (index, record) in reader.records().enumerate() {
        if index >= 50_000 {
            return Err("CSV exceeds 50,000 rows".into());
        }
        let record = record.map_err(|e| format!("CSV row {}: {e}", index + 2))?;
        let id = record[indices[0]].trim().to_string();
        let sentence = record[indices[1]].to_string();
        let date = record[indices[2]].trim().to_string();
        let label = record[indices[3]].trim().to_lowercase();
        if id.is_empty() || id.len() > 256 || !ids.insert(id.clone()) {
            return Err(format!(
                "CSV row {} has an empty, oversized or duplicate id",
                index + 2
            ));
        }
        if sentence.trim().is_empty() || sentence.len() > 32_768 {
            return Err(format!("CSV row {} has empty or oversized text", index + 2));
        }
        if !valid_date(&date) {
            return Err(format!(
                "CSV row {} date must be a valid YYYY-MM-DD",
                index + 2
            ));
        }
        if !["", "true", "false", "unsure"].contains(&label.as_str()) {
            return Err(format!("CSV row {} has invalid label {label:?}", index + 2));
        }
        let form = match form_column
            .map(|i| record[i].trim())
            .filter(|s| !s.is_empty())
        {
            Some(value) => serde_json::from_str(value)
                .map_err(|e| format!("CSV row {} form JSON: {e}", index + 2))?,
            None => Vec::new(),
        };
        rows.push(InputRow {
            id,
            text: sentence,
            date,
            label,
            form,
        });
    }
    if rows.is_empty() {
        return Err("CSV contains no input rows".into());
    }
    Ok(rows)
}

fn valid_date(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return false;
    }
    if bytes
        .iter()
        .enumerate()
        .any(|(i, c)| i != 4 && i != 7 && !c.is_ascii_digit())
    {
        return false;
    }
    let year = value[..4].parse::<u32>().unwrap_or(0);
    let month = value[5..7].parse::<usize>().unwrap_or(0);
    let day = value[8..].parse::<u32>().unwrap_or(0);
    if year == 0 || !(1..=12).contains(&month) {
        return false;
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
    day > 0 && day <= days[month - 1]
}

pub fn output_csv(predictions: &[Prediction], claims: &[Claim]) -> Result<String, String> {
    let mut writer = csv::WriterBuilder::new().from_writer(Vec::new());
    writer
        .write_record(["id", "type", "text", "form", "label", "confidence"])
        .map_err(|e| e.to_string())?;
    let mut ids = BTreeSet::new();
    for prediction in predictions {
        if prediction
            .known_label
            .as_deref()
            .is_some_and(|s| !s.is_empty())
        {
            continue;
        }
        if !ids.insert(prediction.id.as_str()) {
            return Err("Duplicate prediction id".into());
        }
        if !["true", "false", "unsure"].contains(&prediction.label.as_str()) {
            return Err(format!("Invalid verdict for {}", prediction.id));
        }
        let confidence = if prediction.label == "unsure" {
            String::new()
        } else {
            let value = prediction
                .confidence
                .ok_or("A definite label requires confidence")?;
            if !value.is_finite() || !(0.5..=1.0).contains(&value) {
                return Err(format!("Invalid confidence for {}", prediction.id));
            }
            value.to_string()
        };
        writer
            .write_record([
                prediction.id.as_str(),
                "",
                "",
                "",
                prediction.label.as_str(),
                &confidence,
            ])
            .map_err(|e| e.to_string())?;
    }
    let mut texts = BTreeSet::new();
    for claim in claims {
        if claim.id.is_empty()
            || claim.id.len() > 64
            || !claim
                .id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
            || !ids.insert(claim.id.as_str())
        {
            return Err("Invalid or duplicate generated claim id".into());
        }
        if claim.text.trim().is_empty()
            || claim.text.chars().count() > 300
            || !texts.insert(claim.text.as_str())
        {
            return Err("Empty, oversized or duplicate generated claim text".into());
        }
        if !["fact", "compare", "change", "at_event", "relation"].contains(&claim.kind.as_str())
            || !claim.confidence.is_finite()
            || !(0.5..=1.0).contains(&claim.confidence)
            || !claim.form.is_object()
        {
            return Err("Invalid generated claim type, form or confidence".into());
        }
        let form = serde_json::to_string(&claim.form).map_err(|e| e.to_string())?;
        writer
            .write_record([
                claim.id.as_str(),
                claim.kind.as_str(),
                claim.text.as_str(),
                &form,
                "true",
                &claim.confidence.to_string(),
            ])
            .map_err(|e| e.to_string())?;
    }
    let bytes = writer.into_inner().map_err(|e| e.to_string())?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("Arena output exceeds 16 MiB".into());
    }
    String::from_utf8(bytes).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn input_handles_quoted_text_bom_and_missing_forms() {
        let rows = read_csv("\u{feff}id,text,date,label\nx,\"one, two\",2026-10-28,\n").unwrap();
        assert_eq!(rows[0].text, "one, two");
        assert!(rows[0].form.is_empty());
        assert!(rows[0].label.is_empty());
    }
    #[test]
    fn input_rejects_duplicates_invalid_dates_and_labels() {
        for csv in [
            "id,text,date,label\nx,a,2026-02-30,true\n",
            "id,text,date,label\nx,a,2026-02-28,maybe\n",
            "id,text,date,label\nx,a,2026-02-28,true\nx,b,2026-02-28,false\n",
        ] {
            assert!(read_csv(csv).is_err());
        }
    }
}
