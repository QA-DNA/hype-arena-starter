use std::{
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};

static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Lab {
    path: PathBuf,
}
impl Lab {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "veridyct-extraction-test-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        fs::write(
            path.join("lexicon.json"),
            include_str!("../../../data/lexicon.json"),
        )
        .unwrap();
        let lab = Self { path };
        lab.ok(&[
            "lexicon",
            "compile",
            "--input",
            "lexicon.json",
            "--output",
            "index.json",
        ]);
        lab
    }
    fn command(&self, args: &[&str]) -> std::process::Output {
        Command::new(env!("CARGO_BIN_EXE_veridyct"))
            .args(args)
            .current_dir(&self.path)
            .output()
            .unwrap()
    }
    fn ok(&self, args: &[&str]) {
        let output = self.command(args);
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert!(output.stdout.is_empty());
    }
    fn records(&self, file: &str) -> Vec<csv::StringRecord> {
        csv::Reader::from_path(self.path.join(file))
            .unwrap()
            .records()
            .map(Result::unwrap)
            .collect()
    }
}
impl Drop for Lab {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}

#[test]
fn csv_round_trip_combined_and_staged_paths_are_identical() {
    let lab = Lab::new();
    let mut input = csv::Writer::from_path(lab.path.join("input.csv")).unwrap();
    input
        .write_record(["id", "text", "date", "label", "form"])
        .unwrap();
    input
        .write_record([
            "comma,id",
            "Gemini speaks 6 languages, and connects to 9 integrations.\n\"Release notes\"",
            "2026-10-28",
            "false",
            "not valid JSON and must never be parsed",
        ])
        .unwrap();
    input.flush().unwrap();
    lab.ok(&[
        "normalize",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "normalized.csv",
    ]);
    lab.ok(&[
        "split",
        "--index",
        "index.json",
        "--input",
        "normalized.csv",
        "--output",
        "staged.csv",
    ]);
    lab.ok(&[
        "parse",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "combined.csv",
        "--summary",
        "rows.csv",
    ]);
    assert_eq!(
        fs::read(lab.path.join("staged.csv")).unwrap(),
        fs::read(lab.path.join("combined.csv")).unwrap()
    );
    let records = lab.records("combined.csv");
    assert!(records.len() >= 2);
    assert!(
        records
            .iter()
            .all(|r| &r[0] == "comma,id" && &r[3] == "false")
    );
    assert_eq!(lab.records("rows.csv").len(), 1);
}

#[test]
fn labels_and_forms_do_not_influence_extraction() {
    let lab = Lab::new();
    fs::write(
        lab.path.join("one.csv"),
        "id,text,date,label,form\nr1,Gemini speaks 6 languages.,2026-10-28,true,ignored\n",
    )
    .unwrap();
    fs::write(
        lab.path.join("two.csv"),
        "id,text,date\nr1,Gemini speaks 6 languages.,2026-10-28\n",
    )
    .unwrap();
    for (input, output) in [("one.csv", "one-out.csv"), ("two.csv", "two-out.csv")] {
        lab.ok(&[
            "parse",
            "--index",
            "index.json",
            "--input",
            input,
            "--output",
            output,
        ]);
    }
    let a = lab.records("one-out.csv");
    let b = lab.records("two-out.csv");
    assert_eq!(a.len(), b.len());
    for (a, b) in a.iter().zip(&b) {
        assert_eq!(
            a.iter()
                .enumerate()
                .filter(|(i, _)| *i != 3)
                .collect::<Vec<_>>(),
            b.iter()
                .enumerate()
                .filter(|(i, _)| *i != 3)
                .collect::<Vec<_>>()
        );
    }
}

