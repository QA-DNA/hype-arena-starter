use serde_json::json;
use veridyct_belief_tools::belief::{
    Belief, BeliefBounds, BeliefError, Composition, LeafAssessment, ProbabilityRange, compose,
};
use veridyct_core::{
    Fact, InputRow, Probabilities,
    claim_program::{
        CharSpan, ClaimExpr, ComparisonOp, MAX_PROGRAM_DEPTH, MAX_PROGRAM_NODES, SlotReference,
        TruthValue,
    },
    knowledge::{KnowledgeGraph, Resolution, Status, compare_recorded_values},
};

fn atom(attribute: &str, number: i64) -> ClaimExpr {
    ClaimExpr::Atom(Fact {
        subject: "Hooly".into(),
        attribute: attribute.into(),
        value: json!({"kind":"quantity", "op":"eq", "value":number, "unit":"people"}),
    })
}

fn unknown() -> ClaimExpr {
    ClaimExpr::Unknown {
        span: CharSpan::default(),
        reason: "missing clause".into(),
    }
}

fn unsupported() -> ClaimExpr {
    ClaimExpr::Unsupported {
        span: CharSpan::default(),
        reason: "unsupported quantifier".into(),
    }
}

fn result(expression: &ClaimExpr, values: &[(&str, TruthValue, Option<Belief>)]) -> Composition {
    compose(
        expression,
        &mut |f| {
            let (_, hard, estimate) = values
                .iter()
                .find(|(name, _, _)| *name == f.attribute)
                .unwrap();
            LeafAssessment {
                hard: *hard,
                estimate: *estimate,
                evidence_ids: vec![format!("row-{}", f.attribute)],
            }
        },
        &mut |_, _, _| LeafAssessment::unresolved(),
    )
}

fn near(left: f64, right: f64) {
    assert!((left - right).abs() < 2e-12, "{left} != {right}");
}

fn range(value: ProbabilityRange, lower: f64, upper: f64) {
    near(value.lower(), lower);
    near(value.upper(), upper);
}

fn contains(bounds: BeliefBounds, belief: Belief) {
    for (r, p) in [
        (bounds.true_mass(), belief.p_true()),
        (bounds.false_mass(), belief.p_false()),
        (bounds.unsure_mass(), belief.p_unsure()),
    ] {
        assert!(
            p >= r.lower() - 2e-12 && p <= r.upper() + 2e-12,
            "{p} outside {r:?}"
        );
    }
}

fn valid_mass(value: Belief) {
    let parts = [value.p_true(), value.p_false(), value.p_unsure()];
    assert!(
        parts
            .iter()
            .all(|p| p.is_finite() && (0.0..=1.0).contains(p))
    );
    near(parts.iter().sum(), 1.0);
}

fn valid_bounds(bounds: BeliefBounds) {
    let ranges = [
        bounds.true_mass(),
        bounds.false_mass(),
        bounds.unsure_mass(),
    ];
    for r in ranges {
        assert!(r.lower().is_finite() && r.upper().is_finite());
        assert!(0.0 <= r.lower() && r.lower() <= r.upper() && r.upper() <= 1.0);
    }
    assert!(ranges.iter().map(|r| r.lower()).sum::<f64>() <= 1.0 + 2e-12);
    assert!(ranges.iter().map(|r| r.upper()).sum::<f64>() >= 1.0 - 2e-12);
    valid_mass(bounds.uncommitted_mass());
}

