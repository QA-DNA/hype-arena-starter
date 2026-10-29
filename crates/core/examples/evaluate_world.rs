//! Public-only world evaluation. Gold labels are read only after prediction.
//! --oracle-forms is an explicit reasoning-only diagnostic, never pipeline accuracy.
#![allow(dead_code)]
use veridyct_core::{engine, model, temporal};

use model::{Fact, InputRow, Prediction};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
    time::Instant,
};

const LABELS: [&str; 3] = ["true", "false", "unsure"];

fn load_csv(path: &Path) -> Result<Vec<InputRow>, Box<dyn std::error::Error>> {
    let mut reader = csv::Reader::from_path(path)?;
    let headers = reader.headers()?.clone();
    let field = |name: &str| -> Result<usize, Box<dyn std::error::Error>> {
        headers
            .iter()
            .position(|x| x == name)
            .ok_or_else(|| format!("Missing CSV column {name}").into())
    };
    let id = field("id")?;
    let text = field("text")?;
    let date = field("date")?;
    let label = field("label")?;
    let form = headers.iter().position(|x| x == "form");
    reader
        .records()
        .map(|record| {
            let r = record?;
            Ok(InputRow {
                id: r.get(id).unwrap_or_default().into(),
                text: r.get(text).unwrap_or_default().into(),
                date: r.get(date).unwrap_or_default().into(),
                label: r.get(label).unwrap_or_default().into(),
                form: match form.and_then(|i| r.get(i)).filter(|s| !s.is_empty()) {
                    Some(s) => serde_json::from_str(s)?,
                    None => vec![],
                },
            })
        })
        .collect()
}

fn normalized_number(value: &Value) -> Value {
    match value {
        Value::Number(n) => n.as_f64().map_or_else(|| value.clone(), |v| json!(v)),
        Value::Array(a) => Value::Array(a.iter().map(normalized_number).collect()),
        Value::Object(o) => Value::Object(
            o.iter()
                .map(|(k, v)| (k.clone(), normalized_number(v)))
                .collect(),
        ),
        _ => value.clone(),
    }
}

fn tuples(facts: &[Fact], normalize: bool) -> Vec<String> {
    let mut out: Vec<_> = facts
        .iter()
        .map(|fact| {
            let v = json!(fact);
            serde_json::to_string(&if normalize { normalized_number(&v) } else { v })
                .unwrap_or_default()
        })
        .collect();
    out.sort();
    out
}

fn metrics(confusion: &[[usize; 3]; 3]) -> Value {
    let rows: usize = confusion.iter().flatten().sum();
    let mut classes = vec![];
    let mut f1_sum = 0.0;
    let mut recall_sum = 0.0;
    let divide = |a: usize, b: usize| if b == 0 { 0.0 } else { a as f64 / b as f64 };
    for (i, label) in LABELS.iter().enumerate() {
        let support = confusion[i].iter().sum();
        let predictions = confusion.iter().map(|r| r[i]).sum();
        let precision = divide(confusion[i][i], predictions);
        let recall = divide(confusion[i][i], support);
        let f1 = if precision + recall == 0.0 {
            0.0
        } else {
            2.0 * precision * recall / (precision + recall)
        };
        f1_sum += f1;
        recall_sum += recall;
        classes.push(
            json!({"label":label,"support":support,"precision":precision,"recall":recall,"f1":f1}),
        );
    }
    let correct = (0..3).map(|i| confusion[i][i]).sum();
    json!({"rows":rows,"correct":correct,"accuracy":divide(correct,rows),"macro_f1":f1_sum/3.0,"balanced_accuracy":recall_sum/3.0,"confusion":confusion,"classes":classes})
}

