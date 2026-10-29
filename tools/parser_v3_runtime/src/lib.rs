//! Input-only bridge to the independent parser evaluator. No scorer is linked.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use veridyct_core::{
    Fact,
    claim_context::ClaimContext,
    claim_parsing::ClaimParser,
    claim_program::ClaimExpr,
    structured::{SchemaParser, ValueCandidate},
};
use veridyct_extractor::{Extractor, Options, grammar::Grammar};

#[cfg(feature = "frozen-baseline")]
mod model {
    pub use veridyct_core::Fact;
}
#[cfg(feature = "frozen-baseline")]
include!(concat!(env!("OUT_DIR"), "/frozen.rs"));

pub const MAX_TEXT_CHARS: usize = 65_536;
pub const MAX_PRIOR_TEXTS: usize = 64;
pub const MAX_CONTEXT_CHARS: usize = 262_144;

#[derive(Clone, Debug, Deserialize)]
pub struct Input {
    pub id: String,
    pub document_id: String,
    pub text: String,
    pub context: InputContext,
}

#[derive(Clone, Debug, Deserialize)]
pub struct InputContext {
    pub enabled: bool,
    pub document_id: String,
    pub prior_texts: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Prediction {
    pub id: String,
    pub status: String,
    pub ast: Value,
    pub assertions: Vec<Fact>,
    pub notes: Vec<String>,
    pub proposal_sha256: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Backend {
    Program,
    Schema,
    #[cfg(feature = "frozen-baseline")]
    FrozenSchema,
}

pub struct Adapter {
    grammar: Grammar,
    schema: SchemaParser,
    shared: ClaimParser,
    context: ClaimContext,
    native: Option<Extractor>,
    backend: Backend,
    variant: String,
    #[cfg(feature = "frozen-baseline")]
    frozen_schema: frozen_structured::SchemaParser,
}

impl Adapter {
    pub fn compile(
        lexicon: &Value,
        backend: Backend,
        variant: &str,
        model: Option<&str>,
    ) -> Result<Self, String> {
        if ![
            "none",
            "reverse_candidates",
            "shuffle_candidates",
            "replace_candidate_ids",
            "inject_untrusted_gold_fields",
            "reverse_document_order",
        ]
        .contains(&variant)
        {
            return Err("unknown adapter variant".into());
        }
        Ok(Self {
            // The existing selected-v2 literal grammar is frozen source. Only
            // public lexicon names are supplied; no oracle values or families.
            grammar: Grammar::new(lexicon, &[]).map_err(|e| e.to_string())?,
            schema: SchemaParser::compile(lexicon)?,
            shared: ClaimParser::compile(lexicon)?,
            context: ClaimContext::compile(lexicon)?,
            native: model
                .map(|path| {
                    Extractor::load(
                        path,
                        Options {
                            threads: 1,
                            batch_size: 1,
                            ..Options::default()
                        },
                    )
                    .map_err(|e| e.to_string())
                })
                .transpose()?,
            backend,
            variant: variant.to_owned(),
            #[cfg(feature = "frozen-baseline")]
            frozen_schema: frozen_structured::SchemaParser::compile(lexicon)?,
        })
    }

    pub fn parse(&mut self, input: Input) -> Prediction {
        let id = input.id.clone();
        match self.parse_inner(&input) {
            Ok(prediction) => prediction,
            Err(error) => Prediction {
                id,
                status: "unresolved".into(),
                ast: Value::Null,
                assertions: Vec::new(),
                notes: vec![error],
                proposal_sha256: None,
            },
        }
    }

    fn parse_inner(&mut self, input: &Input) -> Result<Prediction, String> {
        if input.text.chars().take(MAX_TEXT_CHARS + 1).count() > MAX_TEXT_CHARS
            || input.context.prior_texts.len() > MAX_PRIOR_TEXTS
            || input
                .context
                .prior_texts
                .iter()
                .map(|t| t.chars().take(MAX_CONTEXT_CHARS + 1).count())
                .sum::<usize>()
                > MAX_CONTEXT_CHARS
        {
            return Err("input/context size limit".into());
        }
        let raw_candidates = self
            .grammar
            .binding_candidates(&input.text)
            .map_err(|e| format!("unsupported_value grammar: {e}"))?;
        if raw_candidates.len() > 4096 {
            return Err("candidate limit".into());
        }
        // Candidate IDs and additional fields are an untrusted envelope. Each
        // nuisance run really changes it, then the same typed boundary drops it.
        let mut envelopes: Vec<_> = raw_candidates
            .into_iter()
            .enumerate()
            .map(|(i, c)| json!({"id":format!("candidate-{i}"),"start":c.start,"end":c.end,"value":c.value}))
            .collect();
        match self.variant.as_str() {
            "reverse_candidates" => envelopes.reverse(),
            "shuffle_candidates" => {
                let n = envelopes.len();
                for i in (1..n).rev() {
                    envelopes.swap(i, (i.wrapping_mul(1_664_525) + 1_013_904_223) % (i + 1));
                }
            }
            "replace_candidate_ids" => {
                for (i, envelope) in envelopes.iter_mut().enumerate() {
                    envelope["id"] = json!(format!("unrelated-{}", 999_999 - i));
                }
            }
            "inject_untrusted_gold_fields" => {
                for envelope in &mut envelopes {
                    envelope["gold"] =
                        json!({"subject":"made-up-owner","family":"untrusted","truth":true});
                    envelope["expected_attribute"] = json!("untrusted_attribute");
                }
            }
            _ => {}
        }
        let mut candidates: Vec<ValueCandidate> = envelopes
            .into_iter()
            .map(serde_json::from_value)
            .collect::<Result<_, _>>()
            .map_err(|e| e.to_string())?;
        // Canonical ordering makes equal proposals independent of upstream order.
        candidates.sort_by_cached_key(|c| (c.start, c.end, c.value.to_string()));
        candidates.dedup();

        self.context.reset();
        let enabled = input.context.enabled
            && !input.document_id.is_empty()
            && input.context.document_id == input.document_id;
        let document = enabled.then_some("explicit-document");
        if enabled {
            for prior in &input.context.prior_texts {
                self.context
                    .prepare(document, "prior", "2000-01-01", prior, &[])?;
            }
        }
        let prepared =
            self.context
                .prepare(document, "current", "2000-01-01", &input.text, &candidates)?;
        let mut notes = prepared.notes;
        let neural: Vec<Fact> = if let Some(native) = &mut self.native {
            // Inference uses text only, with no implicit previous-row memory.
            let encoded = native
                .encode(&prepared.text, "", "text-only")
                .map_err(|e| e.to_string())?;
            native
                .predict_encoded(&[&encoded])
                .map_err(|e| e.to_string())?
                .into_iter()
                .flatten()
                .map(|a| serde_json::from_value(a.atom).map_err(|e| e.to_string()))
                .collect::<Result<_, _>>()?
        } else {
            Vec::new()
        };
        let proposal_sha256 =
            Some(format!("{:x}", Sha256::digest(serde_json::to_vec(
            &json!({"text":prepared.text,"candidates":prepared.candidates,"neural":neural}),
        ).expect("proposal JSON"))));
        let (expression, complete) = match self.backend {
            Backend::Program => {
                self.shared.reset();
                if enabled {
                    for prior in &input.context.prior_texts {
                        self.shared
                            .parse(document, "prior", "2000-01-01", prior, &[], &[])?;
                    }
                }
                let compiled = self.shared.parse(
                    document,
                    "current",
                    "2000-01-01",
                    &input.text,
                    &candidates,
                    &neural,
                )?;
                notes.extend(compiled.notes);
                let expression = compiled
                    .program
                    .map(|p| p.expression)
                    .unwrap_or_else(|| facts_expression(compiled.facts));
                (expression, compiled.complete)
            }
            Backend::Schema => {
                let parsed = self
                    .schema
                    .parse(&prepared.text, &prepared.candidates, &neural);
                notes.extend(parsed.notes);
                (facts_expression(parsed.facts), parsed.complete)
            }
            #[cfg(feature = "frozen-baseline")]
            Backend::FrozenSchema => {
                let candidates: Vec<_> = prepared
                    .candidates
                    .iter()
                    .map(|c| frozen_structured::ValueCandidate {
                        start: c.start,
                        end: c.end,
                        value: c.value.clone(),
                    })
                    .collect();
                let parsed = self
                    .frozen_schema
                    .parse(&prepared.text, &candidates, &neural);
                notes.extend(parsed.notes);
                (facts_expression(parsed.facts), parsed.complete)
            }
        };
        let ast = export_ast(&expression).unwrap_or(Value::Null);
        let mut assertions = Vec::new();
        collect_assertions(&expression, false, &mut assertions);
        assertions.sort_by_cached_key(|f| serde_json::to_string(f).expect("Fact JSON"));
        assertions.dedup();
        notes.sort();
        notes.dedup();
        let status = if complete && !ast.is_null() {
            "parsed"
        } else if !assertions.is_empty() || !ast.is_null() {
            "partial"
        } else if notes.iter().any(|n| n.to_lowercase().contains("ambigu")) {
            "ambiguous"
        } else {
            "unresolved"
        };
        Ok(Prediction {
            id: input.id.clone(),
            status: status.into(),
            ast,
            assertions,
            notes,
            proposal_sha256,
        })
    }
}

pub fn facts_expression(facts: Vec<Fact>) -> ClaimExpr {
    let mut expressions: Vec<_> = facts.into_iter().map(ClaimExpr::Atom).collect();
    if expressions.len() == 1 {
        expressions.remove(0)
    } else {
        ClaimExpr::All(expressions)
    }
}

pub fn export_ast(expression: &ClaimExpr) -> Option<Value> {
    Some(match expression {
        ClaimExpr::Atom(fact) => json!({"type":"atom","fact":fact}),
        ClaimExpr::All(children) | ClaimExpr::Any(children) => {
            let children = children
                .iter()
                .map(export_ast)
                .collect::<Option<Vec<_>>>()?;
            match children.len() {
                0 => return None,
                1 => children.into_iter().next()?,
                _ => {
                    json!({"type":if matches!(expression, ClaimExpr::All(_)) {"all"} else {"any"},"children":children})
                }
            }
        }
        ClaimExpr::Not(child) => json!({"type":"not","child":export_ast(child)?}),
        ClaimExpr::Compare { left, op, right } => {
            let reference = |slot: &veridyct_core::claim_program::SlotReference| {
                let mut out = json!({"subject":slot.subject,"attribute":slot.attribute});
                if let Some(date) = &slot.date {
                    out["date"] = json!(date);
                }
                out
            };
            json!({"type":"compare","left":reference(left),"op":op,"right":reference(right)})
        }
        ClaimExpr::Unknown { .. } | ClaimExpr::Unsupported { .. } => return None,
    })
}

fn collect_assertions(expression: &ClaimExpr, negative: bool, out: &mut Vec<Fact>) {
    match expression {
        ClaimExpr::Atom(fact) => {
            let mut fact = fact.clone();
            if negative {
                let inverse = match fact.value["op"].as_str().unwrap_or("eq") {
                    "eq" => "ne",
                    "ne" => "eq",
                    "lt" => "ge",
                    "le" => "gt",
                    "gt" => "le",
                    "ge" => "lt",
                    _ => return,
                };
                fact.value["op"] = json!(inverse);
            }
            out.push(fact);
        }
        ClaimExpr::All(children) | ClaimExpr::Any(children) => {
            for child in children {
                collect_assertions(child, negative, out);
            }
        }
        ClaimExpr::Not(child) => collect_assertions(child, !negative, out),
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lexicon() -> Value {
        json!({"subjects":[
            {"name":"Hooly Cloud","aliases":[],"attributes":["regions","uptime_sla"]},
            {"name":"Hooly AI Pro","aliases":["Pro"],"attributes":["price"]}
        ],"events":[]})
    }

    fn input(text: &str) -> Input {
        Input {
            id: "opaque".into(),
            document_id: "doc".into(),
            text: text.into(),
            context: InputContext {
                enabled: true,
                document_id: "doc".into(),
                prior_texts: Vec::new(),
            },
        }
    }

    #[test]
    fn ids_and_untrusted_gold_never_change_prediction() {
        let mut adapter = Adapter::compile(&lexicon(), Backend::Program, "none", None).unwrap();
        let a = adapter.parse(input("Hooly Cloud has 3 regions."));
        let mut value = serde_json::to_value(json!({"id":"replacement","document_id":"doc",
            "text":"Hooly Cloud has 3 regions.","context":{"enabled":true,"document_id":"doc","prior_texts":[]},
            "gold":{"subject":"invented","value":999},"form":[{"subject":"invented"}],"label":"false"})).unwrap();
        value["candidates"] = json!([{"start":0,"end":10,"value":{"kind":"money","value":999}}]);
        let b = adapter.parse(serde_json::from_value(value).unwrap());
        assert_eq!(a.ast, b.ast);
        assert_eq!(a.assertions, b.assertions);
        assert_eq!(a.notes, b.notes);
        assert_eq!(a.status, b.status);
        assert_eq!(a.proposal_sha256, b.proposal_sha256);
        assert_eq!(a.assertions[0].subject, "Hooly Cloud");
    }

    #[test]
    fn all_candidate_envelope_variants_execute_and_preserve_parse() {
        let row =
            input("Hooly Cloud's regions is 3 regions and Hooly Cloud's uptime SLA is 99.9%.");
        let a = Adapter::compile(&lexicon(), Backend::Program, "none", None)
            .unwrap()
            .parse(row.clone());
        for variant in [
            "reverse_candidates",
            "shuffle_candidates",
            "replace_candidate_ids",
            "inject_untrusted_gold_fields",
        ] {
            let b = Adapter::compile(&lexicon(), Backend::Program, variant, None)
                .unwrap()
                .parse(row.clone());
            assert_eq!(a.ast, b.ast, "{variant}");
            assert_eq!(a.assertions, b.assertions, "{variant}");
            assert_eq!(a.proposal_sha256, b.proposal_sha256, "{variant}");
        }
    }

    #[test]
    fn explicit_context_resolves_and_mismatched_or_disabled_context_abstains() {
        let mut adapter = Adapter::compile(&lexicon(), Backend::Program, "none", None).unwrap();
        let mut row = input("Its uptime SLA is 99.9%.");
        row.context.prior_texts = vec!["Hooly Cloud has 3 regions.".into()];
        let enabled = adapter.parse(row.clone());
        assert_eq!(enabled.assertions.len(), 1, "{enabled:?}");
        assert_eq!(enabled.assertions[0].subject, "Hooly Cloud");
        row.context.document_id = "different-document".into();
        assert!(adapter.parse(row.clone()).assertions.is_empty());
        row.context.document_id = "doc".into();
        row.context.enabled = false;
        assert!(adapter.parse(row).assertions.is_empty());
        // Reusing the adapter must not retain the previous row's declared topic.
        assert!(
            adapter
                .parse(input("Its uptime SLA is 99.9%."))
                .assertions
                .is_empty()
        );
    }

    #[test]
    fn excessive_text_and_context_reject_before_candidate_generation() {
        let mut adapter = Adapter::compile(&lexicon(), Backend::Program, "none", None).unwrap();
        for row in [
            input(&"é".repeat(MAX_TEXT_CHARS + 1)),
            Input {
                context: InputContext {
                    prior_texts: vec!["x".into(); MAX_PRIOR_TEXTS + 1],
                    ..input("x").context
                },
                ..input("x")
            },
        ] {
            let out = adapter.parse(row);
            assert_eq!(out.status, "unresolved");
            assert!(out.ast.is_null());
            assert!(out.assertions.is_empty());
            assert!(out.notes[0].contains("limit"));
        }
    }

    #[test]
    fn unicode_currency_and_foreign_owner_have_independent_controls() {
        let mut adapter = Adapter::compile(&lexicon(), Backend::Program, "none", None).unwrap();
        let known = adapter.parse(input("Hooly AI Pro's price is €17 per month."));
        assert_eq!(known.assertions.len(), 1, "{known:?}");
        assert_eq!(known.assertions[0].value["kind"], "money");
        assert_eq!(known.assertions[0].value["currency"], "EUR");
        assert_eq!(known.assertions[0].value["per"], "month");
        let foreign = adapter.parse(input(
            "Emberkeep offers €17 per month and competes with Hooly AI Pro.",
        ));
        assert!(foreign.assertions.is_empty(), "{foreign:?}");
        assert!(foreign.ast.is_null());
    }
}
