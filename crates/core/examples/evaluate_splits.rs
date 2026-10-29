//! Offline CPU evaluation; run through tools/evaluate-splits.ps1 or --help.
//! Reference labels/forms stay outside both Engine::new and prediction inputs.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    env, fs,
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use unicode_normalization::UnicodeNormalization;
use veridyct_core::{Engine, Fact, InputRow, Prediction, read_csv};

const LABELS: [&str; 3] = ["true", "false", "unsure"];
const SPLITS: [&str; 5] = [
    "random",
    "bundle_group",
    "template_group",
    "forward_time",
    "every_fifth",
];

struct Options {
    practice: PathBuf,
    lexicon: PathBuf,
    assignments: PathBuf,
    output: PathBuf,
    external: Option<PathBuf>,
    test_ids: Option<PathBuf>,
    predictions: Option<PathBuf>,
    splits: Vec<String>,
}

impl Options {
    fn parse() -> Result<Option<Self>, String> {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let setting = |name: &str, fallback: &str| {
            env::var_os(name)
                .map(PathBuf::from)
                .unwrap_or_else(|| root.join(fallback))
        };
        let mut options = Self {
            practice: setting("VERIDYCT_EVAL_PRACTICE", "data/practice.csv"),
            lexicon: setting("VERIDYCT_EVAL_LEXICON", "data/lexicon.json"),
            assignments: setting(
                "VERIDYCT_EVAL_ASSIGNMENTS",
                "analysis/practice/outputs/split_assignments.csv",
            ),
            output: env::var_os("VERIDYCT_EVAL_OUTPUT")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("-")),
            external: env::var_os("VERIDYCT_EVAL_EXTERNAL").map(PathBuf::from),
            test_ids: env::var_os("VERIDYCT_EVAL_TEST_IDS").map(PathBuf::from),
            predictions: env::var_os("VERIDYCT_EVAL_PREDICTIONS").map(PathBuf::from),
            splits: SPLITS.iter().map(|s| (*s).to_owned()).collect(),
        };
        let mut args = env::args().skip(1);
        while let Some(arg) = args.next() {
            if arg == "--help" || arg == "-h" {
                println!(
                    "evaluate_splits [--practice CSV] [--lexicon JSON] [--assignments CSV] \
                     [--output JSON|-] [--splits random,bundle_group,template_group,forward_time,every_fifth] \
                     [--external CSV] [--test-ids IDS [--predictions JSONL]]\n\
                     External CSV uses id,text,date,label and optional form (JSON array); labels are gold.\n\
                     External evaluation trains on practice only, excluding matching IDs and normalized texts.\n\
                     --test-ids replaces named splits with a custom holdout (one ID per line or JSON array).\n\
                     --predictions requires --test-ids and adds paired neural-plus-template verdicts and raw parser tuple scores; JSONL uses id,prediction:[{{atom:Fact}}].\n\
                     Environment: VERIDYCT_EVAL_PRACTICE, _LEXICON, _ASSIGNMENTS, _OUTPUT, _EXTERNAL; \
                     VERIDYCT_EVAL_COMMIT records the source revision.\n\
                     JSON goes to stdout by default; progress goes to stderr. No runtime network or LLM."
                );
                return Ok(None);
            }
            if ![
                "--practice",
                "--lexicon",
                "--assignments",
                "--output",
                "--splits",
                "--external",
                "--test-ids",
                "--predictions",
            ]
            .contains(&arg.as_str())
            {
                return Err(format!("Unknown option {arg:?}; use --help"));
            }
            let value = args.next().ok_or_else(|| format!("{arg} needs a value"))?;
            if value.is_empty() || value.starts_with("--") {
                return Err(format!("{arg} needs a nonempty value"));
            }
            match arg.as_str() {
                "--practice" => options.practice = value.into(),
                "--lexicon" => options.lexicon = value.into(),
                "--assignments" => options.assignments = value.into(),
                "--output" => options.output = value.into(),
                "--external" => options.external = Some(value.into()),
                "--test-ids" => options.test_ids = Some(value.into()),
                "--predictions" => options.predictions = Some(value.into()),
                "--splits" => {
                    options.splits = value.split(',').map(str::to_owned).collect();
                }
                _ => unreachable!(),
            }
        }
        let unique: BTreeSet<_> = options.splits.iter().collect();
        if unique.len() != options.splits.len() || unique.iter().any(|s| s.is_empty()) {
            return Err("Split names must be nonempty and unique".into());
        }
        if options.predictions.is_some() && options.test_ids.is_none() {
            return Err("--predictions requires --test-ids: pretrained extraction must not leak across the five practice splits".into());
        }
        if options.test_ids.is_some() && options.external.is_some() {
            return Err("Use --test-ids and --external in separate runs".into());
        }
        Ok(Some(options))
    }
}

