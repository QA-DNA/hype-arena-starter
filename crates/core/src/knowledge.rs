//! Compiled, provenance-preserving evidence index. No world knowledge is invented.
//!
//! Observation dates remain observation dates. Historical continuity contributes
//! model features, never a hard assertion about an unobserved date. A false row
//! is a disjunction of false atoms, not a list of negative facts.
use crate::model::{Evidence, Fact, InputRow};
use crate::temporal::{ValidityScope, explicit_scope};
use crate::typed::{numeric, version_against_exact};
use num_bigint::BigInt;
use num_rational::BigRational;
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;

type Key = (String, String);

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Supported,
    Contradicted,
    Unknown,
    Conflict,
}

#[derive(Clone, Debug, Serialize)]
pub struct Resolution {
    pub status: Status,
    pub evidence: Vec<Evidence>,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct KnowledgeSummary {
    pub accepted_observations: usize,
    pub negative_constraints: usize,
    pub unresolved_false_compounds: usize,
    pub unknown_rows: usize,
    pub indexed_properties: usize,
    pub explicit_validity_scopes: usize,
}

#[derive(Clone, Default)]
pub struct KnowledgeGraph {
    positive: BTreeMap<Key, Vec<Evidence>>,
    negative: BTreeMap<Key, Vec<Evidence>>,
    compounds: Vec<InputRow>,
    summary: KnowledgeSummary,
    scopes: BTreeMap<String, ValidityScope>,
}

fn key(f: &Fact) -> Key {
    (f.subject.clone(), f.attribute.clone())
}

fn evidence(row: &InputRow, fact: &Fact) -> Evidence {
    Evidence {
        row_id: row.id.clone(),
        text: row.text.clone(),
        date: row.date.clone(),
        label: row.label.clone(),
        fact: fact.clone(),
    }
}

impl KnowledgeGraph {
    pub fn compile(rows: &[InputRow]) -> Self {
        let mut graph = Self::default();
        for row in rows {
            if let Some(scope) = explicit_scope(&row.text) {
                graph.scopes.insert(row.id.clone(), scope);
            }
            match row.label.as_str() {
                "true" => {
                    for fact in &row.form {
                        graph
                            .positive
                            .entry(key(fact))
                            .or_default()
                            .push(evidence(row, fact));
                        graph.summary.accepted_observations += 1;
                    }
                }
                "false" if row.form.len() == 1 => {
                    let fact = &row.form[0];
                    graph
                        .negative
                        .entry(key(fact))
                        .or_default()
                        .push(evidence(row, fact));
                    graph.summary.negative_constraints += 1;
                }
                "false" if row.form.len() > 1 => graph.compounds.push(row.clone()),
                "unsure" => graph.summary.unknown_rows += 1,
                _ => {}
            }
        }
        for items in graph
            .positive
            .values_mut()
            .chain(graph.negative.values_mut())
        {
            items.sort_by(|a, b| a.date.cmp(&b.date).then(a.row_id.cmp(&b.row_id)));
        }
        graph.summary.unresolved_false_compounds = graph.compounds.len();
        graph.summary.indexed_properties = graph.positive.len();
        graph.summary.explicit_validity_scopes = graph.scopes.len();
        graph
    }

    pub fn summary(&self) -> &KnowledgeSummary {
        &self.summary
    }

    /// A reviewable data artifact; the executable builds this index from its
    /// supplied training partition rather than loading a hidden all-practice graph.
    pub fn snapshot(&self) -> Value {
        serde_json::json!({
            "schema_version": 1,
            "summary": self.summary,
            "date_semantics": "Source page observation dates, not inferred validity intervals",
            "accepted_observations": self.positive.values().flatten().collect::<Vec<_>>(),
            "negative_constraints": self.negative.values().flatten().collect::<Vec<_>>(),
            "false_compound_constraints": self.compounds,
            "explicit_validity_scopes": self.scopes,
            "inference": "Same-day typed predicate entailment; false-compound unit propagation requires independent premises",
            "unlabelled_policy": "Assertions from unlabelled rows never become accepted evidence by repetition or model verdict"
        })
    }