#[test]
fn validated_masses_reject_invalid_inputs_instead_of_normalizing_scores() {
    let cases = [
        ([f64::NAN, 0.0, 1.0], BeliefError::NonFinite),
        ([0.0, f64::INFINITY, 0.0], BeliefError::NonFinite),
        ([0.0, 0.0, f64::NEG_INFINITY], BeliefError::NonFinite),
        ([-0.01, 0.0, 1.0], BeliefError::OutOfRange),
        ([1.01, 0.0, 0.0], BeliefError::OutOfRange),
        ([0.0, 0.0, 0.0], BeliefError::NotUnitSum),
        ([0.3, 0.3, 0.3], BeliefError::NotUnitSum),
        ([0.6, 0.6, 0.0], BeliefError::NotUnitSum),
        ([0.5, 0.5, 1e-10], BeliefError::NotUnitSum),
    ];
    for ([t, f, u], error) in cases {
        assert_eq!(Belief::try_new(t, f, u), Err(error));
    }
    for [t, f, u] in [
        [0.1, 0.2, 0.7],
        [0.99, 0.0, 0.01],
        [0.1, 0.9, f64::EPSILON],
        [1.0, f64::EPSILON, 0.0],
    ] {
        valid_mass(Belief::try_new(t, f, u).unwrap());
    }
    assert!(Belief::try_from(&Probabilities::default()).is_err());
    let original = Belief::try_new(0.17, 0.08, 0.75).unwrap();
    let legacy: Probabilities = original.into();
    assert_eq!(Belief::try_from(&legacy).unwrap(), original);
}

#[test]
fn complete_kleene_truth_tables_and_all_three_negations() {
    use TruthValue::{False as F, True as T, Unknown as U};
    let rows = [
        (T, T, T, T),
        (T, F, F, T),
        (T, U, U, T),
        (F, T, F, T),
        (F, F, F, F),
        (F, U, F, U),
        (U, T, U, T),
        (U, F, F, U),
        (U, U, U, U),
    ];
    let mass = |v| match v {
        T => Belief::TRUE,
        F => Belief::FALSE,
        U => Belief::UNKNOWN,
    };
    for (a, b, and, or) in rows {
        let values = [("a", a, Some(mass(a))), ("b", b, Some(mass(b)))];
        for (expression, expected) in [
            (ClaimExpr::All(vec![atom("a", 1), atom("b", 2)]), and),
            (ClaimExpr::Any(vec![atom("a", 1), atom("b", 2)]), or),
        ] {
            let output = result(&expression, &values);
            assert_eq!(output.hard, expected, "{expression:?}");
            contains(output.soft, mass(expected));
            assert_eq!(output.soft, BeliefBounds::point(mass(expected)));
        }
    }
    for (value, expected) in [(T, F), (F, T), (U, U)] {
        let expression = ClaimExpr::Not(Box::new(atom("a", 1)));
        let output = result(&expression, &[("a", value, Some(mass(value)))]);
        assert_eq!(output.hard, expected);
        assert_eq!(output.soft, BeliefBounds::point(mass(expected)));
    }
}

#[test]
fn false_and_unknown_true_or_unknown_and_empty_unsupported_branches() {
    use TruthValue::{False as F, True as T, Unknown as U};
    for branch in [
        unknown(),
        unsupported(),
        ClaimExpr::All(vec![]),
        ClaimExpr::Any(vec![]),
    ] {
        let standalone = result(&branch, &[]);
        assert_eq!(standalone.hard, U);
        assert_eq!(standalone.soft, BeliefBounds::point(Belief::UNKNOWN));
        let a = result(
            &ClaimExpr::All(vec![branch.clone(), atom("f", 0)]),
            &[("f", F, Some(Belief::FALSE))],
        );
        let b = result(
            &ClaimExpr::Any(vec![branch.clone(), atom("t", 1)]),
            &[("t", T, Some(Belief::TRUE))],
        );
        assert_eq!(a.hard, F);
        assert_eq!(a.soft, BeliefBounds::point(Belief::FALSE));
        assert_eq!(b.hard, T);
        assert_eq!(b.soft, BeliefBounds::point(Belief::TRUE));
        let c = result(&ClaimExpr::Not(Box::new(branch)), &[]);
        assert_eq!(c.hard, U);
        assert_eq!(c.soft, BeliefBounds::point(Belief::UNKNOWN));
    }
}

