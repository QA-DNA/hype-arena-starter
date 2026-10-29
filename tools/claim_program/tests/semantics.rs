use serde_json::{Value, json};
use veridyct_claim_program_tools::{
    claim_program::{
        CharSpan, ClaimExpr, ClaimProgram, ComparisonOp, MAX_PROGRAM_DEPTH, ProgramParser,
        SlotReference, TruthValue,
    },
    structured::{SchemaParser, ValueCandidate},
};
use veridyct_core::Fact;

fn lexicon() -> Value {
    json!({"subjects":[
        {"name":"Atlas","aliases":["Atlas Inc."],"attributes":["secure","price","version","released","power","cloud_provider","description"]},
        {"name":"Boreal","aliases":[],"attributes":["secure","price","version","released","power"]},
        {"name":"Élan","aliases":[],"attributes":["secure","price"]},
        {"name":"Research and Development","aliases":["R and D"],"attributes":["secure","description"]},
        {"name":"All Systems","aliases":[],"attributes":["secure"]}
    ]})
}

fn parser() -> ProgramParser {
    ProgramParser::compile(&lexicon()).unwrap()
}

fn candidate(text: &str, raw: &str, value: Value) -> ValueCandidate {
    let byte = text.find(raw).unwrap();
    ValueCandidate {
        start: text[..byte].chars().count(),
        end: text[..byte + raw.len()].chars().count(),
        value,
    }
}

fn parse(text: &str, raw: &[(&str, Value)]) -> ClaimProgram {
    parser().parse(
        text,
        &raw.iter()
            .map(|(s, v)| candidate(text, s, v.clone()))
            .collect::<Vec<_>>(),
        &[],
    )
}

fn evaluate(p: &ClaimProgram) -> TruthValue {
    p.evaluate(
        &mut |f| match (f.subject.as_str(), f.value["value"].as_bool()) {
            ("Atlas", Some(true)) | ("Boreal", Some(false)) => TruthValue::True,
            ("Atlas", Some(false)) | ("Boreal", Some(true)) => TruthValue::False,
            _ => TruthValue::Unknown,
        },
        &mut |_, _, _| TruthValue::Unknown,
    )
}

#[test]
fn kleene_truth_tables_include_order_independent_unknowns() {
    let states = [TruthValue::False, TruthValue::Unknown, TruthValue::True];
    for a in states {
        for b in states {
            for reversed in [false, true] {
                let mut values = vec![a, b];
                if reversed {
                    values.reverse();
                }
                for all in [false, true] {
                    let children: Vec<_> = values
                        .iter()
                        .enumerate()
                        .map(|(i, _)| {
                            ClaimExpr::Atom(Fact {
                                subject: i.to_string(),
                                attribute: "secure".into(),
                                value: json!({"kind":"boolean","value":true}),
                            })
                        })
                        .collect();
                    let expression = if all {
                        ClaimExpr::All(children)
                    } else {
                        ClaimExpr::Any(children)
                    };
                    let result = expression.evaluate(
                        &mut |f| values[f.subject.parse::<usize>().unwrap()],
                        &mut |_, _, _| panic!("not a comparison"),
                    );
                    let expected = if all && values.contains(&TruthValue::False) {
                        TruthValue::False
                    } else if !all && values.contains(&TruthValue::True) {
                        TruthValue::True
                    } else if values.contains(&TruthValue::Unknown) {
                        TruthValue::Unknown
                    } else if all {
                        TruthValue::True
                    } else {
                        TruthValue::False
                    };
                    assert_eq!(result, expected, "{values:?}, all={all}");
                }
            }
        }
    }
    for expression in [ClaimExpr::All(vec![]), ClaimExpr::Any(vec![])] {
        assert_eq!(
            expression.evaluate(&mut |_| TruthValue::True, &mut |_, _, _| TruthValue::True),
            TruthValue::Unknown
        );
    }
}

