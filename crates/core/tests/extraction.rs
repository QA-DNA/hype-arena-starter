//! Development-authored parser fixtures (Codex); not evidence about Hooly truth.
use veridyct_core::extraction::{LexiconIndex, Normalizer, ParsedRow, ReviewedAlias, Splitter};

fn normalizer() -> Normalizer {
    Normalizer::new(
        LexiconIndex::compile(include_str!("../../../data/lexicon.json"), vec![]).unwrap(),
    )
    .unwrap()
}
fn parse(text: &str) -> ParsedRow {
    let normalizer = normalizer();
    Splitter::new(&normalizer.index)
        .unwrap()
        .split(normalizer.normalize("test", "2026-10-28", text).unwrap())
        .unwrap()
}
fn pairs(row: &ParsedRow) -> Vec<(&str, &str)> {
    row.assertions
        .iter()
        .filter(|a| a.status == "paired")
        .map(|a| {
            (
                a.subject.as_deref().unwrap(),
                a.attribute.as_deref().unwrap(),
            )
        })
        .collect()
}

#[test]
fn longest_names_aliases_unicode_and_source_mapping() {
    let n = normalizer();
    let text = "Éva: Pixel 10 Pro costs €1,200; Gemini speaks 6 languages.";
    let row = n.normalize("r", "", text).unwrap();
    assert_eq!(
        row.normalized_text,
        "Éva: Hooly Pixel 10 Pro costs €1,200; Hooly Gemini speaks 6 languages."
    );
    assert_eq!(
        row.mentions
            .iter()
            .map(|m| m.subject.as_str())
            .collect::<Vec<_>>(),
        ["Hooly Pixel 10 Pro", "Hooly Gemini"]
    );
    for mention in &row.mentions {
        assert_eq!(
            row.source_spans(mention.normalized_span),
            [mention.original_span]
        );
        assert!(mention.original_span.slice(text).is_some());
    }
    n.validate_row(&row).unwrap();
    let twice = n.normalize("r", "", &row.normalized_text).unwrap();
    assert_eq!(twice.normalized_text, row.normalized_text);
}

#[test]
fn ordinary_words_and_unknown_shorthand_are_not_rewritten() {
    let n = normalizer();
    let text = "Search the maps and translate photos after an outage. Cloud has 4 regions.";
    let row = n.normalize("r", "", text).unwrap();
    assert_eq!(row.normalized_text, text);
    assert!(row.mentions.is_empty());
    assert_eq!(row.issues.len(), 5);
    assert_eq!(parse(text).status, "unresolved");
}

#[test]
fn collisions_remain_candidates_and_reviewed_aliases_are_explicit() {
    let json = r#"{"subjects":[{"name":"Alpha","aliases":["shared"],"attributes":["price"]},{"name":"Beta","aliases":["shared"],"attributes":["price"]}]}"#;
    let n = Normalizer::new(
        LexiconIndex::compile(
            json,
            vec![ReviewedAlias {
                alias: "A-one".into(),
                subject: "Alpha".into(),
                provenance: "fixture review".into(),
            }],
        )
        .unwrap(),
    )
    .unwrap();
    let row = n
        .normalize("r", "", "shared costs €3; A-one costs €4")
        .unwrap();
    assert_eq!(row.issues[0].candidates, ["Alpha", "Beta"]);
    assert_eq!(row.normalized_text, "shared costs €3; Alpha costs €4");
}

#[test]
fn index_and_normalization_tampering_is_rejected() {
    let n = normalizer();
    let mut index = n.index.clone();
    index.surfaces[0].subjects.clear();
    assert!(Normalizer::new(index).is_err());
    let mut row = n.normalize("r", "", "Gemini speaks 6 languages").unwrap();
    row.normalized_text.push('!');
    assert!(n.validate_row(&row).is_err());
}

#[test]
fn shared_subject_and_negation_remain_verbatim() {
    let row = parse("Gemini speaks over 6 languages and connects to 9 integrations.");
    assert_eq!(
        pairs(&row),
        [
            ("Hooly Gemini", "languages"),
            ("Hooly Gemini", "integrations")
        ]
    );
    assert_eq!(row.assertions[0].assertion_text, "speaks over 6 languages");
    let row = parse("Hooly Docs does not work offline yet.");
    assert_eq!(pairs(&row), [("Hooly Docs", "offline_editing")]);
    assert_eq!(
        row.assertions[0].assertion_text,
        "does not work offline yet."
    );
}

#[test]
fn eight_assertions_across_three_subjects() {
    let row = parse(
        "Hooly AI Pro costs €59 per month with 1 seat; Hooly Workspace costs €199 per month with 10 seats and a 99.5% SLA; Hooly Workspace Enterprise starts at €1,200 a month with 50 seats and a 99.9% SLA.",
    );
    assert_eq!(
        pairs(&row),
        [
            ("Hooly AI Pro", "price"),
            ("Hooly AI Pro", "included_seats"),
            ("Hooly Workspace", "price"),
            ("Hooly Workspace", "included_seats"),
            ("Hooly Workspace", "uptime_sla"),
            ("Hooly Workspace Enterprise", "price"),
            ("Hooly Workspace Enterprise", "included_seats"),
            ("Hooly Workspace Enterprise", "uptime_sla")
        ]
    );
    assert_eq!(row.status, "split");
    assert!(row.assertions[5].assertion_text.contains("€1,200"));
}

