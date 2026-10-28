//! Bounded discourse resolution. Mentioned claims are never accepted as true facts.
use super::{
    ExtractionError, LexiconIndex, NormalizedRow, ParsedRow, Qualifier, SourceReference, Span,
    Splitter,
};
use regex::Regex;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

const WINDOW: usize = 8;
const MAX_TOPICS: usize = 64;
#[derive(Clone)]
struct Topic {
    subject: String,
    source: SourceReference,
    ordinal: usize,
    person: bool,
    versions: Vec<Qualifier>,
}

/// One instance per ordered CSV stream. `reset` starts a new document/file.
/// Context stores only bounded mention metadata, never full previous rows or labels.
pub struct DocumentExtractor {
    splitter: Splitter,
    topics: VecDeque<Topic>,
    ordinal: usize,
    date: String,
    personal: Regex,
    referential: Regex,
    version_reference: Regex,
    named_actor: Regex,
    named_plan: Regex,
    unlisted_names: Vec<String>,
}

impl DocumentExtractor {
    pub fn new(index: &LexiconIndex) -> Result<Self, ExtractionError> {
        let re = |s| Regex::new(s).map_err(|e| ExtractionError(format!("Discourse rule: {e}")));
        Ok(Self {
            unlisted_names: index
                .subjects
                .iter()
                .filter_map(|s| s.name.strip_prefix("Hooly "))
                .filter(|s| s.contains(' '))
                .map(str::to_string)
                .collect(),
            named_plan: re(r"^(?:and )?(?:the |a )?[A-Z][A-Za-z]+ (?:plan|tier|subscription)\b")?,
            named_actor: re(
                r"^(?:and )?[A-Z][a-z]+(?: [A-Z][a-z]+)? (?:costs|has|holds|supports|stores)\b",
            )?,
            splitter: Splitter::new(index)?,
            topics: VecDeque::new(),
            ordinal: 0,
            date: String::new(),
            personal: re(r"(?i)^(?:he|she|his|her|they|their)\b")?,
            referential: re(
                r"(?i)^(?:it|its|he|she|his|her|they|their|the (?:platform|service|product|team)|this (?:release|version))\b",
            )?,
            version_reference: re(r"(?i)^(?:it|its|this (?:release|version))\b")?,
        })
    }
    pub fn reset(&mut self) {
        self.topics.clear();
        self.ordinal = 0;
        self.date.clear();
    }