    /// A hard decision uses only constraints on the query's own observation date.
    /// It excludes both the query ID and its text during leave-one-out training.
    pub fn resolve(
        &self,
        fact: &Fact,
        date: &str,
        exclude_id: &str,
        exclude_text: &str,
    ) -> Resolution {
        self.resolve_base(fact, date, exclude_id, exclude_text, true)
    }

    fn active(&self, source_id: &str, source_date: &str, query_date: &str) -> bool {
        self.scopes
            .get(source_id)
            .map_or_else(|| source_date == query_date, |s| s.contains(query_date))
    }

    fn resolve_base(
        &self,
        fact: &Fact,
        date: &str,
        exclude_id: &str,
        exclude_text: &str,
        compounds: bool,
    ) -> Resolution {
        let allowed = |e: &&Evidence| {
            self.active(&e.row_id, &e.date, date)
                && e.row_id != exclude_id
                && !e.text.eq_ignore_ascii_case(exclude_text)
        };
        let positives: Vec<_> = self
            .positive
            .get(&key(fact))
            .into_iter()
            .flatten()
            .filter(allowed)
            .collect();
        let negatives: Vec<_> = self
            .negative
            .get(&key(fact))
            .into_iter()
            .flatten()
            .filter(allowed)
            .collect();
        let mut supported = false;
        let mut contradicted = false;
        let mut sources = Vec::new();
        let mut domain: Option<Vec<Interval>> = None;
        // Inconsistent name constraints must abstain even when a third queried
        // name differs from both sources. Numeric domains are checked below too.
        let inconsistent = positives.iter().enumerate().any(|(i, a)| {
            positives[i + 1..]
                .iter()
                .any(|b| entails(&a.fact.value, &b.fact.value, false) == Some(false))
                || negatives
                    .iter()
                    .any(|b| entails(&a.fact.value, &b.fact.value, true) == Some(false))
        });
        if inconsistent {
            supported = true;
            contradicted = true;
            sources.extend(positives.iter().chain(&negatives).map(|e| (*e).clone()));
        }
        for (source, negate) in positives
            .iter()
            .map(|e| (*e, false))
            .chain(negatives.iter().map(|e| (*e, true)))
        {
            if let Some(status) = entails(&fact.value, &source.fact.value, negate) {
                supported |= status;
                contradicted |= !status;
                sources.push(source.clone());
            }
            if compatible(&fact.value, &source.fact.value)
                && let Some(mut bounds) = intervals(&source.fact.value)
            {
                if negate {
                    bounds = complement(&bounds);
                }
                domain = Some(match domain {
                    None => bounds,
                    Some(old) => intersect(&old, &bounds),
                });
                if !sources
                    .iter()
                    .any(|s| s.row_id == source.row_id && s.fact == source.fact)
                {
                    sources.push(source.clone());
                }
            }
        }
        if let (Some(domain), Some(query)) = (&domain, intervals(&fact.value)) {
            if domain.is_empty() {
                supported = true;
                contradicted = true;
            } else if intersect(domain, &query).is_empty() {
                contradicted = true;
            } else if intersect(domain, &complement(&query)).is_empty() {
                supported = true;
            }
        }
        // Unit propagation: only when every OTHER atom is independently supported.
        // Inferred negatives never recursively justify the premises of this rule.
        if compounds {
            for row in &self.compounds {
                if !self.active(&row.id, &row.date, date)
                    || row.id == exclude_id
                    || row.text.eq_ignore_ascii_case(exclude_text)
                {
                    continue;
                }
                for (index, candidate) in row.form.iter().enumerate() {
                    if key(candidate) != key(fact) {
                        continue;
                    }
                    let premises: Vec<_> = row
                        .form
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| *i != index)
                        .map(|(_, f)| self.resolve_base(f, date, exclude_id, exclude_text, false))
                        .collect();
                    if !premises.iter().all(|r| r.status == Status::Supported) {
                        continue;
                    }
                    if let Some(status) = entails(&fact.value, &candidate.value, true) {
                        supported |= status;
                        contradicted |= !status;
                        sources.push(evidence(row, candidate));
                        for premise in premises {
                            sources.extend(premise.evidence);
                        }
                    }
                }
            }
        }
        sources.sort_by(|a, b| {
            a.row_id
                .cmp(&b.row_id)
                .then(a.fact.attribute.cmp(&b.fact.attribute))
        });
        sources.dedup_by(|a, b| a.row_id == b.row_id && a.fact == b.fact);
        sources.truncate(12);
        Resolution {
            status: match (supported, contradicted) {
                (true, false) => Status::Supported,
                (false, true) => Status::Contradicted,
                (true, true) => Status::Conflict,
                _ => Status::Unknown,
            },
            evidence: sources,
        }
    }