#[test]
fn explicit_parallel_percentages_are_aligned_only_with_respectively() {
    let text = "Hooly's Q4 results, Hooly's Q1 results, Hooly's Q2 results and Hooly's Q3 results have advertising shares of 78%, 72%, 66%, 61%, respectively.";
    let row = parse(text);
    assert_eq!(
        pairs(&row),
        [
            ("Hooly Q4 2025 Results", "advertising_share"),
            ("Hooly Q1 2026 Results", "advertising_share"),
            ("Hooly Q2 2026 Results", "advertising_share"),
            ("Hooly Q3 2026 Results", "advertising_share")
        ]
    );
    assert_eq!(
        row.assertions
            .iter()
            .map(|a| a.assertion_text.as_str())
            .collect::<Vec<_>>(),
        ["78%", "72%", "66%", "61%"]
    );
    assert_eq!(parse("Ads: 78%, 72%, 66%, 61%").status, "unresolved");
}

#[test]
fn repeated_pairs_are_not_deduplicated() {
    let row = parse("Hooly AI Pro costs €49 per month; Hooly AI Pro costs €59 per month.");
    assert_eq!(
        pairs(&row),
        [("Hooly AI Pro", "price"), ("Hooly AI Pro", "price")]
    );
    assert_ne!(
        row.assertions[0].occurrence_id,
        row.assertions[1].occurrence_id
    );
}

#[test]
fn shared_predicate_distributes_to_explicit_subjects() {
    let row = parse("Hooly Cloud and Hooly Workspace have over 100 customers.");
    assert_eq!(
        pairs(&row),
        [
            ("Hooly Cloud", "customers"),
            ("Hooly Workspace", "customers")
        ]
    );
}

#[test]
fn conditions_unknown_clauses_and_entity_objects_are_not_flattened() {
    assert_eq!(
        parse("Hooly AI Pro costs €59 if the plan renews.").status,
        "unresolved"
    );
    let row = parse("Gemini speaks 6 languages and does something undocumented.");
    assert_eq!(row.status, "partial");
    assert!(
        row.assertions
            .iter()
            .any(|a| a.assertion_text.contains("undocumented") && a.status == "unresolved")
    );
    assert_eq!(
        parse("Holdan joined Hooly on 12 January 2026.").status,
        "unresolved"
    );
    assert_eq!(parse("He manages 4 engineers.").status, "unresolved");
    assert_eq!(parse("").status, "unresolved");
}

#[test]
fn dates_and_decimal_versions_are_not_split_by_punctuation() {
    let row = parse("Hooly Docs launched on March 12, 2026.");
    assert_eq!(pairs(&row), [("Hooly Docs", "launched")]);
    assert_eq!(row.assertions.len(), 1);
    let row = parse("Gemini v2.3.1 ships today.");
    assert_eq!(pairs(&row), [("Hooly Gemini", "version")]);
    assert!(row.assertions[0].assertion_text.contains("v2.3.1"));
}

#[test]
fn billing_options_preserve_words_without_interpreting_amounts() {
    let row = parse("Hooly Jules is €19 a month, or €190 a year, after a 14-day trial.");
    assert_eq!(
        pairs(&row),
        [
            ("Hooly Jules", "price"),
            ("Hooly Jules", "annual_price"),
            ("Hooly Jules", "free_trial")
        ]
    );
}

#[test]
fn shared_negation_and_unaligned_subject_lists_remain_unresolved() {
    assert_eq!(
        parse("Gemini does not support image input and voice mode.").status,
        "unresolved"
    );
    assert_eq!(
        parse("Gemini may support image input and voice mode.").status,
        "unresolved"
    );
    assert_eq!(
        parse("Hooly's Q1 results and Hooly's Q2 results have advertising shares of 78%, 72%.")
            .status,
        "unresolved"
    );
    let row = parse("Gemini speaks 6 languages and UnknownCorp has 9 integrations.");
    assert_eq!(pairs(&row), [("Hooly Gemini", "languages")]);
    assert_eq!(row.status, "partial");
    assert_eq!(
        pairs(&parse("Hooly Cloud serves more than 100 customers.")),
        [("Hooly Cloud", "customers")]
    );
}

#[test]
fn object_coordination_does_not_break_the_assertion() {
    let row = parse("Hooly Docs checks spelling and grammar in 8 languages.");
    assert_eq!(pairs(&row), [("Hooly Docs", "languages")]);
    assert_eq!(row.assertions.len(), 1);
    let row = parse("Hooly Docs comes with 30 templates.");
    assert_eq!(pairs(&row), [("Hooly Docs", "templates")]);
    assert_eq!(row.assertions.len(), 1);
}

#[test]
fn invalid_offsets_are_errors_not_panics() {
    let n = normalizer();
    let mut row = n.normalize("r", "", "Gemini speaks 6 languages").unwrap();
    row.offsets[0].normalized.start = usize::MAX;
    assert!(Splitter::new(&n.index).unwrap().split(row).is_err());
}