#[test]
fn soft_bounds_do_not_assume_independence_or_promote_estimates_to_proof() {
    let a = Belief::try_new(0.8, 0.1, 0.1).unwrap();
    let b = Belief::try_new(0.7, 0.2, 0.1).unwrap();
    let values = [
        ("a", TruthValue::Unknown, Some(a)),
        ("b", TruthValue::Unknown, Some(b)),
    ];
    let and = result(&ClaimExpr::All(vec![atom("a", 1), atom("b", 2)]), &values);
    assert_eq!(and.hard, TruthValue::Unknown);
    range(and.soft.true_mass(), 0.5, 0.7);
    range(and.soft.false_mass(), 0.2, 0.3);
    range(and.soft.unsure_mass(), 0.0, 0.3);
    let mass = and.soft.uncommitted_mass();
    near(mass.p_true(), 0.5);
    near(mass.p_false(), 0.2);
    near(mass.p_unsure(), 0.3);
    let or = result(&ClaimExpr::Any(vec![atom("a", 1), atom("b", 2)]), &values);
    range(or.soft.true_mass(), 0.8, 1.0);
    range(or.soft.false_mass(), 0.0, 0.1);
    range(or.soft.unsure_mass(), 0.0, 0.2);
    let negation = result(&ClaimExpr::Not(Box::new(atom("a", 1))), &values);
    assert_eq!(negation.soft, BeliefBounds::point(a.negated()));
    near(a.negated().p_unsure(), a.p_unsure());
    let hard_true = result(
        &atom("a", 1),
        &[("a", TruthValue::True, Some(Belief::FALSE))],
    );
    assert_eq!(hard_true.hard, TruthValue::True);
    assert_eq!(hard_true.soft, BeliefBounds::point(Belief::FALSE));
}

#[test]
fn duplicate_invariance_includes_nested_reordered_groups_and_single_callback() {
    let a = atom("a", 1);
    let b = atom("b", 2);
    let values = [
        (
            "a",
            TruthValue::Unknown,
            Some(Belief::try_new(0.8, 0.1, 0.1).unwrap()),
        ),
        (
            "b",
            TruthValue::Unknown,
            Some(Belief::try_new(0.6, 0.3, 0.1).unwrap()),
        ),
    ];
    for all in [true, false] {
        let group = |items| {
            if all {
                ClaimExpr::All(items)
            } else {
                ClaimExpr::Any(items)
            }
        };
        let baseline = result(&group(vec![a.clone(), b.clone()]), &values);
        let repeated = result(
            &group(vec![
                a.clone(),
                group(vec![b.clone(), a.clone()]),
                b.clone(),
            ]),
            &values,
        );
        assert_eq!(repeated.hard, baseline.hard);
        assert_eq!(repeated.soft, baseline.soft);
        assert_eq!(repeated.evidence_ids, baseline.evidence_ids);
        assert_eq!(repeated.diagnostics.unique_leaves, 2);
        assert_eq!(repeated.diagnostics.duplicate_leaves, 2);
        let inside = if all {
            ClaimExpr::Any(vec![a.clone(), b.clone()])
        } else {
            ClaimExpr::All(vec![a.clone(), b.clone()])
        };
        let reordered = if all {
            ClaimExpr::Any(vec![b.clone(), a.clone()])
        } else {
            ClaimExpr::All(vec![b.clone(), a.clone()])
        };
        assert_eq!(
            result(&group(vec![inside.clone(), reordered]), &values).soft,
            result(&inside, &values).soft
        );
    }
    let mut calls = 0;
    let output = compose(
        &ClaimExpr::All(vec![a.clone(); 100]),
        &mut |_| {
            calls += 1;
            LeafAssessment {
                hard: TruthValue::Unknown,
                estimate: values[0].2,
                evidence_ids: vec!["row-1".into(); 2],
            }
        },
        &mut |_, _, _| unreachable!(),
    );
    assert_eq!(calls, 1);
    assert_eq!(output.soft, BeliefBounds::point(values[0].2.unwrap()));
    assert_eq!(output.evidence_ids, ["row-1"]);
    assert_eq!(output.diagnostics.shared_evidence_ids, 0);
}

