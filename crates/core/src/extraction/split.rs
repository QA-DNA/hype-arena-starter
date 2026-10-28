use super::{
    AssertionText, ExtractionError, LexiconIndex, Mention, NormalizedRow, ParsedRow, Span,
};
use regex::Regex;
use std::collections::{BTreeMap, BTreeSet};

struct Cue {
    attribute: String,
    pattern: Regex,
}

/// Rules locate attribute phrases; they do not interpret the values in those phrases.
pub struct Splitter {
    fingerprint: String,
    attributes: BTreeMap<String, BTreeSet<String>>,
    cues: Vec<Cue>,
    separators: Regex,
    scope: Regex,
    percent: Regex,
    inherit_prefix: Regex,
}

impl Splitter {
    pub fn new(index: &LexiconIndex) -> Result<Self, ExtractionError> {
        index.validate()?;
        let attributes: BTreeMap<String, BTreeSet<String>> = index
            .subjects
            .iter()
            .map(|s| (s.name.clone(), s.attributes.iter().cloned().collect()))
            .collect();
        let all: BTreeSet<_> = attributes
            .values()
            .flat_map(|s| s.iter().cloned())
            .collect();
        let manual: BTreeMap<String, Vec<String>> =
            serde_json::from_str(include_str!("attribute-cues.json"))
                .map_err(|e| ExtractionError(format!("Invalid bundled attribute cues: {e}")))?;
        let mut cues = Vec::new();
        for attribute in all {
            let literal = attribute.replace('_', " ");
            let mut patterns = vec![regex::escape(&literal).replace(' ', r"[\s_-]+")];
            if let Some(extra) = manual.get(&attribute) {
                patterns.extend(extra.iter().cloned());
            }
            // Do not guess singular forms for arbitrary words. Only a final regular s.
            if literal.ends_with('s') && !literal.ends_with("ss") {
                patterns.push(format!(
                    r"(?:[0-9][0-9,.]*|one|a|an)\s+{}",
                    regex::escape(&literal[..literal.len() - 1]).replace(' ', r"[\s_-]+")
                ));
            }
            let pattern = Regex::new(&format!(r"(?i)(?:{})\b", patterns.join("|")))
                .map_err(|e| ExtractionError(format!("Attribute {attribute}: {e}")))?;
            cues.push(Cue { attribute, pattern });
        }
        let regex = |s| Regex::new(s).map_err(|e| ExtractionError(format!("Splitter rule: {e}")));
        Ok(Self {
            fingerprint: index.fingerprint.clone(),
            attributes,
            cues,
            separators: regex(
                r"(?i);|[.!?](?:\s+|$)|,\s*|\s+\band\b\s+|\s+\bwith\b\s+|\s+\bbut\b\s+|\s+\bor\b\s+|\s+\bafter a\b\s+",
            )?,
            scope: regex(
                r"(?i)\b(?:if|unless|either|neither|between|versus|whereas|instead|except|respectively)\b|\b(?:used to|no longer)\b|\d\s*[–—]\s*\d|\b(?:not|never|cannot|without|might|could|may)\b[^;]*\band\b|n't\b[^;]*\band\b",
            )?,
            percent: regex(r"(?i)(?:over |under |at least |up to )?\d+(?:\.\d+)?\s*%")?,
            inherit_prefix: regex(
                r"(?i)^(?:(?:has|have|is|are|was|were|costs?|covers?|connects?|speaks?|supports?|includes?|offers?|serves?|runs?|comes?|keeps?|sends?|weighs?|lasts?|holds?|starts?|launched|opened|does|provides?|allows?|stores?|retains?)\b|[€$£0-9]|(?:a|an|or|after a)\s+[€$£0-9])",
            )?,
        })
    }

    /// Takes a structured normalized object directly. No intermediate CSV or display text.
    pub fn split(&self, row: NormalizedRow) -> Result<ParsedRow, ExtractionError> {
        if row.index_fingerprint != self.fingerprint || row.schema_version != super::SCHEMA_VERSION
        {
            return Err(ExtractionError(
                "Splitter and normalized row use different indexes".into(),
            ));
        }
        row.validate_alignment()?;
        let mut assertions = if let Some(result) = self.shared_subjects(&row) {
            result
        } else {
            self.clauses(&row)
        };
        if assertions.is_empty() {
            assertions.push(self.unresolved(
                &row,
                Span {
                    start: 0,
                    end: row.normalized_text.len(),
                },
                None,
                "empty_or_unsupported_text",
            ));
        }
        for (i, assertion) in assertions.iter_mut().enumerate() {
            assertion.occurrence_id = format!("{}:a{}", row.id, i + 1);
        }
        let paired = assertions.iter().filter(|a| a.status == "paired").count();
        let status = if paired == 0 {
            "unresolved"
        } else if paired == assertions.len() && row.issues.is_empty() {
            "split"
        } else {
            "partial"
        };
        Ok(ParsedRow {
            row,
            assertions,
            status: status.into(),
        })
    }

