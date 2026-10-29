//! Development-authored regressions for overlapping frozen proposals.
use serde_json::{Value, json};
use veridyct_claim_program_tools::{
    claim_program::ProgramParser,
    structured::{SchemaParser, ValueCandidate},
};

fn candidate(text: &str, raw: &str, value: Value) -> ValueCandidate {
    let byte = text.find(raw).unwrap();
    ValueCandidate {
        start: text[..byte].chars().count(),
        end: text[..byte + raw.len()].chars().count(),
        value,
    }
}

#[test]
fn overlapping_names_never_rewrite_typed_literals_in_either_candidate_order() {
    let lexicon = json!({"subjects":[{"name":"Élan","attributes":["memory","power","price","version","released","delay"]}]});
    let program = ProgramParser::compile(&lexicon).unwrap();
    let schema = SchemaParser::compile(&lexicon).unwrap();
    for (field, raw, nominal, typed, expected) in [
        (
            "memory",
            "48 GB",
            "GB",
            json!({"kind":"quantity","value":48,"unit":"gb"}),
            json!({"kind":"quantity","value":48,"unit":"GB"}),
        ),
        (
            "power",
            "31 mW",
            "mW",
            json!({"kind":"quantity","value":31,"unit":"mw"}),
            json!({"kind":"quantity","value":31,"unit":"mW"}),
        ),
        (
            "price",
            "27 USD",
            "USD",
            json!({"kind":"money","value":27,"currency":"EUR"}),
            json!({"kind":"money","value":27,"currency":"USD"}),
        ),
        (
            "version",
            "v3.14.8",
            "v3.14.8",
            json!({"kind":"version","value":"0.0.0"}),
            json!({"kind":"version","value":"3.14.8"}),
        ),
        (
            "released",
            "2024-02-29",
            "2024-02-29",
            json!({"kind":"date","value":"2023-01-01"}),
            json!({"kind":"date","value":"2024-02-29"}),
        ),
        (
            "delay",
            "19 milliseconds",
            "milliseconds",
            json!({"kind":"duration","value":19,"unit":"s"}),
            json!({"kind":"duration","value":19,"unit":"ms"}),
        ),
    ] {
        let text = format!("Élan {field} is {raw}");
        let mut candidates = vec![
            candidate(&text, raw, typed),
            candidate(&text, nominal, json!({"kind":"name","value":nominal})),
        ];
        for _ in 0..2 {
            let direct = schema.parse(&text, &candidates, &[]);
            let parsed = program.parse(&text, &candidates, &[]);
            assert!(direct.complete, "{text}: {direct:?}");
            assert!(parsed.complete, "{text}: {parsed:?}");
            assert_eq!(direct.facts.len(), 1, "{text}: {direct:?}");
            assert_eq!(direct.facts[0].value, expected, "{text}");
            assert_eq!(parsed.legacy_facts().unwrap(), direct.facts, "{text}");
            candidates.reverse();
        }
    }
}

#[test]
fn opaque_unicode_names_keep_lexical_unknowns_and_booleans_literal() {
    let parser = ProgramParser::compile(&json!({"subjects":[
        {"name":"Élan","attributes":["description"]},
        {"name":"Boreal","attributes":["secure"]}
    ]}))
    .unwrap();
    for name in [
        "True and False",
        "Unknown and Unrecorded",
        "Réseau and Développement",
    ] {
        let text = format!("Élan description is \"{name}\" or Boreal secure is true");
        let parsed = parser.parse(
            &text,
            &[candidate(&text, name, json!({"kind":"name","value":name}))],
            &[],
        );
        assert!(parsed.complete, "{name}: {parsed:?}");
        assert!(parsed.structured);
    }
}
