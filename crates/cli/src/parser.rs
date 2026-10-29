//! Optional experimental CPU extractor. The default executable is pure Rust.
//! The helper proposes assertions; it cannot change labels or trusted evidence.
use serde_json::Value;
use std::{error::Error, fs, path::Path, process::Command};
use veridyct_core::{
    ExtractionHints, InputRow,
    extraction::{LexiconIndex, NormalizedRow, Normalizer},
    structured::{SchemaParser, ValueCandidate},
};

pub fn enrich(
    rows: &mut [InputRow],
    output_directory: &Path,
    lexicon: &Value,
) -> Result<ExtractionHints, Box<dyn Error>> {
    let mut hints = ExtractionHints::default();
    let native = std::env::var_os("VERIDYCT_NATIVE_EXTRACTOR");
    let mut command = if let Some(executable) = &native {
        Command::new(executable)
    } else if let Some(helper) = std::env::var_os("VERIDYCT_NEURAL_HELPER") {
        let mut cmd = Command::new("python3");
        cmd.arg(helper);
        cmd
    } else {
        return Ok(hints);
    };
    let context = std::env::var("VERIDYCT_PARSER_CONTEXT").unwrap_or_else(|_| "none".into());
    if !matches!(context.as_str(), "none" | "previous3text") {
        return Err("VERIDYCT_PARSER_CONTEXT must be none or previous3text".into());
    }
    let structured = if std::env::var("VERIDYCT_STRUCTURED_PARSER").is_ok_and(|v| v == "1") {
        if native.is_none() {
            return Err("Structured candidate binding requires the native extractor".into());
        }
        command.args(["--export-candidates", "true"]);
        Some(SchemaParser::compile(lexicon)?)
    } else {
        None
    };
    if native.is_some()
        && let Ok(batching) = std::env::var("VERIDYCT_PARSER_BATCHING")
    {
        if !matches!(batching.as_str(), "padded" | "exact-length") {
            return Err("Unsupported VERIDYCT_PARSER_BATCHING".into());
        }
        command.args(["--batching", batching.as_str()]);
    }
    fs::create_dir_all(output_directory)?;
    let prefix = format!(".parser-{}", std::process::id());
    let input = output_directory.join(format!("{prefix}-input.json"));
    let output = output_directory.join(format!("{prefix}-output.json"));
    let paths = TemporaryFiles(vec![input.clone(), output.clone()]);
    // Explicit validity is interpreted by the graph, separately from the
    // assertion body. Keep original text/provenance in the application rows.
    let parser_rows: Vec<InputRow> = rows
        .iter()
        .map(|row| {
            let mut parsed = row.clone();
            if let Some(scope) = veridyct_core::temporal::explicit_scope(&row.text) {
                parsed.text = row.text[scope.body_offset_bytes..].to_owned();
            }
            parsed
        })
        .collect();
    fs::write(&input, serde_json::to_vec(&parser_rows)?)?;
    let bundle = std::env::var_os("VERIDYCT_NEURAL_BUNDLE")
        .unwrap_or_else(|| "/opt/veridyct-extractor/model".into());
    eprintln!(
        "Frozen ONNX parser: CPU only, native={}, context={context}; extraction scores are not truth probabilities.",
        native.is_some()
    );
    let status = command
        .args(["--bundle"])
        .arg(bundle)
        .arg("--input")
        .arg(&input)
        .arg("--output")
        .arg(&output)
        .args(["--context", context.as_str()])
        .status()?;
    if !status.success() {
        return Err(format!("Frozen parser exited with {status}").into());
    }
    if fs::metadata(&output)?.len() > 128 * 1024 * 1024 {
        return Err("Frozen parser output exceeds 128 MiB budget".into());
    }
    let enriched: Vec<Value> = serde_json::from_slice(&fs::read(&output)?)?;
    if enriched.len() != rows.len() {
        return Err("Parser changed the number of input rows".into());
    }
    let mut bound = 0;
    let normalizer = Normalizer::new(LexiconIndex::compile(&lexicon.to_string(), Vec::new())?)?;
    for ((original, parser_input), raw) in rows.iter_mut().zip(&parser_rows).zip(enriched) {
        let mut parsed: InputRow = serde_json::from_value(raw.clone())?;
        if original.id != parsed.id
            || parser_input.text != parsed.text
            || original.date != parsed.date
            || original.label != parsed.label
        {
            return Err("Parser changed an ID, source text, date, label or input order".into());
        }
        if original.form.is_empty()
            && let Some(schema) = &structured
        {
            let candidates: Vec<ValueCandidate> =
                if let Some(values) = raw.get("_extractor_candidates") {
                    serde_json::from_value(values.clone())?
                } else {
                    Vec::new()
                };
            let result = schema.parse(&parser_input.text, &candidates, &parsed.form);
            if result
                .notes
                .iter()
                .any(|n| n.starts_with("explicit_unknown"))
            {
                hints.explicit_unknown.insert(original.id.clone());
            }
            if result.facts != parsed.form {
                bound += 1;
            }
            if requires_abstention(result.complete, &result.notes)
                || raw.get("_extractor_candidate_error").is_some()
                || raw.get("_extractor_candidate_truncated") == Some(&Value::Bool(true))
            {
                hints.incomplete.insert(original.id.clone());
            }
            parsed.form = result.facts;
            if parsed.form.is_empty() {
                hints.recognized_empty.insert(original.id.clone());
            }
        }
        if original.form.is_empty() && original.label.is_empty() {
            let normalized =
                normalizer.normalize(&original.id, &original.date, &parser_input.text)?;
            let before = parsed.form.len();
            // A frozen closed-world classifier can nominate an unrelated known
            // owner for a new company. The owner must be grounded in input text;
            // previous-row context without document boundaries is not a proof.
            parsed
                .form
                .retain(|fact| grounded_owner(&parser_input.text, &normalized, fact));
            if parsed.form.len() != before {
                hints.incomplete.insert(original.id.clone());
            }
            if parsed.form.is_empty() {
                hints.recognized_empty.insert(original.id.clone());
            }
        }
        if parsed.form.len() > 64 {
            return Err("Parser returned more than 64 assertions for one sentence".into());
        }
        if original.form.is_empty() {
            original.form = parsed.form;
        }
    }
    if structured.is_some() {
        eprintln!(
            "Schema binding changed {bound} rows; {} intentionally empty, {} unresolved/unknown.",
            hints.recognized_empty.len(),
            hints.incomplete.len()
        );
    }
    drop(paths);
    Ok(hints)
}

