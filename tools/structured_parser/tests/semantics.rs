use serde_json::{Value, json};
use veridyct_core::Fact;
use veridyct_structured_parser_tools::structured::{Parsed, SchemaParser, ValueCandidate};

fn parser() -> SchemaParser {
    SchemaParser::compile(&json!({"subjects":[
        {"name":"Atlas","aliases":["Atlas Inc."],"attributes":["power","price","pro_price","version","stable_version","released","secure","median_time_to_recover","cloud_provider","soc2_certified","active_users","unknown_count","included_seats"]},
        {"name":"Atlas Pro","aliases":["Pro"],"attributes":["power","price","secure"]},
        {"name":"Boreal","aliases":["B"],"attributes":["price","secure","power"]},
        {"name":"Cloud Lab","aliases":["Cloud"],"attributes":["capacity","seats","users"]},
        {"name":"Atlas 10","aliases":[],"attributes":["power","secure"]},
        {"name":"Atlas I/O","aliases":[],"attributes":["released"]},
        {"name":"Unknown Lab","aliases":[],"attributes":["capacity"]}
    ]})).unwrap()
}

fn candidate(text: &str, raw: &str, value: Value) -> ValueCandidate {
    let start = text.find(raw).unwrap();
    ValueCandidate {
        start: text[..start].chars().count(),
        end: text[..start + raw.len()].chars().count(),
        value,
    }
}

fn parse(text: &str, values: &[(&str, Value)]) -> Parsed {
    let candidates = values
        .iter()
        .map(|(raw, v)| candidate(text, raw, v.clone()))
        .collect::<Vec<_>>();
    parser().parse(text, &candidates, &[])
}

fn only(p: Parsed, subject: &str, attribute: &str, value: Value) {
    assert!(p.complete, "{p:?}");
    assert_eq!(
        p.facts,
        [Fact {
            subject: subject.into(),
            attribute: attribute.into(),
            value
        }],
        "notes: {:?}",
        p.notes
    );
}

#[test]
fn explicit_subject_replaces_wrong_neural_subject_without_truth_lookup() {
    let text = "Boreal records 339.94 EUR per month for price.";
    let neural = vec![Fact {
        subject: "Atlas Pro".into(),
        attribute: "price".into(),
        value: json!({"kind":"money","value":339.94,"currency":"EUR","per":"month"}),
    }];
    only(
        parser().parse(
            text,
            &[candidate(
                text,
                "339.94 EUR per month",
                neural[0].value.clone(),
            )],
            &neural,
        ),
        "Boreal",
        "price",
        neural[0].value.clone(),
    );
}

#[test]
fn no_schema_cue_retains_neural_fallback_byte_for_byte() {
    let text = "Atlas sells a bargain package.";
    let neural = vec![Fact {
        subject: "Atlas".into(),
        attribute: "price".into(),
        value: json!({"kind":"money","value":17.1,"currency":"EUR"}),
    }];
    let p = parser().parse(text, &[], &neural);
    assert_eq!(p.facts, neural);
    assert!(!p.complete);
}

#[test]
fn longest_names_and_longest_fields_win() {
    only(
        parse(
            "Atlas Pro's price is €8/month.",
            &[(
                "€8/month",
                json!({"kind":"money","value":8,"currency":"EUR","per":"month"}),
            )],
        ),
        "Atlas Pro",
        "price",
        json!({"kind":"money","value":8,"currency":"EUR","per":"month"}),
    );
    only(
        parse(
            "Atlas's stable-version is version 2.3.",
            &[("version 2.3", json!({"kind":"version","value":"2.3"}))],
        ),
        "Atlas",
        "stable_version",
        json!({"kind":"version","value":"2.3"}),
    );
    only(
        parse(
            "Atlas Pro: price, €8/month.",
            &[(
                "€8/month",
                json!({"kind":"money","value":8,"currency":"EUR","per":"month"}),
            )],
        ),
        "Atlas Pro",
        "price",
        json!({"kind":"money","value":8,"currency":"EUR","per":"month"}),
    );
}