#[test]
fn same_slot_and_shared_source_constraints_keep_dependence_bounds() {
    let mut lower = atom("team_size", 10);
    let mut upper = atom("team_size", 20);
    if let ClaimExpr::Atom(f) = &mut lower {
        f.value["op"] = json!("gt");
    }
    if let ClaimExpr::Atom(f) = &mut upper {
        f.value["op"] = json!("lt");
    }
    let expression = ClaimExpr::All(vec![lower, upper]);
    let estimate = Belief::try_new(0.8, 0.1, 0.1).unwrap();
    let output = compose(
        &expression,
        &mut |_| LeafAssessment {
            hard: TruthValue::Unknown,
            estimate: Some(estimate),
            evidence_ids: vec!["same-source".into()],
        },
        &mut |_, _, _| unreachable!(),
    );
    assert_eq!(output.diagnostics.unique_leaves, 2);
    assert_eq!(output.diagnostics.shared_slot_leaves, 2);
    assert_eq!(output.diagnostics.shared_evidence_ids, 1);
    assert_eq!(output.evidence_ids, ["same-source"]);
    range(output.soft.true_mass(), 0.6, 0.8);
    range(output.soft.false_mass(), 0.1, 0.2);
    assert!(output.soft.true_mass().lower() < output.soft.true_mass().upper());
    // These overlapping predicates share a latent value and evidence source;
    // marginal estimates cannot provide an exact-evidence proof of either.
    assert_eq!(output.hard, TruthValue::Unknown);
}

#[test]
fn absence_of_proof_and_missing_posterior_are_not_categorical_unsure() {
    let unresolved = compose(
        &atom("a", 1),
        &mut |_| LeafAssessment::unresolved(),
        &mut |_, _, _| unreachable!(),
    );
    assert_eq!(unresolved.hard, TruthValue::Unknown);
    assert_eq!(unresolved.soft, BeliefBounds::VACUOUS);
    assert_eq!(unresolved.soft.uncommitted_mass(), Belief::UNKNOWN);
    assert_eq!(unresolved.diagnostics.missing_estimates, 1);
    let categorical = compose(
        &atom("a", 1),
        &mut |_| LeafAssessment::categorical_unknown(),
        &mut |_, _, _| unreachable!(),
    );
    assert_eq!(categorical.hard, TruthValue::Unknown);
    assert_eq!(categorical.soft, BeliefBounds::point(Belief::UNKNOWN));
    assert_eq!(categorical.diagnostics.missing_estimates, 0);
    // A scalar P(true | decided) is insufficient: this API requires all masses.
    let chain_like = Probabilities {
        p_true: 0.9,
        p_false: 0.0,
        p_unsure: 0.0,
    };
    assert!(Belief::try_from(&chain_like).is_err());
}

#[test]
fn exact_resolution_adapter_never_turns_conflict_into_true_or_false() {
    for (status, expected) in [
        (Status::Supported, TruthValue::True),
        (Status::Contradicted, TruthValue::False),
        (Status::Unknown, TruthValue::Unknown),
        (Status::Conflict, TruthValue::Unknown),
    ] {
        let assessment = LeafAssessment::from_resolution(&Resolution {
            status,
            evidence: vec![],
        });
        assert_eq!(assessment.hard, expected);
        assert_eq!(assessment.estimate, None);
    }
}