struct Dataset {
    rows: Vec<InputRow>,
    annotated: BTreeSet<String>,
    fingerprint: Value,
}

fn load_dataset(path: &Path) -> Result<Dataset, String> {
    let text = read_text(path)?;
    let rows = read_csv(&text)?;
    for row in &rows {
        if !LABELS.contains(&row.label.as_str()) {
            return Err(format!(
                "{}: row {} needs a gold label",
                path.display(),
                row.id
            ));
        }
    }
    // Missing/blank forms are unannotated; an explicit [] is an annotated empty set.
    let text = text.trim_start_matches('\u{feff}');
    let header = text.lines().next().unwrap_or_default();
    let delimiter = if header.matches(';').count() > header.matches(',').count() {
        b';'
    } else {
        b','
    };
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(delimiter)
        .from_reader(text.as_bytes());
    let headers = reader.headers().map_err(|e| e.to_string())?.clone();
    let id_column = headers
        .iter()
        .position(|h| h.trim() == "id")
        .ok_or("Missing id")?;
    let form_column = headers.iter().position(|h| h.trim() == "form");
    let mut annotated = BTreeSet::new();
    if let Some(column) = form_column {
        for record in reader.records() {
            let record = record.map_err(|e| e.to_string())?;
            if !record[column].trim().is_empty() {
                annotated.insert(record[id_column].trim().to_owned());
            }
        }
    }
    Ok(Dataset {
        rows,
        annotated,
        fingerprint: fingerprint(path)?,
    })
}

#[derive(Deserialize)]
struct Assignment {
    split: String,
    partition: String,
    id: String,
}

fn load_assignments(path: &Path) -> Result<Vec<Assignment>, String> {
    let text = read_text(path)?;
    let mut reader = csv::Reader::from_reader(text.trim_start_matches('\u{feff}').as_bytes());
    reader
        .deserialize()
        .map(|r| r.map_err(|e| e.to_string()))
        .collect()
}

fn load_test_ids(path: &Path) -> Result<BTreeSet<String>, String> {
    let text = read_text(path)?;
    let text = text.trim_start_matches('\u{feff}').trim();
    let ids: Vec<String> = if text.starts_with('[') {
        serde_json::from_str(text).map_err(|e| format!("Test IDs JSON: {e}"))?
    } else {
        text.lines()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_owned)
            .collect()
    };
    let unique: BTreeSet<_> = ids.iter().cloned().collect();
    if unique.is_empty() || unique.len() != ids.len() || unique.iter().any(|id| id.is_empty()) {
        return Err("Test IDs must be nonempty and unique".into());
    }
    Ok(unique)
}

fn load_predictions(
    path: &Path,
    selected: &BTreeSet<String>,
) -> Result<BTreeMap<String, Vec<Fact>>, String> {
    let text = read_text(path)?;
    parse_predictions(&text, selected)
}

fn parse_predictions(
    text: &str,
    selected: &BTreeSet<String>,
) -> Result<BTreeMap<String, Vec<Fact>>, String> {
    let mut predictions = BTreeMap::new();
    for (index, line) in text.trim_start_matches('\u{feff}').lines().enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let row: Value = serde_json::from_str(line)
            .map_err(|e| format!("Prediction line {}: {e}", index + 1))?;
        let id = row["id"].as_str().ok_or("Prediction row needs an id")?;
        if !selected.contains(id) {
            continue;
        }
        let atoms = row["prediction"]
            .as_array()
            .ok_or_else(|| format!("Prediction {id} needs a prediction array"))?;
        let forms: Vec<Fact> = atoms
            .iter()
            .map(|atom| {
                let fact = atom.get("atom").unwrap_or(atom);
                serde_json::from_value(fact.clone()).map_err(|e| format!("Prediction {id}: {e}"))
            })
            .collect::<Result<_, _>>()?;
        if predictions.insert(id.to_owned(), forms).is_some() {
            return Err(format!("Duplicate selected prediction {id}"));
        }
    }
    if predictions.len() != selected.len() {
        let missing: Vec<_> = selected
            .iter()
            .filter(|id| !predictions.contains_key(*id))
            .take(5)
            .collect();
        return Err(format!(
            "Predictions missing {} selected IDs, including {missing:?}",
            selected.len() - predictions.len()
        ));
    }
    Ok(predictions)
}