#[test]
fn false_and_unknown_and_true_or_unknown_preserve_incomplete_branch() {
    for (text, expected) in [
        (
            "Atlas secure is false and Boreal secure is unknown",
            TruthValue::False,
        ),
        (
            "Boreal secure is unknown and Atlas secure is false",
            TruthValue::False,
        ),
        (
            "Atlas secure is true or Boreal secure is unknown",
            TruthValue::True,
        ),
        (
            "Boreal secure is unknown or Atlas secure is true",
            TruthValue::True,
        ),
        (
            "Atlas secure is true and Boreal secure is unknown",
            TruthValue::Unknown,
        ),
        (
            "Atlas secure is false or Boreal secure is unknown",
            TruthValue::Unknown,
        ),
    ] {
        let p = parse(text, &[]);
        assert!(p.structured, "{p:?}");
        assert!(!p.complete, "{p:?}");
        assert_eq!(p.legacy_facts(), None);
        assert_eq!(evaluate(&p), expected, "{p:?}");
    }
}

#[test]
fn precedence_parentheses_and_nested_negation_have_distinct_scopes() {
    for (text, expected) in [
        (
            "Atlas secure is true or Boreal secure is true and Atlas secure is false",
            TruthValue::True,
        ),
        (
            "(Atlas secure is true or Boreal secure is true) and Atlas secure is false",
            TruthValue::False,
        ),
        (
            "not (Atlas secure is false or not (Boreal secure is false))",
            TruthValue::True,
        ),
        ("not not (Atlas secure is true)", TruthValue::True),
        (
            "neither Atlas secure is false nor Boreal secure is true",
            TruthValue::True,
        ),
        (
            "not all(Atlas secure is true, Boreal secure is true)",
            TruthValue::True,
        ),
        (
            "not all of the following: Atlas secure is true and Boreal secure is true",
            TruthValue::True,
        ),
        (
            "not all(Atlas secure is true, Boreal secure is true) or Atlas secure is false",
            TruthValue::True,
        ),
        (
            "all(Atlas secure is true, Boreal secure is false)",
            TruthValue::True,
        ),
        (
            "any(Atlas secure is false, Boreal secure is false)",
            TruthValue::True,
        ),
        (
            "all(any(Atlas secure is false, Boreal secure is false), Atlas secure is true)",
            TruthValue::True,
        ),
        (
            "any(all(Atlas secure is true, Boreal secure is true), Atlas secure is false)",
            TruthValue::False,
        ),
    ] {
        let p = parse(text, &[]);
        assert!(p.complete, "{text}: {p:?}");
        assert!(p.structured, "{p:?}");
        assert_eq!(evaluate(&p), expected, "{text}: {p:?}");
    }
}

#[test]
fn only_complete_positive_conjunctions_project_to_legacy() {
    let p = parse("Atlas secure is true and (Boreal secure is false)", &[]);
    assert!(p.complete, "{p:?}");
    assert_eq!(p.legacy_facts().unwrap().len(), 2);
    for text in [
        "Atlas secure is true or Boreal secure is false",
        "not (Atlas secure is true)",
        "Atlas secure is true and Boreal secure is missing",
    ] {
        assert_eq!(parse(text, &[]).legacy_facts(), None, "{text}");
    }
}

#[test]
fn lexical_negation_keeps_its_leaf_and_not_less_than_is_ge() {
    let p = parse("Atlas secure is not true or Boreal secure is false", &[]);
    assert!(p.complete, "{p:?}");
    assert_eq!(evaluate(&p), TruthValue::True);
    assert!(
        matches!(p.expression, ClaimExpr::Any(ref children) if matches!(children[0], ClaimExpr::Not(_)))
    );
    let text = "Atlas price is not less than 10 EUR/month and Boreal price is 5 USD/year";
    let p = parse(
        text,
        &[
            (
                "10 EUR/month",
                json!({"kind":"money","value":10,"currency":"EUR","per":"month"}),
            ),
            (
                "5 USD/year",
                json!({"kind":"money","value":5,"currency":"USD","per":"year"}),
            ),
        ],
    );
    let facts = p.legacy_facts().unwrap_or_else(|| panic!("{p:?}"));
    assert_eq!(
        facts[0].value,
        json!({"kind":"money","value":10,"currency":"EUR","per":"month","op":"ge"})
    );
    assert_eq!(
        facts[1].value,
        json!({"kind":"money","value":5,"currency":"USD","per":"year"})
    );
}