    pub fn split(&mut self, row: NormalizedRow) -> Result<ParsedRow, ExtractionError> {
        // Validate/parse before mutating stream state: a failed call is retryable.
        let mut parsed = self.splitter.split(row)?;
        self.ordinal += 1;
        parsed.input_ordinal = Some(self.ordinal);
        let boundary = if self.ordinal == 1 {
            "stream_start"
        } else if parsed.row.date.is_empty() || self.date != parsed.row.date {
            "date_boundary"
        } else {
            "same_date_candidate_block"
        };
        if boundary != "same_date_candidate_block" {
            self.topics.clear();
        }
        self.date.clone_from(&parsed.row.date);
        self.topics
            .retain(|t| self.ordinal.saturating_sub(t.ordinal) <= WINDOW);
        parsed.context_boundary = boundary.into();

        // An explicit new product topic prevents stale cross-product inheritance.
        let primary: BTreeSet<_> = parsed
            .assertions
            .iter()
            .filter(|a| a.status == "paired")
            .filter_map(|a| a.subject.clone())
            .filter(|s| !self.is_person(s))
            .collect();
        if !primary.is_empty() {
            self.topics
                .retain(|t| t.person || primary.iter().any(|s| related(s, &t.subject)));
        }

        let foreign_actor = self.named_actor.is_match(&parsed.row.normalized_text)
            && parsed.row.mentions.is_empty()
            && !self.referential.is_match(&parsed.row.normalized_text);
        for assertion in &mut parsed.assertions {
            if foreign_actor {
                continue;
            }
            if assertion.status == "paired"
                || assertion.group_id.is_some()
                || matches!(
                    assertion.reason.as_str(),
                    "complexity_limit"
                        | "unsupported_scope_or_alignment"
                        | "multiple_attributes_in_fragment"
                )
            {
                continue;
            }
            let wording = assertion.assertion_text.trim();
            let reference = self.referential.is_match(wording);
            // Explicit subjects take precedence. A leading pronoun can refer to a
            // different grammatical role than a person named later in the clause.
            if !reference && (!parsed.row.mentions.is_empty() || assertion.subject.is_some()) {
                continue;
            }
            if !reference
                && (self.named_actor.is_match(wording)
                    || self.named_plan.is_match(wording)
                    || self
                        .unlisted_names
                        .iter()
                        .any(|name| wording.contains(name)))
            {
                continue;
            }
            let personal = self.personal.is_match(wording);
            let mentions: Vec<_> = parsed
                .row
                .mentions
                .iter()
                .filter(|m| m.normalized_span.overlaps(assertion.normalized_span))
                .map(|m| Span {
                    start: m
                        .normalized_span
                        .start
                        .saturating_sub(assertion.normalized_span.start),
                    end: m
                        .normalized_span
                        .end
                        .saturating_sub(assertion.normalized_span.start),
                })
                .collect();
            let mut candidates: BTreeMap<String, (Topic, BTreeSet<String>)> = BTreeMap::new();
            for topic in &self.topics {
                if reference && personal != topic.person {
                    continue;
                }
                let attrs = self
                    .splitter
                    .find_attributes(&topic.subject, wording, &mentions);
                if !attrs.is_empty() {
                    candidates.insert(topic.subject.clone(), (topic.clone(), attrs));
                }
            }
            assertion.subject_candidates = candidates.keys().cloned().collect();
            if candidates.len() == 1 {
                let (_, (topic, attrs)) = candidates.into_iter().next().expect("one candidate");
                if attrs.len() == 1 {
                    assertion.subject = Some(topic.subject);
                    assertion.attribute = attrs.into_iter().next();
                    assertion.status = "paired".into();
                    assertion.reason.clear();
                    assertion.rule = "compatible_preceding_topic".into();
                    assertion.subject_origin = "preceding_row".into();
                    assertion.subject_source_span = None;
                    assertion.evidence.retain(|r| r.role != "subject");
                    assertion.evidence.push(topic.source);
                    if self.version_reference.is_match(wording) {
                        let ambiguous = topic.versions.len() > 1;
                        for mut version in topic.versions {
                            version.origin = if ambiguous {
                                "ambiguous_preceding_row"
                            } else {
                                "preceding_row"
                            }
                            .into();
                            assertion.qualifiers.push(version);
                        }
                    }
                } else {
                    assertion.reason = "context_multiple_attributes".into();
                }
            } else if !assertion.subject_candidates.is_empty() {
                assertion.reason = "ambiguous_preceding_subject".into();
            }
        }
        // Only explicit mentions refresh topics. Resolved pronoun chains cannot
        // extend the window indefinitely or create independent supporting sources.
        for mention in parsed.row.mentions.iter().take(MAX_TOPICS) {
            let person = self.is_person(&mention.subject);
            let versions = parsed
                .assertions
                .iter()
                .filter(|a| a.subject.as_ref() == Some(&mention.subject))
                .flat_map(|a| a.qualifiers.iter())
                .filter(|q| q.kind == "version" && q.origin == "explicit")
                .take(4)
                .cloned()
                .fold(Vec::new(), |mut v, q| {
                    if !v.contains(&q) {
                        v.push(q);
                    }
                    v
                });
            self.topics.retain(|t| t.subject != mention.subject);
            self.topics.push_back(Topic {
                subject: mention.subject.clone(),
                ordinal: self.ordinal,
                person,
                versions,
                source: SourceReference {
                    row_id: parsed.row.id.clone(),
                    span: mention.original_span,
                    role: "subject".into(),
                },
            });
            while self.topics.len() > MAX_TOPICS {
                self.topics.pop_front();
            }
        }
        refresh_status(&mut parsed);
        Ok(parsed)
    }
    fn is_person(&self, subject: &str) -> bool {
        // Lexicon-derived role hint, not name/gender or external world knowledge.
        self.splitter.allowed(subject, "joined")
            || self.splitter.allowed(subject, "previous_employer")
    }
}
fn related(a: &str, b: &str) -> bool {
    a == b
        || a.strip_prefix(b).is_some_and(|tail| tail.starts_with(' '))
        || b.strip_prefix(a).is_some_and(|tail| tail.starts_with(' '))
}
pub(super) fn refresh_status(parsed: &mut ParsedRow) {
    let paired = parsed
        .assertions
        .iter()
        .filter(|a| a.status == "paired")
        .count();
    parsed.status = if paired == 0 {
        "unresolved"
    } else if paired == parsed.assertions.len() && parsed.row.issues.is_empty() {
        "split"
    } else {
        "partial"
    }
    .into();
}