    fn shared_subjects(&self, row: &NormalizedRow) -> Option<Vec<AssertionText>> {
        let text = &row.normalized_text;
        if row.mentions.len() < 2 {
            return None;
        }
        let first = row.mentions.first()?;
        if !text[..first.normalized_span.start]
            .trim_matches(|c: char| c.is_whitespace() || c == '"')
            .is_empty()
        {
            return None;
        }
        // Only an explicitly coordinated subject list at the start of the row.
        for pair in row.mentions.windows(2) {
            let between = text[pair[0].normalized_span.end..pair[1].normalized_span.start].trim();
            if !matches!(between, "," | "and" | ", and" | "&") {
                return None;
            }
        }
        let tail_start = row.mentions.last()?.normalized_span.end;
        let tail = &text[tail_start..];
        let unaligned = || {
            Some(vec![self.unresolved(
                row,
                Span {
                    start: 0,
                    end: text.len(),
                },
                None,
                "unsupported_scope_or_alignment",
            )])
        };
        let is_respective = tail.to_lowercase().contains("respectively");
        if !is_respective && self.scope.is_match(tail) {
            return unaligned();
        }
        let mut attribute = None;
        for mention in &row.mentions {
            let attrs = self.find_attributes(&mention.subject, tail, &[]);
            if attrs.len() != 1 {
                return unaligned();
            }
            let current = attrs.into_iter().next()?;
            if attribute.as_ref().is_some_and(|a| *a != current) {
                return unaligned();
            }
            attribute = Some(current);
        }
        let attribute = attribute?;
        if is_respective {
            let values: Vec<_> = self.percent.find_iter(tail).collect();
            if values.len() != row.mentions.len() {
                return unaligned();
            }
            // Reject extra numeric claims outside the aligned percentage spans.
            let mut residue = tail.to_string();
            for value in values.iter().rev() {
                residue.replace_range(value.range(), " ");
            }
            if residue.chars().any(|c| c.is_ascii_digit()) || residue.contains(';') {
                return unaligned();
            }
            Some(
                row.mentions
                    .iter()
                    .zip(values)
                    .map(|(mention, value)| {
                        self.paired(
                            row,
                            Span {
                                start: tail_start + value.start(),
                                end: tail_start + value.end(),
                            },
                            mention,
                            &attribute,
                            "explicit_respectively_percent_list",
                        )
                    })
                    .collect(),
            )
        } else {
            // Sharing one phrase requires one scalar-looking clause, not an unaligned list.
            if tail.contains(',')
                || tail.contains(';')
                || tail.to_lowercase().contains(" and ")
                || has_general_or(tail)
            {
                return unaligned();
            }
            Some(
                row.mentions
                    .iter()
                    .map(|mention| {
                        self.paired(
                            row,
                            trim(
                                text,
                                Span {
                                    start: tail_start,
                                    end: text.len(),
                                },
                            ),
                            mention,
                            &attribute,
                            "explicit_shared_predicate",
                        )
                    })
                    .collect(),
            )
        }
    }