#[test]
fn contractions_and_never_are_local_negations_with_unicode_safe_offsets() {
    for text in [
        "Atlas secure isn't true",
        "Atlas secure isn’t true",
        "Atlas secure is never true",
    ] {
        let p = parse(text, &[]);
        assert!(p.complete, "{p:?}");
        assert!(p.structured);
        assert!(matches!(p.expression, ClaimExpr::Not(_)), "{p:?}");
        assert_eq!(evaluate(&p), TruthValue::False);
    }
    let text = "Atlas price isn’t 12.75 EUR/month or Boreal secure is true";
    let p = parse(
        text,
        &[(
            "12.75 EUR/month",
            json!({"kind":"money","value":12.75,"currency":"EUR","per":"month"}),
        )],
    );
    assert!(p.complete, "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::Any(ref a) if matches!(a[0],ClaimExpr::Not(ref n) if matches!(**n,ClaimExpr::Atom(ref f) if f.value["value"]==12.75)))
    );
}

#[test]
fn unicode_offsets_are_rebased_and_neural_does_not_broadcast() {
    let text =
        "Élan secure is true or (Atlas price is 12.75 EUR/month and Boreal secure is unknown)";
    let p = parser().parse(
        text,
        &[candidate(
            text,
            "12.75 EUR/month",
            json!({"kind":"money","value":12.75,"currency":"EUR","per":"month"}),
        )],
        &[Fact {
            subject: "Boreal".into(),
            attribute: "secure".into(),
            value: json!({"kind":"boolean","value":true}),
        }],
    );
    let encoded = serde_json::to_value(&p).unwrap();
    assert!(!encoded.to_string().contains("neural_fallback"), "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::Any(ref c) if matches!(c[1], ClaimExpr::All(ref a) if matches!(a[0],ClaimExpr::Atom(ref f) if f.value["value"]==12.75)))
    );
    let missing = "Élan secure is true and Boreal secure is missing";
    let p = parse(missing, &[]);
    let start = missing[..missing.find("Boreal").unwrap()].chars().count();
    assert!(
        matches!(p.expression,ClaimExpr::All(ref c) if matches!(c[1],ClaimExpr::Unknown{span,..} if span.start==start && span.end==missing.chars().count())),
        "{p:?}"
    );
}

#[test]
fn currencies_dates_versions_and_units_stay_in_each_leaf() {
    let text = "(Atlas version is v2.10 or Boreal released is 2026-03) and Atlas power is 2.75 kW";
    let p = parse(
        text,
        &[
            ("v2.10", json!({"kind":"version","value":"2.10"})),
            ("2026-03", json!({"kind":"date","value":"2026-03"})),
            (
                "2.75 kW",
                json!({"kind":"quantity","value":2.75,"unit":"kW"}),
            ),
        ],
    );
    assert!(p.complete, "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::All(ref c) if matches!(c[0],ClaimExpr::Any(ref a) if matches!(a[0],ClaimExpr::Atom(ref f) if f.value["value"]=="2.10") && matches!(a[1],ClaimExpr::Atom(ref f) if f.value["value"]=="2026-03")) && matches!(c[1],ClaimExpr::Atom(ref f) if f.value["unit"]=="kW"))
    );
}

