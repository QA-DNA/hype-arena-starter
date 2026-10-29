//! Parity of the Rust F2 chain with the Python reference (labs/kb-campaign/F2/export_rust_fixture.py).
//! Practice folds are committed; the Sdev-jt world is local suite data, read from
//! VERIDYCT_KB_CHAIN_SDEV when set.
use serde_json::Value;
use veridyct_core::kb_chain::{self, ChainRow, KbLexicon, Label};

const FIXTURE: &str = include_str!("data/kb-chain-practice.txt");

/// Expected prediction: row index, label initial, confidence.
type Expected = (usize, char, Option<f64>);

fn code(l: Label) -> char {
    l.as_str().chars().next().unwrap()
}

fn conf_of(bits: &str) -> Option<f64> {
    (bits != "-").then(|| f64::from_bits(u64::from_str_radix(bits, 16).unwrap()))
}

/// (label mismatches, compared rows, max |confidence difference|)
fn compare(out: &[kb_chain::ChainOutput], expected: &[Expected]) -> (usize, usize, f64) {
    let mut bad = 0;
    let mut diff: f64 = 0.0;
    for &(i, l, c) in expected {
        let o = &out[i];
        if code(o.label) != l {
            bad += 1;
            eprintln!(
                "row {i}: rust {:?} {:?}, python {l} {c:?}",
                o.label, o.confidence
            );
            continue;
        }
        match (o.confidence, c) {
            (Some(a), Some(b)) => diff = diff.max((a - b).abs()),
            (None, None) => {}
            _ => bad += 1,
        }
    }
    (bad, expected.len(), diff)
}

fn points(pred: Label, gold: &str) -> f64 {
    match (pred.as_str() == gold, pred) {
        (true, _) => 1.0,
        (false, Label::Unsure) => 0.0,
        _ => -1.0,
    }
}

#[test]
fn practice_folds_match_python() {
    let lexicon: Value = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
    let lex = KbLexicon::new(&lexicon);
    let mut practice = veridyct_core::read_csv(include_str!("../../../data/practice.csv")).unwrap();
    practice.sort_by_key(|r| r.id[2..].parse::<i64>().unwrap());
    let dates: Vec<i64> = practice
        .iter()
        .map(|r| kb_chain::date_ordinal(&r.date).unwrap())
        .collect();
    let ids: Vec<i64> = practice
        .iter()
        .map(|r| r.id[2..].parse().unwrap())
        .collect();
    let page = kb_chain::pages_of(&dates, &vec![true; dates.len()], Some(&ids));
    let facts: Vec<_> = practice.iter().map(|r| lex.model_facts(&r.form)).collect();

    let mut folds: Vec<(String, Vec<bool>, Vec<Expected>)> = Vec::new();
    // VERIDYCT_KB_CHAIN_PRACTICE: an alternative local fixture in the same format (e.g. every P10 seed).
    let fixture = std::env::var("VERIDYCT_KB_CHAIN_PRACTICE").map_or_else(
        |_| FIXTURE.to_owned(),
        |p| std::fs::read_to_string(p).unwrap(),
    );
    for line in fixture.lines() {
        let p: Vec<&str> = line.split(' ').collect();
        match p[0] {
            "fold" => folds.push((
                format!("{}-{}", p[1], p[2]),
                p[3].bytes().map(|b| b == b'1').collect(),
                Vec::new(),
            )),
            "pred" => folds.last_mut().unwrap().2.push((
                p[1].parse().unwrap(),
                p[2].chars().next().unwrap(),
                conf_of(p[3]),
            )),
            _ => {}
        }
    }
    let (mut p80, mut n80, mut p10) = (0.0, 0usize, Vec::new());
    let (mut bad_all, mut n_all, mut diff_all) = (0, 0, 0.0f64);
    let mut max_states = 0;
    let mut sums = (0, 0);
    for (name, mask, expected) in &folds {
        let rows: Vec<ChainRow> = (0..practice.len())
            .map(|i| ChainRow {
                date: dates[i],
                page: page[i],
                label: mask[page[i]].then(|| Label::parse(&practice[i].label).unwrap()),
                facts: facts[i].clone(),
            })
            .collect();
        let run = kb_chain::run(&rows, None).expect("two-class fold");
        max_states = max_states.max(run.max_states);
        sums = (sums.0.max(run.cells), sums.1.max(run.steps));
        assert!(run.rows.iter().all(|o| !o.over_budget));
        let out = run.rows;
        let scored: Vec<usize> = (0..rows.len()).filter(|&i| !mask[page[i]]).collect();
        let pts: f64 = scored
            .iter()
            .map(|&i| points(out[i].label, &practice[i].label))
            .sum();
        if name.starts_with("P80") {
            p80 += pts;
            n80 += scored.len();
        } else {
            p10.push(pts / scored.len() as f64);
        }
        if !expected.is_empty() {
            let (bad, n, diff) = compare(&out, expected);
            eprintln!(
                "{name}: labels identical {}/{n}, max confidence diff {diff:e}",
                n - bad
            );
            bad_all += bad;
            n_all += n;
            diff_all = diff_all.max(diff);
        }
    }
    let p10_mean = p10.iter().sum::<f64>() / p10.len() as f64;
    eprintln!(
        "practice folds: max key states {max_states} (budget {}), max cells {} steps {}",
        kb_chain::MAX_KEY_STATES,
        sums.0,
        sums.1
    );
    eprintln!(
        "P80 pooled points {:.4}; P10 mean points {:.4} over {} seeds; parity {}/{} labels, max diff {diff_all:e}",
        p80 / n80 as f64,
        p10_mean,
        p10.len(),
        n_all - bad_all,
        n_all
    );
    assert_eq!(bad_all, 0);
    assert!(diff_all <= 1e-9);
}