#[test]
fn comparisons_delegate_exact_money_units_and_partial_dates() {
    let slot = |subject: &str| SlotReference {
        subject: subject.into(),
        attribute: "recorded".into(),
        date: Some("2026-10-29".into()),
    };
    let cases = [
        (
            json!({"kind":"quantity","op":"eq","value":1000,"unit":"MB"}),
            json!({"kind":"quantity","op":"eq","value":1,"unit":"GB"}),
            TruthValue::True,
        ),
        (
            json!({"kind":"money","op":"eq","value":10,"currency":"USD","per":"month"}),
            json!({"kind":"money","op":"eq","value":10,"currency":"EUR","per":"month"}),
            TruthValue::Unknown,
        ),
        (
            json!({"kind":"money","op":"eq","value":10,"currency":"USD","per":"month"}),
            json!({"kind":"money","op":"eq","value":10,"currency":"USD","per":"year"}),
            TruthValue::Unknown,
        ),
        (
            json!({"kind":"date","op":"eq","value":"2026"}),
            json!({"kind":"date","op":"eq","value":"2026-10-29"}),
            TruthValue::Unknown,
        ),
        (
            json!({"kind":"date","op":"eq","value":"2025"}),
            json!({"kind":"date","op":"eq","value":"2026"}),
            TruthValue::False,
        ),
    ];
    for (left_value, right_value, expected) in cases {
        let expression = ClaimExpr::Compare {
            left: slot("left"),
            op: ComparisonOp::Eq,
            right: slot("right"),
        };
        let mut calls = 0;
        let output = compose(
            &expression,
            &mut |_| unreachable!(),
            &mut |left, op, right| {
                calls += 1;
                assert_eq!(left, &slot("left"));
                assert_eq!(right, &slot("right"));
                assert_eq!(op, ComparisonOp::Eq);
                let hard = match compare_recorded_values(&left_value, &right_value, "eq") {
                    Some(true) => TruthValue::True,
                    Some(false) => TruthValue::False,
                    None => TruthValue::Unknown,
                };
                LeafAssessment {
                    hard,
                    ..LeafAssessment::unresolved()
                }
            },
        );
        assert_eq!(calls, 1);
        assert_eq!(output.hard, expected, "{left_value:?} {right_value:?}");
        assert_eq!(output.soft, BeliefBounds::VACUOUS);
    }
}

#[test]
fn knowledge_graph_keeps_temporal_gaps_unknown_and_sources_preserved() {
    let ClaimExpr::Atom(fact) = atom("team_size", 10) else {
        unreachable!()
    };
    let rows = [InputRow {
        id: "source".into(),
        text: "Hooly has 10 people.".into(),
        date: "2026-10-28".into(),
        label: "true".into(),
        form: vec![fact.clone()],
    }];
    let graph = KnowledgeGraph::compile(&rows);
    for (date, expected) in [
        ("2026-10-28", TruthValue::True),
        ("2026-10-29", TruthValue::Unknown),
    ] {
        let output = compose(
            &ClaimExpr::Atom(fact.clone()),
            &mut |f| LeafAssessment::from_resolution(&graph.resolve(f, date, "target", "Query")),
            &mut |_, _, _| unreachable!(),
        );
        assert_eq!(output.hard, expected);
        assert_eq!(output.soft, BeliefBounds::VACUOUS);
        if expected == TruthValue::True {
            assert_eq!(output.evidence_ids, ["source"]);
        }
    }
}

#[test]
fn traversal_limits_reject_the_whole_program_before_any_callback() {
    let mut deep = atom("a", 1);
    for _ in 0..MAX_PROGRAM_DEPTH + 1 {
        deep = ClaimExpr::Not(Box::new(deep));
    }
    let wide = ClaimExpr::All(
        (0..MAX_PROGRAM_NODES)
            .map(|n| atom("a", n as i64))
            .collect(),
    );
    for expression in [
        deep,
        wide,
        ClaimExpr::Any(vec![unknown(); MAX_PROGRAM_NODES + 1]),
    ] {
        let output = compose(
            &expression,
            &mut |_| panic!("over-budget atom callback"),
            &mut |_, _, _| panic!("over-budget comparison callback"),
        );
        assert!(output.diagnostics.budget_exceeded);
        assert_eq!(output.hard, TruthValue::Unknown);
        assert_eq!(output.soft, BeliefBounds::VACUOUS);
        assert!(output.evidence_ids.is_empty());
    }
    let mut valid = atom("a", 1);
    for _ in 0..MAX_PROGRAM_DEPTH {
        valid = ClaimExpr::Not(Box::new(valid));
    }
    assert!(
        !result(&valid, &[("a", TruthValue::True, Some(Belief::TRUE))])
            .diagnostics
            .budget_exceeded
    );
}

