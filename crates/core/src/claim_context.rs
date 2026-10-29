//! Explicit-document linguistic context, never factual evidence.
//!
//! Only a unique compatible antecedent can replace a leading reference. All
//! replacements retain original-row provenance and rebase Unicode candidate
//! offsets. An absent document ID disables cross-row memory completely.
use crate::extraction::{DocumentExtractor, LexiconIndex, Normalizer};
use crate::structured::ValueCandidate;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::LazyLock;

static REFERENCE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^\s*(?P<reference>its|his|her|their|our|it|he|she|they|the (?:platform|service|product|team|event|conference)|this (?:release|version|event))\b")
        .expect("source reference grammar")
});

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ContextBinding {
    pub subject: String,
    pub attribute: String,
    pub antecedent_row_id: String,
    /// Unicode scalar offsets in the original current text, half-open.
    pub start: usize,
    pub end: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PreparedClaim {
    pub text: String,
    pub candidates: Vec<ValueCandidate>,
    pub bindings: Vec<ContextBinding>,
    pub notes: Vec<String>,
}

pub struct ClaimContext {
    normalizer: Normalizer,
    extractor: DocumentExtractor,
    document_id: Option<String>,
}

impl ClaimContext {
    pub fn compile(lexicon: &Value) -> Result<Self, String> {
        let index =
            LexiconIndex::compile(&lexicon.to_string(), Vec::new()).map_err(|e| e.to_string())?;
        let normalizer = Normalizer::new(index).map_err(|e| e.to_string())?;
        let extractor = DocumentExtractor::new(&normalizer.index).map_err(|e| e.to_string())?;
        Ok(Self {
            normalizer,
            extractor,
            document_id: None,
        })
    }

    pub fn reset(&mut self) {
        self.extractor.reset();
        self.document_id = None;
    }

    pub fn prepare(
        &mut self,
        document_id: Option<&str>,
        row_id: &str,
        date: &str,
        text: &str,
        candidates: &[ValueCandidate],
    ) -> Result<PreparedClaim, String> {
        if text.chars().count() > 65_536 || candidates.len() > 4096 {
            return Err("context input size limit".into());
        }
        // Validate before changing state; malformed input cannot create a topic.
        let normalized = self
            .normalizer
            .normalize(row_id, date, text)
            .map_err(|e| e.to_string())?;
        let document_id = document_id.filter(|id| !id.trim().is_empty());
        if document_id.is_none() || self.document_id.as_deref() != document_id {
            self.extractor.reset();
        }
        self.document_id = document_id.map(str::to_owned);
        let parsed = if document_id.is_some() {
            self.extractor.split_in_document(normalized)
        } else {
            self.extractor.split(normalized)
        }
        .map_err(|e| e.to_string())?;
        let mut bindings = Vec::new();
        let mut edits: BTreeMap<(usize, usize), String> = BTreeMap::new();
        let mut notes = Vec::new();
        for assertion in &parsed.assertions {
            if !assertion.subject_candidates.is_empty()
                && assertion.reason == "ambiguous_preceding_subject"
            {
                notes.push("ambiguous_context:multiple compatible preceding subjects".into());
            }
            if document_id.is_none()
                || assertion.status != "paired"
                || assertion.subject_origin != "preceding_row"
            {
                continue;
            }
            let (Some(subject), Some(attribute), Some(source)) = (
                &assertion.subject,
                &assertion.attribute,
                assertion.evidence.iter().find(|e| e.role == "subject"),
            ) else {
                continue;
            };
            let (Some(start), Some(end)) = (
                assertion.source_spans.iter().map(|s| s.start).min(),
                assertion.source_spans.iter().map(|s| s.end).max(),
            ) else {
                continue;
            };
            let Some(clause) = text.get(start..end) else {
                continue;
            };
            let Some(captures) = REFERENCE.captures(clause) else {
                continue;
            };
            let mention = captures.name("reference").expect("named reference capture");
            let mention_start = start + mention.start();
            let mention_end = start + mention.end();
            let word = mention.as_str().to_ascii_lowercase();
            let replacement = if matches!(word.as_str(), "its" | "his" | "her" | "their" | "our") {
                format!("{subject}'s")
            } else {
                subject.clone()
            };
            if let Some(old) = edits.insert((mention_start, mention_end), replacement.clone())
                && old != replacement
            {
                return Err("inconsistent context binding".into());
            }
            bindings.push(ContextBinding {
                subject: subject.clone(),
                attribute: attribute.clone(),
                antecedent_row_id: source.row_id.clone(),
                start: text[..mention_start].chars().count(),
                end: text[..mention_end].chars().count(),
            });
        }
        let edits: Vec<_> = edits.into_iter().collect();
        if edits.windows(2).any(|e| e[0].0.1 > e[1].0.0) {
            return Err("overlapping context replacements".into());
        }
        let mut rewritten = String::with_capacity(text.len());
        let mut cursor = 0;
        for ((start, end), replacement) in &edits {
            rewritten.push_str(&text[cursor..*start]);
            rewritten.push_str(replacement);
            cursor = *end;
        }
        rewritten.push_str(&text[cursor..]);
        let character_edits: Vec<_> = edits
            .iter()
            .map(|((start, end), replacement)| {
                (
                    text[..*start].chars().count(),
                    text[..*end].chars().count(),
                    replacement.chars().count(),
                )
            })
            .collect();
        let text_len = text.chars().count();
        let mut rebased = Vec::new();
        for candidate in candidates {
            if candidate.start >= candidate.end || candidate.end > text_len {
                notes.push("invalid candidate character span in context preparation".into());
                continue;
            }
            if character_edits
                .iter()
                .any(|(s, e, _)| *s < candidate.end && candidate.start < *e)
            {
                notes.push("candidate overlaps a resolved reference; discarded".into());
                continue;
            }
            let rebase = |position: usize| {
                character_edits
                    .iter()
                    .filter(|(_, end, _)| *end <= position)
                    .fold(position as isize, |p, (start, end, length)| {
                        p + *length as isize - (*end - *start) as isize
                    }) as usize
            };
            rebased.push(ValueCandidate {
                start: rebase(candidate.start),
                end: rebase(candidate.end),
                value: candidate.value.clone(),
            });
        }
        Ok(PreparedClaim {
            text: rewritten,
            candidates: rebased,
            bindings,
            notes,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn context() -> ClaimContext {
        ClaimContext::compile(
            &serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap(),
        )
        .unwrap()
    }
    fn candidate(text: &str, raw: &str) -> ValueCandidate {
        let start = text.find(raw).unwrap();
        ValueCandidate {
            start: text[..start].chars().count(),
            end: text[..start + raw.len()].chars().count(),
            value: json!({"kind":"percent","value":99.9}),
        }
    }
    #[test]
    fn explicit_document_binds_product_despite_named_person_and_rebases_offsets() {
        let mut c = context();
        c.prepare(
            Some("doc"),
            "person",
            "2026-01-01",
            "Holdan joined Hooly.",
            &[],
        )
        .unwrap();
        c.prepare(
            Some("doc"),
            "product",
            "2026-01-01",
            "Hooly Cloud has 3 regions.",
            &[],
        )
        .unwrap();
        let text = "Its paid accounts carry a 99.9% uptime promise, which Holdan now owns.";
        let out = c
            .prepare(
                Some("doc"),
                "query",
                "2026-01-02",
                text,
                &[candidate(text, "99.9%")],
            )
            .unwrap();
        assert!(out.text.starts_with("Hooly Cloud's"), "{out:?}");
        assert_eq!(out.bindings[0].antecedent_row_id, "product");
        assert_eq!(out.bindings[0].attribute, "uptime_sla");
        assert_eq!(
            out.text
                .chars()
                .skip(out.candidates[0].start)
                .take(out.candidates[0].end - out.candidates[0].start)
                .collect::<String>(),
            "99.9%"
        );
    }
    #[test]
    fn missing_or_changed_document_never_inherits_subject() {
        let mut c = context();
        c.prepare(
            Some("a"),
            "source",
            "2026-01-01",
            "Hooly Cloud has 3 regions.",
            &[],
        )
        .unwrap();
        let text = "Its uptime SLA is 99.9%.";
        assert_eq!(
            c.prepare(Some("b"), "other", "2026-01-01", text, &[])
                .unwrap()
                .text,
            text
        );
        c.prepare(
            None,
            "source2",
            "2026-01-01",
            "Hooly Cloud has 3 regions.",
            &[],
        )
        .unwrap();
        assert_eq!(
            c.prepare(None, "none", "2026-01-01", text, &[])
                .unwrap()
                .text,
            text
        );
    }
    #[test]
    fn event_reference_survives_six_rows_without_fact_memory() {
        let mut c = context();
        c.prepare(
            Some("event"),
            "intro",
            "2026-01-01",
            "Hooly Cloud Next 2026 takes place on 4 May 2026.",
            &[],
        )
        .unwrap();
        for n in 0..5 {
            c.prepare(
                Some("event"),
                &format!("gap-{n}"),
                "2026-01-01",
                "The coffee is cold.",
                &[],
            )
            .unwrap();
        }
        let out = c
            .prepare(
                Some("event"),
                "sponsors",
                "2026-01-01",
                "Our 14 sponsors support the event.",
                &[],
            )
            .unwrap();
        assert!(
            out.bindings
                .iter()
                .any(|b| b.subject == "Hooly Cloud Next 2026" && b.attribute == "sponsors"),
            "{out:?}"
        );
    }
    #[test]
    fn invalid_candidate_is_reported_and_never_rebased_into_a_value() {
        let mut c = context();
        let out = c
            .prepare(
                None,
                "q",
                "2026-01-01",
                "Hello.",
                &[ValueCandidate {
                    start: 99,
                    end: 100,
                    value: json!({"kind":"quantity","value":1,"unit":"user"}),
                }],
            )
            .unwrap();
        assert!(out.candidates.is_empty());
        assert!(out.notes.iter().any(|n| n.contains("invalid candidate")));
    }
}