fn class(label: &str) -> Option<usize> {
    LABELS.iter().position(|x| *x == label)
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut options = BTreeMap::<String, String>::new();
    let mut oracle = false;
    let mut oracle_anchors = false;
    let mut oracle_targets = false;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--oracle-forms" {
            oracle = true;
            oracle_anchors = true;
            oracle_targets = true;
        } else if arg == "--oracle-anchor-forms" {
            oracle_anchors = true;
        } else if arg == "--oracle-target-forms" {
            oracle_targets = true;
        } else if arg == "--help" {
            println!(
                "evaluate_world --input PUBLIC.csv --lexicon JSON --gold GOLD.csv --output REPORT.json [--parsed JSON] [--oracle-forms | --oracle-anchor-forms | --oracle-target-forms] [--practice CSV] [--emit-parser-input JSON]"
            );
            return Ok(());
        } else {
            options.insert(
                arg.clone(),
                args.next().ok_or(format!("Missing value for {arg}"))?,
            );
        }
    }
    let required = |name: &str| -> Result<PathBuf, Box<dyn std::error::Error>> {
        options
            .get(name)
            .map(PathBuf::from)
            .ok_or_else(|| format!("Missing {name}").into())
    };
    let input = required("--input")?;
    let mut rows = load_csv(&input)?;
    for row in &mut rows {
        row.form.clear();
    }
    if let Some(output) = options.get("--emit-parser-input") {
        for row in &mut rows {
            if let Some(scope) = temporal::explicit_scope(&row.text) {
                row.text = row.text[scope.body_offset_bytes..].to_owned();
            }
        }
        fs::write(output, serde_json::to_vec(&rows)?)?;
        return Ok(());
    }
    let lexicon_path = required("--lexicon")?;
    let gold_path = required("--gold")?;
    let output = required("--output")?;
    let lexicon: Value = serde_json::from_slice(&fs::read(&lexicon_path)?)?;
    let practice_path = options
        .get("--practice")
        .map(PathBuf::from)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/practice.csv"));
    let practice = load_csv(&practice_path)?;
    if let Some(parsed) = options.get("--parsed") {
        let predictions: Vec<InputRow> = serde_json::from_slice(&fs::read(parsed)?)?;
        let forms: BTreeMap<_, _> = predictions.into_iter().map(|r| (r.id, r.form)).collect();
        for row in &mut rows {
            row.form = forms.get(&row.id).cloned().unwrap_or_default();
        }
    }
    // Oracle mode is visibly separate. Normal prediction never opens gold here.
    let oracle_rows = if oracle_anchors || oracle_targets {
        Some(load_csv(&gold_path)?)
    } else {
        None
    };
    if let Some(gold) = &oracle_rows {
        let forms: BTreeMap<_, _> = gold.iter().map(|r| (&r.id, &r.form)).collect();
        for row in &mut rows {
            if (!row.label.is_empty() && oracle_anchors) || (row.label.is_empty() && oracle_targets)
            {
                row.form = forms.get(&row.id).copied().cloned().unwrap_or_default();
            }
        }
    }
    let start = Instant::now();
    let engine = engine::Engine::new(&practice, &lexicon)?;
    let canonical_seed_present = engine.canonical_seed_present(&rows);
    let predictions: Vec<Prediction> = engine.predict_universe(&rows);
    drop(engine);
    let prediction_seconds = start.elapsed().as_secs_f64();
    let gold = oracle_rows.unwrap_or(load_csv(&gold_path)?);
    let gold: BTreeMap<_, _> = gold.into_iter().map(|r| (r.id.clone(), r)).collect();
    let mut wrong_anchor_slots = BTreeSet::new();
    for (row, prediction) in rows
        .iter()
        .zip(&predictions)
        .filter(|(r, _)| !r.label.is_empty())
    {
        if let Some(reference) = gold.get(&row.id)
            && tuples(&prediction.facts, true) != tuples(&reference.form, true)
        {
            for fact in prediction.facts.iter().chain(&reference.form) {
                wrong_anchor_slots.insert((fact.subject.clone(), fact.attribute.clone()));
            }
        }
    }
    let mut confusion = [[0usize; 3]; 3];
    let mut by_kind = BTreeMap::<String, [[usize; 3]; 3]>::new();
    let mut errors = vec![];
    let mut targets = 0;
    let mut exact = 0;
    let mut strict_exact = 0;
    let mut reasoning_errors = 0;
    let mut parse_errors = 0;
    let mut anchor_rows = 0;
    let mut anchor_exact = 0;
    let mut true_proofs = 0;
    let mut false_proofs = 0;
    let mut anchor_parse_errors = 0;
    let mut all_results = Vec::with_capacity(predictions.len());
    for (row, prediction) in rows.iter().zip(predictions) {
        let Some(reference) = gold.get(&row.id) else {
            return Err(format!("Gold missing ID {}", row.id).into());
        };
        let tuple_exact = tuples(&prediction.facts, true) == tuples(&reference.form, true);
        if !row.label.is_empty() {
            anchor_rows += 1;
            anchor_exact += usize::from(tuple_exact);
            continue;
        }
        let y = class(&reference.label).ok_or("Invalid gold label")?;
        let p = class(&prediction.label).ok_or("Invalid predicted label")?;
        confusion[y][p] += 1;
        targets += 1;
        exact += usize::from(tuple_exact);
        strict_exact +=
            usize::from(tuples(&prediction.facts, false) == tuples(&reference.form, false));
        let kinds: BTreeSet<_> = reference
            .form
            .iter()
            .filter_map(|f| f.value["kind"].as_str())
            .collect();
        for kind in kinds {
            by_kind.entry(kind.into()).or_default()[y][p] += 1;
        }
        true_proofs += usize::from(prediction.reason.contains("entails every"));
        false_proofs += usize::from(prediction.reason.contains("refutes at least"));
        let anchor_mismatch = reference
            .form
            .iter()
            .any(|f| wrong_anchor_slots.contains(&(f.subject.clone(), f.attribute.clone())));
        if y != p {
            if tuple_exact {
                reasoning_errors += 1;
                anchor_parse_errors += usize::from(anchor_mismatch);
            } else {
                parse_errors += 1;
            }
        }
        let result = json!({"id":row.id,"text":row.text,"date":row.date,"gold_label":reference.label,"prediction":prediction,"gold_form":reference.form,"tuple_exact":tuple_exact,"anchor_slot_mismatch":anchor_mismatch,"error_class":if tuple_exact{if anchor_mismatch{"anchor_extraction_or_reasoning"}else{"reasoning"}}else{"target_extraction_or_both"}});
        if y != p && errors.len() < 100 {
            errors.push(result.clone());
        }
        all_results.push(result);
    }
    let report = json!({"schema_version":1,"label_order":LABELS,"mode":if oracle{"oracle_forms_diagnostic"}else if oracle_anchors{"oracle_anchors_inferred_targets_diagnostic"}else if oracle_targets{"inferred_anchors_oracle_targets_diagnostic"}else if options.contains_key("--parsed"){"neural_forms_with_engine_fallback_on_empty"}else{"template"},
        "independent_final_evaluation":false,"public_rows":rows.len(),"target_rows":targets,"canonical_seed_present":canonical_seed_present,
        "classification":metrics(&confusion),"by_kind":by_kind.into_iter().map(|(k,c)|(k,metrics(&c))).collect::<BTreeMap<_,_>>(),
        "extraction":{"target_exact_rows":exact,"target_strict_exact_rows":strict_exact,"target_complete_row_exact":exact as f64/targets.max(1) as f64,"visible_anchor_rows":anchor_rows,"visible_anchor_exact_rows":anchor_exact},
        "error_attribution":{"tuple_exact_reasoning_errors":reasoning_errors,"of_exact_errors_anchor_slot_mismatch":anchor_parse_errors,"extraction_or_both_errors":parse_errors,"note":"Exact target errors may involve wrong anchor extraction; tuple mismatch does not prove extraction alone caused the verdict error"},
        "proofs":{"true":true_proofs,"false":false_proofs},"prediction_seconds":prediction_seconds,"errors_up_to_100":errors,
        "protocol":{"gold_labels_enter_solver":false,"gold_forms_enter_solver":oracle_anchors||oracle_targets,"oracle_anchor_forms":oracle_anchors,"oracle_target_forms":oracle_targets,"public_input_forms_stripped":true,"canonical_practice_truth_excluded_from_foreign_world":!canonical_seed_present,"gold_file_opened_after_prediction":!oracle_anchors&&!oracle_targets},"results":all_results});
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(&output, serde_json::to_vec_pretty(&report)?)?;
    eprintln!(
        "{}",
        json!({"mode":report["mode"],"classification":report["classification"],"extraction":report["extraction"],"error_attribution":report["error_attribution"],"seconds":prediction_seconds})
    );
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
