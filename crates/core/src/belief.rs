//! Validated three-class masses and dependence-safe logical composition.
//!
//! Exact evidence decisions and model estimates are separate channels. Nothing
//! here turns a model score into a proof or claims empirical calibration. Soft
//! composition uses marginal Frechet bounds, never an independence assumption.
//! Bounds are conditional on coherent supplied marginals; they cannot repair
//! biased estimates or check domain-specific joint feasibility.
//! `BeliefBounds::uncommitted_mass` puts unidentified mass in unsure; that is an
//! epistemic reporting convention, not a calibrated class posterior.
use crate::claim_program::{
    ClaimExpr, ComparisonOp, MAX_PROGRAM_DEPTH, MAX_PROGRAM_NODES, SlotReference, TruthValue,
};
use crate::knowledge::{Resolution, Status};
use crate::model::{Fact, Probabilities};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

/// Only roundoff-sized sum errors are accepted, not unnormalized model scores.
const SUM_TOLERANCE: f64 = 16.0 * f64::EPSILON;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BeliefError {
    NonFinite,
    OutOfRange,
    NotUnitSum,
}

impl fmt::Display for BeliefError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::NonFinite => "belief masses must be finite",
            Self::OutOfRange => "belief masses must lie in [0, 1]",
            Self::NotUnitSum => "belief masses must sum to one",
        })
    }
}

impl std::error::Error for BeliefError {}

/// A validated mass triple. Deserialization must go through `try_new` or the
/// legacy conversion; private fields prevent bypassing validation.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct Belief {
    p_true: f64,
    p_false: f64,
    p_unsure: f64,
}

impl Belief {
    pub const TRUE: Self = Self {
        p_true: 1.0,
        p_false: 0.0,
        p_unsure: 0.0,
    };
    pub const FALSE: Self = Self {
        p_true: 0.0,
        p_false: 1.0,
        p_unsure: 0.0,
    };
    /// A categorical unknown/unsure mass, distinct from an unavailable estimate.
    pub const UNKNOWN: Self = Self {
        p_true: 0.0,
        p_false: 0.0,
        p_unsure: 1.0,
    };

    pub fn try_new(mut p_true: f64, mut p_false: f64, p_unsure: f64) -> Result<Self, BeliefError> {
        let parts = [p_true, p_false, p_unsure];
        if parts.iter().any(|p| !p.is_finite()) {
            return Err(BeliefError::NonFinite);
        }
        if parts.iter().any(|p| !(0.0..=1.0).contains(p)) {
            return Err(BeliefError::OutOfRange);
        }
        if ((p_true + p_false + p_unsure) - 1.0).abs() > SUM_TOLERANCE {
            return Err(BeliefError::NotUnitSum);
        }
        // Repair only the admitted floating-point residual. Do not normalize
        // arbitrary scores or impose a class balance.
        if p_true + p_false > 1.0 {
            if p_true >= p_false {
                p_true = 1.0 - p_false;
            } else {
                p_false = 1.0 - p_true;
            }
        }
        Ok(Self::from_committed(p_true, p_false))
    }

    fn from_committed(p_true: f64, p_false: f64) -> Self {
        Self {
            p_true,
            p_false,
            p_unsure: (1.0 - (p_true + p_false)).max(0.0),
        }
    }

    pub fn p_true(self) -> f64 {
        self.p_true
    }
    pub fn p_false(self) -> f64 {
        self.p_false
    }
    pub fn p_unsure(self) -> f64 {
        self.p_unsure
    }

    pub fn negated(self) -> Self {
        Self {
            p_true: self.p_false,
            p_false: self.p_true,
            p_unsure: self.p_unsure,
        }
    }

    pub fn to_probabilities(self) -> Probabilities {
        Probabilities {
            p_true: self.p_true,
            p_false: self.p_false,
            p_unsure: self.p_unsure,
        }
    }
}

impl TryFrom<&Probabilities> for Belief {
    type Error = BeliefError;

    fn try_from(value: &Probabilities) -> Result<Self, Self::Error> {
        Self::try_new(value.p_true, value.p_false, value.p_unsure)
    }
}