#[test]
fn all_comparators_apply_to_numeric_date_and_version_values() {
    for (phrase, op) in [
        ("exactly", "eq"),
        ("different from", "ne"),
        ("not equal to", "ne"),
        ("other than", "ne"),
        ("under", "lt"),
        ("no more than", "le"),
        ("over", "gt"),
        ("minimum", "ge"),
        ("no less than", "ge"),
        ("<=", "le"),
        ("≥", "ge"),
    ] {
        for (field, raw, value) in [
            (
                "price",
                "US$ 636.75 a month",
                json!({"kind":"money","value":636.75,"currency":"USD","per":"month"}),
            ),
            (
                "released",
                "2026-03",
                json!({"kind":"date","value":"2026-03"}),
            ),
            ("version", "v2.3", json!({"kind":"version","value":"2.3"})),
        ] {
            let text = format!("Atlas's {field} is {phrase} {raw}.");
            let mut expected = value.clone();
            if op != "eq" {
                expected["op"] = json!(op);
            }
            only(parse(&text, &[(raw, value)]), "Atlas", field, expected);
        }
    }
}

#[test]
fn dates_and_versions_have_kind_specific_operators_and_written_precision() {
    for (phrase, op) in [
        ("before", "lt"),
        ("prior to", "lt"),
        ("after", "gt"),
        ("by", "le"),
        ("no later than", "le"),
        ("no earlier than", "ge"),
    ] {
        let text = format!("Atlas's released is {phrase} 2026-03.");
        only(
            parse(
                &text,
                &[("2026-03", json!({"kind":"date","value":"2026-03"}))],
            ),
            "Atlas",
            "released",
            json!({"kind":"date","value":"2026-03","op":op}),
        );
    }
    for version in ["2.3", "2.3.0", "2.10", "3"] {
        let raw = format!("v{version}");
        let text = format!("Atlas's version is {raw}.");
        only(
            parse(&text, &[(&raw, json!({"kind":"version","value":version}))]),
            "Atlas",
            "version",
            json!({"kind":"version","value":version}),
        );
    }
}

#[test]
fn currency_prefix_spacing_and_billing_channels_are_literal() {
    for (raw, currency, period) in [
        ("US$12", "USD", None),
        ("US$ 12 per user per month", "USD", Some("month")),
        ("12 USD/seat/year", "USD", Some("year")),
        ("EUR 12 per annum", "EUR", Some("year")),
        ("€12 monthly", "EUR", Some("month")),
        ("12 GBP weekly", "GBP", Some("week")),
        ("£12 per day", "GBP", Some("day")),
    ] {
        let text = format!("Atlas's price is {raw}.");
        let mut expected = json!({"kind":"money","value":12,"currency":currency});
        if let Some(p) = period {
            expected["per"] = json!(p);
        }
        only(
            parse(
                &text,
                &[(raw, json!({"kind":"money","value":12,"currency":currency}))],
            ),
            "Atlas",
            "price",
            expected,
        );
    }
}

#[test]
fn decimal_comma_money_repairs_truncated_candidate_with_raw_spelling() {
    let text = "Atlas's price is not equal to 1877,36 EUR per month.";
    only(
        parse(
            text,
            &[(
                "36 EUR per month",
                json!({"kind":"money","value":36,"currency":"EUR","per":"month"}),
            )],
        ),
        "Atlas",
        "price",
        json!({"kind":"money","value":1877.36,"currency":"EUR","per":"month","op":"ne"}),
    );
    let text = "Atlas's price is minimum US$2074,08 a month.";
    only(
        parse(
            text,
            &[(
                "$2074",
                json!({"kind":"money","value":2074,"currency":"USD"}),
            )],
        ),
        "Atlas",
        "price",
        json!({"kind":"money","value":2074.08,"currency":"USD","per":"month","op":"ge"}),
    );
}

