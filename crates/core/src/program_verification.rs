//! Exact logical verification against labelled, date-scoped constraints.
//! Statistical continuity and parser confidence are deliberately separate.
use crate::belief::{Composition, LeafAssessment, compose};
use crate::claim_program::{ClaimProgram, ComparisonOp, TruthValue};
use crate::knowledge::{KnowledgeGraph, compare_recorded_values};
use crate::model::{Evidence, InputRow};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct ProgramVerification {
    pub truth: TruthValue,
    pub evidence: Vec<Evidence>,
    /// Hard logic and soft marginal bounds stay distinct. No model posterior is
    /// invented when an exact-resolution callback supplied only a proof status.
    pub composition: Composition,
}

pub fn verify(
    program: &ClaimProgram,
    row: &InputRow,
    graph: &KnowledgeGraph,
) -> ProgramVerification {
    let mut atom_evidence = Vec::new();
    let mut comparison_evidence = Vec::new();
    let composition = compose(
        &program.expression,
        &mut |fact| {
            let result = graph.resolve(fact, &row.date, &row.id, &row.text);
            let assessment = LeafAssessment::from_resolution(&result);
            atom_evidence.extend(result.evidence);
            assessment
        },
        &mut |left, op, right| {
            let lhs = graph.recorded_value(
                &left.subject,
                &left.attribute,
                left.date.as_deref().unwrap_or(&row.date),
                &row.id,
                &row.text,
            );
            let rhs = graph.recorded_value(
                &right.subject,
                &right.attribute,
                right.date.as_deref().unwrap_or(&row.date),
                &row.id,
                &row.text,
            );
            comparison_evidence.extend(lhs.evidence);
            comparison_evidence.extend(rhs.evidence);
            let result = lhs
                .value
                .as_ref()
                .zip(rhs.value.as_ref())
                .and_then(|(a, b)| {
                    compare_recorded_values(
                        a,
                        b,
                        match op {
                            ComparisonOp::Eq => "eq",
                            ComparisonOp::Ne => "ne",
                            ComparisonOp::Lt => "lt",
                            ComparisonOp::Le => "le",
                            ComparisonOp::Gt => "gt",
                            ComparisonOp::Ge => "ge",
                        },
                    )
                });
            let hard = match result {
                Some(true) => TruthValue::True,
                Some(false) => TruthValue::False,
                None => TruthValue::Unknown,
            };
            LeafAssessment {
                hard,
                estimate: None,
                evidence_ids: Vec::new(),
            }
        },
    );
    atom_evidence.extend(comparison_evidence);
    let mut evidence: Vec<Evidence> = Vec::new();
    for source in atom_evidence {
        if evidence.len() < 32
            && !evidence
                .iter()
                .any(|old| old.row_id == source.row_id && old.fact == source.fact)
        {
            evidence.push(source);
        }
    }
    ProgramVerification {
        truth: composition.hard,
        evidence,
        composition,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        Fact,
        claim_program::{CharSpan, ClaimExpr, SlotReference},
    };
    use serde_json::json;
    fn fact(owner: &str, value: i32) -> Fact {
        Fact {
            subject: owner.into(),
            attribute: "seats".into(),
            value: json!({"kind":"quantity","value":value,"unit":"seat"}),
        }
    }
    fn row() -> InputRow {
        InputRow {
            id: "query".into(),
            text: "independent query".into(),
            date: "2026-05-03".into(),
            ..Default::default()
        }
    }
    fn graph() -> KnowledgeGraph {
        KnowledgeGraph::compile(&[InputRow {
            id: "anchor".into(),
            text: "Hooly AI Pro seats is 5.".into(),
            date: "2026-05-03".into(),
            label: "true".into(),
            form: vec![fact("Hooly AI Pro", 5)],
        }])
    }
    fn program(expression: ClaimExpr) -> ClaimProgram {
        ClaimProgram {
            expression,
            complete: true,
            notes: vec![],
            structured: true,
        }
    }
    fn unknown() -> ClaimExpr {
        ClaimExpr::Unknown {
            span: CharSpan { start: 0, end: 1 },
            reason: "missing".into(),
        }
    }
    #[test]
    fn logical_dominance_and_negation_keep_unknown_unknown() {
        let cases = [
            (
                ClaimExpr::All(vec![ClaimExpr::Atom(fact("Hooly AI Pro", 6)), unknown()]),
                TruthValue::False,
            ),
            (
                ClaimExpr::Any(vec![ClaimExpr::Atom(fact("Hooly AI Pro", 5)), unknown()]),
                TruthValue::True,
            ),
            (ClaimExpr::Not(Box::new(unknown())), TruthValue::Unknown),
            (
                ClaimExpr::All(vec![ClaimExpr::Atom(fact("Hooly AI Pro", 5)), unknown()]),
                TruthValue::Unknown,
            ),
        ];
        for (expr, expected) in cases {
            assert_eq!(verify(&program(expr), &row(), &graph()).truth, expected);
        }
    }
    #[test]
    fn comparisons_require_both_exact_values_on_the_requested_dates() {
        let reference = |name: &str| SlotReference {
            subject: name.into(),
            attribute: "seats".into(),
            date: None,
        };
        let expr = ClaimExpr::Compare {
            left: reference("Hooly AI Pro"),
            op: ComparisonOp::Gt,
            right: reference("Hooly Cloud"),
        };
        assert_eq!(
            verify(&program(expr.clone()), &row(), &graph()).truth,
            TruthValue::Unknown
        );
        let graph = KnowledgeGraph::compile(&[
            InputRow {
                id: "left".into(),
                text: "Left source".into(),
                date: row().date,
                label: "true".into(),
                form: vec![fact("Hooly AI Pro", 5)],
            },
            InputRow {
                id: "right".into(),
                text: "Right source".into(),
                date: row().date,
                label: "true".into(),
                form: vec![fact("Hooly Cloud", 4)],
            },
        ]);
        let result = verify(&program(expr.clone()), &row(), &graph);
        assert_eq!(result.truth, TruthValue::True);
        assert_eq!(result.evidence.len(), 2);
        let mut earlier = row();
        earlier.date = "2026-05-02".into();
        assert_eq!(
            verify(&program(expr), &earlier, &graph).truth,
            TruthValue::Unknown
        );
    }
}