impl From<Belief> for Probabilities {
    fn from(value: Belief) -> Self {
        value.to_probabilities()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct ProbabilityRange {
    lower: f64,
    upper: f64,
}

impl ProbabilityRange {
    pub fn lower(self) -> f64 {
        self.lower
    }
    pub fn upper(self) -> f64 {
        self.upper
    }

    fn point(value: f64) -> Self {
        Self {
            lower: value,
            upper: value,
        }
    }
}

/// Simultaneously valid marginal bounds, intersected with the unit simplex.
/// Endpoints for different classes need not be simultaneously attainable;
/// nesting can make these bounds loose, but never requires independence.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct BeliefBounds {
    true_mass: ProbabilityRange,
    false_mass: ProbabilityRange,
    unsure_mass: ProbabilityRange,
}

impl BeliefBounds {
    /// No complete three-class estimate was supplied. This is not P(unsure)=1.
    pub const VACUOUS: Self = Self {
        true_mass: ProbabilityRange {
            lower: 0.0,
            upper: 1.0,
        },
        false_mass: ProbabilityRange {
            lower: 0.0,
            upper: 1.0,
        },
        unsure_mass: ProbabilityRange {
            lower: 0.0,
            upper: 1.0,
        },
    };

    pub fn point(value: Belief) -> Self {
        Self {
            true_mass: ProbabilityRange::point(value.p_true),
            false_mass: ProbabilityRange::point(value.p_false),
            unsure_mass: ProbabilityRange::point(value.p_unsure),
        }
    }

    pub fn true_mass(self) -> ProbabilityRange {
        self.true_mass
    }

    pub fn false_mass(self) -> ProbabilityRange {
        self.false_mass
    }

    pub fn unsure_mass(self) -> ProbabilityRange {
        self.unsure_mass
    }

    pub fn negated(self) -> Self {
        Self {
            true_mass: self.false_mass,
            false_mass: self.true_mass,
            unsure_mass: self.unsure_mass,
        }
    }

    /// Lower true/false masses with all remaining commitment assigned to unsure.
    /// The resulting unsure mass may exceed the unsure marginal upper bound:
    /// it also includes unidentified dependence/model mass. Do not score this
    /// projection as an independently calibrated three-class posterior.
    pub fn uncommitted_mass(self) -> Belief {
        let t = self.true_mass.lower;
        let f = self.false_mass.lower.min(1.0 - t);
        Belief::from_committed(t, f)
    }

    fn group(children: &[Self], all: bool) -> Self {
        let (intersection, union): (Vec<_>, Vec<_>) = children
            .iter()
            .map(|c| {
                if all {
                    (c.true_mass, c.false_mass)
                } else {
                    (c.false_mass, c.true_mass)
                }
            })
            .unzip();
        // Bonferroni lower bound for intersection, written as a sum of
        // complements to avoid subtracting two nearly equal large numbers.
        let i = ProbabilityRange {
            lower: (1.0 - intersection.iter().map(|r| 1.0 - r.lower).sum::<f64>()).max(0.0),
            upper: intersection.iter().map(|r| r.upper).fold(1.0, f64::min),
        };
        let u = ProbabilityRange {
            lower: union.iter().map(|r| r.lower).fold(0.0, f64::max),
            upper: union.iter().map(|r| r.upper).sum::<f64>().min(1.0),
        };
        let unknown = ProbabilityRange {
            lower: (1.0 - i.upper - u.upper).max(0.0),
            upper: (1.0 - i.lower - u.lower).clamp(0.0, 1.0),
        };
        let mut result = if all {
            Self {
                true_mass: i,
                false_mass: u,
                unsure_mass: unknown,
            }
        } else {
            Self {
                true_mass: u,
                false_mass: i,
                unsure_mass: unknown,
            }
        };
        // Each class is the complement of the other two disjoint classes.
        // One simultaneous pass tightens the envelope without a joint model.
        let ranges = [result.true_mass, result.false_mass, result.unsure_mass];
        let tightened = std::array::from_fn::<_, 3, _>(|n| {
            let others: Vec<_> = (0..3).filter(|j| *j != n).map(|j| ranges[j]).collect();
            let lower = ranges[n]
                .lower
                .max((1.0 - others[0].upper - others[1].upper).max(0.0));
            let upper = ranges[n]
                .upper
                .min((1.0 - others[0].lower - others[1].lower).clamp(0.0, 1.0));
            // A possible crossing is only floating-point roundoff. Widen it.
            ProbabilityRange {
                lower: lower.min(upper),
                upper: lower.max(upper),
            }
        });
        [result.true_mass, result.false_mass, result.unsure_mass] = tightened;
        result
    }
}

/// `hard` is supplied by the exact evidence kernel, never inferred from
/// `estimate`. Evidence identities name sources, not independent trials.
#[derive(Clone, Debug)]
pub struct LeafAssessment {
    pub hard: TruthValue,
    pub estimate: Option<Belief>,
    pub evidence_ids: Vec<String>,
}

impl LeafAssessment {
    pub fn unresolved() -> Self {
        Self {
            hard: TruthValue::Unknown,
            estimate: None,
            evidence_ids: Vec::new(),
        }
    }

