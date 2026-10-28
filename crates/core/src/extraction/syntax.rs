//! Small deterministic NLP grammar: roles, protected spans and qualifier wording.
//! Patterns are development-authored; they provide no factual Hooly evidence.
use super::{ExtractionError, Mention, NormalizedRow, Qualifier, SourceReference, Span};
use regex::Regex;

pub(super) struct Syntax {
    pub predicate: Regex,
    pub named_subject: Regex,
    pub date_apposition: Regex,
    pub temporal_prefix: Regex,
    pub list: Regex,
    pub list_member: Regex,
    version: Regex,
    qualifiers: Vec<(&'static str, Regex)>,
}

impl Syntax {
    pub fn new() -> Result<Self, ExtractionError> {
        let re = |s| Regex::new(s).map_err(|e| ExtractionError(format!("Syntax rule: {e}")));
        Ok(Self {
            named_subject: re(r"^(?:the |a |an )?[A-Z][A-Za-z]+ (?:plan|tier|subscription)\b")?,
            predicate: re(
                r"(?i)\b(?:has|have|is|are|was|were|started|joined|ran|runs|answers|costs|speaks|supports|includes|serves|ships|stores|opened|works|leads|reads|offers|holds|checks|weighs)\b",
            )?,
            date_apposition: re(
                r"(?i)^\s*\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
            )?,
            temporal_prefix: re(
                r"(?i)^\s*(?:from today|last quarter|before [^,]+|when [^,]+|while [^,]+|on \d[^,]*|since [^,]+)\s*$",
            )?,
            list: re(r"(?i)^[\p{L} ]+:\s*[\d,.]+%?\s*,\s*[\d,.]+%?")?,
            list_member: re(r"\d+(?:\.\d+)?%?")?,
            version: re(
                r"(?i)^\s*(?:(?P<track>CLI|API|stable)\s+)?(?:(?:v(?:ersion)?\.?\s*)(?P<marked>\d+(?:\.\d+)*)(?:\b)|(?P<bare>\d+\.\d+(?:\.\d+)*)\b)",
            )?,
            qualifiers: vec![
                (
                    "condition",
                    re(r"(?i)\b(?:if|unless|when|while|provided that)\b[^;.!?]*")?,
                ),
                (
                    "negation",
                    re(r"(?i)\b(?:not|never|no longer|without|no price|cannot)\b|n't\b")?,
                ),
                (
                    "bound",
                    re(
                        r"(?i)\b(?:over|under|more than|less than|at least|at most|up to|about|approximately)\b",
                    )?,
                ),
                (
                    "time",
                    re(
                        r"(?i)\b(?:today|now|last quarter|this week|since [^;,.]+|from \d[^;,.]+|on \d[^;,.]+)\b",
                    )?,
                ),
                (
                    "scheduled",
                    re(r"(?i)\b(?:due on|will|scheduled|expected)\b[^;.!?]*")?,
                ),
                (
                    "population",
                    re(
                        r"(?i)\b(?:beta (?:users|testers)|testers|monthly (?:active )?users|paid accounts|paying customers|users each month)\b",
                    )?,
                ),
                (
                    "cumulative",
                    re(r"(?i)\b(?:sold|so far|since (?:its |the )?[^;,.]*launch)\b")?,
                ),
                (
                    "billing",
                    re(r"(?i)\b(?:per|a|each) (?:month|year|user|seat)\b|/\s*(?:month|year)\b")?,
                ),
                ("alternative", re(r"(?i)\b(?:or|either)\b")?),
            ],
        })
    }

    pub fn version(
        &self,
        row: &NormalizedRow,
        mention: &Mention,
        clause: Span,
    ) -> Option<(String, Span)> {
        if mention.normalized_span.start < clause.start || mention.normalized_span.end > clause.end
        {
            return None;
        }
        let start = mention.normalized_span.end;
        let captures = self
            .version
            .captures(&row.normalized_text[start..clause.end])?;
        let number = captures.name("marked").or_else(|| captures.name("bare"))?;
        let attribute = match captures
            .name("track")
            .map(|m| m.as_str().to_ascii_lowercase())
            .as_deref()
        {
            Some("cli") => "cli_version",
            Some("api") => "api_version",
            Some("stable") => "stable_version",
            _ => "version",
        };
        let whole = captures.get(0)?;
        Some((
            attribute.into(),
            Span {
                start: start + whole.start() + whole.as_str().len()
                    - whole.as_str().trim_start().len(),
                end: start + number.end(),
            },
        ))
    }

    pub fn qualifiers(&self, row: &NormalizedRow, span: Span) -> Vec<Qualifier> {
        let text = &row.normalized_text[span.start..span.end];
        let mut result = Vec::new();
        for (kind, regex) in &self.qualifiers {
            for m in regex.find_iter(text).take(32) {
                let matched = Span {
                    start: span.start + m.start(),
                    end: span.start + m.end(),
                };
                result.push(Qualifier {
                    kind: (*kind).into(),
                    text: m.as_str().into(),
                    origin: "explicit".into(),
                    sources: references(row, matched, kind),
                });
            }
        }
        result
    }
}

pub(super) fn references(row: &NormalizedRow, span: Span, role: &str) -> Vec<SourceReference> {
    row.source_spans(span)
        .into_iter()
        .map(|span| SourceReference {
            row_id: row.id.clone(),
            span,
            role: role.into(),
        })
        .collect()
}
