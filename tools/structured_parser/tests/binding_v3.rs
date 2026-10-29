//! Invented boundary cases; no label, accepted value or world is used by parsing.
use serde_json::{Value, json};
use veridyct_core::Fact;
use veridyct_structured_parser_tools::structured::{Parsed, SchemaParser, ValueCandidate};

fn schema() -> SchemaParser {
    SchemaParser::compile(&json!({"subjects":[
        {"name":"Atlas","attributes":["price","power","secure","cloud_provider","released","version","api_version","weight","uptime_sla","median_response_time"]},
        {"name":"Boreal","attributes":["price","power","secure"]},
        {"name":"Juniper","attributes":["stable_version","ai_sidebar"]}
    ]})).unwrap()
}

fn candidate(text: &str, raw: &str, value: Value) -> ValueCandidate {
    let byte = text.find(raw).unwrap();
    ValueCandidate {
        start: text[..byte].chars().count(),
        end: text[..byte + raw.len()].chars().count(),
        value,
    }
}

fn parse(text: &str, values: &[(&str, Value)]) -> Parsed {
    schema().parse(
        text,
        &values
            .iter()
            .map(|(r, v)| candidate(text, r, v.clone()))
            .collect::<Vec<_>>(),
        &[],
    )
}

fn fact(subject: &str, attribute: &str, value: Value) -> Fact {
    Fact {
        subject: subject.into(),
        attribute: attribute.into(),
        value,
    }
}

#[test]
fn lexical_conjunctions_inside_name_values_are_not_assertion_boundaries() {
    for name in ["Bread and Butter", "Bread-and-Butter", "This but That"] {
        let text = format!("Atlas's cloud provider is {name}.");
        let p = parse(&text, &[(name, json!({"kind":"name","value":name}))]);
        assert!(p.complete, "{p:?}");
        assert_eq!(
            p.facts,
            [fact(
                "Atlas",
                "cloud_provider",
                json!({"kind":"name","value":name})
            )]
        );
    }
}