    fn clauses(&self, row: &NormalizedRow) -> Vec<AssertionText> {
        let text = &row.normalized_text;
        let mut clauses = Vec::new();
        let mut start = 0;
        for separator in self.separators.find_iter(text) {
            let span = Span {
                start: separator.start(),
                end: separator.end(),
            };
            if row
                .mentions
                .iter()
                .any(|m| m.normalized_span.overlaps(span))
            {
                continue;
            }
            let s = separator.as_str();
            if s.trim().eq_ignore_ascii_case("and") || s.trim().eq_ignore_ascii_case("with") {
                let right = text[span.end..].trim_start();
                let explicit_right = row
                    .mentions
                    .iter()
                    .any(|m| m.normalized_span.start == span.end);
                let independent_right = right.chars().next().is_some_and(char::is_uppercase);
                if !self.inherit_prefix.is_match(right) && !explicit_right && !independent_right {
                    continue;
                }
                if s.trim().eq_ignore_ascii_case("with") {
                    // Keep 'comes with 30 templates' together. Split 'costs €19 with 3 seats'.
                    let left = &text[start..span.start];
                    let left_mentions: Vec<_> = row
                        .mentions
                        .iter()
                        .filter(|m| {
                            m.normalized_span.start >= start && m.normalized_span.end <= span.start
                        })
                        .collect();
                    if let Some(subject) = left_mentions.first() {
                        let spans: Vec<_> = left_mentions
                            .iter()
                            .map(|m| Span {
                                start: m.normalized_span.start - start,
                                end: m.normalized_span.end - start,
                            })
                            .collect();
                        if self
                            .find_attributes(&subject.subject, left, &spans)
                            .is_empty()
                        {
                            continue;
                        }
                    }
                }
            }
            // Thousands, decimal/version punctuation, and date commas are not clauses.
            if s.starts_with(',')
                && text[..span.start]
                    .chars()
                    .next_back()
                    .is_some_and(|c| c.is_ascii_digit())
                && text[span.start + 1..]
                    .chars()
                    .next()
                    .is_some_and(|c| c.is_ascii_digit())
            {
                continue;
            }
            if s.starts_with(',') && looks_like_date_comma(text, span.start, span.end) {
                continue;
            }
            // Do not flatten alternatives, ranges, comparisons or conditions.
            let sentence_start = text[..span.start].rfind(';').map_or(0, |p| p + 1);
            let sentence_end = text[span.end..]
                .find(';')
                .map_or(text.len(), |p| span.end + p);
            if self.scope.is_match(&text[sentence_start..sentence_end]) {
                continue;
            }
            let billing_or = s.trim().eq_ignore_ascii_case("or")
                && text[span.end..].trim_start().starts_with(['€', '$', '£'])
                && text[..span.start].contains(['€', '$', '£']);
            if s.trim().eq_ignore_ascii_case("or") && !billing_or {
                continue;
            }
            let end = if s.starts_with(['.', '!', '?']) {
                span.start + 1
            } else {
                span.start
            };
            clauses.push((trim(text, Span { start, end }), s.to_string()));
            start = span.end;
        }
        clauses.push((
            trim(
                text,
                Span {
                    start,
                    end: text.len(),
                },
            ),
            String::new(),
        ));
        let mut result = Vec::new();
        let mut inherited: Option<&Mention> = None;
        for (span, separator) in clauses {
            if span.start == span.end {
                continue;
            }
            let clause = &text[span.start..span.end];
            let mentions: Vec<_> = row
                .mentions
                .iter()
                .filter(|m| m.normalized_span.overlaps(span))
                .collect();
            let distinct: BTreeSet<_> = mentions.iter().map(|m| &m.subject).collect();
            if self.scope.is_match(clause) || has_general_or(clause) {
                result.push(self.unresolved(
                    row,
                    span,
                    if distinct.len() == 1 {
                        mentions.first().copied()
                    } else {
                        inherited
                    },
                    "unsupported_scope_or_alignment",
                ));
                inherited = None;
                continue;
            }
            let subject = if distinct.len() == 1 {
                mentions.first().copied()
            } else if distinct.is_empty() && self.inherit_prefix.is_match(clause) {
                inherited
            } else {
                None
            };
            // A subject can only carry across supported conjunctions within this sentence.
            if let Some(subject) = subject {
                let local_mentions: Vec<_> = mentions
                    .iter()
                    .map(|m| Span {
                        start: m.normalized_span.start - span.start,
                        end: m.normalized_span.end - span.start,
                    })
                    .collect();
                let attrs = self.find_attributes(&subject.subject, clause, &local_mentions);
                if attrs.len() == 1 {
                    let attribute = attrs.iter().next().expect("one attribute");
                    let body = if clause.starts_with(&subject.subject) {
                        trim(
                            text,
                            Span {
                                start: span.start + subject.subject.len(),
                                end: span.end,
                            },
                        )
                    } else {
                        span
                    };
                    let rule = if distinct.is_empty() {
                        "shared_subject_attribute_cue"
                    } else {
                        "explicit_subject_attribute_cue"
                    };
                    result.push(self.paired(row, body, subject, attribute, rule));
                } else {
                    result.push(self.unresolved(
                        row,
                        span,
                        Some(subject),
                        if attrs.is_empty() {
                            "attribute_not_identified"
                        } else {
                            "multiple_attributes_in_fragment"
                        },
                    ));
                }
                inherited = Some(subject);
            } else {
                result.push(self.unresolved(
                    row,
                    span,
                    None,
                    if distinct.is_empty() {
                        "subject_not_identified"
                    } else {
                        "multiple_subjects_in_fragment"
                    },
                ));
                inherited = None;
            }
            if separator.starts_with(['.', '!', '?', ';']) {
                inherited = None;
            }
        }
        result
    }

