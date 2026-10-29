//! Development-authored NLP regressions; synthetic facts are not universe evidence.
use veridyct_core::extraction::{DocumentExtractor, LexiconIndex, Normalizer, ParsedRow, Splitter};
fn setup() -> (Normalizer, DocumentExtractor) {
    let n = Normalizer::new(
        LexiconIndex::compile(include_str!("../../../data/lexicon.json"), vec![]).unwrap(),
    )
    .unwrap();
    let d = DocumentExtractor::new(&n.index).unwrap();
    (n, d)
}
fn pair(r: &ParsedRow, subject: &str, attr: &str) -> bool {
    r.assertions.iter().any(|a| {
        a.status == "paired"
            && a.subject.as_deref() == Some(subject)
            && a.attribute.as_deref() == Some(attr)
    })
}
#[test]
fn person_product_context_and_original_cross_row_spans() {
    let (n, mut d) = setup();
    let first = "Éva: Holdan started at Hooly on 12 January 2026.";
    d.split(n.normalize("intro", "2026-01-12", first).unwrap())
        .unwrap();
    d.split(
        n.normalize("product", "2026-01-12", "Hooly Cloud has 3 regions.")
            .unwrap(),
    )
    .unwrap();
    let r = d
        .split(
            n.normalize(
                "pronoun",
                "2026-01-12",
                "He begins with a crew of 4 engineers.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Holdan", "team_size"));
    let a = r
        .assertions
        .iter()
        .find(|a| a.attribute.as_deref() == Some("team_size"))
        .unwrap();
    assert!(a.subject_source_span.is_none());
    let src = a.evidence.iter().find(|s| s.role == "subject").unwrap();
    assert_eq!(src.row_id, "intro");
    assert_eq!(src.span.slice(first), Some("Holdan"));
    let r = d
        .split(
            n.normalize(
                "its",
                "2026-01-12",
                "Its paid accounts carry a 99.9% uptime promise, which Holdan now owns.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Cloud", "uptime_sla"));
}
#[test]
fn context_expires_resets_and_does_not_guess_between_people() {
    let (n, mut d) = setup();
    d.split(
        n.normalize("a", "2026-01-01", "Holdan joined Hooly.")
            .unwrap(),
    )
    .unwrap();
    let r = d
        .split(
            n.normalize("b", "2026-01-02", "He manages 4 engineers.")
                .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Holdan", "team_size"));
    d.split(
        n.normalize("c", "2026-01-02", "Holdan joined Hooly.")
            .unwrap(),
    )
    .unwrap();
    for i in 0..8 {
        d.split(
            n.normalize(&format!("gap{i}"), "2026-01-02", "Unrelated prose.")
                .unwrap(),
        )
        .unwrap();
    }
    let r = d
        .split(
            n.normalize("late", "2026-01-02", "He manages 4 engineers.")
                .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Holdan", "team_size"));
    d.reset();
    let r = d
        .split(
            n.normalize("reset", "2026-01-02", "He manages 4 engineers.")
                .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Holdan", "team_size"));
    assert_eq!(r.input_ordinal, Some(1));
}
#[test]
fn versions_are_assertions_and_scoped_context_not_product_names() {
    let (n, mut d) = setup();
    let r = d
        .split(
            n.normalize(
                "v",
                "2026-08-19",
                "Hooly Jules v1.2 costs €19 per month and supports 14 languages.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Jules", "version"));
    assert!(pair(&r, "Hooly Jules", "price"));
    assert!(pair(&r, "Hooly Jules", "programming_languages"));
    assert_eq!(
        r.assertions
            .iter()
            .filter(|a| a.attribute.as_deref() == Some("version"))
            .count(),
        1
    );
    let r = d
        .split(
            n.normalize("it", "2026-08-19", "It has 1000 users.")
                .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Jules", "users"));
    assert!(r.assertions.iter().any(|a| {
        a.qualifiers
            .iter()
            .any(|q| q.kind == "version" && q.origin == "preceding_row")
    }));
    let r = d
        .split(
            n.normalize("bare", "2026-08-19", "Hooly Jules has 3000 users.")
                .unwrap(),
        )
        .unwrap();
    assert!(
        r.assertions
            .iter()
            .all(|a| a.qualifiers.iter().all(|q| q.kind != "version"))
    );
    let r = d
        .split(
            n.normalize(
                "android",
                "2026-08-19",
                "Hooly Android 17 has 480,000 beta testers.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Android 17", "beta_testers"));
    assert!(!pair(&r, "Hooly Android 17", "version"));
}
#[test]
fn reviewed_attribute_errors_and_date_attachment() {
    let (n, _) = setup();
    let s = Splitter::new(&n.index).unwrap();
    for (text, subject, attr) in [
        (
            "Hooly Chrome ships a stable version every 4 weeks.",
            "Hooly Chrome",
            "release_cadence",
        ),
        (
            "Hooly Workspace includes 10 seats, and each further seat costs €15 per month.",
            "Hooly Workspace",
            "extra_seat_price",
        ),
        (
            "Each offline Hooly Maps area can take 5 GB.",
            "Hooly Maps",
            "offline_area_limit",
        ),
        (
            "Hooly Jules beta users number 500 testers.",
            "Hooly Jules",
            "beta_testers",
        ),
        (
            "Hooly Chrome tabs sleep after 10 minutes when memory saver is active.",
            "Hooly Chrome",
            "tab_sleep_delay",
        ),
    ] {
        let r = s
            .split(n.normalize("x", "2026-01-01", text).unwrap())
            .unwrap();
        assert!(pair(&r, subject, attr), "{text}: {:?}", r.assertions);
    }
    let r = s
        .split(
            n.normalize(
                "date",
                "2026-04-14",
                "The Hooly Jules beta opens today, 14 April 2026.",
            )
            .unwrap(),
        )
        .unwrap();
    assert_eq!(r.assertions.len(), 1);
    assert!(r.assertions[0].assertion_text.contains("14 April 2026"));
    let r = s
        .split(
            n.normalize(
                "credit",
                "",
                "A trade-in gives up to €200 when ordering a Hooly Pixel Fold.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Hooly Pixel Fold", "price"));
}
#[test]
fn unaligned_lists_remain_one_ordered_group() {
    let (n, _) = setup();
    let s = Splitter::new(&n.index).unwrap();
    let r = s
        .split(n.normalize("list", "", "Ads: 78%, 72%, 66%, 61%").unwrap())
        .unwrap();
    assert_eq!(r.assertions.len(), 1);
    assert_eq!(r.assertions[0].ordered_members.len(), 4);
    assert_eq!(r.assertions[0].status, "unresolved");
}
#[test]
fn common_word_products_need_a_product_predicate() {
    let (n, _) = setup();
    let r = n
        .normalize("a", "", "Android runs on 2,900,000,000 devices.")
        .unwrap();
    assert_eq!(r.mentions[0].subject, "Hooly Android");
    let r = n
        .normalize(
            "b",
            "",
            "Photos stored in Hooly Photos: 4,200,000,000 photos",
        )
        .unwrap();
    assert_eq!(r.mentions.len(), 1);
    assert!(r.issues.is_empty());
}

#[test]
fn unrelated_named_subject_and_ambiguous_people_are_not_borrowed() {
    let json = r#"{"subjects":[{"name":"Alpha","attributes":["price"]},{"name":"Ada","attributes":["joined","team_size"]},{"name":"Bea","attributes":["joined","team_size"]}]}"#;
    let n = Normalizer::new(LexiconIndex::compile(json, vec![]).unwrap()).unwrap();
    let mut d = DocumentExtractor::new(&n.index).unwrap();
    d.split(
        n.normalize("a", "2026-01-01", "Alpha costs €10 a month.")
            .unwrap(),
    )
    .unwrap();
    let r = d
        .split(
            n.normalize("b", "2026-01-01", "Beta costs €20 a month.")
                .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Alpha", "price"));
    d.split(
        n.normalize("c", "2026-01-01", "Ada joined yesterday.")
            .unwrap(),
    )
    .unwrap();
    d.split(n.normalize("d", "2026-01-01", "Bea joined today.").unwrap())
        .unwrap();
    let r = d
        .split(
            n.normalize("e", "2026-01-01", "She manages 4 engineers.")
                .unwrap(),
        )
        .unwrap();
    assert_eq!(r.status, "unresolved");
    assert_eq!(r.assertions[0].subject_candidates, vec!["Ada", "Bea"]);
}
#[test]
fn missing_value_is_not_a_customer_count_and_condition_stays_attached() {
    let (n, mut d) = setup();
    d.split(
        n.normalize("cloud", "2026-01-01", "Hooly Cloud has 4 regions.")
            .unwrap(),
    )
    .unwrap();
    let r = d
        .split(
            n.normalize(
                "customers",
                "2026-01-01",
                "Customers in Europe were credited.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(!pair(&r, "Hooly Cloud", "customers"));
    let r = d
        .split(
            n.normalize(
                "recovery",
                "2026-01-01",
                "When something broke, the median time to recover was 52 min.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Cloud", "median_time_to_recover"));
    let a = r.assertions.iter().find(|a| a.status == "paired").unwrap();
    assert!(a.assertion_text.starts_with("When"));
    assert!(a.qualifiers.iter().any(|q| q.kind == "condition"));
}
#[test]
fn foreign_plan_blocks_context_for_its_coordinated_predicates() {
    let (n, mut d) = setup();
    d.split(
        n.normalize("max", "2026-01-01", "Hooly Photos Max costs €10 per month.")
            .unwrap(),
    )
    .unwrap();
    let r = d
        .split(
            n.normalize(
                "lite",
                "2026-01-01",
                "Lite costs €2 per month and holds 200 GB.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(r.assertions.iter().all(|a| a.status == "unresolved"));
}
#[test]
fn version_tracks_and_releases_do_not_become_original_launch_dates() {
    let (n, _) = setup();
    let s = Splitter::new(&n.index).unwrap();
    let r = s
        .split(
            n.normalize(
                "release",
                "2026-08-19",
                "Hooly Gemini 2.2 went live this week, and files may now weigh 100 MB.",
            )
            .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Gemini", "version"));
    assert!(pair(&r, "Hooly Gemini", "max_upload_size"));
    assert!(!pair(&r, "Hooly Gemini", "launched"));
    assert!(
        r.assertions
            .iter()
            .filter(|a| a.status == "paired")
            .all(|a| a.qualifiers.iter().any(|q| q.kind == "version"))
    );
    let r = s
        .split(
            n.normalize("cli", "", "Hooly Cloud CLI 1.4 ships today.")
                .unwrap(),
        )
        .unwrap();
    assert!(pair(&r, "Hooly Cloud", "cli_version"));
    assert!(!pair(&r, "Hooly Cloud", "version"));
}
#[test]
fn excessive_clause_work_abstains_and_preserves_original() {
    let (n, mut d) = setup();
    let text = "a".repeat(65_537);
    let r = d
        .split(n.normalize("long", "2026-01-01", &text).unwrap())
        .unwrap();
    assert_eq!(r.assertions.len(), 1);
    assert_eq!(r.assertions[0].reason, "complexity_limit");
    assert_eq!(r.row.original_text, text);
}
