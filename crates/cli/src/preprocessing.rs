use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};
use veridyct_core::extraction::{
    DocumentExtractor, LexiconIndex, NormalizedRow, Normalizer, ParsedRow, ReviewedAlias, Splitter,
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

#[derive(Deserialize)]
struct InputRow {
    id: String,
    text: String,
    date: String,
    #[serde(default)]
    label: String,
    // Deliberately no form field: runtime extraction cannot read practice annotations.
}

#[derive(Serialize, Deserialize)]
struct NormalizedCsv {
    id: String,
    date: String,
    parent_label: String,
    original_text: String,
    normalized_text: String,
    schema_version: u32,
    index_fingerprint: String,
    mentions_json: String,
    issues_json: String,
    offsets_json: String,
}
impl NormalizedCsv {
    fn from_row(row: &NormalizedRow, label: &str) -> Result<Self> {
        Ok(Self {
            id: row.id.clone(),
            date: row.date.clone(),
            parent_label: label.into(),
            original_text: row.original_text.clone(),
            normalized_text: row.normalized_text.clone(),
            schema_version: row.schema_version,
            index_fingerprint: row.index_fingerprint.clone(),
            mentions_json: serde_json::to_string(&row.mentions)?,
            issues_json: serde_json::to_string(&row.issues)?,
            offsets_json: serde_json::to_string(&row.offsets)?,
        })
    }
    fn into_row(self) -> Result<(NormalizedRow, String)> {
        Ok((
            NormalizedRow {
                id: self.id,
                date: self.date,
                original_text: self.original_text,
                normalized_text: self.normalized_text,
                schema_version: self.schema_version,
                index_fingerprint: self.index_fingerprint,
                mentions: serde_json::from_str(&self.mentions_json)?,
                issues: serde_json::from_str(&self.issues_json)?,
                offsets: serde_json::from_str(&self.offsets_json)?,
            },
            self.parent_label,
        ))
    }
}

const NORMALIZED_HEADER: &[&str] = &[
    "id",
    "date",
    "parent_label",
    "original_text",
    "normalized_text",
    "schema_version",
    "index_fingerprint",
    "mentions_json",
    "issues_json",
    "offsets_json",
];
const ASSERTION_HEADER: &[&str] = &[
    "id",
    "occurrence_id",
    "date",
    "parent_label",
    "row_status",
    "status",
    "subject",
    "attribute",
    "assertion_text",
    "reason",
    "rule",
    "normalized_start",
    "normalized_end",
    "subject_source_start",
    "subject_source_end",
    "source_spans_json",
    "normalization_issues_json",
    "original_text",
    "normalized_text",
    "index_fingerprint",
    "schema_version",
    "input_ordinal",
    "context_boundary",
    "subject_origin",
    "evidence_json",
    "qualifiers_json",
    "subject_candidates_json",
    "group_id",
    "ordered_members_json",
];
const SUMMARY_HEADER: &[&str] = &[
    "id",
    "date",
    "parent_label",
    "row_status",
    "paired_count",
    "unresolved_count",
    "normalization_issue_count",
    "original_text",
    "normalized_text",
];

struct AtomicOutput {
    destination: PathBuf,
    temporary: PathBuf,
}
impl AtomicOutput {
    fn new(destination: &Path) -> Result<(Self, File)> {
        let parent = destination
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent)?;
        let name = destination
            .file_name()
            .ok_or("Output path must name a file")?
            .to_string_lossy();
        let temporary = parent.join(format!(".{name}.{}.tmp", std::process::id()));
        let file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)?;
        Ok((
            Self {
                destination: destination.into(),
                temporary,
            },
            file,
        ))
    }
    fn commit(self) -> Result<()> {
        fs::rename(&self.temporary, &self.destination)?;
        Ok(())
    }
}
impl Drop for AtomicOutput {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.temporary);
    }
}