    /// Temporal signals are statistical features, not proof of persistence.
    pub fn features(&self, row: &InputRow, facts: &[Fact]) -> Vec<f64> {
        let mut out = vec![0.0; 24];
        let n = facts.len().max(1) as f64;
        out[0] = f64::from(facts.is_empty());
        for fact in facts {
            let resolution = self.resolve(fact, &row.date, &row.id, &row.text);
            let i = match resolution.status {
                Status::Supported => 1,
                Status::Contradicted => 2,
                Status::Unknown => 3,
                Status::Conflict => 4,
            };
            out[i] += 1.0 / n;
            let previous: Vec<_> = self
                .positive
                .get(&key(fact))
                .into_iter()
                .flatten()
                .filter(|e| {
                    e.date <= row.date
                        && e.row_id != row.id
                        && !e.text.eq_ignore_ascii_case(&row.text)
                })
                .collect();
            if previous.is_empty() {
                out[5] += 1.0 / n;
            }
            if let Some(last) = previous.last() {
                match entails(&fact.value, &last.fact.value, false) {
                    Some(true) => out[6] += 1.0 / n,
                    Some(false) => out[7] += 1.0 / n,
                    None => out[8] += 1.0 / n,
                }
                if let (Some(a), Some(b)) = (
                    fact.value["value"].as_f64(),
                    last.fact.value["value"].as_f64(),
                ) && compatible(&fact.value, &last.fact.value)
                {
                    out[9] += ((a - b).abs() / (b.abs() + 1.0)).min(10.0) / n;
                    out[10] += f64::from(a > b) / n;
                    out[11] += f64::from(a < b) / n;
                }
                let gap = day_number(&row.date)
                    .zip(day_number(&last.date))
                    .map_or(366.0, |(a, b)| (a - b).max(0.0));
                out[12] += (gap / 366.0).min(3.0) / n;
            }
            for source in &previous {
                match entails(&fact.value, &source.fact.value, false) {
                    Some(true) => out[13] += 1.0 / (n * previous.len() as f64),
                    Some(false) => out[14] += 1.0 / (n * previous.len() as f64),
                    None => {}
                }
            }
            out[15] += (previous.len().min(10) as f64) / 10.0 / n;
            let prior_negative = self
                .negative
                .get(&key(fact))
                .into_iter()
                .flatten()
                .filter(|e| {
                    e.date <= row.date
                        && e.row_id != row.id
                        && !e.text.eq_ignore_ascii_case(&row.text)
                });
            for source in prior_negative {
                match entails(&fact.value, &source.fact.value, true) {
                    Some(false) => out[16] = (out[16] + 1.0 / n).min(1.0),
                    Some(true) => out[17] = (out[17] + 1.0 / n).min(1.0),
                    None => {}
                }
            }
            for (i, kind) in ["name", "boolean", "date", "version", "money", "percent"]
                .iter()
                .enumerate()
            {
                out[18 + i] += f64::from(fact.value["kind"] == *kind) / n;
            }
        }
        out
    }
}

fn compatible(a: &Value, b: &Value) -> bool {
    if a["kind"] != b["kind"] {
        return false;
    }
    if matches!(
        a["kind"].as_str(),
        Some("quantity" | "money" | "percent" | "duration")
    ) {
        return numeric(a)
            .zip(numeric(b))
            .is_some_and(|(x, y)| x.dimension == y.dimension);
    }
    ["unit", "currency", "per"]
        .iter()
        .all(|f| a.get(*f) == b.get(*f))
}

