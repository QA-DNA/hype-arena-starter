//! Shared text compilation. Linguistic context and value proposals are never evidence.
use crate::claim_context::{ClaimContext, ContextBinding};
use crate::claim_program::{CharSpan, ClaimExpr, ClaimProgram, ProgramParser};
use crate::extraction::{LexiconIndex, NormalizedRow, Normalizer};
use crate::model::Fact;
use crate::structured::{SchemaParser, ValueCandidate};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompiledClaim {
    /// Only ordinary positive conjunctions may enter a flat evidence interface.
    pub facts: Vec<Fact>,
    pub program: Option<ClaimProgram>,
    pub complete: bool,
    /// A known missing clause, unlike an ordinary statistical parser fallback.
    pub incomplete: bool,
    pub explicit_unknown: bool,
    pub bindings: Vec<ContextBinding>,
    pub notes: Vec<String>,
}

pub struct ClaimParser {
    schema: SchemaParser,
    program: ProgramParser,
    context: ClaimContext,
    normalizer: Normalizer,
}

impl ClaimParser {
    pub fn compile(lexicon: &Value) -> Result<Self, String> {
        Ok(Self {
            schema: SchemaParser::compile(lexicon)?,
            program: ProgramParser::compile(lexicon)?,
            context: ClaimContext::compile(lexicon)?,
            normalizer: Normalizer::new(
                LexiconIndex::compile(&lexicon.to_string(), Vec::new())
                    .map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?,
        })
    }

    pub fn reset(&mut self) {
        self.context.reset();
    }

    /// `document_id` is caller-supplied metadata, never guessed from row ID/date.
    /// An absent ID resets discourse state, preventing unrelated rows leaking topics.
    #[allow(clippy::too_many_arguments)]
    pub fn parse(
        &mut self,
        document_id: Option<&str>,
        row_id: &str,
        date: &str,
        text: &str,
        candidates: &[ValueCandidate],
        neural: &[Fact],
    ) -> Result<CompiledClaim, String> {
        let prepared = self
            .context
            .prepare(document_id, row_id, date, text, candidates)?;
        let normalized = self
            .normalizer
            .normalize(row_id, date, &prepared.text)
            .map_err(|e| e.to_string())?;
        let mut bound = self
            .schema
            .parse(&prepared.text, &prepared.candidates, neural);
        let mut program = self
            .program
            .parse(&prepared.text, &prepared.candidates, neural);
        let mut notes = prepared.notes;
        let explicit_unknown = bound
            .notes
            .iter()
            .chain(&program.notes)
            .any(|n| n.starts_with("explicit_unknown"));
        if program.structured && needs_program(&program.expression) {
            let rejected = ground_program(&mut program.expression, &prepared.text, &normalized);
            if rejected {
                program.complete = false;
                program
                    .notes
                    .push("unresolved:proposed owner is not grounded in the claim".into());
            }
            notes.extend(program.notes.iter().cloned());
            return Ok(CompiledClaim {
                facts: Vec::new(),
                complete: program.complete,
                incomplete: !program.complete,
                explicit_unknown,
                bindings: prepared.bindings,
                notes,
                program: Some(program),
            });
        }
        let before = bound.facts.len();
        bound
            .facts
            .retain(|f| owner_is_grounded(&prepared.text, &normalized, f));
        let rejected = before != bound.facts.len();
        let incomplete = rejected
            || requires_abstention(bound.complete, &bound.notes)
            || notes
                .iter()
                .any(|n| n.starts_with("invalid candidate") || n.starts_with("ambiguous_context"));
        if rejected {
            notes.push("unresolved:proposed owner is not grounded in the claim".into());
        }
        notes.extend(bound.notes);
        Ok(CompiledClaim {
            facts: bound.facts,
            program: None,
            complete: bound.complete && !incomplete,
            incomplete,
            explicit_unknown,
            bindings: prepared.bindings,
            notes,
        })
    }
}

fn needs_program(expression: &ClaimExpr) -> bool {
    match expression {
        ClaimExpr::Atom(_) => false,
        ClaimExpr::All(children) => children.iter().any(needs_program),
        _ => true,
    }
}

fn ground_program(expression: &mut ClaimExpr, text: &str, normalized: &NormalizedRow) -> bool {
    let bad = match expression {
        ClaimExpr::Atom(fact) => !owner_is_grounded(text, normalized, fact),
        ClaimExpr::Compare { left, right, .. } => [left, right].iter().any(|slot| {
            !owner_is_grounded(
                text,
                normalized,
                &Fact {
                    subject: slot.subject.clone(),
                    attribute: slot.attribute.clone(),
                    value: Value::Null,
                },
            )
        }),
        ClaimExpr::All(children) | ClaimExpr::Any(children) => {
            let mut rejected = false;
            for child in children {
                rejected |= ground_program(child, text, normalized);
            }
            return rejected;
        }
        ClaimExpr::Not(child) => return ground_program(child, text, normalized),
        ClaimExpr::Unknown { .. } | ClaimExpr::Unsupported { .. } => false,
    };
    if bad {
        *expression = ClaimExpr::Unknown {
            span: CharSpan {
                start: 0,
                end: text.chars().count(),
            },
            reason: "owner absent or used only as a comparison object".into(),
        };
    }
    bad
}

/// Ground an owner in text, including explicit unique common-word aliases.
/// Merely mentioning a competitor does not assign it the preceding attributes.
pub fn owner_is_grounded(text: &str, normalized: &NormalizedRow, fact: &Fact) -> bool {
    let is_object = |start: usize| {
        let Some(prefix) = text.get(..start) else {
            return true;
        };
        let prefix = prefix.trim_end().to_ascii_lowercase();
        [
            "unlike",
            "competes with",
            "compared with",
            "compared to",
            "as opposed to",
            "versus",
        ]
        .iter()
        .any(|phrase| prefix.ends_with(phrase))
    };
    if normalized
        .mentions
        .iter()
        .any(|m| m.subject == fact.subject && !is_object(m.original_span.start))
    {
        return true;
    }
    normalized.issues.iter().any(|issue| {
        if issue.candidates.len() != 1
            || issue.candidates[0] != fact.subject
            || is_object(issue.original_span.start)
        {
            return false;
        }
        let alias = issue.original_span.slice(text).unwrap_or("");
        let suffix = text.get(issue.original_span.end..).unwrap_or("");
        let possessive = suffix.starts_with("'s") || suffix.starts_with('\u{2019}');
        let field = fact.attribute.replace('_', " ");
        let lower = text.to_ascii_lowercase();
        let explicit_field = lower.contains(&field)
            || fact.attribute.ends_with("_version") && lower.contains("version");
        alias.chars().next().is_some_and(char::is_uppercase) && (possessive || explicit_field)
    })
}

pub fn requires_abstention(complete: bool, notes: &[String]) -> bool {
    if notes.iter().any(|n| {
        n.starts_with("explicit_unknown")
            || n.starts_with("input_limit")
            || n.contains("invalid candidate")
    }) {
        return true;
    }
    if notes
        .iter()
        .any(|n| n == "neural_fallback:no reliable schema binding")
    {
        return false;
    }
    !complete
        && notes
            .iter()
            .any(|n| n.starts_with("unresolved") || n.starts_with("ambiguous"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn lexicon() -> Value {
        json!({"subjects":[
        {"name":"Hooly AI Pro","aliases":["Pro"],"attributes":["price","seats"]},
        {"name":"Hooly Cloud","aliases":[],"attributes":["customers","uptime_sla"]}
    ],"events":[]})
    }

    #[test]
    fn unknown_owner_cannot_inherit_a_known_competitors_price() {
        let mut parser = ClaimParser::compile(&lexicon()).unwrap();
        let value = json!({"kind":"money","value":17,"currency":"EUR","per":"month"});
        let text = "Emberkeep costs EUR 17 per month and competes with Hooly AI Pro.";
        let start = text.find("17").unwrap();
        let out = parser
            .parse(
                None,
                "q",
                "2026-01-01",
                text,
                &[ValueCandidate {
                    value: value.clone(),
                    start,
                    end: start + 2,
                }],
                &[Fact {
                    subject: "Hooly AI Pro".into(),
                    attribute: "price".into(),
                    value,
                }],
            )
            .unwrap();
        assert!(out.facts.is_empty());
        assert!(out.incomplete);
    }

    #[test]
    fn disjunction_is_not_exported_as_two_accepted_facts() {
        let mut parser = ClaimParser::compile(&lexicon()).unwrap();
        let text = "Hooly AI Pro seats is 5 or Hooly Cloud customers is 10.";
        let candidates = [("5", 5), ("10", 10)].map(|(surface, n)| {
            let start = text.find(surface).unwrap();
            ValueCandidate {
                value: json!({"kind":"quantity","value":n,"unit":"seat"}),
                start,
                end: start + surface.len(),
            }
        });
        let out = parser
            .parse(None, "q", "2026-01-01", text, &candidates, &[])
            .unwrap();
        assert!(out.facts.is_empty(), "{out:?}");
        assert!(matches!(out.program.unwrap().expression, ClaimExpr::Any(_)));
    }
}