fn grounded_owner(text: &str, normalized: &NormalizedRow, fact: &veridyct_core::Fact) -> bool {
    let is_object = |start: usize| {
        let prefix = text[..start].trim_end().to_ascii_lowercase();
        [
            "unlike",
            "competes with",
            "compared with",
            "compared to",
            "as opposed to",
            "versus",
        ]
        .iter()
        .any(|phrase| prefix.ends_with(phrase))
    };
    if normalized
        .mentions
        .iter()
        .any(|m| m.subject == fact.subject && !is_object(m.original_span.start))
    {
        return true;
    }
    // Common-word aliases such as Chrome are deliberately conservative in the
    // normalizer. Explicit possessives or attribute-first references can still
    // ground a unique capitalized alias without inventing an entity mapping.
    normalized.issues.iter().any(|issue| {
        if issue.candidates.len() != 1
            || issue.candidates[0] != fact.subject
            || is_object(issue.original_span.start)
        {
            return false;
        }
        let alias = issue.original_span.slice(text).unwrap_or("");
        let suffix = text.get(issue.original_span.end..).unwrap_or("");
        let possessive = suffix.starts_with("'s") || suffix.starts_with('\u{2019}');
        let field = fact.attribute.replace('_', " ");
        let lower = text.to_ascii_lowercase();
        let explicit_field = lower.contains(&field)
            || fact.attribute.ends_with("_version") && lower.contains("version");
        alias.chars().next().is_some_and(char::is_uppercase) && (possessive || explicit_field)
    })
}

fn requires_abstention(complete: bool, notes: &[String]) -> bool {
    if notes.iter().any(|n| {
        n.starts_with("explicit_unknown")
            || n.starts_with("input_limit")
            || n.contains("invalid candidate")
    }) {
        return true;
    }
    // A schema pattern which never grounded any assertion is not evidence that
    // the frozen neural parse omitted a clause. Preserve its ordinary prose path.
    if notes
        .iter()
        .any(|n| n == "neural_fallback:no reliable schema binding")
    {
        return false;
    }
    !complete
        && notes
            .iter()
            .any(|n| n.starts_with("unresolved") || n.starts_with("ambiguous"))
}

struct TemporaryFiles(Vec<std::path::PathBuf>);
impl Drop for TemporaryFiles {
    fn drop(&mut self) {
        for path in &self.0 {
            let _ = fs::remove_file(path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::requires_abstention;
    #[test]
    fn owner_guard_preserves_explicit_aliases_and_rejects_comparison_objects() {
        use super::*;
        use serde_json::json;
        let normalizer = Normalizer::new(
            LexiconIndex::compile(include_str!("../../../data/lexicon.json"), Vec::new()).unwrap(),
        )
        .unwrap();
        let chrome = veridyct_core::Fact {
            subject: "Hooly Chrome".into(),
            attribute: "stable_version".into(),
            value: json!({"kind":"version","value":"12.4"}),
        };
        for text in [
            "The version of Chrome is v12.4.",
            "Chrome's stable version is 12.4.",
        ] {
            let row = normalizer.normalize("q", "2026-01-01", text).unwrap();
            assert!(grounded_owner(text, &row, &chrome), "{text}: {row:?}");
        }
        let pro = veridyct_core::Fact {
            subject: "Hooly AI Pro".into(),
            attribute: "price".into(),
            value: json!({"kind":"money","value":17,"currency":"EUR","per":"month"}),
        };
        let text = "Emberkeep offers EUR 17 per month and competes with Hooly AI Pro.";
        let row = normalizer.normalize("q", "2026-01-01", text).unwrap();
        assert!(!grounded_owner(text, &row, &pro));
    }
    #[test]
    fn ordinary_neural_fallback_is_distinct_from_a_known_missing_clause() {
        let notes = |v: &[&str]| v.iter().map(|x| (*x).to_owned()).collect::<Vec<_>>();
        assert!(!requires_abstention(
            false,
            &notes(&[
                "unresolved subject for customers",
                "neural_fallback:no reliable schema binding"
            ])
        ));
        assert!(requires_abstention(
            false,
            &notes(&["unresolved subject for customers"])
        ));
        assert!(requires_abstention(
            true,
            &notes(&["explicit_unknown:Atlas:customers"])
        ));
        assert!(requires_abstention(
            false,
            &notes(&[
                "input_limit:characters",
                "neural_fallback:no reliable schema binding"
            ])
        ));
    }
}
