//! Production-router regressions. Synthetic examples are hand-authored; practice
//! diagnostics are familiar gold-form folds, not an independent accuracy claim.
use serde_json::{Value, json};
use veridyct_core::{
    Engine, Evidence, ExtractionHints, Fact, InputRow, Prediction, Probabilities, kb_chain,
};

fn lexicon() -> Value {
    json!({"subjects":[{"name":"Audit Cloud","aliases":["Audit"],"attributes":["seats","price","uptime","owner"]}]})
}

fn fact(attribute: &str, value: Value) -> Fact {
    Fact {
        subject: "Audit Cloud".into(),
        attribute: attribute.into(),
        value,
    }
}

fn seats(n: u64) -> Fact {
    fact("seats", json!({"kind":"quantity","value":n,"unit":"seat"}))
}

fn row(id: &str, text: &str, date: &str, label: &str, form: Vec<Fact>) -> InputRow {
    InputRow {
        id: id.into(),
        text: text.into(),
        date: date.into(),
        label: label.into(),
        form,
    }
}

fn anchors() -> Vec<InputRow> {
    vec![
        row(
            "yes",
            "Audit Cloud has 10 seats.",
            "2026-01-10",
            "true",
            vec![seats(10)],
        ),
        row(
            "no",
            "Audit Cloud has 99 seats.",
            "2026-01-10",
            "false",
            vec![seats(99)],
        ),
    ]
}

fn predictions(rows: &[InputRow]) -> Vec<Prediction> {
    rows.iter()
        .map(|r| Prediction {
            id: r.id.clone(),
            text: r.text.clone(),
            date: r.date.clone(),
            known_label: (!r.label.is_empty()).then(|| r.label.clone()),
            label: if r.label.is_empty() {
                "true".into()
            } else {
                r.label.clone()
            },
            confidence: Some(0.8371),
            probabilities: Probabilities {
                p_true: 0.8371,
                p_false: 0.1029,
                p_unsure: 0.06,
            },
            facts: r.form.clone(),
            evidence: Vec::new(),
            reason: "engine sentinel".into(),
        })
        .collect()
}

fn route(rows: &[InputRow], p: &mut [Prediction], hints: &ExtractionHints) -> kb_chain::Routed {
    kb_chain::relabel(rows, p, &lexicon(), hints, true, &|_| false)
}

fn valid_scores(p: &Prediction) {
    let scores = [
        p.probabilities.p_true,
        p.probabilities.p_false,
        p.probabilities.p_unsure,
    ];
    assert!(
        scores
            .iter()
            .all(|v| v.is_finite() && (0.0..=1.0).contains(v)),
        "{p:?}"
    );
    assert!((scores.iter().sum::<f64>() - 1.0).abs() < 1e-12);
    assert_eq!(p.confidence.is_none(), p.label == "unsure");
}

#[test]
fn no_facts_cannot_become_true_even_with_a_known_owner_distractor() {
    let mut rows = anchors();
    rows.push(row(
        "query",
        "Zephyrvault uses Audit Cloud; its capacity is 7.",
        "2026-01-10",
        "",
        vec![],
    ));
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(p[2].label, "unsure");
    assert_eq!(p[2].confidence, None);
    valid_scores(&p[2]);
}

#[test]
fn foreign_owner_cannot_borrow_a_known_names_exact_evidence() {
    let mut rows = anchors();
    // Deliberately reproduce an upstream binder error. Mentioning the known
    // schema owner does not make it the owner of Zephyrvault's seat count.
    rows.push(row(
        "query",
        "Zephyrvault has 10 seats and uses Audit Cloud.",
        "2026-01-10",
        "",
        vec![seats(10)],
    ));
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(p[2].label, "unsure");
}

#[test]
fn explicit_unknown_and_incomplete_supported_subsets_abstain() {
    for unknown in [true, false] {
        let mut rows = anchors();
        rows.push(row(
            "query",
            "Audit Cloud seats = 10; its price is unknown.",
            "2026-01-10",
            "",
            vec![seats(10)],
        ));
        let mut hints = ExtractionHints::default();
        if unknown {
            hints.explicit_unknown.insert("query".into());
        } else {
            hints.incomplete.insert("query".into());
        }
        let mut p = predictions(&rows);
        route(&rows, &mut p, &hints);
        assert_eq!(p[2].label, "unsure");
        valid_scores(&p[2]);
    }
}

#[test]
fn exact_false_dominates_an_explicit_unknown_conjunct() {
    let mut rows = anchors();
    rows.push(row(
        "query",
        "Audit Cloud seats = 11; its price is unknown.",
        "2026-01-10",
        "",
        vec![seats(11)],
    ));
    let mut hints = ExtractionHints::default();
    hints.explicit_unknown.insert("query".into());
    hints.incomplete.insert("query".into());
    let mut p = predictions(&rows);
    p[2].label = "false".into();
    p[2].probabilities = Probabilities {
        p_true: 0.02,
        p_false: 0.94137,
        p_unsure: 0.03863,
    };
    p[2].confidence = Some(0.94137);
    let before = serde_json::to_string(&p[2]).unwrap();
    route(&rows, &mut p, &hints);
    assert_eq!(serde_json::to_string(&p[2]).unwrap(), before);
}