#[test]
fn billing_descriptors_and_year_like_money_fragments_are_not_values() {
    for text in [
        "Atlas's price [USD, one-off] is 1046.27 USD.",
        "The price [USD, one-off] of Atlas is 1046.27 USD.",
        "Atlas records 1046.27 USD for price [USD, one-off].",
    ] {
        only(
            parse(
                text,
                &[
                    ("one-off", json!({"kind":"quantity","value":1,"unit":"off"})),
                    (
                        "1046.27 USD",
                        json!({"kind":"money","value":1046.27,"currency":"USD"}),
                    ),
                ],
            ),
            "Atlas",
            "price",
            json!({"kind":"money","value":1046.27,"currency":"USD"}),
        );
    }
    let text = "The price [USD, per month] of Atlas is 1984,39 USD/month.";
    only(
        parse(
            text,
            &[
                ("1984", json!({"kind":"date","value":"1984"})),
                (
                    "39 USD/month",
                    json!({"kind":"money","value":39,"currency":"USD","per":"month"}),
                ),
            ],
        ),
        "Atlas",
        "price",
        json!({"kind":"money","value":1984.39,"currency":"USD","per":"month"}),
    );
}

#[test]
fn unresolved_elliptical_clause_keeps_measured_neural_fact_incomplete() {
    let text = "Atlas's power is 5 W; and 9 users use it.";
    let power = json!({"kind":"quantity","value":5,"unit":"W"});
    let users = json!({"kind":"quantity","value":9,"unit":"user"});
    let neural = vec![
        Fact {
            subject: "Atlas".into(),
            attribute: "power".into(),
            value: power.clone(),
        },
        Fact {
            subject: "Atlas".into(),
            attribute: "active_users".into(),
            value: users.clone(),
        },
    ];
    let p = parser().parse(
        text,
        &[
            candidate(text, "5 W", power),
            candidate(text, "9 users", users),
        ],
        &neural,
    );
    assert_eq!(p.facts, neural);
    assert!(!p.complete);
    assert!(
        p.notes
            .iter()
            .any(|n| n.starts_with("neural_clause_fallback:"))
    );
}

#[test]
fn all_four_public_practice_ellipsis_regressions_keep_neural_facts() {
    let lexicon: Value = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
    let schema = SchemaParser::compile(&lexicon).unwrap();
    let examples = vec![
        (
            "Gemini still speaks 6 languages and connects to 9 integrations; the big expansion comes in the spring.",
            "Hooly Gemini",
            vec![
                ("6 languages", "languages", 6, "language"),
                ("9 integrations", "integrations", 9, "integration"),
            ],
        ),
        (
            "Hooly starts the year with 38 employees and 1,000 customers.",
            "Hooly",
            vec![
                ("38 employees", "employees", 38, "employee"),
                ("1,000 customers", "paying_customers", 1000, "customer"),
            ],
        ),
        (
            "Hooly has 74 employees and 3,200 customers, in 14 countries.",
            "Hooly",
            vec![
                ("74 employees", "employees", 74, "employee"),
                ("3,200 customers", "paying_customers", 3200, "customer"),
                ("14 countries", "customer_countries", 14, "country"),
            ],
        ),
        (
            "Hooly has 74 employees, and 3,200 customers use it.",
            "Hooly",
            vec![
                ("74 employees", "employees", 74, "employee"),
                ("3,200 customers", "paying_customers", 3200, "customer"),
            ],
        ),
    ];
    for (text, subject, values) in examples {
        let neural: Vec<_> = values
            .iter()
            .map(|(_, attribute, n, unit)| Fact {
                subject: subject.into(),
                attribute: (*attribute).into(),
                value: json!({"kind":"quantity","value":n,"unit":unit}),
            })
            .collect();
        let proposals: Vec<_> = values
            .iter()
            .zip(&neural)
            .map(|((raw, _, _, _), fact)| candidate(text, raw, fact.value.clone()))
            .collect();
        let parsed = schema.parse(text, &proposals, &neural);
        assert_eq!(parsed.facts, neural, "{text}: {:?}", parsed.notes);
        assert!(!parsed.complete, "{text}");
    }
}

