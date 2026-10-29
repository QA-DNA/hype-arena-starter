use anyhow::Result;
use serde_json::{Value, json};
use veridyct_extractor::{
    encode::tokens,
    grammar::{Grammar, canonical, clauses},
};

fn grammar() -> Result<Grammar> {
    Grammar::new(
        &json!({"subjects":[{"name":"Hooly AI Pro","aliases":["AI Pro"],"attributes":["price"]}]}),
        &["Gavin Bellson".into()],
    )
}

#[test]
fn binding_extensions_preserve_frozen_candidates_and_unicode_offsets() -> Result<()> {
    let grammar = grammar()?;
    let text = "Café screen size is 1.25 in.";
    let frozen = grammar.candidates(text)?;
    let binding = grammar.binding_candidates(text)?;
    assert!(frozen.iter().all(|candidate| binding.contains(candidate)));
    let extra = binding
        .iter()
        .find(|candidate| candidate.value["unit"] == "inch")
        .unwrap();
    assert_eq!(
        text.chars()
            .skip(extra.start)
            .take(extra.end - extra.start)
            .collect::<String>(),
        "1.25 in"
    );
    assert_eq!(extra.value["value"], json!(1.25));
    assert_eq!(grammar.candidates(text)?, frozen);
    Ok(())
}

#[test]
fn all_eight_value_kinds_and_frozen_operators() -> Result<()> {
    let g = grammar()?;
    let cases: [(&str, Value); 14] = [
        (
            "AI Pro costs €79 per month.",
            json!({"kind":"money","value":79,"currency":"EUR","per":"month"}),
        ),
        (
            "It costs under €49.99 a month.",
            json!({"kind":"money","value":49.99,"currency":"EUR","per":"month","op":"lt"}),
        ),
        (
            "Its version is newer than 0.11.5.",
            json!({"kind":"version","value":"0.11.5","op":"gt"}),
        ),
        (
            "Its version is no newer than 20.0.",
            json!({"kind":"version","value":"20.0","op":"le"}),
        ),
        (
            "Growth is at least -26.62%.",
            json!({"kind":"percent","value":-26.62,"op":"ge"}),
        ),
        (
            "It reaches 35 m down.",
            json!({"kind":"quantity","value":35,"unit":"m"}),
        ),
        (
            "It serves 536 teams.",
            json!({"kind":"quantity","value":536,"unit":"team"}),
        ),
        ("Hooly Docs 2.0", json!({"kind":"version","value":"2.0"})),
        (
            "Cold start measures 1.9 s.",
            json!({"kind":"duration","value":1.9,"unit":"s"}),
        ),
        (
            "It closed after 3 days.",
            json!({"kind":"duration","value":3,"unit":"day"}),
        ),
        (
            "It occupies 4 data centre sites.",
            json!({"kind":"quantity","value":4,"unit":"site"}),
        ),
        (
            "It replies in under a second.",
            json!({"kind":"duration","value":1,"unit":"s","op":"lt"}),
        ),
        (
            "Its venue is Ringsend Forum.",
            json!({"kind":"name","value":"Ringsend Forum"}),
        ),
        ("It is certified.", json!({"kind":"boolean","value":true})),
    ];
    for (text, value) in cases {
        assert!(
            g.candidates(text)?.iter().any(|c| c.value == value),
            "{text}: {value}"
        );
    }
    let text = "€49 was mentioned; joined no earlier than the 25th of April 2025.";
    let candidates = g.candidates(text)?;
    let candidate = candidates
        .iter()
        .find(|c| c.value == json!({"kind":"date","value":"2025-04-25","op":"ge"}))
        .unwrap();
    assert_eq!(
        text.chars()
            .skip(candidate.start)
            .take(candidate.end - candidate.start)
            .collect::<String>(),
        "25th of April 2025"
    );
    Ok(())
}

#[test]
fn token_offsets_are_python_characters_and_casefolds_expand() -> Result<()> {
    let ts = tokens("€79 Straße e\u{301} İ's 東京")?;
    assert_eq!(
        ts.iter().map(|t| t.word.as_str()).collect::<Vec<_>>(),
        ["€", "79", "strasse", "e", "\u{301}", "i\u{307}'s", "東京"]
    );
    assert_eq!((ts[1].start, ts[1].end), (1, 3));
    assert_eq!((ts[2].start, ts[2].end), (4, 10));
    assert_eq!((ts[6].start, ts[6].end), (18, 20));
    Ok(())
}

#[test]
fn decimal_dates_and_clause_boolean_order_remain_frozen() -> Result<()> {
    let text = "It costs €49.99; It has 1,234 teams and 12 people.";
    let spans = clauses(text)?;
    assert_eq!(spans.len(), 3);
    let candidates = grammar()?.candidates(text)?;
    for (a, b) in spans {
        let booleans: Vec<_> = candidates
            .iter()
            .filter(|c| c.start == a && c.end == b && c.value["kind"] == "boolean")
            .map(|c| c.value["value"].as_bool().unwrap())
            .collect();
        assert_eq!(booleans, [false, true]);
    }
    assert_eq!(
        canonical(&json!({"kind":"percent","value":24.0})),
        canonical(&json!({"kind":"percent","value":24}))
    );
    assert_eq!(
        canonical(&json!({"kind":"money","value":0.5800000000000001})),
        canonical(&json!({"kind":"money","value":0.58}))
    );
    Ok(())
}