#[test]
fn exact_typed_proofs_preserve_the_whole_prediction_and_precision() {
    for n in [9_007_199_254_740_993, 9_007_199_254_740_994] {
        let mut rows = anchors();
        rows[0].form = vec![seats(9_007_199_254_740_993)];
        rows.push(row(
            "query",
            "Audit Cloud seats are recorded here.",
            "2026-01-10",
            "",
            vec![seats(n)],
        ));
        let mut p = predictions(&rows);
        p[2].label = if n == 9_007_199_254_740_993 {
            "true"
        } else {
            "false"
        }
        .into();
        p[2].confidence = Some(0.94137);
        p[2].probabilities = if p[2].label == "true" {
            Probabilities {
                p_true: 0.94137,
                p_false: 0.02,
                p_unsure: 0.03863,
            }
        } else {
            Probabilities {
                p_true: 0.02,
                p_false: 0.94137,
                p_unsure: 0.03863,
            }
        };
        p[2].evidence.push(Evidence {
            row_id: rows[0].id.clone(),
            text: rows[0].text.clone(),
            date: rows[0].date.clone(),
            label: rows[0].label.clone(),
            fact: rows[0].form[0].clone(),
        });
        let before = serde_json::to_string(&p[2]).unwrap();
        route(&rows, &mut p, &ExtractionHints::default());
        assert_eq!(serde_json::to_string(&p[2]).unwrap(), before);
        valid_scores(&p[2]);
    }
}

#[test]
fn conflicts_on_the_observation_date_cannot_be_outvoted() {
    let mut rows = anchors();
    rows.push(row(
        "conflict",
        "Audit Cloud seats = 20.",
        "2026-01-10",
        "true",
        vec![seats(20)],
    ));
    rows.push(row(
        "query",
        "Audit Cloud seats = 10.",
        "2026-01-10",
        "",
        vec![seats(10)],
    ));
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(p[3].label, "unsure");
    valid_scores(&p[3]);
}

#[test]
fn false_compound_does_not_make_each_atom_false_without_independent_premises() {
    let mut rows = vec![
        row(
            "yes",
            "Audit Cloud uptime is 99%.",
            "2026-01-10",
            "true",
            vec![fact("uptime", json!({"kind":"percent","value":99}))],
        ),
        row(
            "no",
            "Audit Cloud has 10 seats and its price is 5.",
            "2026-01-10",
            "false",
            vec![
                seats(10),
                fact(
                    "price",
                    json!({"kind":"money","value":5,"currency":"EUR","per":"month"}),
                ),
            ],
        ),
        row(
            "query",
            "Audit Cloud seats = 10.",
            "2026-01-10",
            "",
            vec![seats(10)],
        ),
    ];
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(p[2].label, "unsure");
    rows.insert(
        2,
        row(
            "independent",
            "Audit Cloud costs 5 per month.",
            "2026-01-10",
            "true",
            vec![fact(
                "price",
                json!({"kind":"money","value":5,"currency":"EUR","per":"month"}),
            )],
        ),
    );
    let mut p = predictions(&rows);
    p[3].label = "false".into();
    let before = serde_json::to_string(&p[3]).unwrap();
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(serde_json::to_string(&p[3]).unwrap(), before);
}

#[test]
fn observation_dates_are_statistical_context_and_explicit_validity_is_respected() {
    for date in ["2026-01-09", "2026-01-11"] {
        let mut rows = anchors();
        rows.push(row(
            "query",
            "Audit Cloud seats = 10.",
            date,
            "",
            vec![seats(10)],
        ));
        let mut p = predictions(&rows);
        route(&rows, &mut p, &ExtractionHints::default());
        valid_scores(&p[2]);
        assert!(
            p[2].reason.contains("Statistical") || p[2].label == "unsure",
            "{:?}",
            p[2]
        );
        assert!(
            p[2].evidence.is_empty(),
            "no future/past observation is fabricated as an exact proof"
        );
        assert_ne!(p[2].confidence, Some(1.0));
    }
    let mut rows = anchors();
    rows[0].text =
        "From January 1, 2026 through January 10, 2026, Audit Cloud has 10 seats.".into();
    rows[1].text =
        "From January 1, 2026 through January 10, 2026, Audit Cloud has 99 seats.".into();
    rows.push(row(
        "query",
        "Audit Cloud seats = 10.",
        "2026-01-11",
        "",
        vec![seats(10)],
    ));
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(
        p[2].label, "unsure",
        "a closed explicit validity interval is not extrapolated"
    );
}

#[test]
fn missing_key_and_repeated_unlabelled_votes_cannot_create_evidence() {
    let mut rows = anchors();
    for i in 0..40 {
        rows.push(row(
            &format!("query-{i}"),
            "Audit Cloud owner is Zephyrvault.",
            if i % 2 == 0 {
                "2026-01-10"
            } else {
                "2026-01-11"
            },
            "",
            vec![fact("owner", json!({"kind":"name","value":"Zephyrvault"}))],
        ));
    }
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert!(
        p[2..]
            .iter()
            .all(|p| p.label == "unsure" && p.confidence.is_none())
    );
}