#[test]
fn physical_symbols_keep_case_and_unknown_units_are_not_schema_filtered() {
    for unit in ["kW", "mW", "MW", "kHz", "MHz", "GHz", "mAh", "GB", "B", "m"] {
        let raw = format!("0.1321 {unit}");
        let text = format!("Atlas's power is {raw}.");
        only(
            parse(
                &text,
                &[(
                    &raw,
                    json!({"kind":"quantity","value":0.1321,"unit":unit.to_lowercase()}),
                )],
            ),
            "Atlas",
            "power",
            json!({"kind":"quantity","value":0.1321,"unit":unit}),
        );
    }
    let p = parse(
        "Atlas's power is 5 bananas; and Boreal's price is 10 ms.",
        &[
            (
                "5 bananas",
                json!({"kind":"quantity","value":5,"unit":"banana"}),
            ),
            ("10 ms", json!({"kind":"duration","value":10,"unit":"ms"})),
        ],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts.len(), 2);
    assert_eq!(p.facts[1].value["kind"], "duration");
}

#[test]
fn embedded_names_numerals_and_count_nouns_do_not_invent_assertions() {
    let text = "Atlas 10's power is 0.000061 TB.";
    only(
        parse(
            text,
            &[
                (
                    "10's power",
                    json!({"kind":"quantity","value":10,"unit":"power"}),
                ),
                (
                    "0.000061 TB",
                    json!({"kind":"quantity","value":0.000061,"unit":"TB"}),
                ),
                ("TB", json!({"kind":"name","value":"TB"})),
            ],
        ),
        "Atlas 10",
        "power",
        json!({"kind":"quantity","value":0.000061,"unit":"TB"}),
    );
    let text = "Atlas's SOC 2 certified is yes.";
    only(
        parse(
            text,
            &[
                ("SOC", json!({"kind":"name","value":"SOC"})),
                (
                    "2 certified",
                    json!({"kind":"quantity","value":2,"unit":"certified"}),
                ),
            ],
        ),
        "Atlas",
        "soc2_certified",
        json!({"kind":"boolean","value":true}),
    );
    let text = "Atlas's included seats is not equal to 29.1 seats.";
    only(
        parse(
            text,
            &[(
                "29.1 seats",
                json!({"kind":"quantity","value":29.1,"unit":"seat"}),
            )],
        ),
        "Atlas",
        "included_seats",
        json!({"kind":"quantity","value":29.1,"unit":"seat","op":"ne"}),
    );
    let text = "Atlas's released is no later than 12 August 2026.";
    only(
        parse(
            text,
            &[
                (
                    "12 August 2026",
                    json!({"kind":"date","value":"2026-08-12"}),
                ),
                ("August", json!({"kind":"name","value":"August"})),
            ],
        ),
        "Atlas",
        "released",
        json!({"kind":"date","value":"2026-08-12","op":"le"}),
    );
}

#[test]
fn fixed_and_calendar_durations_remain_written_units() {
    for (raw, number, unit) in [
        ("30 days", 30, "day"),
        ("1 month", 1, "month"),
        ("12 months", 12, "month"),
        ("1 year", 1, "year"),
        ("44,640 s", 44640, "s"),
    ] {
        let text = format!("Atlas's median time to recover is not equal to {raw}.");
        only(
            parse(
                &text,
                &[(raw, json!({"kind":"duration","value":number,"unit":unit}))],
            ),
            "Atlas",
            "median_time_to_recover",
            json!({"kind":"duration","value":number,"unit":unit,"op":"ne"}),
        );
    }
}