fn split_rows<'a>(
    name: &str,
    rows: &'a [InputRow],
    assignments: &[Assignment],
) -> Result<(Vec<&'a InputRow>, Vec<&'a InputRow>), String> {
    let known: BTreeSet<_> = rows.iter().map(|r| r.id.as_str()).collect();
    let mut partitions = BTreeMap::new();
    for assignment in assignments.iter().filter(|a| a.split == name) {
        if !["train", "test"].contains(&assignment.partition.as_str()) {
            return Err(format!(
                "{name}: invalid partition {:?}",
                assignment.partition
            ));
        }
        if !known.contains(assignment.id.as_str()) {
            return Err(format!("{name}: unknown row ID {}", assignment.id));
        }
        if partitions
            .insert(assignment.id.as_str(), assignment.partition.as_str())
            .is_some()
        {
            return Err(format!(
                "{name}: duplicate assignment for {}",
                assignment.id
            ));
        }
    }
    if partitions.len() != rows.len() {
        return Err(format!(
            "{name}: expected {} unique assigned rows, got {}",
            rows.len(),
            partitions.len()
        ));
    }
    let mut training = Vec::new();
    let mut test = Vec::new();
    // Source order, not assignment order, controls training and report order.
    for row in rows {
        if partitions[row.id.as_str()] == "train" {
            training.push(row);
        } else {
            test.push(row);
        }
    }
    if training.is_empty() || test.is_empty() {
        return Err(format!("{name}: both train and test must be nonempty"));
    }
    Ok((training, test))
}