pub fn run(args: &[String]) -> Result<()> {
    let (command, options) = if args.first().is_some_and(|s| s == "lexicon") {
        if args.get(1).is_none_or(|s| s != "compile") {
            return Err("Use lexicon compile --input lexicon.json --output index.json".into());
        }
        ("compile", &args[2..])
    } else {
        (args[0].as_str(), &args[1..])
    };
    let allowed = if command == "compile" {
        vec!["--input", "--output", "--aliases"]
    } else if command == "normalize" {
        vec!["--index", "--input", "--output"]
    } else {
        vec!["--index", "--input", "--output", "--summary", "--context"]
    };
    if !options.len().is_multiple_of(2) {
        return Err("Every option requires a value; see --help".into());
    }
    let mut opts = BTreeMap::new();
    for pair in options.chunks_exact(2) {
        if !allowed.contains(&pair[0].as_str())
            || opts.insert(pair[0].as_str(), pair[1].as_str()).is_some()
        {
            return Err(format!("Unknown or repeated option: {}", pair[0]).into());
        }
    }
    let required = |name| {
        opts.get(name)
            .copied()
            .ok_or_else(|| format!("Missing {name}"))
    };
    let input = Path::new(required("--input")?);
    let output = Path::new(required("--output")?);
    let summary_path = opts.get("--summary").map(Path::new);
    let mut paths = Vec::new();
    for (key, path) in &opts {
        if *key == "--context" {
            continue;
        }
        let path = Path::new(path);
        let absolute = absolute_path(path)?;
        if paths.contains(&absolute) {
            return Err(
                "Input, index, aliases, output and summary must use different paths".into(),
            );
        }
        paths.push(absolute);
    }
    if command == "compile" {
        let aliases: Vec<ReviewedAlias> = match opts.get("--aliases") {
            Some(path) => serde_json::from_reader(File::open(path)?)?,
            None => Vec::new(),
        };
        let index = LexiconIndex::compile(&fs::read_to_string(input)?, aliases)?;
        let (atomic, mut file) = AtomicOutput::new(output)?;
        serde_json::to_writer_pretty(&mut file, &index)?;
        file.write_all(b"\n")?;
        file.sync_all()?;
        drop(file);
        atomic.commit()?;
        eprintln!(
            "Compiled {} subjects and {} lookup surfaces; fingerprint {}",
            index.subjects.len(),
            index.surfaces.len(),
            index.fingerprint
        );
        return Ok(());
    }
    let index: LexiconIndex = serde_json::from_reader(File::open(required("--index")?)?)?;
    let normalizer = Normalizer::new(index)?;
    let splitter = Splitter::new(&normalizer.index)?;
    let mut document = DocumentExtractor::new(&normalizer.index)?;
    let context = opts.get("--context").copied().unwrap_or("previous");
    if !matches!(context, "previous" | "off") {
        return Err("--context must be previous or off".into());
    }
    let mut reader = csv::Reader::from_path(input)?;
    let headers = reader.headers()?.clone();
    let header_set: BTreeSet<_> = headers.iter().collect();
    if header_set.len() != headers.len() {
        return Err("Duplicate CSV column names".into());
    }
    let required_headers = if command == "split" {
        NORMALIZED_HEADER
    } else {
        &["id", "text", "date"]
    };
    for header in required_headers {
        if !header_set.contains(header) {
            return Err(format!("Input CSV is missing column {header:?}").into());
        }
    }
    let (atomic, file) = AtomicOutput::new(output)?;
    let mut writer = csv::WriterBuilder::new()
        .has_headers(false)
        .from_writer(file);
    writer.write_record(if command == "normalize" {
        NORMALIZED_HEADER
    } else {
        ASSERTION_HEADER
    })?;
    let (summary_atomic, mut summary) = if let Some(path) = summary_path {
        let (a, file) = AtomicOutput::new(path)?;
        let mut w = csv::Writer::from_writer(file);
        w.write_record(SUMMARY_HEADER)?;
        (Some(a), Some(w))
    } else {
        (None, None)
    };
    let mut ids = BTreeSet::new();
    let mut paired_count = 0;
    let mut unresolved_count = 0;
    for (n, record) in reader.records().enumerate() {
        let record = record.map_err(|e| format!("CSV record {}: {e}", n + 1))?;
        let (row, label) = if command == "split" {
            let data: NormalizedCsv = record.deserialize(Some(&headers))?;
            let (row, label) = data.into_row()?;
            normalizer.validate_row(&row)?;
            (row, label)
        } else {
            let input: InputRow = record.deserialize(Some(&headers))?;
            (
                normalizer.normalize(&input.id, &input.date, &input.text)?,
                input.label,
            )
        };
        if !ids.insert(row.id.clone()) {
            return Err(format!("Duplicate row ID {:?}", row.id).into());
        }
        if command == "normalize" {
            writer.serialize(NormalizedCsv::from_row(&row, &label)?)?;
        } else {
            let parsed = if context == "off" {
                splitter.split(row)?
            } else {
                document.split(row)?
            };
            let paired = parsed
                .assertions
                .iter()
                .filter(|a| a.status == "paired")
                .count();
            paired_count += paired;
            unresolved_count += parsed.assertions.len() - paired;
            write_assertions(&mut writer, &parsed, &label)?;
            if let Some(summary) = &mut summary {
                summary.write_record([
                    parsed.row.id.as_str(),
                    &parsed.row.date,
                    &label,
                    &parsed.status,
                    &paired.to_string(),
                    &(parsed.assertions.len() - paired).to_string(),
                    &parsed.row.issues.len().to_string(),
                    &parsed.row.original_text,
                    &parsed.row.normalized_text,
                ])?;
            }
        }
    }
    writer.flush()?;
    writer.get_ref().sync_all()?;
    drop(writer);
    if let Some(mut summary) = summary {
        summary.flush()?;
        summary.get_ref().sync_all()?;
        drop(summary);
    }
    // Each file is atomic. The optional summary and main CSV are not a transaction.
    if let Some(summary_atomic) = summary_atomic {
        summary_atomic.commit()?;
    }
    atomic.commit()?;
    eprintln!(
        "Processed {} rows; {paired_count} paired assertion fragments; {unresolved_count} unresolved fragments",
        ids.len()
    );
    Ok(())
}