#[test]
fn exact_scale_and_large_integers_do_not_use_float_arithmetic() {
    only(
        parse(
            "Atlas's active users is 13.58208M users.",
            &[(
                "13.58208M users",
                json!({"kind":"quantity","value":13582080,"unit":"user"}),
            )],
        ),
        "Atlas",
        "active_users",
        json!({"kind":"quantity","value":13582080,"unit":"user"}),
    );
    only(
        parse(
            "Atlas's active users is 9007199254740993 users.",
            &[(
                "9007199254740993 users",
                json!({"kind":"quantity","value":9007199254740992u64,"unit":"user"}),
            )],
        ),
        "Atlas",
        "active_users",
        json!({"kind":"quantity","value":9007199254740993u64,"unit":"user"}),
    );
    let exact: Value =
        serde_json::from_str(r#"{"kind":"quantity","value":0.123456789012345678901,"unit":"W"}"#)
            .unwrap();
    only(
        parse(
            "Atlas's power is 0.123456789012345678901 W.",
            &[(
                "0.123456789012345678901 W",
                json!({"kind":"quantity","value":0.1,"unit":"w"}),
            )],
        ),
        "Atlas",
        "power",
        exact,
    );
}

#[test]
fn word_numbers_reuse_frozen_values_and_repair_unit_case_and_nouns() {
    only(
        parse(
            "Atlas's power is minimum five kW.",
            &[("five kW", json!({"kind":"quantity","value":5,"unit":"kw"}))],
        ),
        "Atlas",
        "power",
        json!({"kind":"quantity","value":5,"unit":"kW","op":"ge"}),
    );
    only(
        parse(
            "Atlas's included seats is minimum forty-one seats.",
            &[(
                "forty-one seats",
                json!({"kind":"quantity","value":41,"unit":"seat"}),
            )],
        ),
        "Atlas",
        "included_seats",
        json!({"kind":"quantity","value":41,"unit":"seat","op":"ge"}),
    );
}

#[test]
fn unicode_character_offsets_and_invalid_spans_are_safe() {
    let text = "🔎 Atlas’s price is €49,99 a month.";
    // Topical emoji is deliberately outside the subject grammar; the
    // possessive still supplies a direct subject/attribute relation.
    only(
        parse(
            text,
            &[(
                "€49,99 a month",
                json!({"kind":"money","value":99,"currency":"EUR"}),
            )],
        ),
        "Atlas",
        "price",
        json!({"kind":"money","value":49.99,"currency":"EUR","per":"month"}),
    );
    let p = parser().parse(
        "Atlas's power is 4 W.",
        &[ValueCandidate {
            start: 99,
            end: 100,
            value: json!({"kind":"quantity","value":4,"unit":"W"}),
        }],
        &[],
    );
    assert!(!p.complete);
    assert!(p.facts.is_empty());
    assert!(p.notes.iter().any(|n| n.contains("invalid candidate")));
}

#[test]
fn explicit_record_subject_is_row_local_and_overridden_by_explicit_names() {
    let text = "Record subject: Atlas. Its price is €12; and Boreal's power is 4 W.";
    let p = parse(
        text,
        &[
            ("€12", json!({"kind":"money","value":12,"currency":"EUR"})),
            ("4 W", json!({"kind":"quantity","value":4,"unit":"W"})),
        ],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts[0].subject, "Atlas");
    assert_eq!(p.facts[1].subject, "Boreal");
    let text = "Its price is €12.";
    assert!(
        !parse(
            text,
            &[("€12", json!({"kind":"money","value":12,"currency":"EUR"}))]
        )
        .complete
    );
    let text = "Record subject: Atlas.\n\nIts price is €12.";
    assert!(
        !parse(
            text,
            &[("€12", json!({"kind":"money","value":12,"currency":"EUR"}))]
        )
        .complete
    );
    only(
        parse(
            "Record subject: Atlas I/O. It records different from 2023 for released.",
            &[("2023", json!({"kind":"date","value":"2023"}))],
        ),
        "Atlas I/O",
        "released",
        json!({"kind":"date","value":"2023","op":"ne"}),
    );
    only(
        parse(
            "Record subject: Atlas Inc. Its price is €12.",
            &[("€12", json!({"kind":"money","value":12,"currency":"EUR"}))],
        ),
        "Atlas",
        "price",
        json!({"kind":"money","value":12,"currency":"EUR"}),
    );
}

#[test]
fn aliases_with_abbreviations_do_not_end_binding_sentences() {
    only(
        parse(
            "The released of Atlas Inc. is 2026-03.",
            &[("2026-03", json!({"kind":"date","value":"2026-03"}))],
        ),
        "Atlas",
        "released",
        json!({"kind":"date","value":"2026-03"}),
    );
}

#[test]
fn boolean_literals_and_never_global_negation() {
    let p = parse(
        "Atlas's secure is not equal to no; and Boreal's secure is yes.",
        &[],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts.len(), 2);
    assert_eq!(
        p.facts[0].value,
        json!({"kind":"boolean","value":false,"op":"ne"})
    );
    assert_eq!(p.facts[1].value, json!({"kind":"boolean","value":true}));
}

#[test]
fn unknown_declarations_never_promote_booleans() {
    let text =
        "From 2024-01-01 through 2024-04-01, Atlas's secure is explicitly unrecorded (unknown).";
    let neural = vec![Fact {
        subject: "Atlas".into(),
        attribute: "secure".into(),
        value: json!({"kind":"boolean","value":true}),
    }];
    let p = parser().parse(text, &[], &neural);
    assert!(p.complete, "{p:?}");
    assert!(p.facts.is_empty());
    assert!(p.notes.iter().any(|n| n == "explicit_unknown:Atlas:secure"));
    only(
        parse(
            "Atlas's cloud provider is Unknown Lab.",
            &[("Unknown Lab", json!({"kind":"name","value":"Unknown Lab"}))],
        ),
        "Atlas",
        "cloud_provider",
        json!({"kind":"name","value":"Unknown Lab"}),
    );
}

#[test]
fn interval_dates_identifier_numbers_and_entity_digits_are_not_assertion_values() {
    let text = "From 2024-01-01 through 2024-04-01, Atlas's released is 2026-03. Document reference: 2027 (identifier only).";
    let p = parse(
        text,
        &[
            ("2024-01-01", json!({"kind":"date","value":"2024-01-01"})),
            ("2024-04-01", json!({"kind":"date","value":"2024-04-01"})),
            ("2026-03", json!({"kind":"date","value":"2026-03"})),
            ("2027", json!({"kind":"date","value":"2027"})),
        ],
    );
    only(
        p,
        "Atlas",
        "released",
        json!({"kind":"date","value":"2026-03"}),
    );
}

#[test]
fn a_partial_compound_and_ambiguous_values_remain_incomplete() {
    let p = parse(
        "Atlas's power is 3 W; and a mysterious unsupported assertion holds.",
        &[("3 W", json!({"kind":"quantity","value":3,"unit":"W"}))],
    );
    assert!(!p.complete);
    assert_eq!(p.facts.len(), 1);
    let p = parse(
        "Atlas's price changed from €3 to €4.",
        &[
            ("€3", json!({"kind":"money","value":3,"currency":"EUR"})),
            ("€4", json!({"kind":"money","value":4,"currency":"EUR"})),
        ],
    );
    assert!(!p.complete);
    assert!(p.facts.is_empty());
    for text in ["Atlas's power is about 5 W.", "Atlas's power is 5 W or so."] {
        let p = parse(
            text,
            &[("5 W", json!({"kind":"quantity","value":5,"unit":"W"}))],
        );
        assert!(!p.complete, "{p:?}");
        assert!(p.facts.is_empty());
    }
}

#[test]
fn attribute_first_value_first_and_punctuation_variants_bind() {
    for text in [
        "The price of Atlas is €12.",
        "€12 is the recorded price for Atlas.",
        "For Atlas, the recorded price stands at €12.",
        "The register gives Atlas a price of €12.",
        "Atlas has €12 as its price.",
        "Atlas: price, €12.",
        "Atlas's entry lists price as €12.",
    ] {
        only(
            parse(
                text,
                &[("€12", json!({"kind":"money","value":12,"currency":"EUR"}))],
            ),
            "Atlas",
            "price",
            json!({"kind":"money","value":12,"currency":"EUR"}),
        );
    }
    only(
        parse("Atlas's SOC-2/certified is yes.", &[]),
        "Atlas",
        "soc2_certified",
        json!({"kind":"boolean","value":true}),
    );
}

#[test]
fn malformed_schema_is_an_error_and_ambiguous_aliases_stay_unresolved() {
    assert!(SchemaParser::compile(&json!({})).is_err());
    assert!(SchemaParser::compile(&json!({"subjects":[{"name":"X","attributes":[3]}]})).is_err());
    let p=SchemaParser::compile(&json!({"subjects":[{"name":"X","aliases":["same"],"attributes":["price"]},{"name":"Y","aliases":["same"],"attributes":["price"]}]})).unwrap();
    let text = "same's price is €12.";
    let out = p.parse(
        text,
        &[candidate(
            text,
            "€12",
            json!({"kind":"money","value":12,"currency":"EUR"}),
        )],
        &[],
    );
    assert!(!out.complete);
    assert!(out.facts.is_empty());
}