#[test]
fn slot_comparisons_only_use_canonical_names_fields_and_explicit_dates() {
    for (operator, op) in [
        ("not less than", ComparisonOp::Ge),
        (">=", ComparisonOp::Ge),
        ("≤", ComparisonOp::Le),
        ("not equal to", ComparisonOp::Ne),
        ("<", ComparisonOp::Lt),
        ("equals", ComparisonOp::Eq),
        ("greater than", ComparisonOp::Gt),
    ] {
        let text =
            format!("Atlas Inc.'s price on 2026-03 is {operator} Boreal's price on 2025-12-31");
        let p = parse(&text, &[]);
        assert!(p.complete, "{p:?}");
        assert_eq!(
            p.expression,
            ClaimExpr::Compare {
                left: SlotReference {
                    subject: "Atlas".into(),
                    attribute: "price".into(),
                    date: Some("2026-03".into())
                },
                op,
                right: SlotReference {
                    subject: "Boreal".into(),
                    attribute: "price".into(),
                    date: Some("2025-12-31".into())
                },
            }
        );
        assert_eq!(p.legacy_facts(), None);
    }
    for text in [
        "Atlas price >= Boreal price",
        "Atlas power before Boreal power",
    ] {
        let p = parse(text, &[]);
        assert!(
            matches!(p.expression,ClaimExpr::Compare{ref left,ref right,..} if left.date.is_none() && right.date.is_none()),
            "{p:?}"
        );
    }
    for text in [
        "Atlas price is greater than its price",
        "Atlas price > Boreal price > Atlas price",
        "Atlas price on 2026-02-30 > Boreal price",
        "Atlas price > Unknown Person price",
    ] {
        let p = parse(text, &[]);
        assert!(!p.complete, "{p:?}");
        assert!(p.structured, "{p:?}");
        assert_eq!(evaluate(&p), TruthValue::Unknown);
    }
}

#[test]
fn comparison_callbacks_can_refuse_mismatched_currency_or_billing_period() {
    let p = parse("Atlas price > Boreal price", &[]);
    for (left, right) in [
        (
            json!({"currency":"EUR","per":"month"}),
            json!({"currency":"USD","per":"month"}),
        ),
        (
            json!({"currency":"EUR","per":"month"}),
            json!({"currency":"EUR","per":"year"}),
        ),
    ] {
        let mut calls = 0;
        assert_eq!(
            p.evaluate(
                &mut |_| panic!("slot comparison must not become atom"),
                &mut |_, op, _| {
                    calls += 1;
                    assert_eq!(op, ComparisonOp::Gt);
                    if left["currency"] != right["currency"] || left["per"] != right["per"] {
                        TruthValue::Unknown
                    } else {
                        TruthValue::True
                    }
                }
            ),
            TruthValue::Unknown
        );
        assert_eq!(calls, 1);
    }
}

#[test]
fn names_quoted_values_and_ordinary_prose_do_not_create_operators() {
    for text in [
        "Research and Development secure is true",
        "\"Research and Development\" secure is true",
        "R and D secure is true",
        "All Systems secure is true",
    ] {
        let p = parse(text, &[]);
        assert!(p.complete, "{text}: {p:?}");
        assert!(!p.structured, "{text}: {p:?}");
        assert_eq!(p.legacy_facts().unwrap().len(), 1);
    }
    let text = "Atlas description is \"end-to-end research and support\" or Boreal secure is true";
    let p = parse(
        text,
        &[(
            "end-to-end research and support",
            json!({"kind":"name","value":"end-to-end research and support"}),
        )],
    );
    assert!(p.complete, "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::Any(ref a) if a.len()==2),
        "{p:?}"
    );
    assert!(
        matches!(p.expression,ClaimExpr::Any(ref a) if matches!(a[0],ClaimExpr::Atom(ref f) if f.value["value"]=="end-to-end research and support")),
        "{p:?}"
    );
    let text = "Atlas provides an end-to-end service and support";
    let neural = [Fact {
        subject: "Atlas".into(),
        attribute: "price".into(),
        value: json!({"kind":"money","value":10,"currency":"EUR"}),
    }];
    let p = parser().parse(text, &[], &neural);
    let old = SchemaParser::compile(&lexicon())
        .unwrap()
        .parse(text, &[], &neural);
    assert!(!p.structured, "{p:?}");
    assert_eq!(p.complete, old.complete);
    assert!(
        matches!(p.expression,ClaimExpr::All(ref a) if matches!(a[0],ClaimExpr::Atom(ref f) if f==&neural[0]))
    );
    let text = "Atlas description is helpful and reliable";
    let p = parser().parse(text, &[], &neural);
    assert!(!p.structured, "ordinary descriptive prose: {p:?}");
    let text = "Atlas description is \"True and False\" or Boreal secure is true";
    let p = parse(
        text,
        &[(
            "True and False",
            json!({"kind":"name","value":"True and False"}),
        )],
    );
    assert!(p.complete, "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::Any(ref a) if matches!(a[0],ClaimExpr::Atom(ref f) if f.value["value"]=="True and False"))
    );
}