/// Whether every value allowed by the observation satisfies (or refutes) query.
pub fn entails(query: &Value, observation: &Value, negate_observation: bool) -> Option<bool> {
    if !compatible(query, observation) {
        return None;
    }
    if query["kind"] == "version" {
        return version_against_exact(query, observation, negate_observation);
    }
    if let (Some(q), Some(mut o)) = (intervals(query), intervals(observation)) {
        if negate_observation {
            o = complement(&o);
        }
        if o.is_empty() {
            return None;
        }
        if intersect(&o, &q).is_empty() {
            return Some(false);
        }
        if intersect(&o, &complement(&q)).is_empty() {
            return Some(true);
        }
        return None;
    }
    let qop = query["op"].as_str().unwrap_or("eq");
    let mut oop = observation["op"].as_str().unwrap_or("eq");
    if negate_observation {
        oop = match oop {
            "eq" => "ne",
            "ne" => "eq",
            _ => return None,
        };
    }
    // Booleans have a closed two-value domain; unlike names, the complement of
    // true identifies false exactly (and conversely).
    if let (Some(q), Some(o)) = (query["value"].as_bool(), observation["value"].as_bool()) {
        let actual = match oop {
            "eq" => o,
            "ne" => !o,
            _ => return None,
        };
        return match qop {
            "eq" => Some(q == actual),
            "ne" => Some(q != actual),
            _ => None,
        };
    }
    let equal = query["value"] == observation["value"];
    match (qop, oop, equal) {
        ("eq", "eq", e) => Some(e),
        ("ne", "eq", e) => Some(!e),
        ("eq", "ne", true) => Some(false),
        ("ne", "ne", true) => Some(true),
        _ => None,
    }
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum Bound {
    NegativeInfinity,
    Finite(BigRational),
    PositiveInfinity,
}

#[derive(Clone, Debug)]
struct Interval {
    lo: Bound,
    hi: Bound,
    lc: bool,
    hc: bool,
}
fn interval(lo: Bound, hi: Bound, lc: bool, hc: bool) -> Option<Interval> {
    (lo < hi || (lo == hi && lc && hc)).then_some(Interval { lo, hi, lc, hc })
}
fn intersect(a: &[Interval], b: &[Interval]) -> Vec<Interval> {
    let mut out = Vec::new();
    for x in a {
        for y in b {
            let lo = x.lo.clone().max(y.lo.clone());
            let hi = x.hi.clone().min(y.hi.clone());
            let lc = (lo != x.lo || x.lc) && (lo != y.lo || y.lc);
            let hc = (hi != x.hi || x.hc) && (hi != y.hi || y.hc);
            if let Some(i) = interval(lo, hi, lc, hc) {
                out.push(i);
            }
        }
    }
    out.sort_by(|x, y| x.lo.cmp(&y.lo));
    out
}
fn complement(items: &[Interval]) -> Vec<Interval> {
    let mut items = items.to_vec();
    items.sort_by(|a, b| a.lo.cmp(&b.lo));
    let mut out = Vec::new();
    let mut lo = Bound::NegativeInfinity;
    let mut lc = false;
    for item in items {
        if let Some(i) = interval(lo, item.lo, lc, !item.lc) {
            out.push(i);
        }
        lo = item.hi;
        lc = !item.hc;
    }
    if let Some(i) = interval(lo, Bound::PositiveInfinity, lc, false) {
        out.push(i);
    }
    out
}
fn intervals(v: &Value) -> Option<Vec<Interval>> {
    let (lo, hi) = if v["kind"] == "date" {
        let (a, b) = date_bounds(v["value"].as_str()?)?;
        (
            Bound::Finite(BigRational::from_integer(BigInt::from(a as i64))),
            Bound::Finite(BigRational::from_integer(BigInt::from(b as i64))),
        )
    } else {
        let n = Bound::Finite(numeric(v)?.amount);
        (n.clone(), n)
    };
    let op = v["op"].as_str().unwrap_or("eq");
    let exact = Interval {
        lo: lo.clone(),
        hi: hi.clone(),
        lc: true,
        hc: true,
    };
    Some(match op {
        "eq" => vec![exact],
        "ne" => complement(&[exact]),
        "gt" => vec![Interval {
            lo: hi,
            hi: Bound::PositiveInfinity,
            lc: false,
            hc: false,
        }],
        "ge" => vec![Interval {
            lo,
            hi: Bound::PositiveInfinity,
            lc: true,
            hc: false,
        }],
        "lt" => vec![Interval {
            lo: Bound::NegativeInfinity,
            hi: lo,
            lc: false,
            hc: false,
        }],
        "le" => vec![Interval {
            lo: Bound::NegativeInfinity,
            hi,
            lc: false,
            hc: true,
        }],
        _ => return None,
    })
}
fn date_bounds(s: &str) -> Option<(f64, f64)> {
    let p: Vec<_> = s.split('-').collect();
    let year: i32 = p.first()?.parse().ok()?;
    if !(1..=9998).contains(&year) || p.len() > 3 {
        return None;
    }
    let month: u32 = p.get(1).map_or(Some(1), |m| m.parse().ok())?;
    if !(1..=12).contains(&month) {
        return None;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    let day: u32 = p.get(2).map_or(Some(1), |d| d.parse().ok())?;
    if day == 0 || day > days[month as usize - 1] {
        return None;
    }
    let base = |y: i32, m: u32, d: u32| {
        let before = y - 1;
        let annual = before * 365 + before / 4 - before / 100 + before / 400;
        let previous: u32 = days[..m as usize - 1].iter().sum();
        f64::from(annual) + f64::from(previous) + f64::from(d)
    };
    let lo = base(year, month, day);
    let hi = match p.len() {
        1 => base(year, 12, 31),
        2 => base(year, month, days[month as usize - 1]),
        _ => lo,
    };
    Some((lo, hi))
}
fn day_number(s: &str) -> Option<f64> {
    date_bounds(s).map(|v| v.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn q(n: f64, op: &str) -> Value {
        json!({"kind":"quantity","unit":"customer","value":n,"op":op})
    }
    fn fact(n: f64) -> Fact {
        Fact {
            subject: "Cloud".into(),
            attribute: "customers".into(),
            value: q(n, "eq"),
        }
    }
    fn row(id: &str, label: &str, form: Vec<Fact>) -> InputRow {
        InputRow {
            id: id.into(),
            text: id.into(),
            date: "2026-10-29".into(),
            label: label.into(),
            form,
        }
    }
    #[test]
    fn inequality_entailment_is_directional_and_preserves_open_boundaries() {
        assert_eq!(entails(&q(100.0, "gt"), &q(101.0, "eq"), false), Some(true));
        assert_eq!(
            entails(&q(100.0, "gt"), &q(100.0, "eq"), false),
            Some(false)
        );
        assert_eq!(entails(&q(101.0, "eq"), &q(100.0, "gt"), false), None);
        assert_eq!(
            entails(&q(100.0, "le"), &q(100.0, "gt"), false),
            Some(false)
        );
        assert_eq!(entails(&q(100.0, "gt"), &q(100.0, "le"), true), Some(true));
    }
    #[test]
    fn intersected_constraints_can_identify_one_exact_value() {
        let mut lower = fact(100.0);
        lower.value = q(100.0, "ge");
        let mut upper = fact(100.0);
        upper.value = q(100.0, "le");
        let g = KnowledgeGraph::compile(&[
            row("lo", "true", vec![lower]),
            row("hi", "true", vec![upper]),
        ]);
        assert_eq!(
            g.resolve(&fact(100.0), "2026-10-29", "new", "new").status,
            Status::Supported
        );
        assert_eq!(
            g.resolve(&fact(101.0), "2026-10-29", "new", "new").status,
            Status::Contradicted
        );
    }
    #[test]
    fn explicit_interval_is_used_but_never_extended_from_a_page_date() {
        let mut anchor = row("interval", "true", vec![fact(100.0)]);
        anchor.date = "2026-02-01".into();
        anchor.text =
            "From February 1, 2026 through June 30, 2026, Cloud serves 100 customers.".into();
        let graph = KnowledgeGraph::compile(&[anchor]);
        assert_eq!(
            graph
                .resolve(&fact(100.0), "2026-03-15", "query", "query")
                .status,
            Status::Supported
        );
        assert_eq!(
            graph
                .resolve(&fact(101.0), "2026-06-30", "query", "query")
                .status,
            Status::Contradicted
        );
        assert_eq!(
            graph
                .resolve(&fact(100.0), "2026-07-01", "query", "query")
                .status,
            Status::Unknown
        );
        assert_eq!(
            graph
                .resolve(&fact(100.0), "2026-01-31", "query", "query")
                .status,
            Status::Unknown
        );
    }
    #[test]
    fn currencies_and_partial_dates_are_not_equal_by_number_or_prefix() {
        let a = json!({"kind":"money","currency":"EUR","value":79,"per":"month"});
        let b = json!({"kind":"money","currency":"USD","value":79,"per":"month"});
        assert_eq!(entails(&a, &b, false), None);
        let d = |s| json!({"kind":"date","value":s});
        assert_eq!(entails(&d("2026"), &d("2026-10-29"), false), Some(true));
        assert_eq!(entails(&d("2026-10-29"), &d("2026"), false), None);
        assert_eq!(entails(&d("2026-11"), &d("2026-10-29"), false), Some(false));
        assert!(date_bounds("2026-02-30").is_none());
    }
    #[test]
    fn predicate_comparisons_use_exact_decimals_and_convert_compatible_units() {
        let q = |v, u| json!({"kind":"quantity","value":v,"unit":u});
        assert_eq!(entails(&q(1.2, "GB"), &q(1200.0, "MB"), false), Some(true));
        let large: Value = serde_json::from_str(
            r#"{"kind":"quantity","value":9007199254740993,"unit":"customer"}"#,
        )
        .unwrap();
        let smaller: Value = serde_json::from_str(
            r#"{"kind":"quantity","value":9007199254740992,"unit":"customer"}"#,
        )
        .unwrap();
        assert_eq!(entails(&large, &smaller, false), Some(false));
    }
    #[test]
    fn false_boolean_identifies_its_complement_but_false_name_does_not() {
        let yes = serde_json::json!({"kind":"boolean","value":true});
        let no = serde_json::json!({"kind":"boolean","value":false});
        assert_eq!(entails(&no, &yes, true), Some(true));
        let name = |s| serde_json::json!({"kind":"name","value":s});
        assert_eq!(entails(&name("B"), &name("A"), true), None);
    }
    #[test]
    fn false_compound_requires_independent_supported_premises() {
        let mut a = fact(1.0);
        a.attribute = "regions".into();
        let b = fact(10.0);
        let negative = row("bad", "false", vec![a.clone(), b.clone()]);
        let g = KnowledgeGraph::compile(std::slice::from_ref(&negative));
        assert_eq!(
            g.resolve(&b, "2026-10-29", "new", "new").status,
            Status::Unknown
        );
        let g = KnowledgeGraph::compile(&[negative, row("anchor", "true", vec![a])]);
        let r = g.resolve(&b, "2026-10-29", "new", "new");
        assert_eq!(r.status, Status::Contradicted);
        assert_eq!(r.evidence.len(), 2);
    }
    #[test]
    fn no_future_no_unlabelled_no_self_support_and_conflicts_abstain() {
        let g = KnowledgeGraph::compile(&[
            row("t", "true", vec![fact(10.0)]),
            row("f", "false", vec![fact(10.0)]),
            row("u", "", vec![fact(20.0)]),
        ]);
        assert_eq!(
            g.resolve(&fact(10.0), "2026-10-28", "x", "x").status,
            Status::Unknown
        );
        assert_eq!(
            g.resolve(&fact(20.0), "2026-10-29", "x", "x").status,
            Status::Conflict
        );
        assert_eq!(
            g.resolve(&fact(10.0), "2026-10-29", "x", "x").status,
            Status::Conflict
        );
        let g = KnowledgeGraph::compile(&[row("t", "true", vec![fact(10.0)])]);
        assert_eq!(
            g.resolve(&fact(10.0), "2026-10-29", "t", "t").status,
            Status::Unknown
        );
    }
}