#[test]
fn malformed_input_does_not_publish_partial_output_or_destroy_input() {
    let lab = Lab::new();
    let original = "id,text,date\nr1,Gemini speaks 6 languages.,2026-10-28\nr1,Hooly Cloud has 4 regions.,2026-10-28\n";
    fs::write(lab.path.join("input.csv"), original).unwrap();
    fs::write(lab.path.join("output.csv"), "previous output").unwrap();
    let output = lab.command(&[
        "parse",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "output.csv",
    ]);
    assert_eq!(output.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&output.stderr).contains("Duplicate row ID"));
    assert_eq!(
        fs::read_to_string(lab.path.join("output.csv")).unwrap(),
        "previous output"
    );
    let output = lab.command(&[
        "parse",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "./input.csv",
    ]);
    assert_eq!(output.status.code(), Some(2));
    assert_eq!(
        fs::read_to_string(lab.path.join("input.csv")).unwrap(),
        original
    );
}

#[test]
fn empty_input_has_headers_and_missing_required_columns_fail() {
    let lab = Lab::new();
    fs::write(lab.path.join("empty.csv"), "id,text,date\n").unwrap();
    lab.ok(&[
        "parse",
        "--index",
        "index.json",
        "--input",
        "empty.csv",
        "--output",
        "output.csv",
    ]);
    assert!(lab.records("output.csv").is_empty());
    assert!(
        fs::read_to_string(lab.path.join("output.csv"))
            .unwrap()
            .starts_with("id,occurrence_id,")
    );
    fs::write(lab.path.join("bad.csv"), "id,label\n").unwrap();
    assert_eq!(
        lab.command(&[
            "parse",
            "--index",
            "index.json",
            "--input",
            "bad.csv",
            "--output",
            "bad-output.csv"
        ])
        .status
        .code(),
        Some(2)
    );
    assert!(!lab.path.join("bad-output.csv").exists());
}

#[test]
fn persisted_normalized_records_must_match_their_index_and_source() {
    let lab = Lab::new();
    fs::write(
        lab.path.join("input.csv"),
        "id,text,date\nr1,Gemini speaks 6 languages.,2026-10-28\n",
    )
    .unwrap();
    lab.ok(&[
        "normalize",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "normalized.csv",
    ]);
    let modified = fs::read_to_string(lab.path.join("normalized.csv"))
        .unwrap()
        .replace("Hooly Gemini speaks 6", "Hooly Gemini speaks 8");
    fs::write(lab.path.join("modified.csv"), modified).unwrap();
    assert_eq!(
        lab.command(&[
            "split",
            "--index",
            "index.json",
            "--input",
            "modified.csv",
            "--output",
            "output.csv"
        ])
        .status
        .code(),
        Some(2)
    );
    assert!(!lab.path.join("output.csv").exists());
}

#[test]
fn context_stream_has_staged_parity_and_can_be_disabled() {
    let lab = Lab::new();
    fs::write(lab.path.join("input.csv"), "id,text,date,label,form\na,Holdan joined Hooly.,2026-01-01,false,ignored\nb,He manages 4 engineers.,2026-01-01,,ignored\n").unwrap();
    lab.ok(&[
        "normalize",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "normalized.csv",
    ]);
    for (command, input, output) in [
        ("parse", "input.csv", "combined.csv"),
        ("split", "normalized.csv", "staged.csv"),
    ] {
        lab.ok(&[
            command,
            "--index",
            "index.json",
            "--input",
            input,
            "--output",
            output,
        ]);
    }
    assert_eq!(
        fs::read(lab.path.join("combined.csv")).unwrap(),
        fs::read(lab.path.join("staged.csv")).unwrap()
    );
    let data = fs::read_to_string(lab.path.join("combined.csv")).unwrap();
    assert!(data.contains("preceding_row"));
    assert!(data.contains("team_size"));
    lab.ok(&[
        "parse",
        "--index",
        "index.json",
        "--input",
        "input.csv",
        "--output",
        "local.csv",
        "--context",
        "off",
    ]);
    assert!(
        !fs::read_to_string(lab.path.join("local.csv"))
            .unwrap()
            .contains("team_size")
    );
}