fn normalize(text: &str) -> String {
    // Mirrors the engine's NFKC/case/whitespace normalization; punctuation is retained.
    text.nfkc()
        .collect::<String>()
        .to_lowercase()
        .replace('\u{df}', "ss")
        .replace('\u{3c2}', "\u{3c3}")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn hide_gold(row: &InputRow) -> InputRow {
    InputRow {
        id: row.id.clone(),
        text: row.text.clone(),
        date: row.date.clone(),
        label: String::new(),
        form: Vec::new(),
    }
}

fn clean_training(training: &[&InputRow], test: &[&InputRow]) -> (Vec<InputRow>, usize, usize) {
    let texts: BTreeSet<_> = test.iter().map(|r| normalize(&r.text)).collect();
    let ids: BTreeSet<_> = test.iter().map(|r| r.id.as_str()).collect();
    let mut by_text = 0;
    let mut by_id = 0;
    let training = training
        .iter()
        .filter_map(|row| {
            // Counts are exclusive, with text exclusion taking precedence.
            if texts.contains(&normalize(&row.text)) {
                by_text += 1;
                None
            } else if ids.contains(row.id.as_str()) {
                by_id += 1;
                None
            } else {
                Some((*row).clone())
            }
        })
        .collect();
    (training, by_text, by_id)
}

#[derive(Debug, Serialize)]
struct ClassMetrics {
    label: &'static str,
    support: usize,
    predicted: usize,
    precision: f64,
    recall: f64,
    f1: f64,
}

#[derive(Debug, Serialize)]
struct Metrics {
    confusion: [[usize; 3]; 3],
    accuracy: f64,
    macro_f1: f64,
    classes: Vec<ClassMetrics>,
}

fn divide(n: usize, d: usize) -> f64 {
    if d == 0 { 0.0 } else { n as f64 / d as f64 }
}

fn metrics(confusion: [[usize; 3]; 3]) -> Metrics {
    let classes: Vec<_> = (0..3)
        .map(|i| {
            let support = confusion[i].iter().sum();
            let predicted = (0..3).map(|j| confusion[j][i]).sum();
            ClassMetrics {
                label: LABELS[i],
                support,
                predicted,
                precision: divide(confusion[i][i], predicted),
                recall: divide(confusion[i][i], support),
                f1: divide(2 * confusion[i][i], support + predicted),
            }
        })
        .collect();
    Metrics {
        accuracy: divide(
            (0..3).map(|i| confusion[i][i]).sum(),
            confusion.iter().flatten().sum(),
        ),
        macro_f1: classes.iter().map(|c| c.f1).sum::<f64>() / 3.0,
        confusion,
        classes,
    }
}

fn label_index(label: &str) -> Result<usize, String> {
    LABELS
        .iter()
        .position(|&s| s == label)
        .ok_or_else(|| format!("Invalid label {label:?}"))
}

#[derive(Default, Debug, Serialize)]
struct TupleCounts {
    true_positive: usize,
    false_positive: usize,
    false_negative: usize,
}

impl TupleCounts {
    fn f1(&self) -> f64 {
        let denominator = 2 * self.true_positive + self.false_positive + self.false_negative;
        if denominator == 0 {
            1.0
        } else {
            divide(2 * self.true_positive, denominator)
        }
    }
    fn exact(&self) -> bool {
        self.false_positive == 0 && self.false_negative == 0
    }
}

#[derive(Default)]
struct TupleAccumulator {
    counts: TupleCounts,
    scored_rows: usize,
    exact_rows: usize,
    row_f1_sum: f64,
}

impl TupleAccumulator {
    fn add(&mut self, counts: &TupleCounts) {
        self.scored_rows += 1;
        self.exact_rows += usize::from(counts.exact());
        self.row_f1_sum += counts.f1();
        self.counts.true_positive += counts.true_positive;
        self.counts.false_positive += counts.false_positive;
        self.counts.false_negative += counts.false_negative;
    }

    fn report(&self) -> Value {
        if self.scored_rows == 0 {
            return Value::Null;
        }
        let counts = &self.counts;
        json!({
            "scored_rows": self.scored_rows, "exact_rows": self.exact_rows,
            "exact_accuracy": divide(self.exact_rows, self.scored_rows),
            "micro_precision": if counts.true_positive + counts.false_positive == 0 { f64::from(counts.false_negative == 0) } else { divide(counts.true_positive, counts.true_positive + counts.false_positive) },
            "micro_recall": if counts.true_positive + counts.false_negative == 0 { 1.0 } else { divide(counts.true_positive, counts.true_positive + counts.false_negative) },
            "micro_f1": counts.f1(), "row_macro_f1": self.row_f1_sum / self.scored_rows as f64,
            "counts": counts,
        })
    }
}

fn tuple_counts(gold: &[Fact], predicted: &[Fact]) -> Result<TupleCounts, String> {
    let encode = |facts: &[Fact]| -> Result<BTreeSet<String>, String> {
        facts
            .iter()
            .map(|f| serde_json::to_string(f).map_err(|e| e.to_string()))
            .collect()
    };
    let gold = encode(gold)?;
    let predicted = encode(predicted)?;
    Ok(TupleCounts {
        true_positive: gold.intersection(&predicted).count(),
        false_positive: predicted.difference(&gold).count(),
        false_negative: gold.difference(&predicted).count(),
    })
}

#[derive(Serialize)]
struct RowResult<'a> {
    id: &'a str,
    gold_label: &'a str,
    gold_form: Option<&'a [Fact]>,
    correct: bool,
    extraction: Vec<Fact>,
    tuple_counts: Option<TupleCounts>,
    parser_extraction: Option<Vec<Fact>>,
    parser_tuple_counts: Option<TupleCounts>,
    prediction: Prediction,
}