fn write_assertions(writer: &mut csv::Writer<File>, parsed: &ParsedRow, label: &str) -> Result<()> {
    let row = &parsed.row;
    let issues = serde_json::to_string(&row.issues)?;
    for a in &parsed.assertions {
        writer.write_record([
            row.id.as_str(),
            &a.occurrence_id,
            &row.date,
            label,
            &parsed.status,
            &a.status,
            a.subject.as_deref().unwrap_or(""),
            a.attribute.as_deref().unwrap_or(""),
            &a.assertion_text,
            &a.reason,
            &a.rule,
            &a.normalized_span.start.to_string(),
            &a.normalized_span.end.to_string(),
            &a.subject_source_span
                .map(|s| s.start.to_string())
                .unwrap_or_default(),
            &a.subject_source_span
                .map(|s| s.end.to_string())
                .unwrap_or_default(),
            &serde_json::to_string(&a.source_spans)?,
            &issues,
            &row.original_text,
            &row.normalized_text,
            &row.index_fingerprint,
            &row.schema_version.to_string(),
            &parsed
                .input_ordinal
                .map(|n| n.to_string())
                .unwrap_or_default(),
            &parsed.context_boundary,
            &a.subject_origin,
            &serde_json::to_string(&a.evidence)?,
            &serde_json::to_string(&a.qualifiers)?,
            &serde_json::to_string(&a.subject_candidates)?,
            a.group_id.as_deref().unwrap_or(""),
            &serde_json::to_string(&a.ordered_members)?,
        ])?;
    }
    Ok(())
}

fn absolute_path(path: &Path) -> Result<PathBuf> {
    if path.exists() {
        return Ok(path.canonicalize()?);
    }
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    // Resolve existing ancestor symlinks even when output directories do not exist yet.
    let mut ancestor = absolute.as_path();
    let mut tail = Vec::new();
    while !ancestor.exists() {
        tail.push(ancestor.file_name().ok_or("Invalid path")?);
        ancestor = ancestor.parent().ok_or("Invalid path")?;
    }
    let mut result = ancestor.canonicalize()?;
    for part in tail.into_iter().rev() {
        result.push(part);
    }
    Ok(result)
}