#[test]
fn sdev_world_matches_python_when_available() {
    let Some(path) = std::env::var_os("VERIDYCT_KB_CHAIN_SDEV") else {
        eprintln!("VERIDYCT_KB_CHAIN_SDEV not set: skipped (local suite data)");
        return;
    };
    let text = std::fs::read_to_string(path).unwrap();
    let mut lines = text.lines();
    let head: Value = serde_json::from_str(lines.next().unwrap()).unwrap();
    let lex = KbLexicon::new(&head["lexicon"]);
    let mut rows = Vec::new();
    let mut expected = Vec::new();
    for (i, line) in lines.enumerate() {
        let r: Value = serde_json::from_str(line).unwrap();
        rows.push(ChainRow {
            date: r["date"].as_i64().unwrap(),
            page: r["page"].as_u64().unwrap() as usize,
            label: r["label"].as_str().and_then(Label::parse),
            facts: lex.facts(&r["assertions"]),
        });
        if r["label"].is_null() {
            expected.push((
                i,
                r["pred"].as_str().unwrap().chars().next().unwrap(),
                conf_of(r["conf"].as_str().unwrap()),
            ));
        }
    }
    let started = std::time::Instant::now();
    let run = kb_chain::run(&rows, None).unwrap();
    assert!(run.rows.iter().all(|o| !o.over_budget));
    let (bad, n, diff) = compare(&run.rows, &expected);
    eprintln!(
        "Sdev-jt: {} rows in {:.3}s; labels identical {}/{n}, max confidence diff {diff:e}, max key states {}, cells {}, steps {}",
        rows.len(),
        started.elapsed().as_secs_f64(),
        n - bad,
        run.max_states,
        run.cells,
        run.steps
    );
    assert_eq!(bad, 0);
    assert!(diff <= 1e-9);
}

/// Practice in id order with practice pages (every row labelled, consecutive ids), gold forms.
fn practice_world() -> (Vec<veridyct_core::InputRow>, KbLexicon, Vec<ChainRow>) {
    let lexicon: Value = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
    let lex = KbLexicon::new(&lexicon);
    let practice = veridyct_core::read_csv(include_str!("../../../data/practice.csv")).unwrap();
    let rows = kb_chain::practice_rows(&practice, &lex);
    let mut sorted = practice;
    sorted.sort_by_key(|r| r.id[2..].parse::<i64>().unwrap());
    (sorted, lex, rows)
}

/// T2 SPEC-G1 check (lab: T2/spec_dump.py): 390 practice rows scored with neural extractor
/// forms, the other 1,507 labelled with gold forms; G1 label and scaled confidence to 4 decimals.
#[test]
fn guarded_labeller_matches_spec_g1() {
    let (practice, lex, mut rows) = practice_world();
    let index: std::collections::HashMap<&str, usize> = practice
        .iter()
        .enumerate()
        .map(|(i, r)| (r.id.as_str(), i))
        .collect();
    let mut checks = Vec::new();
    for line in include_str!("data/kb-chain-g1-p390.jsonl").lines().skip(1) {
        let r: Value = serde_json::from_str(line).unwrap();
        let i = index[r["id"].as_str().unwrap()];
        rows[i].label = None;
        rows[i].facts = lex.facts(&r["form"]);
        checks.push((i, r));
    }
    let out = kb_chain::guarded(&rows, None).unwrap();
    let mut bad = 0;
    for (i, r) in &checks {
        let (label, conf) = out[*i].expect("practice keys are within the budget");
        let want = r["g1_conf_rel"].as_f64();
        let close = match (conf, want) {
            (Some(a), Some(b)) => (a - b).abs() <= 5.001e-5,
            (None, None) => true,
            _ => false,
        };
        if label.as_str() != r["g1_label"].as_str().unwrap() || !close {
            bad += 1;
            eprintln!(
                "{}: rust {label:?} {conf:?}, spec {} {want:?}",
                r["id"], r["g1_label"]
            );
        }
    }
    eprintln!(
        "SPEC-G1 P390: {}/{} rows match",
        checks.len() - bad,
        checks.len()
    );
    assert_eq!(bad, 0);
}

/// A one-class labelled world is labelled by the practice fit, as `Std.fit` falls back.
#[test]
fn one_class_world_uses_the_practice_fit() {
    let (practice, _, rows) = practice_world();
    let mut world = rows.clone();
    for (row, input) in world.iter_mut().zip(&practice) {
        if input.label != "true" {
            row.label = None;
        }
    }
    assert!(kb_chain::run(&world, None).is_none());
    let trues = practice.iter().filter(|r| r.label == "true").count();
    let run = kb_chain::run(&world, Some(&rows)).unwrap();
    assert!((run.rate - trues as f64 / practice.len() as f64).abs() < 1e-12);
    assert!(
        run.rows
            .iter()
            .all(|o| o.confidence.is_none_or(|c| (0.5..=1.0).contains(&c)))
    );
}