fn evaluate(
    name: &str,
    provided_training: &[&InputRow],
    test: &[&InputRow],
    annotated: &BTreeSet<String>,
    lexicon: &Value,
    predicted_forms: Option<&BTreeMap<String, Vec<Fact>>>,
) -> Result<Value, String> {
    let started = Instant::now();
    let (training, excluded_text, excluded_id) = clean_training(provided_training, test);
    if training.is_empty() || test.is_empty() {
        return Err(format!(
            "{name}: empty training or test after leakage exclusion"
        ));
    }
    let mut inputs: Vec<_> = test.iter().map(|r| hide_gold(r)).collect();
    if let Some(parsed) = predicted_forms {
        for input in &mut inputs {
            // Explicit, separately reported hybrid mode: attach model output only.
            input.form = parsed
                .get(&input.id)
                .ok_or_else(|| format!("Missing parser prediction {}", input.id))?
                .clone();
        }
    }
    let training_ids: BTreeSet<_> = training.iter().map(|r| r.id.as_str()).collect();
    let mut training_counts = [0; 3];
    for row in &training {
        training_counts[label_index(&row.label)?] += 1;
    }
    let mut majority = 0;
    for i in 1..3 {
        if training_counts[i] > training_counts[majority] {
            majority = i;
        }
    }
    let stage = Instant::now();
    let engine = Engine::new(&training, lexicon)?;
    let training_seconds = stage.elapsed().as_secs_f64();
    let stage = Instant::now();
    let predictions = engine.predict(&inputs);
    let prediction_seconds = stage.elapsed().as_secs_f64();
    if predictions.len() != test.len() {
        return Err(format!("{name}: prediction count differs from test count"));
    }
    let stage = Instant::now();
    let extractions: Vec<_> = inputs.iter().map(|r| engine.extract(r)).collect();
    let extraction_seconds = stage.elapsed().as_secs_f64();
    let mut confusion = [[0; 3]; 3];
    let mut majority_confusion = [[0; 3]; 3];
    let mut extraction_totals = TupleAccumulator::default();
    let mut parser_totals = TupleAccumulator::default();
    let mut results = Vec::new();
    for ((gold, prediction), extraction) in test.iter().zip(predictions).zip(extractions) {
        if prediction.id != gold.id || prediction.known_label.is_some() {
            return Err(format!(
                "{name}: prediction order or hidden-label invariant failed"
            ));
        }
        if prediction
            .evidence
            .iter()
            .any(|e| !training_ids.contains(e.row_id.as_str()))
        {
            return Err(format!(
                "{name}: prediction used an evidence row outside training"
            ));
        }
        let expected = label_index(&gold.label)?;
        let chosen = label_index(&prediction.label)?;
        confusion[expected][chosen] += 1;
        majority_confusion[expected][majority] += 1;
        let counts = if annotated.contains(&gold.id) {
            let counts = tuple_counts(&gold.form, &extraction)?;
            extraction_totals.add(&counts);
            Some(counts)
        } else {
            None
        };
        let parser_extraction = predicted_forms.and_then(|p| p.get(&gold.id)).cloned();
        let parser_counts = if let Some(parsed) = &parser_extraction {
            if annotated.contains(&gold.id) {
                let counts = tuple_counts(&gold.form, parsed)?;
                parser_totals.add(&counts);
                Some(counts)
            } else {
                None
            }
        } else {
            None
        };
        results.push(RowResult {
            id: &gold.id,
            gold_label: &gold.label,
            gold_form: counts.as_ref().map(|_| gold.form.as_slice()),
            correct: expected == chosen,
            extraction,
            tuple_counts: counts,
            parser_extraction,
            parser_tuple_counts: parser_counts,
            prediction,
        });
    }
    let classification = metrics(confusion);
    let baseline = metrics(majority_confusion);
    let tuples = extraction_totals.report();
    let elapsed_seconds = started.elapsed().as_secs_f64();
    eprintln!(
        "{name}: train={} test={} accuracy={:.6} macroF1={:.6} majority={:.6} tuple_exact={} elapsed={:.3}s",
        training.len(),
        test.len(),
        classification.accuracy,
        classification.macro_f1,
        baseline.accuracy,
        if extraction_totals.scored_rows == 0 {
            "n/a".into()
        } else {
            format!(
                "{:.6}",
                divide(extraction_totals.exact_rows, extraction_totals.scored_rows)
            )
        },
        elapsed_seconds
    );
    Ok(json!({
        "split": name,
        "training_rows": training.len(), "test_rows": test.len(),
        "training_label_counts": training_counts,
        "classification": classification,
        "majority_baseline": {"label": LABELS[majority], "metrics": baseline},
        "extraction": tuples,
        "raw_parser_extraction": parser_totals.report(),
        "extraction_mode": if predicted_forms.is_some() { "neural_plus_template_fallback_on_empty" } else { "engine_text_only" },
        "timing": {"training_seconds": training_seconds, "prediction_seconds": prediction_seconds,
            "extraction_seconds": extraction_seconds, "elapsed_seconds": elapsed_seconds},
        "leakage_audit": {
            "provided_training_rows": provided_training.len(),
            "excluded_normalized_test_text": excluded_text, "excluded_test_id": excluded_id,
            "test_labels_hidden": true, "test_forms_hidden": true,
            "model_predicted_forms_attached": predicted_forms.is_some(),
            "evidence_restricted_to_training_ids": true,
            "training_ids": training.iter().map(|r| &r.id).collect::<Vec<_>>(),
            "test_ids": test.iter().map(|r| &r.id).collect::<Vec<_>>()
        },
        "results": results,
    }))
}

fn read_text(path: &Path) -> Result<String, String> {
    fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))
}