#[test]
fn comparator_words_are_bounded_and_inches_are_not_unclosed_quotes() {
    for (phrase, op) in [
        ("not less than", "ge"),
        ("not more than", "le"),
        ("not equal to", "ne"),
    ] {
        let text = format!("Atlas price is {phrase} 10 EUR or more");
        let p = parse(
            &text,
            &[(
                "10 EUR",
                json!({"kind":"money","value":10,"currency":"EUR"}),
            )],
        );
        let facts = p.legacy_facts().unwrap_or_else(|| panic!("{p:?}"));
        assert!(!p.structured, "{p:?}");
        assert_eq!(facts[0].value["op"], op);
    }
    let text = "Atlas power is 15\" and Boreal power is 30 cm";
    let p = parse(
        text,
        &[
            ("15\"", json!({"kind":"quantity","value":15,"unit":"inch"})),
            ("30 cm", json!({"kind":"quantity","value":30,"unit":"cm"})),
        ],
    );
    assert!(p.complete, "{p:?}");
    let facts = p.legacy_facts().unwrap();
    assert_eq!(facts[0].value["unit"], "inch");
    assert_eq!(facts[1].value["unit"], "cm");
    for text in [
        "Atlas price overlaps Boreal price",
        "Atlas price is not lesser than Boreal price",
    ] {
        let p = parse(text, &[]);
        assert!(!p.complete, "{p:?}");
        assert!(!matches!(p.expression, ClaimExpr::Compare { .. }));
    }
}

#[test]
fn typed_version_literals_are_not_a_second_comparison_slot() {
    for phrase in ["equals", "not equal to", "older than", "no newer than"] {
        let text = format!("Atlas version is {phrase} version 2.3.0");
        let p = parse(
            &text,
            &[("version 2.3.0", json!({"kind":"version","value":"2.3.0"}))],
        );
        assert!(p.complete, "{p:?}");
        assert!(!matches!(p.expression, ClaimExpr::Compare { .. }), "{p:?}");
        assert_eq!(p.legacy_facts().unwrap()[0].value["value"], "2.3.0");
    }
}

#[test]
fn aliases_inside_attribute_identifiers_are_not_extra_slot_subjects() {
    let parser = ProgramParser::compile(&json!({"subjects":[
        {"name":"Atlas","attributes":["cloud_provider"]},
        {"name":"Boreal","attributes":["cloud_provider"]},
        {"name":"Cloud","attributes":["secure"]}
    ]}))
    .unwrap();
    let p = parser.parse("Atlas cloud_provider = Boreal cloud_provider", &[], &[]);
    assert!(p.complete, "{p:?}");
    assert!(
        matches!(p.expression,ClaimExpr::Compare{left:ref l,right:ref r,..} if l.subject=="Atlas" && r.subject=="Boreal" && l.attribute=="cloud_provider" && r.attribute=="cloud_provider")
    );
}