    /// Explicitly supplied categorical unknown, rather than lack of a proof.
    /// Parser-unknown branches also use this mass as their logical state.
    pub fn categorical_unknown() -> Self {
        Self {
            estimate: Some(Belief::UNKNOWN),
            ..Self::unresolved()
        }
    }

    pub fn from_resolution(value: &Resolution) -> Self {
        Self {
            hard: match value.status {
                Status::Supported => TruthValue::True,
                Status::Contradicted => TruthValue::False,
                Status::Unknown | Status::Conflict => TruthValue::Unknown,
            },
            estimate: None,
            evidence_ids: value.evidence.iter().map(|e| e.row_id.clone()).collect(),
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct CompositionDiagnostics {
    pub visited_nodes: usize,
    pub unique_leaves: usize,
    pub duplicate_leaves: usize,
    /// Distinct leaves sharing (subject, attribute), even across query dates.
    pub shared_slot_leaves: usize,
    pub shared_evidence_ids: usize,
    pub missing_estimates: usize,
    pub unknown_branches: usize,
    pub unsupported_branches: usize,
    pub empty_groups: usize,
    pub budget_exceeded: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Composition {
    pub hard: TruthValue,
    pub soft: BeliefBounds,
    /// Sorted unique source IDs supplied by callbacks. These retain provenance
    /// for all evaluated leaves; they are not a minimal whole-program proof.
    pub evidence_ids: Vec<String>,
    pub diagnostics: CompositionDiagnostics,
}

/// Compose a bounded AST with one callback per distinct syntactic leaf.
/// Callbacks own evidence/date/type validation and must be deterministic during
/// this call. There is deliberately no conversion from a scalar chain score.
///
/// Same-operator groups are flattened and deduplicated, including reordered
/// identical subexpressions. Different predicates on one slot or source are
/// never deduplicated as if equivalent and never treated as independent.
/// Compare is passed to the exact caller verbatim; this module does no numeric,
/// money, date, version or identifier comparison.
pub fn compose<A, C>(expression: &ClaimExpr, atom: &mut A, comparison: &mut C) -> Composition
where
    A: FnMut(&Fact) -> LeafAssessment,
    C: FnMut(&SlotReference, ComparisonOp, &SlotReference) -> LeafAssessment,
{
    let mut diagnostics = CompositionDiagnostics::default();
    if !within_budget(expression, 0, &mut diagnostics.visited_nodes) {
        diagnostics.budget_exceeded = true;
        return Composition {
            hard: TruthValue::Unknown,
            soft: BeliefBounds::VACUOUS,
            evidence_ids: Vec::new(),
            diagnostics,
        };
    }
    let mut state = Composer {
        leaves: Vec::new(),
        nodes: Vec::new(),
        evidence: BTreeMap::new(),
        slots: BTreeMap::new(),
        diagnostics,
    };
    let root = state.visit(expression, atom, comparison);
    state.diagnostics.unique_leaves = state.leaves.len();
    state.diagnostics.shared_slot_leaves = state
        .slots
        .values()
        .filter(|ids| ids.len() > 1)
        .flat_map(|ids| ids.iter().copied())
        .collect::<BTreeSet<_>>()
        .len();
    state.diagnostics.shared_evidence_ids = state.evidence.values().filter(|n| **n > 1).count();
    Composition {
        hard: state.nodes[root].hard,
        soft: state.nodes[root].soft,
        evidence_ids: state.evidence.into_keys().collect(),
        diagnostics: state.diagnostics,
    }
}

fn within_budget(expression: &ClaimExpr, depth: usize, visited: &mut usize) -> bool {
    *visited += 1;
    if depth > MAX_PROGRAM_DEPTH || *visited > MAX_PROGRAM_NODES {
        return false;
    }
    match expression {
        ClaimExpr::All(children) | ClaimExpr::Any(children) => {
            children.len() <= MAX_PROGRAM_NODES
                && children
                    .iter()
                    .all(|c| within_budget(c, depth + 1, visited))
        }
        ClaimExpr::Not(child) => within_budget(child, depth + 1, visited),
        _ => true,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum NodeKey {
    Unknown,
    Leaf(usize),
    Not(usize),
    All(Vec<usize>),
    Any(Vec<usize>),
}

struct Node {
    key: NodeKey,
    hard: TruthValue,
    soft: BeliefBounds,
}

struct Composer<'a> {
    leaves: Vec<(&'a ClaimExpr, usize)>,
    nodes: Vec<Node>,
    evidence: BTreeMap<String, usize>,
    slots: BTreeMap<(&'a str, &'a str), BTreeSet<usize>>,
    diagnostics: CompositionDiagnostics,
}

fn inverted(value: TruthValue) -> TruthValue {
    match value {
        TruthValue::True => TruthValue::False,
        TruthValue::False => TruthValue::True,
        TruthValue::Unknown => TruthValue::Unknown,
    }
}

impl<'a> Composer<'a> {
    fn insert(&mut self, key: NodeKey, hard: TruthValue, soft: BeliefBounds) -> usize {
        if let Some(id) = self.nodes.iter().position(|n| n.key == key) {
            return id;
        }
        let id = self.nodes.len();
        self.nodes.push(Node { key, hard, soft });
        id
    }

    fn visit<A, C>(&mut self, expression: &'a ClaimExpr, atom: &mut A, comparison: &mut C) -> usize
    where
        A: FnMut(&Fact) -> LeafAssessment,
        C: FnMut(&SlotReference, ComparisonOp, &SlotReference) -> LeafAssessment,
    {
        match expression {
            ClaimExpr::Atom(_) | ClaimExpr::Compare { .. } => {
                if let Some((_, id)) = self.leaves.iter().find(|(e, _)| *e == expression) {
                    self.diagnostics.duplicate_leaves += 1;
                    return *id;
                }
                let leaf = self.leaves.len();
                let assessment = match expression {
                    ClaimExpr::Atom(f) => {
                        self.slots
                            .entry((&f.subject, &f.attribute))
                            .or_default()
                            .insert(leaf);
                        atom(f)
                    }
                    ClaimExpr::Compare { left, op, right } => {
                        for slot in [left, right] {
                            self.slots
                                .entry((&slot.subject, &slot.attribute))
                                .or_default()
                                .insert(leaf);
                        }
                        comparison(left, *op, right)
                    }
                    _ => unreachable!(),
                };
                self.diagnostics.missing_estimates += usize::from(assessment.estimate.is_none());
                // Repetition of a source within one leaf is not another trial.
                for id in assessment.evidence_ids.into_iter().collect::<BTreeSet<_>>() {
                    *self.evidence.entry(id).or_default() += 1;
                }
                let id = self.insert(
                    NodeKey::Leaf(leaf),
                    assessment.hard,
                    assessment
                        .estimate
                        .map_or(BeliefBounds::VACUOUS, BeliefBounds::point),
                );
                self.leaves.push((expression, id));
                id
            }
            ClaimExpr::Not(child) => {
                let id = self.visit(child, atom, comparison);
                if let NodeKey::Not(original) = self.nodes[id].key {
                    return original;
                }
                self.insert(
                    NodeKey::Not(id),
                    inverted(self.nodes[id].hard),
                    self.nodes[id].soft.negated(),
                )
            }
            ClaimExpr::All(children) | ClaimExpr::Any(children) if !children.is_empty() => {
                let all = matches!(expression, ClaimExpr::All(_));
                let mut ids = BTreeSet::new();
                for child in children {
                    let id = self.visit(child, atom, comparison);
                    match &self.nodes[id].key {
                        NodeKey::All(nested) if all => ids.extend(nested),
                        NodeKey::Any(nested) if !all => ids.extend(nested),
                        _ => {
                            ids.insert(id);
                        }
                    }
                }
                let ids: Vec<_> = ids.into_iter().collect();
                if ids.len() == 1 {
                    return ids[0];
                }
                let decisive = if all {
                    TruthValue::False
                } else {
                    TruthValue::True
                };
                let hard = if ids.iter().any(|id| self.nodes[*id].hard == decisive) {
                    decisive
                } else if ids
                    .iter()
                    .any(|id| self.nodes[*id].hard == TruthValue::Unknown)
                {
                    TruthValue::Unknown
                } else {
                    inverted(decisive)
                };
                let soft = BeliefBounds::group(
                    &ids.iter()
                        .map(|id| self.nodes[*id].soft)
                        .collect::<Vec<_>>(),
                    all,
                );
                self.insert(
                    if all {
                        NodeKey::All(ids)
                    } else {
                        NodeKey::Any(ids)
                    },
                    hard,
                    soft,
                )
            }
            ClaimExpr::Unknown { .. }
            | ClaimExpr::Unsupported { .. }
            | ClaimExpr::All(_)
            | ClaimExpr::Any(_) => {
                match expression {
                    ClaimExpr::Unknown { .. } => self.diagnostics.unknown_branches += 1,
                    ClaimExpr::Unsupported { .. } => self.diagnostics.unsupported_branches += 1,
                    _ => self.diagnostics.empty_groups += 1,
                }
                self.insert(
                    NodeKey::Unknown,
                    TruthValue::Unknown,
                    BeliefBounds::point(Belief::UNKNOWN),
                )
            }
        }
    }
}
