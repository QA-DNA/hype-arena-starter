//! Parity of the Rust F2 chain with the Python reference (labs/kb-campaign/F2/export_rust_fixture.py).
//! Practice folds are committed; the Sdev-jt world is local suite data, read from
//! VERIDYCT_KB_CHAIN_SDEV when set.
use serde_json::Value;
use veridyct_core::kb_chain::{self, ChainRow, KbLexicon, Label};

const FIXTURE: &str = include_str!("data/kb-chain-practice.txt");

fn code(l: Label) -> char {
    l.as_str().chars().next().unwrap()
}

fn conf_of(bits: &str) -> Option<f64> {
    (bits != "-").then(|| f64::from_bits(u64::from_str_radix(bits, 16).unwrap()))
}

/// (label mismatches, compared rows, max |confidence difference|)
fn compare(out: &[kb_chain::ChainOutput], expected: &[(usize, char, Option<f64>)]) -> (usize, usize, f64) {
    let mut bad = 0;
    let mut diff: f64 = 0.0;
    for &(i, l, c) in expected {
        let o = &out[i];
        if code(o.label) != l {
            bad += 1;
            eprintln!("row {i}: rust {:?} {:?}, python {l} {c:?}", o.label, o.confidence);
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
    let dates: Vec<i64> = practice.iter().map(|r| kb_chain::date_ordinal(&r.date).unwrap()).collect();
    let ids: Vec<i64> = practice.iter().map(|r| r.id[2..].parse().unwrap()).collect();
    let page = kb_chain::pages_of(&dates, &vec![true; dates.len()], Some(&ids));
    let facts: Vec<_> = practice.iter().map(|r| lex.model_facts(&r.form)).collect();

    let mut folds: Vec<(String, Vec<bool>, Vec<(usize, char, Option<f64>)>)> = Vec::new();
    for line in FIXTURE.lines() {
        let p: Vec<&str> = line.split(' ').collect();
        match p[0] {
            "fold" => folds.push((format!("{}-{}", p[1], p[2]), p[3].bytes().map(|b| b == b'1').collect(), Vec::new())),
            "pred" => folds.last_mut().unwrap().2.push((p[1].parse().unwrap(), p[2].chars().next().unwrap(), conf_of(p[3]))),
            _ => {}
        }
    }
    let (mut p80, mut n80, mut p10) = (0.0, 0usize, Vec::new());
    let (mut bad_all, mut n_all, mut diff_all) = (0, 0, 0.0f64);
    for (name, mask, expected) in &folds {
        let rows: Vec<ChainRow> = (0..practice.len())
            .map(|i| ChainRow {
                date: dates[i],
                page: page[i],
                label: mask[page[i]].then(|| Label::parse(&practice[i].label).unwrap()),
                facts: facts[i].clone(),
            })
            .collect();
        let out = kb_chain::run(&rows).expect("two-class fold");
        let scored: Vec<usize> = (0..rows.len()).filter(|&i| !mask[page[i]]).collect();
        let pts: f64 = scored.iter().map(|&i| points(out[i].label, &practice[i].label)).sum();
        if name.starts_with("P80") {
            p80 += pts;
            n80 += scored.len();
        } else {
            p10.push(pts / scored.len() as f64);
        }
        if !expected.is_empty() {
            let (bad, n, diff) = compare(&out, expected);
            eprintln!("{name}: labels identical {}/{n}, max confidence diff {diff:e}", n - bad);
            bad_all += bad;
            n_all += n;
            diff_all = diff_all.max(diff);
        }
    }
    let p10_mean = p10.iter().sum::<f64>() / p10.len() as f64;
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
            expected.push((i, r["pred"].as_str().unwrap().chars().next().unwrap(), conf_of(r["conf"].as_str().unwrap())));
        }
    }
    let started = std::time::Instant::now();
    let out = kb_chain::run(&rows).unwrap();
    let (bad, n, diff) = compare(&out, &expected);
    eprintln!(
        "Sdev-jt: {} rows in {:.3}s; labels identical {}/{n}, max confidence diff {diff:e}",
        rows.len(),
        started.elapsed().as_secs_f64(),
        n - bad
    );
    assert_eq!(bad, 0);
    assert!(diff <= 1e-9);
}
