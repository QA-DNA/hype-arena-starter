//! Row-local, deterministic preprocessing. No labels, forms, truth decisions or value parsing.

mod lexicon;
mod split;

pub use lexicon::{LexiconIndex, Normalizer, ReviewedAlias, Subject};
use serde::{Deserialize, Serialize};
pub use split::Splitter;
use std::fmt;

pub const SCHEMA_VERSION: u32 = 1;
pub const MAX_TEXT_BYTES: usize = 1_048_576;

#[derive(Debug)]
pub struct ExtractionError(pub String);
impl fmt::Display for ExtractionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for ExtractionError {}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}
impl Span {
    pub fn slice<'a>(&self, text: &'a str) -> Option<&'a str> {
        text.get(self.start..self.end)
    }
    pub fn overlaps(self, other: Self) -> bool {
        self.start < other.end && other.start < self.end
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Mention {
    pub subject: String,
    pub original_span: Span,
    pub normalized_span: Span,
    pub provenance: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NormalizationIssue {
    pub original_span: Span,
    pub candidates: Vec<String>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct OffsetSegment {
    pub original: Span,
    pub normalized: Span,
    pub replacement: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NormalizedRow {
    pub schema_version: u32,
    pub index_fingerprint: String,
    pub id: String,
    pub date: String,
    pub original_text: String,
    pub normalized_text: String,
    pub mentions: Vec<Mention>,
    pub issues: Vec<NormalizationIssue>,
    pub offsets: Vec<OffsetSegment>,
}
impl NormalizedRow {
    pub fn validate_alignment(&self) -> Result<(), ExtractionError> {
        let mut original_end = 0;
        let mut normalized_end = 0;
        for offset in &self.offsets {
            if offset.original.start != original_end
                || offset.normalized.start != normalized_end
                || offset.original.slice(&self.original_text).is_none()
                || offset.normalized.slice(&self.normalized_text).is_none()
                || (!offset.replacement
                    && offset.original.slice(&self.original_text)
                        != offset.normalized.slice(&self.normalized_text))
            {
                return Err(ExtractionError("Invalid normalization alignment".into()));
            }
            original_end = offset.original.end;
            normalized_end = offset.normalized.end;
        }
        if original_end != self.original_text.len()
            || normalized_end != self.normalized_text.len()
            || self
                .mentions
                .windows(2)
                .any(|m| m[0].normalized_span.end > m[1].normalized_span.start)
            || self.mentions.iter().any(|m| {
                m.normalized_span.slice(&self.normalized_text) != Some(m.subject.as_str())
                    || m.original_span.slice(&self.original_text).is_none()
            })
            || self
                .issues
                .iter()
                .any(|i| i.original_span.slice(&self.original_text).is_none())
        {
            return Err(ExtractionError("Invalid normalization spans".into()));
        }
        Ok(())
    }

    /// Map normalized byte ranges to original UTF-8 ranges without inventing alignment
    /// inside a replaced alias. A replacement maps to the whole original alias.
    pub fn source_spans(&self, span: Span) -> Vec<Span> {
        if self.validate_alignment().is_err() || span.slice(&self.normalized_text).is_none() {
            return Vec::new();
        }
        self.offsets
            .iter()
            .filter(|s| s.normalized.overlaps(span))
            .map(|s| {
                if s.replacement {
                    s.original
                } else {
                    Span {
                        start: s.original.start + span.start.max(s.normalized.start)
                            - s.normalized.start,
                        end: s.original.start + span.end.min(s.normalized.end) - s.normalized.start,
                    }
                }
            })
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct AssertionText {
    pub occurrence_id: String,
    pub subject: Option<String>,
    pub attribute: Option<String>,
    pub assertion_text: String,
    pub normalized_span: Span,
    pub source_spans: Vec<Span>,
    pub subject_source_span: Option<Span>,
    /// `paired` means the rule assigned a pair, not that the statement is true.
    pub status: String,
    pub reason: String,
    pub rule: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ParsedRow {
    pub row: NormalizedRow,
    /// `split`, `partial`, or `unresolved`; not a truth or completeness certificate.
    pub status: String,
    pub assertions: Vec<AssertionText>,
}