fn fingerprint(path: &Path) -> Result<Value, String> {
    let bytes = fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let hash = bytes.iter().fold(0xcbf29ce484222325_u64, |h, b| {
        (h ^ u64::from(*b)).wrapping_mul(0x100000001b3)
    });
    Ok(json!({"path": path, "bytes": bytes.len(), "fnv1a64": format!("{hash:016x}")}))
}

fn linux_status(prefix: &str) -> Option<String> {
    fs::read_to_string("/proc/self/status")
        .ok()?
        .lines()
        .find(|line| line.starts_with(prefix))
        .map(str::to_owned)
}

fn run() -> Result<(), String> {
    let Some(options) = Options::parse()? else {
        return Ok(());
    };
    if options.output != Path::new("-") {
        let output = fs::canonicalize(&options.output).ok();
        for input in [&options.practice, &options.lexicon, &options.assignments]
            .into_iter()
            .chain(options.external.iter())
            .chain(options.test_ids.iter())
            .chain(options.predictions.iter())
        {
            if output.is_some() && output == fs::canonicalize(input).ok() {
                return Err("Output must not overwrite an input file".into());
            }
        }
    }
    let started = Instant::now();
    let practice = load_dataset(&options.practice)?;
    let lexicon: Value =
        serde_json::from_str(&read_text(&options.lexicon)?).map_err(|e| e.to_string())?;
    let custom_ids = options.test_ids.as_deref().map(load_test_ids).transpose()?;
    let parsed = options
        .predictions
        .as_deref()
        .map(|path| {
            load_predictions(
                path,
                custom_ids
                    .as_ref()
                    .ok_or("Predictions need selected test IDs")?,
            )
        })
        .transpose()?;
    // Validate all requested partitions before doing any expensive training.
    let plans = if let Some(ids) = &custom_ids {
        let known: BTreeSet<_> = practice.rows.iter().map(|r| r.id.clone()).collect();
        if !ids.is_subset(&known) {
            return Err(format!(
                "Unknown custom test IDs: {:?}",
                ids.difference(&known).take(5).collect::<Vec<_>>()
            ));
        }
        let (test, training): (Vec<_>, Vec<_>) =
            practice.rows.iter().partition(|r| ids.contains(&r.id));
        vec![("custom_ids".to_owned(), (training, test))]
    } else {
        let assignments = load_assignments(&options.assignments)?;
        options
            .splits
            .iter()
            .map(|name| {
                split_rows(name, &practice.rows, &assignments).map(|rows| (name.clone(), rows))
            })
            .collect::<Result<Vec<_>, _>>()?
    };
    let external = options.external.as_deref().map(load_dataset).transpose()?;
    let mut reports = Vec::new();
    for (name, (training, test)) in plans {
        reports.push(evaluate(
            &name,
            &training,
            &test,
            &practice.annotated,
            &lexicon,
            None,
        )?);
        if let Some(parsed) = &parsed {
            reports.push(evaluate(
                &format!("{name}_neural_template"),
                &training,
                &test,
                &practice.annotated,
                &lexicon,
                Some(parsed),
            )?);
        }
    }
    if let Some(external) = &external {
        let training: Vec<_> = practice.rows.iter().collect();
        let test: Vec<_> = external.rows.iter().collect();
        reports.push(evaluate(
            "external",
            &training,
            &test,
            &external.annotated,
            &lexicon,
            None,
        )?);
    }
    let hardware = fs::read_to_string("/proc/cpuinfo")
        .unwrap_or_default()
        .lines()
        .find(|line| line.starts_with("model name"))
        .map(str::to_owned)
        .or_else(|| env::var("PROCESSOR_IDENTIFIER").ok());
    let report = json!({
        "schema_version": 1,
        "label_order": LABELS, "confusion_orientation": "rows=gold, columns=prediction",
        "generated_unix_seconds": SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| e.to_string())?.as_secs(),
        "source_commit": env::var("VERIDYCT_EVAL_COMMIT").unwrap_or_else(|_| "unspecified; set VERIDYCT_EVAL_COMMIT".into()),
        "inputs": {"practice": practice.fingerprint, "lexicon": fingerprint(&options.lexicon)?,
            "assignments": if custom_ids.is_some() { None } else { Some(fingerprint(&options.assignments)?) },
            "external": external.as_ref().map(|e| &e.fingerprint),
            "test_ids": options.test_ids.as_deref().map(fingerprint).transpose()?,
            "parser_predictions": options.predictions.as_deref().map(fingerprint).transpose()?},
        "runtime": {"profile": if cfg!(debug_assertions) { "debug" } else { "release" },
            "os": env::consts::OS, "architecture": env::consts::ARCH, "hardware": hardware,
            "available_cpus": std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1),
            "compute_threads": 1, "peak_rss": linux_status("VmHWM:"),
            "elapsed_seconds": started.elapsed().as_secs_f64()},
        "protocol": {
            "training": "Each split trains a fresh Engine on its train rows only; remove every normalized test text and matching test ID before construction. External evaluation trains on cleaned full practice only.",
            "prediction": "Gold labels/forms are always stripped before Engine::predict/extract. Text-only mode supplies empty forms. Explicit --predictions with --test-ids adds separately reported frozen model output forms only; empty predicted forms fall back to engine templates. No test rows enter training or evidence.",
            "normalization": "NFKC, lowercase, sharp-s/final-sigma folds, collapse whitespace; punctuation retained, matching current engine.",
            "classification": "All three classes contribute equally to macro-F1; undefined class precision/recall/F1 is zero. Majority chosen from cleaned train labels only; ties true,false,unsure.",
            "tuples": "Exact typed (subject,attribute,value JSON) sets: order/duplicates ignored; no fuzzy value matching. Score only nonblank gold form cells (explicit [] is gold empty). Micro counts pooled over scored rows; empty/empty row F1=1.",
            "limits": "Practice-derived diagnostics share facts across splits and may already have informed model tuning. Scores are uncalibrated; this is not independent final validation. This harness calls the linked Engine directly; any future externally pretrained parser requires a separately verified training-ID manifest before interpreting split results."
        },
        "splits": reports,
    });
    let mut encoded = serde_json::to_string_pretty(&report).map_err(|e| e.to_string())?;
    encoded.push('\n');
    if options.output == Path::new("-") {
        print!("{encoded}");
    } else {
        if let Some(parent) = options
            .output
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
        {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        fs::write(&options.output, encoded)
            .map_err(|e| format!("{}: {e}", options.output.display()))?;
        eprintln!("Report: {}", options.output.display());
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("evaluate_splits: {error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(id: &str, text: &str, label: &str) -> InputRow {
        InputRow {
            id: id.into(),
            text: text.into(),
            date: "2026-01-01".into(),
            label: label.into(),
            form: vec![],
        }
    }

    #[test]
    fn removes_normalized_duplicates_and_external_id_collisions() {
        let a = row("a", "  STRA\u{df}E \u{ff21} ", "true");
        let b = row("b", "Different text", "false");
        let c = row("safe", "Keep me", "unsure");
        let gold = row("b", "strasse a", "false");
        let (training, text, id) = clean_training(&[&a, &b, &c], &[&gold]);
        assert_eq!((text, id), (1, 1));
        assert_eq!(training[0].id, "safe");
        let mut gold = gold;
        gold.form.push(Fact {
            subject: "Secret".into(),
            attribute: "hidden".into(),
            value: json!({"kind":"number","value":90210}),
        });
        let input = hide_gold(&gold);
        assert!(input.label.is_empty() && input.form.is_empty());
        assert_eq!(
            (input.id, input.text, input.date),
            (gold.id, gold.text, gold.date)
        );
    }

    #[test]
    fn confusion_metrics_include_minority_and_absent_classes() {
        let m = metrics([[2, 1, 0], [1, 1, 0], [0, 1, 0]]);
        assert!((m.accuracy - 0.5).abs() < 1e-12);
        assert!((m.macro_f1 - (2.0 / 3.0 + 0.4) / 3.0).abs() < 1e-12);
        assert_eq!(m.classes[2].recall, 0.0);
        assert_eq!(m.classes[2].precision, 0.0);
        assert_eq!(m.classes[1].support, 2);
    }

    #[test]
    fn tuple_scoring_is_typed_order_independent_and_penalizes_extra_facts() {
        let a = Fact {
            subject: "S".into(),
            attribute: "A".into(),
            value: json!({"kind":"number","value":1}),
        };
        let b = Fact {
            value: json!({"kind":"number","value":"1"}),
            ..a.clone()
        };
        let counts = tuple_counts(&[a.clone(), a.clone()], &[b, a]).unwrap();
        assert_eq!(
            (
                counts.true_positive,
                counts.false_positive,
                counts.false_negative
            ),
            (1, 1, 0)
        );
        assert!((counts.f1() - 2.0 / 3.0).abs() < 1e-12);
        assert!(tuple_counts(&[], &[]).unwrap().exact());
        assert_eq!(tuple_counts(&[], &[]).unwrap().f1(), 1.0);
    }

    #[test]
    fn assignments_reject_missing_unknown_duplicate_and_invalid_rows() {
        let rows = vec![row("a", "A", "true"), row("b", "B", "false")];
        let assignment = |id: &str, partition: &str| Assignment {
            split: "s".into(),
            partition: partition.into(),
            id: id.into(),
        };
        assert!(split_rows("s", &rows, &[assignment("a", "train")]).is_err());
        assert!(
            split_rows(
                "s",
                &rows,
                &[assignment("a", "train"), assignment("z", "test")]
            )
            .is_err()
        );
        assert!(
            split_rows(
                "s",
                &rows,
                &[assignment("a", "train"), assignment("a", "test")]
            )
            .is_err()
        );
        assert!(
            split_rows(
                "s",
                &rows,
                &[assignment("a", "train"), assignment("b", "dev")]
            )
            .is_err()
        );
        let (training, test) = split_rows(
            "s",
            &rows,
            &[assignment("b", "test"), assignment("a", "train")],
        )
        .unwrap();
        assert_eq!(training[0].id, "a");
        assert_eq!(test[0].id, "b");
    }

    #[test]
    fn changing_gold_cannot_change_predictions_or_reveal_a_unique_test_fact() {
        let lexicon = json!({"subjects":[
            {"name":"Hooly", "aliases":[], "attributes":["employees"]},
            {"name":"Secret Entity", "aliases":[], "attributes":["secret_phrase"]}
        ]});
        let mut known = row("train", "Hooly has 30 employees.", "true");
        known.form = vec![Fact {
            subject: "Hooly".into(),
            attribute: "employees".into(),
            value: json!({"kind":"number","value":30}),
        }];
        let mut gold = row("test", "Secret Entity uses ultramarine-862.", "true");
        let secret = Fact {
            subject: "Secret Entity".into(),
            attribute: "secret_phrase".into(),
            value: json!({"kind":"name","value":"ultramarine-862"}),
        };
        gold.form = vec![secret.clone()];
        let mut duplicate = gold.clone();
        duplicate.id = "train-duplicate".into();
        duplicate.text = gold.text.to_uppercase();
        let annotated = BTreeSet::from([gold.id.clone()]);
        let before = evaluate(
            "test",
            &[&known, &duplicate],
            &[&gold],
            &annotated,
            &lexicon,
            None,
        )
        .unwrap();
        gold.label = "false".into();
        gold.form.clear();
        let after = evaluate(
            "test",
            &[&known, &duplicate],
            &[&gold],
            &annotated,
            &lexicon,
            None,
        )
        .unwrap();
        assert_eq!(
            before["results"][0]["prediction"],
            after["results"][0]["prediction"]
        );
        assert_eq!(
            before["results"][0]["extraction"],
            after["results"][0]["extraction"]
        );
        assert_eq!(before["training_rows"], 1);
        assert_eq!(before["leakage_audit"]["excluded_normalized_test_text"], 1);
        let prediction: Prediction =
            serde_json::from_value(before["results"][0]["prediction"].clone()).unwrap();
        assert!(!prediction.facts.contains(&secret));
        assert!(prediction.evidence.iter().all(|e| e.row_id == known.id));
        assert!(prediction.known_label.is_none());
    }

    #[test]
    fn parser_sidecar_requires_complete_unique_selected_ids_and_ignores_gold_fields() {
        let selected = BTreeSet::from(["p-1".to_owned()]);
        let text = "{\"id\":\"synthetic\",\"prediction\":[]}\n{\"id\":\"p-1\",\"label\":\"true\",\"form\":[{\"secret\":1}],\"prediction\":[]}";
        let parsed = parse_predictions(text, &selected).unwrap();
        assert_eq!(parsed.len(), 1);
        assert!(parsed["p-1"].is_empty());
        assert!(parse_predictions("{\"id\":\"p-2\",\"prediction\":[]}", &selected).is_err());
        assert!(
            parse_predictions(
                "{\"id\":\"p-1\",\"prediction\":[]}\n{\"id\":\"p-1\",\"prediction\":[]}",
                &selected
            )
            .is_err()
        );
        assert!(parse_predictions("{\"id\":\"p-1\",\"form\":[]}", &selected).is_err());
    }
}