    fn find_attributes(&self, subject: &str, clause: &str, mentions: &[Span]) -> BTreeSet<String> {
        let Some(allowed) = self.attributes.get(subject) else {
            return BTreeSet::new();
        };
        let mut matches = Vec::new();
        for cue in &self.cues {
            if !allowed.contains(&cue.attribute) {
                continue;
            }
            for m in cue.pattern.find_iter(clause) {
                let span = Span {
                    start: m.start(),
                    end: m.end(),
                };
                if clause[..m.start()]
                    .chars()
                    .next_back()
                    .is_some_and(|c| c.is_alphanumeric() || c == '_')
                    || clause[m.end()..]
                        .chars()
                        .next()
                        .is_some_and(|c| c.is_alphanumeric() || c == '_')
                {
                    continue;
                }
                if !mentions.iter().any(|s| s.overlaps(span)) {
                    matches.push((span, cue.attribute.clone()));
                }
            }
        }
        // Long phrases disambiguate e.g. minimum seats vs seats, annual price vs price.
        matches
            .iter()
            .filter(|(span, _)| {
                !matches.iter().any(|(other, _)| {
                    other.start <= span.start
                        && other.end >= span.end
                        && other.end - other.start > span.end - span.start
                })
            })
            .map(|(_, a)| a.clone())
            .collect()
    }

    fn paired(
        &self,
        row: &NormalizedRow,
        span: Span,
        subject: &Mention,
        attribute: &str,
        rule: &str,
    ) -> AssertionText {
        AssertionText {
            occurrence_id: String::new(),
            subject: Some(subject.subject.clone()),
            attribute: Some(attribute.into()),
            assertion_text: row.normalized_text[span.start..span.end].to_string(),
            normalized_span: span,
            source_spans: row.source_spans(span),
            subject_source_span: Some(subject.original_span),
            status: "paired".into(),
            reason: String::new(),
            rule: rule.into(),
        }
    }

    fn unresolved(
        &self,
        row: &NormalizedRow,
        span: Span,
        subject: Option<&Mention>,
        reason: &str,
    ) -> AssertionText {
        AssertionText {
            occurrence_id: String::new(),
            subject: subject.map(|s| s.subject.clone()),
            attribute: None,
            assertion_text: row.normalized_text[span.start..span.end].to_string(),
            normalized_span: span,
            source_spans: row.source_spans(span),
            subject_source_span: subject.map(|s| s.original_span),
            status: "unresolved".into(),
            reason: reason.into(),
            rule: "retain_fragment".into(),
        }
    }
}

fn trim(text: &str, span: Span) -> Span {
    let part = &text[span.start..span.end];
    let left = part.len() - part.trim_start().len();
    let right = part.trim_end().len();
    Span {
        start: span.start + left,
        end: span.start + right.max(left),
    }
}

fn looks_like_date_comma(text: &str, start: usize, end: usize) -> bool {
    let left = text[..start].to_lowercase();
    let right = text[end..].trim_start();
    let year = right
        .split(|c: char| !c.is_ascii_digit())
        .next()
        .unwrap_or("");
    year.len() == 4
        && [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "jan",
            "feb",
            "mar",
            "apr",
            "jun",
            "jul",
            "aug",
            "sep",
            "oct",
            "nov",
            "dec",
        ]
        .iter()
        .any(|month| {
            left.split_whitespace()
                .rev()
                .take(3)
                .any(|s| s.trim_end_matches('.') == *month)
        })
}

fn has_general_or(clause: &str) -> bool {
    let lower = clause.to_lowercase();
    lower.contains(" or ") && !lower.contains("or more") && !lower.contains("or less")
}