#[test]
fn copied_source_text_under_other_ids_and_unicode_spacing_does_not_self_support() {
    let mut rows = anchors();
    rows.push(row(
        "query",
        "Ａｕｄｉｔ Cloud   has 10 seats.",
        "2026-01-11",
        "",
        vec![seats(10)],
    ));
    let mut p = predictions(&rows);
    route(&rows, &mut p, &ExtractionHints::default());
    assert_eq!(p[2].label, "unsure");
}

#[test]
fn logical_programs_keep_the_engine_even_when_the_fact_bag_is_empty() {
    use veridyct_core::claim_program::{ClaimExpr, ClaimProgram};
    let mut rows = anchors();
    rows.push(row(
        "query",
        "Audit Cloud has 10 seats or it has 99 seats.",
        "2026-01-10",
        "",
        vec![],
    ));
    let mut hints = ExtractionHints::default();
    hints.programs.insert(
        "query".into(),
        ClaimProgram {
            expression: ClaimExpr::Any(vec![
                ClaimExpr::Atom(seats(10)),
                ClaimExpr::Atom(seats(99)),
            ]),
            complete: true,
            notes: vec![],
            structured: true,
        },
    );
    let mut p = predictions(&rows);
    let before = serde_json::to_string(&p[2]).unwrap();
    route(&rows, &mut p, &hints);
    assert_eq!(serde_json::to_string(&p[2]).unwrap(), before);
}

#[test]
#[ignore = "diagnostic: emits familiar-practice metrics, no score threshold"]
fn practice_page_folds_report_route_metrics() {
    let lexicon: Value = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
    let mut practice = veridyct_core::read_csv(include_str!("../../../data/practice.csv")).unwrap();
    practice.sort_by_key(|r| r.id[2..].parse::<i64>().unwrap());
    let mut masks = Vec::new();
    for line in include_str!("data/kb-chain-practice.txt").lines() {
        let p: Vec<_> = line.split(' ').collect();
        if p[0] == "fold" && p[1] == "P80" {
            masks.push((
                format!("{}-{}", p[1], p[2]),
                p[3].bytes().map(|b| b == b'1').collect::<Vec<_>>(),
            ));
        }
    }
    let dates: Vec<_> = practice
        .iter()
        .map(|r| kb_chain::date_ordinal(&r.date).unwrap())
        .collect();
    let ids: Vec<_> = practice
        .iter()
        .map(|r| r.id[2..].parse().unwrap())
        .collect();
    let pages = kb_chain::pages_of(&dates, &vec![true; practice.len()], Some(&ids));
    for (name, mask) in masks {
        let visible: Vec<_> = practice
            .iter()
            .enumerate()
            .filter(|(i, _)| mask[pages[*i]])
            .map(|(_, r)| r.clone())
            .collect();
        let mut rows = practice.clone();
        for (i, row) in rows.iter_mut().enumerate() {
            if !mask[pages[i]] {
                row.label.clear();
            }
        }
        let engine = Engine::new(&visible, &lexicon).unwrap();
        let mut predictions = engine.predict_universe(&rows);
        report(&name, "engine", &practice, &rows, &predictions);
        let routed = kb_chain::relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &ExtractionHints::default(),
            true,
            &|_| false,
        );
        eprintln!("{name}: {routed}");
        report(&name, "router", &practice, &rows, &predictions);
    }
}

fn report(
    name: &str,
    policy: &str,
    gold: &[InputRow],
    rows: &[InputRow],
    predictions: &[Prediction],
) {
    let (mut total, mut correct, mut decided, mut points) = (0usize, 0usize, 0usize, 0i64);
    let (mut counts, mut hits, mut brier) = ([0usize; 3], [0usize; 3], 0.0);
    for ((gold, row), p) in gold.iter().zip(rows).zip(predictions) {
        if !row.label.is_empty() {
            continue;
        }
        let k = ["true", "false", "unsure"]
            .iter()
            .position(|l| *l == gold.label)
            .unwrap();
        counts[k] += 1;
        total += 1;
        if p.label == gold.label {
            correct += 1;
            hits[k] += 1;
            points += 1;
        } else if p.label != "unsure" {
            points -= 1;
        }
        decided += usize::from(p.label != "unsure");
        for (i, score) in [
            p.probabilities.p_true,
            p.probabilities.p_false,
            p.probabilities.p_unsure,
        ]
        .into_iter()
        .enumerate()
        {
            brier += (score - f64::from(i == k)).powi(2);
        }
    }
    eprintln!(
        "{}",
        json!({"fold":name,"policy":policy,"n":total,"accuracy":correct as f64/total as f64,"arena":points as f64/total as f64,"coverage":decided as f64/total as f64,"class_counts":counts,"class_hits":hits,"recall":std::array::from_fn::<_,3,_>(|i| hits[i] as f64 / counts[i].max(1) as f64),"brier3":brier/total as f64})
    );
}