#[test]
fn maximum_accepted_atom_count_keeps_finite_simplex_bounds() {
    let expression = ClaimExpr::All(
        (0..MAX_PROGRAM_NODES - 1)
            .map(|n| atom(&format!("slot{n}"), n as i64))
            .collect(),
    );
    for estimate in [
        Belief::try_new(1.0 - 1e-12, 5e-13, 5e-13).unwrap(),
        Belief::try_new(0.3, 0.6, 0.1).unwrap(),
        Belief::UNKNOWN,
    ] {
        let output = compose(
            &expression,
            &mut |_| LeafAssessment {
                hard: TruthValue::Unknown,
                estimate: Some(estimate),
                evidence_ids: vec![],
            },
            &mut |_, _, _| unreachable!(),
        );
        assert_eq!(output.diagnostics.visited_nodes, MAX_PROGRAM_NODES);
        assert_eq!(output.diagnostics.unique_leaves, MAX_PROGRAM_NODES - 1);
        valid_bounds(output.soft);
        valid_mass(output.soft.uncommitted_mass());
    }
}

#[test]
fn bounds_contain_all_small_correlated_joint_distributions() {
    // Enumerate 3^3 deterministic joint states and several non-independent
    // mixtures. Expected marginals are computed from joint-state evaluation,
    // not from the Frechet formula used by the implementation.
    let states = [TruthValue::True, TruthValue::False, TruthValue::Unknown];
    let mut worlds = Vec::new();
    for a in states {
        for b in states {
            for c in states {
                worlds.push([a, b, c]);
            }
        }
    }
    let a = atom("a", 1);
    let b = atom("b", 2);
    let c = atom("c", 3);
    let expressions = [
        ClaimExpr::All(vec![a.clone(), b.clone(), c.clone()]),
        ClaimExpr::Any(vec![a.clone(), b.clone(), c.clone()]),
        ClaimExpr::All(vec![
            a.clone(),
            ClaimExpr::Any(vec![a.clone(), b.clone()]),
            ClaimExpr::Not(Box::new(c.clone())),
        ]),
        ClaimExpr::Any(vec![
            a.clone(),
            ClaimExpr::All(vec![b.clone(), c.clone()]),
            ClaimExpr::Not(Box::new(a.clone())),
        ]),
    ];
    for first in 0..worlds.len() {
        for second in 0..worlds.len() {
            let mass = |value: &dyn Fn(&[TruthValue; 3]) -> TruthValue| {
                let mut counts = [0.0; 3];
                for (w, weight) in [(worlds[first], 0.25), (worlds[second], 0.75)] {
                    let n = match value(&w) {
                        TruthValue::True => 0,
                        TruthValue::False => 1,
                        TruthValue::Unknown => 2,
                    };
                    counts[n] += weight;
                }
                Belief::try_new(counts[0], counts[1], counts[2]).unwrap()
            };
            let values = [
                ("a", TruthValue::Unknown, Some(mass(&|w| w[0]))),
                ("b", TruthValue::Unknown, Some(mass(&|w| w[1]))),
                ("c", TruthValue::Unknown, Some(mass(&|w| w[2]))),
            ];
            for expression in &expressions {
                let expected = mass(&|world| {
                    expression.evaluate(
                        &mut |f| {
                            world[match f.attribute.as_str() {
                                "a" => 0,
                                "b" => 1,
                                _ => 2,
                            }]
                        },
                        &mut |_, _, _| unreachable!(),
                    )
                });
                let output = result(expression, &values);
                valid_bounds(output.soft);
                contains(output.soft, expected);
            }
        }
    }
}
