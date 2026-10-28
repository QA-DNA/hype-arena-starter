use super::{
    ExtractionError, MAX_TEXT_BYTES, Mention, NormalizationIssue, NormalizedRow, OffsetSegment,
    SCHEMA_VERSION, Span,
};
use regex::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Subject {
    pub name: String,
    #[serde(default)]
    pub aliases: Vec<String>,
    pub attributes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ReviewedAlias {
    pub alias: String,
    pub subject: String,
    /// Human-readable review/source record, not an inferred alias.
    pub provenance: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Surface {
    pub spelling: String,
    pub subjects: Vec<String>,
    pub provenance: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LexiconIndex {
    pub schema_version: u32,
    pub source_sha256: String,
    pub fingerprint: String,
    pub subjects: Vec<Subject>,
    pub reviewed_aliases: Vec<ReviewedAlias>,
    pub surfaces: Vec<Surface>,
}

impl LexiconIndex {
    pub fn compile(json: &str, aliases: Vec<ReviewedAlias>) -> Result<Self, ExtractionError> {
        #[derive(Deserialize)]
        struct Lexicon {
            subjects: Vec<Subject>,
        }
        let input: Lexicon = serde_json::from_str(json)
            .map_err(|e| ExtractionError(format!("Invalid lexicon JSON: {e}")))?;
        Self::build(
            input.subjects,
            aliases,
            format!("{:x}", Sha256::digest(json)),
        )
    }

    fn build(
        mut subjects: Vec<Subject>,
        mut aliases: Vec<ReviewedAlias>,
        source_sha256: String,
    ) -> Result<Self, ExtractionError> {
        if subjects.is_empty() || subjects.len() > 100_000 {
            return Err(ExtractionError(
                "Lexicon must have 1..100000 subjects".into(),
            ));
        }
        let mut names = BTreeSet::new();
        let mut surfaces: BTreeMap<String, (BTreeSet<String>, BTreeSet<String>)> = BTreeMap::new();
        for subject in &mut subjects {
            if subject.name.trim().is_empty()
                || !names.insert(subject.name.to_lowercase())
                || subject.attributes.is_empty()
                || subject.attributes.iter().any(|s| s.trim().is_empty())
            {
                return Err(ExtractionError(format!(
                    "Invalid/duplicate subject or attributes: {:?}",
                    subject.name
                )));
            }
            subject.attributes.sort();
            subject.attributes.dedup();
            subject.aliases.sort();
            subject.aliases.dedup();
            for spelling in std::iter::once(&subject.name).chain(subject.aliases.iter()) {
                if spelling.trim().is_empty() || spelling.len() > 4096 {
                    return Err(ExtractionError("Empty or oversized entity spelling".into()));
                }
                let entry = surfaces.entry(surface_key(spelling)).or_default();
                entry.0.insert(subject.name.clone());
                entry.1.insert("lexicon".into());
            }
        }
        subjects.sort_by(|a, b| a.name.cmp(&b.name));
        aliases.sort_by(|a, b| {
            (&a.alias, &a.subject, &a.provenance).cmp(&(&b.alias, &b.subject, &b.provenance))
        });
        for alias in &aliases {
            if alias.alias.trim().is_empty()
                || alias.alias.len() > 4096
                || alias.provenance.trim().is_empty()
                || !subjects.iter().any(|s| s.name == alias.subject)
            {
                return Err(ExtractionError(format!(
                    "Invalid reviewed alias: {:?}",
                    alias.alias
                )));
            }
            let entry = surfaces.entry(surface_key(&alias.alias)).or_default();
            entry.0.insert(alias.subject.clone());
            entry.1.insert(format!("reviewed: {}", alias.provenance));
        }
        let surfaces: Vec<_> = surfaces
            .into_iter()
            .map(|(spelling, (subjects, origins))| Surface {
                spelling,
                subjects: subjects.into_iter().collect(),
                provenance: origins.into_iter().collect::<Vec<_>>().join("; "),
            })
            .collect();
        let bytes = serde_json::to_vec(&(
            SCHEMA_VERSION,
            &source_sha256,
            &subjects,
            &aliases,
            &surfaces,
        ))
        .map_err(|e| ExtractionError(e.to_string()))?;
        Ok(Self {
            schema_version: SCHEMA_VERSION,
            source_sha256,
            fingerprint: format!("{:x}", Sha256::digest(bytes)),
            subjects,
            reviewed_aliases: aliases,
            surfaces,
        })
    }

    pub fn validate(&self) -> Result<(), ExtractionError> {
        if self.schema_version != SCHEMA_VERSION {
            return Err(ExtractionError(
                "Unsupported lexicon index version; recompile it".into(),
            ));
        }
        let rebuilt = Self::build(
            self.subjects.clone(),
            self.reviewed_aliases.clone(),
            self.source_sha256.clone(),
        )?;
        if rebuilt.fingerprint != self.fingerprint || rebuilt.surfaces != self.surfaces {
            return Err(ExtractionError(
                "Inconsistent lexicon index; recompile it".into(),
            ));
        }
        Ok(())
    }
}

fn surface_key(s: &str) -> String {
    s.replace('’', "'")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn word(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

pub struct Normalizer {
    pub index: LexiconIndex,
    patterns: Vec<(Surface, Regex)>,
}

impl Normalizer {
    pub fn new(index: LexiconIndex) -> Result<Self, ExtractionError> {
        index.validate()?;
        let patterns = index
            .surfaces
            .iter()
            .map(|surface| {
                let pattern = surface
                    .spelling
                    .split_whitespace()
                    .map(regex::escape)
                    .collect::<Vec<_>>()
                    .join(r"\s*")
                    .replace('’', "['’]")
                    .replace("\\'", "['’]");
                // regex::escape does not escape apostrophes.
                let pattern = pattern.replace("'", "['’]");
                Regex::new(&format!("(?i:{pattern})"))
                    .map(|r| (surface.clone(), r))
                    .map_err(|e| ExtractionError(format!("Invalid alias matcher: {e}")))
            })
            .collect::<Result<_, _>>()?;
        Ok(Self { index, patterns })
    }

    pub fn normalize(
        &self,
        id: &str,
        date: &str,
        text: &str,
    ) -> Result<NormalizedRow, ExtractionError> {
        if id.trim().is_empty() {
            return Err(ExtractionError("Row ID must not be empty".into()));
        }
        if text.len() > MAX_TEXT_BYTES {
            return Err(ExtractionError(format!(
                "Row {id}: text exceeds {MAX_TEXT_BYTES} bytes"
            )));
        }
        let mut candidates = Vec::new();
        for (surface, pattern) in &self.patterns {
            for m in pattern.find_iter(text) {
                let before = text[..m.start()].chars().next_back();
                let after = text[m.end()..].chars().next();
                if before.is_some_and(word) || after.is_some_and(word) {
                    continue;
                }
                candidates.push((
                    Span {
                        start: m.start(),
                        end: m.end(),
                    },
                    surface,
                ));
                if candidates.len() > 100_000 {
                    return Err(ExtractionError(format!(
                        "Row {id}: too many entity candidates"
                    )));
                }
            }
        }
        candidates.sort_by_key(|(s, surface)| {
            (
                std::cmp::Reverse(s.end - s.start),
                s.start,
                &surface.spelling,
            )
        });
        let mut chosen: Vec<(Span, &Surface)> = Vec::new();
        for candidate in candidates {
            if !chosen.iter().any(|(s, _)| s.overlaps(candidate.0)) {
                chosen.push(candidate);
            }
        }
        chosen.sort_by_key(|(s, _)| s.start);
        let mut row = NormalizedRow {
            schema_version: SCHEMA_VERSION,
            index_fingerprint: self.index.fingerprint.clone(),
            id: id.into(),
            date: date.into(),
            original_text: text.into(),
            normalized_text: String::new(),
            mentions: Vec::new(),
            issues: Vec::new(),
            offsets: Vec::new(),
        };
        let mut cursor = 0;
        for (span, surface) in chosen {
            let generic = matches!(
                surface.spelling.as_str(),
                "search"
                    | "maps"
                    | "photos"
                    | "translate"
                    | "chrome"
                    | "android"
                    | "outage"
                    | "devices division"
            );
            if surface.subjects.len() != 1 || generic {
                row.issues.push(NormalizationIssue {
                    original_span: span,
                    candidates: surface.subjects.clone(),
                    reason: if generic {
                        "ambiguous_common_word"
                    } else {
                        "alias_collision"
                    }
                    .into(),
                });
                continue;
            }
            push_segment(
                &mut row,
                text,
                Span {
                    start: cursor,
                    end: span.start,
                },
                None,
            );
            let start = row.normalized_text.len();
            push_segment(&mut row, text, span, Some(&surface.subjects[0]));
            row.mentions.push(Mention {
                subject: surface.subjects[0].clone(),
                original_span: span,
                normalized_span: Span {
                    start,
                    end: row.normalized_text.len(),
                },
                provenance: surface.provenance.clone(),
            });
            cursor = span.end;
        }
        push_segment(
            &mut row,
            text,
            Span {
                start: cursor,
                end: text.len(),
            },
            None,
        );
        Ok(row)
    }

    /// Validate persisted normalization records before splitting. The combined
    /// in-memory path does not serialize or reparse its objects.
    pub fn validate_row(&self, row: &NormalizedRow) -> Result<(), ExtractionError> {
        if row.schema_version != SCHEMA_VERSION || row.index_fingerprint != self.index.fingerprint {
            return Err(ExtractionError(format!(
                "Row {}: normalization/index version mismatch",
                row.id
            )));
        }
        let expected = self.normalize(&row.id, &row.date, &row.original_text)?;
        if expected != *row {
            return Err(ExtractionError(format!(
                "Row {}: normalized text or provenance was modified; normalize again",
                row.id
            )));
        }
        Ok(())
    }
}

fn push_segment(row: &mut NormalizedRow, text: &str, span: Span, replacement: Option<&str>) {
    if span.start == span.end {
        return;
    }
    let start = row.normalized_text.len();
    row.normalized_text
        .push_str(replacement.unwrap_or(&text[span.start..span.end]));
    row.offsets.push(OffsetSegment {
        original: span,
        normalized: Span {
            start,
            end: row.normalized_text.len(),
        },
        replacement: replacement.is_some(),
    });
}