#[test]
fn version_keyword_is_not_erased_by_its_frozen_candidate_span() {
    let p = parse(
        "Atlas's version is version 2.3.0.",
        &[("version 2.3.0", json!({"kind":"version","value":"2.3.0"}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(
        p.facts,
        [fact(
            "Atlas",
            "version",
            json!({"kind":"version","value":"2.3.0"})
        )]
    );
    let p = parse(
        "Atlas version 2.3.0 is here.",
        &[("version 2.3.0", json!({"kind":"version","value":"2.3.0"}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts[0].attribute, "version");
}

#[test]
fn explicit_interface_language_selects_the_api_channel() {
    for text in [
        "Atlas's API version is v7.2.",
        "Atlas runs API v7.2.",
        "Atlas runs version 7.2 of the interface.",
    ] {
        let raw = if text.contains("version 7.2") {
            "version 7.2"
        } else {
            "v7.2"
        };
        let p = parse(text, &[(raw, json!({"kind":"version","value":"7.2"}))]);
        assert_eq!(
            p.facts,
            [fact(
                "Atlas",
                "api_version",
                json!({"kind":"version","value":"7.2"})
            )],
            "{text}: {p:?}"
        );
    }
    let p = parse(
        "Atlas v7.2 is here.",
        &[("v7.2", json!({"kind":"version","value":"7.2"}))],
    );
    assert!(!p.complete);
    assert!(p.facts.is_empty(), "ambiguous API/product channel: {p:?}");
}

#[test]
fn possessive_ownership_does_not_cross_another_predicate_subject() {
    let p = parse(
        "Atlas's partner Boreal has price €7.",
        &[("€7", json!({"kind":"money","value":7,"currency":"EUR"}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts[0].subject, "Boreal");
}

#[test]
fn personal_and_plural_pronouns_use_only_unique_row_local_focus() {
    for pronoun in ["Its", "His", "Her", "Their"] {
        let text = format!("Atlas's cloud provider is Boreal. {pronoun} price is €7.");
        let p = parse(
            &text,
            &[
                ("Boreal", json!({"kind":"name","value":"Boreal"})),
                ("€7", json!({"kind":"money","value":7,"currency":"EUR"})),
            ],
        );
        assert!(p.complete, "{p:?}");
        assert_eq!(
            p.facts[1].subject, "Atlas",
            "named value must not steal focus"
        );
    }
    for text in [
        "Atlas's secure is yes.\n\nTheir price is €7.",
        "Atlas's secure is yes, Boreal's power is 4 W. Their price is €7.",
    ] {
        let p = parse(
            text,
            &[
                ("4 W", json!({"kind":"quantity","value":4,"unit":"W"})),
                ("€7", json!({"kind":"money","value":7,"currency":"EUR"})),
            ]
            .into_iter()
            .filter(|(r, _)| text.contains(r))
            .collect::<Vec<_>>(),
        );
        assert!(!p.complete, "{p:?}");
        assert!(!p.facts.iter().any(|f| f.attribute == "price"), "{p:?}");
    }
}

#[test]
fn negation_is_local_to_its_field_and_comparator_complements_are_exact() {
    let p = parse(
        "Atlas's secure is not true, price is €7.",
        &[("€7", json!({"kind":"money","value":7,"currency":"EUR"}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(
        p.facts,
        [
            fact(
                "Atlas",
                "secure",
                json!({"kind":"boolean","value":true,"op":"ne"})
            ),
            fact(
                "Atlas",
                "price",
                json!({"kind":"money","value":7,"currency":"EUR"})
            )
        ]
    );
    for (words, op) in [
        ("not at least", "lt"),
        ("not at most", "gt"),
        ("not under", "ge"),
        ("not over", "le"),
        ("not equal to", "ne"),
    ] {
        let text = format!("Atlas's power is {words} 4 W.");
        let p = parse(
            &text,
            &[("4 W", json!({"kind":"quantity","value":4,"unit":"W"}))],
        );
        assert!(p.complete, "{words}: {p:?}");
        assert_eq!(p.facts[0].value["op"], op, "{words}");
    }
}

#[test]
fn unconsumed_written_values_preserve_partial_neural_fallback() {
    let text = "Atlas's power is 4 W with a milestone on 2026-03.";
    let power = json!({"kind":"quantity","value":4,"unit":"W"});
    let date = json!({"kind":"date","value":"2026-03"});
    let neural = vec![
        fact("Atlas", "power", power.clone()),
        fact("Atlas", "released", date.clone()),
    ];
    let p = schema().parse(
        text,
        &[
            candidate(text, "4 W", power),
            candidate(text, "2026-03", date),
        ],
        &neural,
    );
    assert!(!p.complete, "{p:?}");
    assert_eq!(p.facts, neural);
    assert!(
        p.notes
            .iter()
            .any(|n| n.starts_with("neural_clause_fallback:"))
    );
}

#[test]
fn an_unknown_declaration_does_not_hide_a_later_unconsumed_value() {
    let p = parse(
        "Atlas's secure is unknown; Atlas's power is 4 W with a milestone on 2026-03.",
        &[
            ("4 W", json!({"kind":"quantity","value":4,"unit":"W"})),
            ("2026-03", json!({"kind":"date","value":"2026-03"})),
        ],
    );
    assert!(!p.complete, "{p:?}");
    assert_eq!(p.facts.len(), 1);
}

#[test]
fn literal_quantity_does_not_attach_backwards_across_an_unrelated_verb() {
    let p = parse(
        "Juniper 69.0 brings an AI sidebar.",
        &[
            ("69.0", json!({"kind":"version","value":"69.0"})),
            (
                "69.0 brings",
                json!({"kind":"quantity","value":69,"unit":"bring"}),
            ),
        ],
    );
    assert!(!p.complete, "{p:?}");
    assert_eq!(
        p.facts,
        [fact(
            "Juniper",
            "stable_version",
            json!({"kind":"version","value":"69.0"})
        )]
    );
}

#[test]
fn surface_cues_bind_language_and_do_not_claim_full_coverage() {
    for (text, raw, attr, value) in [
        (
            "Atlas costs €17 a month.",
            "€17 a month",
            "price",
            json!({"kind":"money","value":17,"currency":"EUR","per":"month"}),
        ),
        (
            "Atlas weighs 1.7 kg.",
            "1.7 kg",
            "weight",
            json!({"kind":"quantity","value":1.7,"unit":"kg"}),
        ),
        (
            "Atlas's contractual floor is 99.95 percent.",
            "99.95 percent",
            "uptime_sla",
            json!({"kind":"percent","value":99.95}),
        ),
    ] {
        let p = parse(text, &[(raw, value.clone())]);
        assert!(!p.complete, "{p:?}");
        assert_eq!(p.facts, [fact("Atlas", attr, value)], "{p:?}");
    }
    for text in [
        "Atlas €17.",
        "Atlas has no information.",
        "Atlas is secure.",
    ] {
        let values = if text.contains("€17") {
            vec![("€17", json!({"kind":"money","value":17,"currency":"EUR"}))]
        } else {
            vec![]
        };
        let p = parse(text, &values);
        assert!(!p.complete, "{p:?}");
        assert!(
            p.facts.is_empty(),
            "a schema attribute is not a stated value: {p:?}"
        );
    }
}

#[test]
fn unsupported_billing_periods_and_conflicting_currencies_are_not_one_off_prices() {
    for raw in ["€7 per quarter", "€7/hour", "€7 quarterly", "€7 USD"] {
        let text = format!("Atlas's price is {raw}.");
        let p = parse(
            &text,
            &[(raw, json!({"kind":"money","value":7,"currency":"EUR"}))],
        );
        assert!(!p.complete, "{raw}: {p:?}");
        assert!(p.facts.is_empty(), "{raw}: {p:?}");
    }
}

#[test]
fn approximate_ranges_and_ambiguous_decimals_fail_closed_with_one_candidate() {
    for (text, raw) in [
        ("Atlas's power is 1.500 W.", "1.500 W"),
        ("Atlas's power is almost 4 W.", "4 W"),
        ("Atlas's power is 4 W give or take.", "4 W"),
        ("Atlas's power is 4 W-ish.", "4 W"),
        ("Atlas's power is 2–4 W.", "4 W"),
        ("Atlas's power is 2-4 W.", "4 W"),
        ("Atlas's power is 4 W to 8 W.", "4 W"),
    ] {
        let p = parse(
            text,
            &[(raw, json!({"kind":"quantity","value":4,"unit":"W"}))],
        );
        assert!(!p.complete, "{text}: {p:?}");
        assert!(p.facts.is_empty(), "{text}: {p:?}");
    }
    let p = parse(
        "Atlas's uptime SLA is 99.999%.",
        &[("99.999%", json!({"kind":"percent","value":99.999}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts[0].value["value"], json!(99.999));
}

#[test]
fn explicit_star_units_do_not_become_product_versions() {
    let text = "Reviewers rate Juniper 4.6 stars.";
    let value = json!({"kind":"quantity","value":4.6,"unit":"star"});
    let neural = vec![fact("Juniper", "store_rating", value.clone())];
    let p = schema().parse(
        text,
        &[
            candidate(text, "4.6", json!({"kind":"version","value":"4.6"})),
            candidate(text, "4.6 stars", value),
        ],
        &neural,
    );
    assert!(!p.complete, "{p:?}");
    assert_eq!(p.facts, neural);
}

#[test]
fn an_unparsed_city_name_is_kept_after_a_literal_count_binding() {
    let parser = SchemaParser::compile(
        &json!({"subjects":[{"name":"Juniper Day","attributes":["city","attendees"]}]}),
    )
    .unwrap();
    let text = "Juniper Day in Berlin brought together 300 attendees.";
    let city = json!({"kind":"name","value":"Berlin"});
    let count = json!({"kind":"quantity","value":300,"unit":"attendee"});
    let neural = vec![
        fact("Juniper Day", "city", city.clone()),
        fact("Juniper Day", "attendees", count.clone()),
    ];
    let p = parser.parse(
        text,
        &[
            candidate(text, "Berlin", city),
            candidate(text, "300 attendees", count),
        ],
        &neural,
    );
    assert!(!p.complete, "{p:?}");
    assert!(neural.iter().all(|f| p.facts.contains(f)), "{p:?}");
}

#[test]
fn public_lexicon_live_language_regressions_need_no_truth_labels() {
    let lexicon: Value = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
    let parser = SchemaParser::compile(&lexicon).unwrap();
    let text = "Reminder: Hooly AI Pro is still €49 a month, and Gemini speaks 12 languages.";
    let price = json!({"kind":"money","value":49,"currency":"EUR","per":"month"});
    let languages = json!({"kind":"quantity","value":12,"unit":"language"});
    let p = parser.parse(
        text,
        &[
            candidate(text, "€49 a month", price.clone()),
            candidate(text, "12 languages", languages.clone()),
        ],
        &[],
    );
    assert!(
        p.facts.contains(&fact("Hooly AI Pro", "price", price)),
        "{p:?}"
    );
    assert!(
        p.facts
            .contains(&fact("Hooly Gemini", "languages", languages)),
        "{p:?}"
    );
    assert!(!p.complete, "surface binding retains incomplete coverage");

    for (text, expected) in [
        (
            "The employee survey recommend rate is 71%.",
            "would_recommend",
        ),
        ("The employee survey response rate is 71%.", "response_rate"),
    ] {
        let percent = json!({"kind":"percent","value":71});
        let wrong = vec![fact(
            "Hooly Employee Survey",
            "response_rate",
            percent.clone(),
        )];
        let p = parser.parse(text, &[candidate(text, "71%", percent.clone())], &wrong);
        assert_eq!(
            p.facts,
            [fact("Hooly Employee Survey", expected, percent)],
            "{text}: {p:?}"
        );
    }
    let text = "Hooly Gemini API v2 ships with it.";
    let p = parser.parse(
        text,
        &[candidate(text, "v2", json!({"kind":"version","value":"2"}))],
        &[],
    );
    assert_eq!(
        p.facts,
        [fact(
            "Hooly Gemini",
            "api_version",
            json!({"kind":"version","value":"2"})
        )],
        "{p:?}"
    );

    let text = "Reminder: Hooly AI Pro is still ?49 a month.";
    let p = parser.parse(
        text,
        &[candidate(
            text,
            "49 a month",
            json!({"kind":"money","value":49,"currency":"EUR","per":"month"}),
        )],
        &[],
    );
    assert!(!p.complete, "{p:?}");
    assert!(
        p.facts.is_empty(),
        "missing currency cannot be invented: {p:?}"
    );
}

#[test]
fn counted_noun_modifiers_require_the_written_proposed_noun() {
    let parser = SchemaParser::compile(
        &json!({"subjects":[{"name":"Atlas","attributes":["active_users"]}]}),
    )
    .unwrap();
    for raw in [
        "12 active users",
        "12 monthly active users",
        "12 of our users",
    ] {
        let text = format!("Atlas's active users is {raw}.");
        let p = parser.parse(
            &text,
            &[candidate(
                &text,
                raw,
                json!({"kind":"quantity","value":12,"unit":"user"}),
            )],
            &[],
        );
        assert!(p.complete, "{raw}: {p:?}");
        assert_eq!(
            p.facts[0].value,
            json!({"kind":"quantity","value":12,"unit":"user"})
        );
    }
    let text = "Atlas's active users is 12 active users.";
    let p = parser.parse(
        text,
        &[candidate(
            text,
            "12 active users",
            json!({"kind":"quantity","value":12,"unit":"employee"}),
        )],
        &[],
    );
    assert!(!p.complete, "{p:?}");
    assert!(p.facts.is_empty(), "{p:?}");
}

#[test]
fn currency_suffix_symbols_are_literal_and_repeated_periods_are_ambiguous() {
    for (raw, code) in [
        ("17 €", "EUR"),
        ("17 £/week", "GBP"),
        ("17 US$ per year", "USD"),
    ] {
        let text = format!("Atlas's price is {raw}.");
        let p = parse(
            &text,
            &[(raw, json!({"kind":"money","value":17,"currency":code}))],
        );
        assert!(p.complete, "{raw}: {p:?}");
        assert_eq!(p.facts[0].value["currency"], code);
    }
    let p = parse(
        "Atlas's price is €17/month/year.",
        &[(
            "€17/month/year",
            json!({"kind":"money","value":17,"currency":"EUR"}),
        )],
    );
    assert!(!p.complete, "{p:?}");
    assert!(p.facts.is_empty(), "{p:?}");
}

#[test]
fn iso_dates_keep_the_written_value_and_invalid_calendar_dates_fail_closed() {
    let p = parse(
        "Atlas's released is 2027-03.",
        &[("2027-03", json!({"kind":"date","value":"2026-03-01"}))],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(p.facts[0].value, json!({"kind":"date","value":"2027-03"}));
    for raw in ["2026-02-30", "12/03/2026", "12.03.2026"] {
        let text = format!("Atlas's released is {raw}.");
        let p = parse(&text, &[(raw, json!({"kind":"date","value":"2026-03-12"}))]);
        assert!(!p.complete, "{raw}: {p:?}");
        assert!(p.facts.is_empty(), "{raw}: {p:?}");
    }
}

#[test]
fn an_inline_version_marker_is_not_hidden_by_an_unrelated_field() {
    let p = parse(
        "Atlas version 2.3 has price €17.",
        &[
            ("version 2.3", json!({"kind":"version","value":"2.3"})),
            ("€17", json!({"kind":"money","value":17,"currency":"EUR"})),
        ],
    );
    assert!(p.complete, "{p:?}");
    assert_eq!(
        p.facts,
        [
            fact("Atlas", "version", json!({"kind":"version","value":"2.3"})),
            fact(
                "Atlas",
                "price",
                json!({"kind":"money","value":17,"currency":"EUR"})
            )
        ]
    );
}