#[test]
fn unsupported_conditionals_references_and_deep_inputs_cannot_flatten() {
    for text in [
        "If Atlas secure is true then Boreal secure is false",
        "Atlas secure is true unless Boreal secure is false",
        "Atlas secure is true and (Boreal secure is false",
        "Atlas secure is true or",
        "not only Atlas secure is true but Boreal secure is false",
    ] {
        let p = parse(text, &[]);
        assert!(p.structured, "{text}: {p:?}");
        assert!(!p.complete, "{text}: {p:?}");
        assert_eq!(p.legacy_facts(), None);
    }
    for count in [MAX_PROGRAM_DEPTH + 1, 2000, 10000] {
        let text = format!(
            "{}Atlas secure is true{}",
            "(".repeat(count),
            ")".repeat(count)
        );
        let p = parse(&text, &[]);
        assert!(!p.complete);
        assert_eq!(evaluate(&p), TruthValue::Unknown);
        assert!(p.notes.iter().any(|n| n == "depth_limit"));
    }
    let huge = "Atlas secure is true and ".repeat(600);
    let p = parse(&huge, &[]);
    assert!(!p.complete);
    assert_eq!(evaluate(&p), TruthValue::Unknown);
    let p = parse(&"x".repeat(65537), &[]);
    assert!(p.notes.iter().any(|n| n == "input_limit"));
}

#[test]
fn stable_json_and_spans_and_empty_inputs_have_no_vacuous_truth() {
    let parser = parser();
    for text in [
        "",
        "all()",
        "any()",
        "not ()",
        "Atlas secure is true or ???",
    ] {
        let first = parser.parse(text, &[], &[]);
        let second = parser.parse(text, &[], &[]);
        assert_eq!(
            serde_json::to_string(&first).unwrap(),
            serde_json::to_string(&second).unwrap()
        );
        assert!(!first.complete, "{first:?}");
        assert_eq!(first.legacy_facts(), None);
        if !text.is_empty() {
            assert!(first.structured, "{first:?}");
        }
    }
    let unknown = ClaimExpr::Unknown {
        span: CharSpan { start: 0, end: 1 },
        reason: "unresolved".into(),
    };
    assert_eq!(
        ClaimExpr::Not(Box::new(unknown))
            .evaluate(&mut |_| TruthValue::True, &mut |_, _, _| TruthValue::True),
        TruthValue::Unknown
    );
}

#[test]
fn invalid_candidates_and_unknown_terms_do_not_import_row_neural_facts() {
    let text = "Atlas sells something cheaper or Boreal secure is true";
    let neural = [Fact {
        subject: "Atlas".into(),
        attribute: "price".into(),
        value: json!({"kind":"money","value":99,"currency":"USD"}),
    }];
    let invalid = [
        ValueCandidate {
            start: usize::MAX,
            end: usize::MAX,
            value: json!({"kind":"name","value":"bad"}),
        },
        ValueCandidate {
            start: 0,
            end: usize::MAX,
            value: json!({"kind":"money","value":99,"currency":"USD"}),
        },
    ];
    let p = parser().parse(text, &invalid, &neural);
    assert!(p.structured);
    assert!(!p.complete);
    assert_eq!(p.legacy_facts(), None);
    let value = p.evaluate(
        &mut |f| {
            assert_eq!(f.subject, "Boreal");
            TruthValue::False
        },
        &mut |_, _, _| panic!("not a comparison"),
    );
    assert_eq!(value, TruthValue::Unknown);
    for text in ["Atlas price > it", "its price > their price", "it > it"] {
        let p = parser().parse(text, &[], &neural);
        assert!(p.structured, "{p:?}");
        assert!(!p.complete);
        assert!(
            matches!(p.expression, ClaimExpr::Unsupported { .. }),
            "{p:?}"
        );
    }
}

#[test]
fn malformed_unicode_delimiters_remain_deterministic_and_bounded() {
    let parser = parser();
    let pieces = [
        "Élan secure is true",
        "Atlas secure is false",
        "unknown",
        "🧭",
        "(",
        ")",
        "not ",
        "and ",
        "or ",
        "all(",
        "\"",
        "‘",
        ",",
        "if ",
    ];
    let mut state = 17u64;
    for _ in 0..256 {
        let mut text = String::new();
        for _ in 0..12 {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            text.push_str(pieces[(state >> 32) as usize % pieces.len()]);
            text.push(' ');
        }
        let first = parser.parse(&text, &[], &[]);
        let second = parser.parse(&text, &[], &[]);
        assert_eq!(first, second, "{text}");
        if !first.complete {
            assert_eq!(first.legacy_facts(), None);
        }
    }
}
