//! Evidence-aware CPU baseline, informed by Mihai's practice and lexicon audits.
//!
//! Observation dates are not validity intervals. Only same-day, unambiguous true
//! observations are decisive; learned scores remain uncalibrated estimates.
use crate::{
    forest::RandomForest,
    knowledge::{KnowledgeGraph, KnowledgeSummary, Status, compatible, entails},
    model::*,
};
use regex::Regex;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;
use unicode_normalization::UnicodeNormalization;

#[derive(Clone)]
struct Example {
    row: InputRow,
    terms: BTreeSet<String>,
}

struct Alias {
    pattern: Regex,
    subject: String,
}

pub struct Engine {
    examples: Vec<Example>,
    aliases: Vec<Alias>,
    attributes: BTreeMap<String, BTreeSet<String>>,
    inverted: BTreeMap<String, Vec<usize>>,
    exact: BTreeMap<String, Vec<usize>>,
    observations: BTreeMap<(String, String), Vec<Evidence>>,
    knowledge: KnowledgeGraph,
    boosted: Option<(
        crate::boosted::FeatureIndex,
        crate::boosted::BoostedVerifier,
    )>,
    forest: RandomForest,
    class_priors: [f64; 3],
    earliest_date: String,
    number: Regex,
    percent: Regex,
    money: Regex,
    duration: Regex,
    version: Regex,
    iso_date: Regex,
    written_date: Regex,
    month_date: Regex,
}

#[derive(Clone, Debug, Serialize)]
pub struct HoldoutReport {
    pub training_rows: usize,
    pub test_rows: usize,
    pub accuracy: f64,
    pub macro_f1: f64,
    pub confusion: [[usize; 3]; 3],
    pub majority_accuracy: f64,
    pub majority_label: String,
    pub coverage: f64,
    pub correct: usize,
    pub incorrect: usize,
    pub unsure: usize,
    pub elapsed_ms: u64,
    pub classes: Vec<ClassMetrics>,
    pub results: Vec<EvaluationResult>,
    pub note: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ClassMetrics {
    pub label: String,
    pub support: usize,
    pub precision: f64,
    pub recall: f64,
    pub f1: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct EvaluationResult {
    pub expected: String,
    pub correct: bool,
    pub prediction: Prediction,
}

impl Engine {
    pub fn new(practice: &[InputRow], lexicon: &Value) -> Result<Self, String> {
        let subjects = lexicon["subjects"]
            .as_array()
            .ok_or("Lexicon must contain a subjects array")?;
        if practice.is_empty() {
            return Err("At least one labelled practice row is required".into());
        }
        let mut aliases = Vec::new();
        let mut attributes = BTreeMap::new();
        for subject in subjects {
            let name = subject["name"].as_str().ok_or("Subject name is missing")?;
            let fields = subject["attributes"]
                .as_array()
                .ok_or("Subject attributes are missing")?
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect();
            attributes.insert(name.to_owned(), fields);
            for surface in std::iter::once(name).chain(
                subject["aliases"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str),
            ) {
                aliases.push(Alias {
                    pattern: regex(
                        &normalize(surface)
                            .split_whitespace()
                            .map(regex::escape)
                            .collect::<Vec<_>>()
                            .join(r"\s*"),
                    )?,
                    subject: name.to_owned(),
                });
            }
        }
        let mut engine = Self {
            examples: Vec::new(),
            aliases,
            attributes,
            inverted: BTreeMap::new(),
            exact: BTreeMap::new(),
            observations: BTreeMap::new(),
            knowledge: KnowledgeGraph::default(),
            boosted: None,
            forest: RandomForest::train(&[], &[]),
            class_priors: [1.0 / 3.0; 3],
            earliest_date: practice
                .iter()
                .map(|row| row.date.as_str())
                .min()
                .unwrap_or("")
                .to_owned(),
            number: regex(
                r"(?i)\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(million|billion|thousand)?\s*([a-z][a-z-]*)?",
            )?,
            percent: regex(r"(?i)([0-9]+(?:\.[0-9]+)?)\s*(?:%|percent|per cent)")?,
            money: regex(
                r"(?i)(€|\$|£|EUR|USD|GBP)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(million|billion|thousand)?|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(EUR|USD|GBP)",
            )?,
            duration: regex(
                r"(?i)\b([0-9]+(?:\.[0-9]+)?)\s*(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b",
            )?,
            version: regex(r"(?i)\b(?:v|version\s+)?([0-9]+\.[0-9]+(?:\.[0-9]+)*)\b")?,
            iso_date: regex(r"\b(20[0-9]{2}(?:-[0-9]{2}){0,2})\b")?,
            written_date: regex(
                r"(?i)\b([0-9]{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20[0-9]{2})\b",
            )?,
            month_date: regex(
                r"(?i)\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20[0-9]{2})\b",
            )?,
        };
        for row in practice {
            if class(&row.label).is_none() {
                continue;
            }
            let mut row = row.clone();
            row.form.retain(|fact| engine.valid_fact(fact));
            let index = engine.examples.len();
            let terms = tokenize(&row.text);
            for term in &terms {
                engine.inverted.entry(term.clone()).or_default().push(index);
            }
            engine
                .exact
                .entry(normalize(&row.text))
                .or_default()
                .push(index);
            if row.label == "true" {
                for fact in &row.form {
                    engine
                        .observations
                        .entry(key(fact))
                        .or_default()
                        .push(Evidence {
                            row_id: row.id.clone(),
                            text: row.text.clone(),
                            date: row.date.clone(),
                            label: row.label.clone(),
                            fact: fact.clone(),
                        });
                }
            }
            engine.examples.push(Example { row, terms });
        }
        if engine.examples.is_empty() {
            return Err("Practice contains no valid labels".into());
        }
        engine.knowledge = KnowledgeGraph::compile(
            &engine
                .examples
                .iter()
                .map(|e| e.row.clone())
                .collect::<Vec<_>>(),
        );
        for evidence in engine.observations.values_mut() {
            evidence.sort_by(|a, b| a.date.cmp(&b.date).then(a.row_id.cmp(&b.row_id)));
        }
        let mut x = Vec::with_capacity(engine.examples.len());
        let mut y = Vec::with_capacity(engine.examples.len());
        let mut class_counts = [1.0; 3];
        for example in &engine.examples {
            let nearest = engine.nearest(&example.row.text, Some(&example.row.id));
            // Training features must face the same imperfect template extraction
            // as unseen runtime text; do not feed oracle forms into the forest.
            let inferred_facts = engine.extract_template(&example.row, &nearest);
            x.push(engine.features(
                &example.row,
                &inferred_facts,
                &nearest,
                Some(&example.row.id),
            ));
            y.push(class(&example.row.label).unwrap_or(2));
            // Supervise the verifier with both observed extraction noise and
            // the training partition's supplied parse. Neither uses test forms.
            // Self evidence is excluded in both paths.
            if inferred_facts != example.row.form {
                x.push(engine.features(
                    &example.row,
                    &example.row.form,
                    &nearest,
                    Some(&example.row.id),
                ));
                y.push(class(&example.row.label).unwrap_or(2));
            }
            class_counts[class(&example.row.label).unwrap_or(2)] += 1.0;
        }
        let total: f64 = class_counts.iter().sum();
        engine.class_priors = class_counts.map(|count| count / total);
        engine.forest = RandomForest::train(&x, &y);
        Ok(engine)
    }

    pub fn tree_count(&self) -> usize {
        self.forest.tree_count()
    }

    pub fn knowledge_summary(&self) -> &KnowledgeSummary {
        self.knowledge.summary()
    }

    pub fn with_boosted(mut self, artifact: &str) -> Result<Self, String> {
        let model = crate::boosted::BoostedVerifier::from_json(artifact)?;
        let training: Vec<_> = self.examples.iter().map(|e| e.row.clone()).collect();
        model.validate_training_partition(&training)?;
        self.boosted = Some((crate::boosted::FeatureIndex::compile(&training), model));
        Ok(self)
    }

    /// Forms are assertions, never automatically trusted truth.
    pub fn extract(&self, row: &InputRow) -> Vec<Fact> {
        if !row.form.is_empty() {
            return row
                .form
                .iter()
                .filter(|fact| self.valid_fact(fact))
                .cloned()
                .collect();
        }
        if self.exact.contains_key(&normalize(&row.text)) {
            return self.extract_with_nearest(row, &[]);
        }
        let nearest = self.nearest(&row.text, None);
        self.extract_with_nearest(row, &nearest)
    }

    pub fn predict(&self, rows: &[InputRow]) -> Vec<Prediction> {
        self.predict_using(rows, true, false, &ExtractionHints::default())
    }

    /// Evaluate parsed queries against this engine's training partition only.
    /// Supplied parser diagnostics cannot introduce new evidence or labels.
    pub fn predict_with_hints(
        &self,
        rows: &[InputRow],
        hints: &ExtractionHints,
    ) -> Vec<Prediction> {
        self.predict_using(rows, true, false, hints)
    }

    /// The labelled practice example with this row's normalized text and date, when every such
    /// example agrees on the label. With the canonical seed the engine answers the row with it.
    pub fn practice_match(&self, row: &InputRow) -> Option<&InputRow> {
        let matches: Vec<_> = self
            .exact
            .get(&normalize(&row.text))?
            .iter()
            .map(|&i| &self.examples[i].row)
            .filter(|example| example.date == row.date)
            .collect();
        let first = *matches.first()?;
        matches
            .iter()
            .all(|example| example.label == first.label)
            .then_some(first)
    }

    /// The competition includes the canonical practice rows. Other evaluation
    /// worlds may reuse its schema but have different facts: never import the
    /// canonical world's truth merely because its parser was used for training.
    pub fn canonical_seed_present(&self, rows: &[InputRow]) -> bool {
        let mut observed: BTreeMap<_, Vec<&str>> = BTreeMap::new();
        for row in rows {
            observed
                .entry((normalize(&row.text), row.date.as_str()))
                .or_default()
                .push(&row.label);
        }
        self.examples.iter().all(|e| {
            observed
                .get(&(normalize(&e.row.text), e.row.date.as_str()))
                .is_some_and(|labels| {
                    labels
                        .iter()
                        .all(|label| label.is_empty() || *label == e.row.label)
                })
        })
    }

    pub fn predict_universe(&self, rows: &[InputRow]) -> Vec<Prediction> {
        self.predict_universe_with_hints(rows, &ExtractionHints::default())
    }

    pub fn predict_universe_with_hints(
        &self,
        rows: &[InputRow],
        hints: &ExtractionHints,
    ) -> Vec<Prediction> {
        let canonical = self.canonical_seed_present(rows);
        self.predict_using(rows, canonical, !canonical, hints)
    }

    fn predict_using(
        &self,
        rows: &[InputRow],
        use_seed: bool,
        conservative: bool,
        hints: &ExtractionHints,
    ) -> Vec<Prediction> {
        // Known labels supplied with the current universe are usable evidence too.
        // Repeated unlabelled statements never enter this pool.
        let mut context: BTreeMap<(String, String), Vec<Evidence>> = BTreeMap::new();
        for row in rows.iter().filter(|row| row.label == "true") {
            if hints.recognized_empty.contains(&row.id) {
                continue;
            }
            for fact in self.extract(row) {
                context.entry(key(&fact)).or_default().push(Evidence {
                    row_id: row.id.clone(),
                    text: row.text.clone(),
                    date: row.date.clone(),
                    label: "true".into(),
                    fact,
                });
            }
        }
        let mut evidence_rows: Vec<_> = if use_seed {
            self.examples.iter().map(|e| e.row.clone()).collect()
        } else {
            Vec::new()
        };
        let seed_ids: BTreeSet<_> = evidence_rows.iter().map(|r| r.id.clone()).collect();
        for row in rows
            .iter()
            .filter(|r| class(&r.label).is_some() && !seed_ids.contains(&r.id))
        {
            let mut parsed = row.clone();
            parsed.form = if hints.recognized_empty.contains(&row.id) {
                Vec::new()
            } else {
                self.extract(row)
            };
            // An imperfect parser can omit a conjunct. A runtime false row is
            // not a safe single-atom negative unless its complete parse is known.
            if parsed.label == "false" && !self.exact.contains_key(&normalize(&parsed.text)) {
                parsed.form.clear();
            }
            evidence_rows.push(parsed);
        }
        let knowledge = KnowledgeGraph::compile(&evidence_rows);
        rows.iter()
            .map(|row| self.predict_one(row, &context, &knowledge, use_seed, conservative, hints))
            .collect()
    }

    fn predict_one(
        &self,
        row: &InputRow,
        context: &BTreeMap<(String, String), Vec<Evidence>>,
        knowledge: &KnowledgeGraph,
        use_seed: bool,
        conservative: bool,
        hints: &ExtractionHints,
    ) -> Prediction {
        let nearest = self.nearest(&row.text, None);
        let facts = if hints.recognized_empty.contains(&row.id) {
            Vec::new()
        } else {
            self.extract_with_nearest(row, &nearest)
        };
        let features = self.features(row, &facts, &nearest, None);
        let mut scores = self.forest.predict(&features);
        // Each tree is trained on balanced bootstrap samples. Restore observed
        // class priors before choosing a label; this is not held-out calibration.
        for (score, prior) in scores.iter_mut().zip(self.class_priors) {
            *score *= prior;
        }
        let score_sum: f64 = scores.iter().sum();
        scores = scores.map(|score| score / score_sum);
        let mut boosted_used = false;
        if let Some((index, model)) = &self.boosted
            && let Ok(probabilities) = model.predict(&index.features(row, &facts))
        {
            // This model was fitted on ordinary class proportions, so applying
            // the balanced-forest prior correction again would be incorrect.
            scores = probabilities;
            boosted_used = true;
        }
        let mut evidence = Vec::new();
        let mut supported = 0;
        let mut contradicted = 0;
        let mut conflicts = 0;
        let mut temporal_supported = 0;
        let mut temporal_contradicted = 0;
        for fact in &facts {
            let resolution = knowledge.resolve(fact, &row.date, &row.id, &row.text);
            match resolution.status {
                Status::Supported => supported += 1,
                Status::Contradicted => contradicted += 1,
                Status::Conflict => conflicts += 1,
                Status::Unknown => {}
            }
            evidence.extend(resolution.evidence);
            let observations = self
                .observations
                .get(&key(fact))
                .filter(|_| use_seed)
                .into_iter()
                .flatten()
                .chain(context.get(&key(fact)).into_iter().flatten())
                .filter(|e| e.date <= row.date && e.row_id != row.id)
                .collect::<Vec<_>>();
            let dated_judgement = match resolution.status {
                Status::Supported => Some(true),
                Status::Contradicted => Some(false),
                Status::Conflict => None,
                Status::Unknown => latest_history_judgement(fact, &observations),
            };
            match dated_judgement {
                Some(true) => temporal_supported += 1,
                Some(false) => temporal_contradicted += 1,
                None => {}
            }
            let mut related = observations;
            related.sort_by(|a, b| b.date.cmp(&a.date).then(a.row_id.cmp(&b.row_id)));
            for e in related.into_iter().take(3) {
                if evidence.len() < 12
                    && !evidence
                        .iter()
                        .any(|old: &Evidence| old.row_id == e.row_id && old.fact == e.fact)
                {
                    evidence.push(e.clone());
                }
            }
        }
        let mut reason = "Random Forest estimate from lexical, value and evidence features; scores are not independently calibrated.".to_owned();
        if boosted_used {
            reason="Gradient-boosted verifier estimate from structured assertion/evidence features; scores are not independently calibrated.".into();
        }
        let mut memory = None;
        if use_seed && let Some(first) = self.practice_match(row) {
            memory = class(&first.label);
            for fact in &first.form {
                if evidence.len() < 12
                    && !evidence
                        .iter()
                        .any(|e| e.row_id == first.id && e.fact == *fact)
                {
                    evidence.push(Evidence {
                        row_id: first.id.clone(),
                        text: first.text.clone(),
                        date: first.date.clone(),
                        label: first.label.clone(),
                        fact: fact.clone(),
                    });
                }
            }
        }
        let chosen;
        if let Some(known) = class(&row.label) {
            chosen = known;
            scores = peak(known, 1.0);
            reason = "Label supplied by the dataset; this row is evidence, not a hidden-label prediction.".into();
        } else if let Some(known) = memory {
            chosen = known;
            scores = peak(known, 0.99);
            reason = "Exact text and date match a labelled practice row. This is a familiar training example, not a generalization measurement.".into();
        } else if let Some(program) = hints.programs.get(&row.id) {
            let result = crate::program_verification::verify(program, row, knowledge);
            chosen = match result.truth {
                crate::claim_program::TruthValue::True => 0,
                crate::claim_program::TruthValue::False => 1,
                crate::claim_program::TruthValue::Unknown => 2,
            };
            // The exact logical outcome is conditional on the extracted AST.
            // This legacy confidence allowance is not a calibrated frequency.
            scores = peak(chosen, if chosen == 2 { 0.8 } else { 0.94 });
            evidence = result.evidence;
            reason = "Scope-aware three-valued verification of the claim program against labelled constraints on the requested dates. Unknown comparisons, missing branches and conflicting values remain unresolved; no positive fact flattening or statistical prior changes the logical result. Scores are not independently calibrated.".into();
        } else if !facts.is_empty() && contradicted > 0 {
            chosen = 1;
            scores = peak(1, 0.94);
            reason = "The compiled evidence graph refutes at least one extracted assertion on this date, using typed predicates and labelled source constraints.".into();
        } else if facts.is_empty()
            || hints.explicit_unknown.contains(&row.id)
            || hints.incomplete.contains(&row.id)
        {
            chosen = 2;
            scores = peak(2, 0.8);
            reason = if facts.is_empty() {
                "No grounded assertion was extracted. A learned class prior cannot establish a factual verdict."
            } else {
                "The parser left an asserted clause unresolved. A matching subset cannot establish the entire conjunction."
            }.into();
        } else if !facts.is_empty()
            && supported == facts.len()
            && !hints.incomplete.contains(&row.id)
        {
            chosen = 0;
            scores = peak(0, 0.94);
            reason = "The compiled evidence graph entails every extracted assertion on this date; extraction can still be incomplete. Scores are not calibrated truth probabilities.".into();
        } else if conflicts > 0 {
            chosen = 2;
            scores = peak(2, 0.8);
            reason = "Conflicting labelled evidence on this date; the graph abstains instead of choosing one inconsistent source.".into();
        } else if conservative {
            chosen = 2;
            scores = peak(2, 0.8);
            reason = "The supplied universe does not contain the canonical evidence seed. No complete proof from its own labelled evidence and explicit validity intervals is available; the system abstains.".into();
        } else if row.date < self.earliest_date {
            chosen = 2;
            scores = peak(2, 0.8);
            reason = "Insufficient grounded extraction or relevant evidence; the system abstains."
                .into();
        } else {
            let best = (0..3)
                .max_by(|&a, &b| scores[a].total_cmp(&scores[b]))
                .unwrap_or(2);
            if best == 0 && temporal_supported != facts.len()
                || best == 1 && temporal_contradicted == 0
            {
                chosen = 2;
                scores = peak(2, 0.8);
                reason = "The statistical verdict lacks compatible dated evidence for the full claim. Later records cannot justify an earlier value, and support for one conjunct cannot resolve another. Earlier observations are not a proved validity interval.".into();
            } else if best == 2 || scores[best] < 0.5 {
                chosen = 2;
                scores[2] = scores[2].max(scores[0].max(scores[1]) + 0.05);
                let sum: f64 = scores.iter().sum();
                scores = scores.map(|p| p / sum);
                reason = "No decisive same-day evidence and insufficient model confidence. Earlier observations are shown for review; they do not prove a validity interval.".into();
            } else {
                chosen = best;
                if evidence.is_empty() {
                    reason.push_str(" No grounded supporting observation was found: this label is a statistical estimate only.");
                } else {
                    reason.push_str(" Supporting observations may be earlier than the query; temporal continuity is unproven.");
                }
            }
        }
        Prediction {
            id: row.id.clone(),
            text: row.text.clone(),
            date: row.date.clone(),
            known_label: class(&row.label).map(|_| row.label.clone()),
            label: label(chosen).into(),
            probabilities: Probabilities {
                p_true: scores[0],
                p_false: scores[1],
                p_unsure: scores[2],
            },
            confidence: if chosen == 2 {
                None
            } else {
                Some(scores[chosen].max(0.5))
            },
            facts,
            evidence,
            reason,
        }
    }

    fn valid_fact(&self, fact: &Fact) -> bool {
        self.attributes
            .get(&fact.subject)
            .is_some_and(|fields| fields.contains(&fact.attribute))
            && fact.value.get("kind").is_some()
            && fact.value.get("value").is_some()
    }

    fn entities(&self, text: &str) -> Vec<String> {
        // Port of Mihai's raw_matches / longest_matches / longest_predict,
        // analysis/01_lexicon_analysis.ipynb, organizer fork commit 4478b99.
        let normalized = normalize(text);
        let mut spans: BTreeMap<(usize, usize), BTreeSet<String>> = BTreeMap::new();
        for alias in &self.aliases {
            for matched in alias.pattern.find_iter(&normalized) {
                let start = matched.start();
                let end = matched.end();
                let before = normalized[..start].chars().next_back();
                let after = normalized[end..].chars().next();
                if before.is_some_and(word_character) || after.is_some_and(word_character) {
                    continue;
                }
                spans
                    .entry((start, end))
                    .or_default()
                    .insert(alias.subject.clone());
            }
        }
        let mut candidates: Vec<_> = spans.into_iter().collect();
        candidates.sort_by(|((a, b), _), ((c, d), _)| (d - c).cmp(&(b - a)).then(a.cmp(c)));
        let mut occupied = Vec::new();
        let mut result = BTreeSet::new();
        for ((start, end), owners) in candidates {
            if !occupied.iter().any(|&(a, b)| start < b && a < end) {
                occupied.push((start, end));
                result.extend(owners);
            }
        }
        result.into_iter().collect()
    }

    fn nearest(&self, text: &str, exclude_id: Option<&str>) -> Vec<(usize, f64)> {
        let terms = tokenize(text);
        let mut counts: BTreeMap<usize, usize> = BTreeMap::new();
        for term in &terms {
            if let Some(indices) = self.inverted.get(term) {
                for &i in indices {
                    *counts.entry(i).or_default() += 1;
                }
            }
        }
        let normalized = normalize(text);
        let mut result: Vec<_> = counts
            .into_iter()
            .filter_map(|(i, intersection)| {
                let example = &self.examples[i];
                if exclude_id.is_some_and(|id| {
                    example.row.id == id || normalize(&example.row.text) == normalized
                }) {
                    return None;
                }
                let union = terms.len() + example.terms.len() - intersection;
                Some((i, intersection as f64 / union.max(1) as f64))
            })
            .collect();
        result.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
        result.truncate(16);
        result
    }

    fn extract_with_nearest(&self, row: &InputRow, nearest: &[(usize, f64)]) -> Vec<Fact> {
        if !row.form.is_empty() {
            return row
                .form
                .iter()
                .filter(|f| self.valid_fact(f))
                .cloned()
                .collect();
        }
        if let Some(indices) = self.exact.get(&normalize(&row.text)) {
            let best = indices.iter().min_by_key(|&&i| {
                if self.examples[i].row.date == row.date {
                    0
                } else {
                    1
                }
            });
            if let Some(&i) = best {
                return self.examples[i].row.form.clone();
            }
        }
        // A new unlabelled entity must not inherit a known company's facts
        // solely because its sentence resembles a training template. Explicit
        // forms and exact known source texts were handled above.
        if row.label.is_empty() && self.entities(&row.text).is_empty() {
            return Vec::new();
        }
        self.extract_template(row, nearest)
    }

    fn extract_template(&self, row: &InputRow, nearest: &[(usize, f64)]) -> Vec<Fact> {
        let entities = self.entities(&row.text);
        let Some(&(index, similarity)) = nearest.iter().find(|&&(i, sim)| {
            sim >= 0.34
                && (entities.is_empty()
                    || self.examples[i]
                        .row
                        .form
                        .iter()
                        .any(|f| entities.contains(&f.subject)))
        }) else {
            return Vec::new();
        };
        let example = &self.examples[index];
        if entities.is_empty() && similarity < 0.58 {
            return Vec::new();
        }
        let mut facts = Vec::new();
        for original in &example.row.form {
            let mut fact = original.clone();
            if !entities.is_empty() && !entities.contains(&fact.subject) {
                let replacements: Vec<_> = entities
                    .iter()
                    .filter(|entity| {
                        self.attributes
                            .get(*entity)
                            .is_some_and(|a| a.contains(&fact.attribute))
                    })
                    .collect();
                if replacements.len() == 1 {
                    fact.subject = replacements[0].clone();
                } else {
                    continue;
                }
            }
            if let Some(value) = self.adapt_value(&row.text, &row.date, &fact.value, &fact.subject)
            {
                fact.value = value;
                if self.valid_fact(&fact) && !facts.contains(&fact) {
                    facts.push(fact);
                }
            }
        }
        facts
    }

    fn adapt_value(
        &self,
        text: &str,
        date: &str,
        original: &Value,
        subject: &str,
    ) -> Option<Value> {
        let kind = original["kind"].as_str()?;
        let lower = text.to_lowercase();
        let mut result = original.clone();
        match kind {
            "boolean" => {
                let negative = tokenize(text)
                    .iter()
                    .any(|word| matches!(word.as_str(), "not" | "never" | "no" | "without"))
                    || lower.contains("n't");
                result["value"] = json!(!negative);
            }
            "name" => {
                let original_name = original["value"].as_str()?;
                if lower.contains(&original_name.to_lowercase()) {
                    return Some(result);
                }
                let candidates: Vec<_> = self
                    .entities(text)
                    .into_iter()
                    .filter(|name| name != original_name && name != subject)
                    .collect();
                if candidates.len() == 1 {
                    result["value"] = json!(candidates[0]);
                } else {
                    return None;
                }
            }
            "percent" => {
                let captures = self.percent.captures(text)?;
                result["value"] = json!(parse_number(&captures[1], None)?);
            }
            "quantity" => {
                let unit = original["unit"].as_str()?;
                let candidates: Vec<_> = self
                    .number
                    .captures_iter(text)
                    .filter(|c| {
                        c.get(3)
                            .is_some_and(|noun| singular(noun.as_str()) == singular(unit))
                    })
                    .collect();
                if candidates.len() != 1 {
                    return None;
                }
                let c = &candidates[0];
                result["value"] = json!(parse_number(&c[1], c.get(2).map(|m| m.as_str()))?);
            }
            "money" => {
                let c = self.money.captures(text)?;
                let (currency, number, multiplier) = if let Some(currency) = c.get(1) {
                    (
                        currency.as_str(),
                        c.get(2)?.as_str(),
                        c.get(3).map(|m| m.as_str()),
                    )
                } else {
                    (c.get(5)?.as_str(), c.get(4)?.as_str(), None)
                };
                result["value"] = json!(parse_number(number, multiplier)?);
                result["currency"] = json!(match currency.to_uppercase().as_str() {
                    "€" | "EUR" => "EUR",
                    "$" | "USD" => "USD",
                    "£" | "GBP" => "GBP",
                    _ => return None,
                });
                if lower.contains("per month")
                    || lower.contains("a month")
                    || lower.contains("monthly")
                {
                    result["per"] = json!("month");
                } else if lower.contains("per year")
                    || lower.contains("a year")
                    || lower.contains("annually")
                {
                    result["per"] = json!("year");
                }
            }
            "duration" => {
                let c = self.duration.captures(text)?;
                result["value"] = json!(parse_number(&c[1], None)?);
                result["unit"] = json!(singular(&c[2]));
            }
            "version" => {
                result["value"] = json!(self.version.captures(text)?.get(1)?.as_str());
            }
            "date" => {
                if let Some(c) = self.written_date.captures(text) {
                    result["value"] = json!(format!(
                        "{}-{:02}-{:02}",
                        &c[3],
                        month(&c[2])?,
                        c[1].parse::<u32>().ok()?
                    ));
                } else if let Some(c) = self.month_date.captures(text) {
                    result["value"] = json!(format!("{}-{:02}", &c[2], month(&c[1])?));
                } else if let Some(c) = self.iso_date.captures(text) {
                    result["value"] = json!(&c[1]);
                } else if lower.contains("today") {
                    result["value"] = json!(date);
                } else {
                    return None;
                }
            }
            _ => return None,
        }
        if kind != "name" && kind != "boolean" {
            result.as_object_mut()?.remove("op");
            for (phrase, op) in [
                ("at least ", "ge"),
                ("at most ", "le"),
                ("more than ", "gt"),
                ("over ", "gt"),
                ("fewer than ", "lt"),
                ("under ", "lt"),
            ] {
                if lower.contains(phrase) {
                    result["op"] = json!(op);
                    break;
                }
            }
        }
        Some(result)
    }

    fn features(
        &self,
        row: &InputRow,
        facts: &[Fact],
        nearest: &[(usize, f64)],
        exclude: Option<&str>,
    ) -> Vec<f64> {
        let terms = tokenize(&row.text);
        let mut result = vec![0.0; 80];
        for term in &terms {
            let hash = term.bytes().fold(0xcbf29ce484222325u64, |hash, b| {
                (hash ^ u64::from(b)).wrapping_mul(0x100000001b3)
            });
            result[hash as usize % 64] += 1.0 / (terms.len().max(1) as f64).sqrt();
        }
        result[64] = (row.text.len() as f64 / 200.0).min(3.0);
        result[65] = row.text.bytes().filter(u8::is_ascii_digit).count() as f64 / 20.0;
        result[66] = f64::from(
            terms
                .iter()
                .any(|word| matches!(word.as_str(), "not" | "never" | "no" | "without")),
        );
        result[67] = f64::from(terms.iter().any(|word| {
            matches!(
                word.as_str(),
                "reportedly" | "rumour" | "rumor" | "perhaps" | "might" | "could"
            )
        }));
        result[68] = facts.len() as f64 / 3.0;
        result[69] = self.entities(&row.text).len() as f64 / 3.0;
        for &(i, similarity) in nearest {
            let other = &self.examples[i].row;
            if other.date > row.date {
                continue;
            }
            if let Some(label) = class(&other.label) {
                result[70 + label] = result[70 + label].max(similarity);
            }
        }
        let mut support: f64 = 0.0;
        let mut conflict: f64 = 0.0;
        let mut missing: f64 = 0.0;
        for fact in facts {
            let related: Vec<_> = self
                .observations
                .get(&key(fact))
                .into_iter()
                .flatten()
                .filter(|e| e.date <= row.date && exclude.is_none_or(|id| e.row_id != id))
                .collect();
            if related.is_empty() {
                missing += 1.0;
            }
            for e in related {
                if e.date == row.date {
                    match compatible_values(&fact.value, &e.fact.value) {
                        Some(true) => support += 1.0,
                        Some(false) => conflict += 1.0,
                        None => {}
                    }
                }
            }
        }
        result[73] = support.min(4.0) / 4.0;
        result[74] = conflict.min(4.0) / 4.0;
        result[75] = missing / facts.len().max(1) as f64;
        result[76] = nearest.first().map_or(0.0, |(_, s)| *s);
        result[77] = f64::from(facts.iter().any(|f| f.value["kind"] == "boolean"));
        result[78] = f64::from(facts.iter().any(|f| f.value["op"].is_string()));
        result[79] = f64::from(row.text.contains(';') || row.text.contains(" and "));
        result.extend(self.knowledge.features(row, facts));
        result
    }
}

/// Deterministic every-fifth holdout. Test texts are removed entirely from training.
/// This is a diagnostic split, not independent application validation.
pub fn evaluate_holdout(practice: &[InputRow], lexicon: &Value) -> Result<HoldoutReport, String> {
    let started = Instant::now();
    if practice.iter().any(|row| class(&row.label).is_none()) {
        return Err("Accuracy evaluation requires a reference label for every source row".into());
    }
    let held_texts: BTreeSet<_> = practice
        .iter()
        .enumerate()
        .filter(|(i, _)| i % 5 == 0)
        .map(|(_, r)| normalize(&r.text))
        .collect();
    let train: Vec<_> = practice
        .iter()
        .filter(|r| !held_texts.contains(&normalize(&r.text)))
        .cloned()
        .collect();
    let tests: Vec<_> = practice
        .iter()
        .enumerate()
        .filter(|(i, _)| i % 5 == 0)
        .map(|(_, r)| r.clone())
        .collect();
    let input: Vec<_> = tests
        .iter()
        .map(|r| InputRow {
            id: r.id.clone(),
            text: r.text.clone(),
            date: r.date.clone(),
            label: String::new(),
            form: Vec::new(),
        })
        .collect();
    let engine = Engine::new(&train, lexicon)?;
    let predictions = engine.predict(&input);
    let mut confusion = [[0usize; 3]; 3];
    for (expected, prediction) in tests.iter().zip(&predictions) {
        confusion[class(&expected.label).unwrap_or(2)][class(&prediction.label).unwrap_or(2)] += 1;
    }
    let correct: usize = (0..3).map(|i| confusion[i][i]).sum();
    let classes: Vec<ClassMetrics> = (0..3)
        .map(|i| {
            let tp = confusion[i][i] as f64;
            let actual: usize = confusion[i].iter().sum();
            let predicted: usize = confusion.iter().map(|row| row[i]).sum();
            let f1 = if actual + predicted == 0 {
                0.0
            } else {
                2.0 * tp / (actual + predicted) as f64
            };
            ClassMetrics {
                label: label(i).into(),
                support: actual,
                precision: if predicted == 0 {
                    0.0
                } else {
                    tp / predicted as f64
                },
                recall: if actual == 0 { 0.0 } else { tp / actual as f64 },
                f1,
            }
        })
        .collect();
    let macro_f1 = classes.iter().map(|metrics| metrics.f1).sum::<f64>() / 3.0;
    let mut training_counts = [0usize; 3];
    for row in &train {
        training_counts[class(&row.label).unwrap_or(2)] += 1;
    }
    // Select the baseline label using training data only. Ties use the stable
    // true/false/unsure order, never information from hidden test labels.
    let mut majority = 0;
    for i in 1..3 {
        if training_counts[i] > training_counts[majority] {
            majority = i;
        }
    }
    let unsure = confusion.iter().map(|row| row[2]).sum::<usize>();
    let denominator = tests.len().max(1) as f64;
    let majority_correct = tests
        .iter()
        .filter(|row| class(&row.label) == Some(majority))
        .count();
    let results = tests
        .iter()
        .zip(predictions)
        .map(|(expected, prediction)| EvaluationResult {
            correct: expected.label == prediction.label,
            expected: expected.label.clone(),
            prediction,
        })
        .collect();
    Ok(HoldoutReport {
        training_rows: train.len(),
        test_rows: tests.len(),
        accuracy: correct as f64 / denominator,
        macro_f1,
        confusion,
        majority_accuracy: majority_correct as f64 / denominator,
        majority_label: label(majority).into(),
        coverage: (tests.len() - unsure) as f64 / denominator,
        correct,
        incorrect: tests.len() - correct,
        unsure,
        elapsed_ms: started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64,
        classes,
        results,
        note: "Every fifth practice row is held out. Its label and form are removed before prediction, and all matching normalized test texts are excluded from training and source evidence. Shared facts and templates remain. This split informed earlier model tuning, so it is a diagnostic, not independent validation. Majority baseline selects its constant label from training only. Scores are uncalibrated model estimates; rows with no reference label cannot have measured accuracy.".into(),
    })
}

/// A sanity gate for a statistical estimate, not proof of temporal continuity.
/// The caller has already excluded future sources. Older matching values must
/// not outvote a newer incompatible value of the same typed property/channel.
fn latest_history_judgement(fact: &Fact, observations: &[&Evidence]) -> Option<bool> {
    let latest = observations
        .iter()
        .filter(|e| compatible(&fact.value, &e.fact.value))
        .map(|e| e.date.as_str())
        .max()?;
    let mut yes = false;
    let mut no = false;
    for source in observations
        .iter()
        .filter(|e| e.date == latest && compatible(&fact.value, &e.fact.value))
    {
        match entails(&fact.value, &source.fact.value, false) {
            Some(true) => yes = true,
            Some(false) => no = true,
            None => {}
        }
    }
    match (yes, no) {
        (true, false) => Some(true),
        (false, true) => Some(false),
        _ => None,
    }
}

fn regex(pattern: &str) -> Result<Regex, String> {
    Regex::new(pattern).map_err(|error| error.to_string())
}
// Mihai's normalise: NFKC, Unicode case folding, collapsed whitespace. ASCII
// lexicon names fold identically; sharp-s and final-sigma folds are explicit.
fn normalize(text: &str) -> String {
    text.nfkc()
        .collect::<String>()
        .to_lowercase()
        .replace('ß', "ss")
        .replace('ς', "σ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
fn word_character(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}
fn key(fact: &Fact) -> (String, String) {
    (fact.subject.clone(), fact.attribute.clone())
}
fn class(label: &str) -> Option<usize> {
    match label {
        "true" => Some(0),
        "false" => Some(1),
        "unsure" => Some(2),
        _ => None,
    }
}
fn label(class: usize) -> &'static str {
    ["true", "false", "unsure"][class]
}
fn peak(class: usize, probability: f64) -> [f64; 3] {
    let mut p = [(1.0 - probability) / 2.0; 3];
    p[class] = probability;
    p
}
fn tokenize(text: &str) -> BTreeSet<String> {
    text.to_lowercase()
        .split(|c: char| !c.is_alphanumeric() && c != '\'')
        .filter(|word| {
            word.len() > 1
                && !matches!(
                    *word,
                    "the"
                        | "and"
                        | "its"
                        | "for"
                        | "with"
                        | "from"
                        | "has"
                        | "have"
                        | "had"
                        | "was"
                        | "were"
                        | "that"
                        | "this"
                        | "are"
                        | "into"
                        | "than"
                        | "our"
                        | "their"
                        | "his"
                        | "her"
                        | "been"
                        | "but"
                        | "now"
                        | "them"
                        | "they"
                        | "you"
                        | "your"
                        | "of"
                        | "to"
                        | "on"
                        | "at"
                        | "in"
                        | "is"
                        | "it"
                        | "an"
                        | "as"
                        | "by"
                )
        })
        .map(str::to_owned)
        .collect()
}
fn singular(word: &str) -> String {
    let word = word.to_lowercase();
    word.strip_suffix('s').unwrap_or(&word).to_owned()
}
fn parse_number(text: &str, multiplier: Option<&str>) -> Option<f64> {
    let n = text.replace(',', "").parse::<f64>().ok()?;
    Some(
        n * match multiplier.unwrap_or("").to_lowercase().as_str() {
            "million" => 1e6,
            "billion" => 1e9,
            "thousand" => 1e3,
            _ => 1.0,
        },
    )
}
fn month(name: &str) -> Option<usize> {
    [
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
    ]
    .iter()
    .position(|m| *m == name.to_lowercase())
    .map(|m| m + 1)
}

/// Only directly comparable exact values can establish a contradiction.
fn compatible_values(claim: &Value, observed: &Value) -> Option<bool> {
    if claim["kind"] != observed["kind"]
        || claim.get("op").is_some_and(|op| op != "eq")
        || observed.get("op").is_some_and(|op| op != "eq")
    {
        return None;
    }
    for field in ["unit", "currency", "per"] {
        if claim.get(field) != observed.get(field) {
            return None;
        }
    }
    if let (Some(a), Some(b)) = (claim["value"].as_f64(), observed["value"].as_f64()) {
        Some(a == b)
    } else {
        Some(claim["value"] == observed["value"])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixtures() -> (Vec<InputRow>, Value) {
        let lexicon = json!({"subjects":[{"name":"Hooly Cloud","aliases":["Cloud"],"attributes":["customers","uptime"]},{"name":"Hooly","aliases":[],"attributes":["customers"]}]});
        let rows = (0..24)
            .map(|i| InputRow {
                id: format!("p-{i}"),
                text: format!("Hooly Cloud serves {} customers.", 10 + i),
                date: format!("2026-01-{:02}", i + 1),
                label: if i % 3 == 0 { "false" } else { "true" }.into(),
                form: vec![Fact {
                    subject: "Hooly Cloud".into(),
                    attribute: "customers".into(),
                    value: json!({"kind":"quantity","value":10+i,"unit":"customer"}),
                }],
            })
            .collect();
        (rows, lexicon)
    }
    #[test]
    fn extracts_changed_quantity_and_longest_entity() {
        let (rows, lexicon) = fixtures();
        let engine = Engine::new(&rows, &lexicon).unwrap();
        let row = InputRow {
            id: "new".into(),
            text: "Hooly Cloud serves 900 customers.".into(),
            date: "2026-01-12".into(),
            ..Default::default()
        };
        let facts = engine.extract(&row);
        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0].subject, "Hooly Cloud");
        assert_eq!(facts[0].value["value"], 900.0);
    }
    #[test]
    fn counterfactual_universe_uses_its_own_anchors_not_training_world_truth() {
        let (training, lexicon) = fixtures();
        let engine = Engine::new(&training, &lexicon).unwrap();
        let f = |n| Fact {
            subject: "Hooly Cloud".into(),
            attribute: "customers".into(),
            value: json!({"kind":"quantity","value":n,"unit":"customer"}),
        };
        let rows=vec![
            InputRow{id:"anchor".into(),text:"From January 1, 2026 through January 31, 2026, Hooly Cloud serves 900 customers.".into(),date:"2026-01-01".into(),label:"true".into(),form:vec![f(900)]},
            InputRow{id:"new-true".into(),text:"Hooly Cloud serves 900 customers.".into(),date:"2026-01-12".into(),form:vec![f(900)],..Default::default()},
            InputRow{id:"new-false".into(),text:"Hooly Cloud serves 21 customers.".into(),date:"2026-01-12".into(),form:vec![f(21)],..Default::default()},
            InputRow{id:"new-unknown".into(),text:"Hooly Cloud serves 900 customers.".into(),date:"2026-02-01".into(),form:vec![f(900)],..Default::default()},
        ];
        assert!(!engine.canonical_seed_present(&rows));
        let predictions = engine.predict_universe(&rows);
        assert_eq!(
            predictions
                .iter()
                .map(|p| p.label.as_str())
                .collect::<Vec<_>>(),
            ["true", "true", "false", "unsure"]
        );
        assert!(
            predictions[1..]
                .iter()
                .flat_map(|p| &p.evidence)
                .all(|e| e.row_id == "anchor")
        );
        assert!(engine.canonical_seed_present(&training));
        let mut altered = training.clone();
        altered[1].label = "false".into();
        assert!(!engine.canonical_seed_present(&altered));
    }
    #[test]
    fn incomplete_parse_cannot_prove_a_whole_claim_but_can_refute_it() {
        let (training, lexicon) = fixtures();
        let engine = Engine::new(&training, &lexicon).unwrap();
        let fact = |n| Fact {
            subject: "Hooly Cloud".into(),
            attribute: "customers".into(),
            value: json!({"kind":"quantity","value":n,"unit":"customer"}),
        };
        let rows = vec![
            InputRow {id:"source".into(), text:"From 2026-01-01 through 2026-01-31, the customer register records 900 customers.".into(), date:"2026-01-01".into(), label:"true".into(), form:vec![fact(900)]},
            InputRow {id:"partial-match".into(), text:"The customer count is 900 and a second clause is unresolved.".into(), date:"2026-01-12".into(), form:vec![fact(900)], ..Default::default()},
            InputRow {id:"partial-false".into(), text:"The customer count is 901 and a second clause is unresolved.".into(), date:"2026-01-12".into(), form:vec![fact(901)], ..Default::default()},
            InputRow {id:"intentionally-empty".into(), text:"Hooly Cloud serves 900 customers.".into(), date:"2026-01-12".into(), ..Default::default()},
        ];
        let hints = ExtractionHints {
            incomplete: ["partial-match".into(), "partial-false".into()].into(),
            recognized_empty: ["intentionally-empty".into()].into(),
            ..Default::default()
        };
        let predictions = engine.predict_universe_with_hints(&rows, &hints);
        assert_eq!(predictions[1].label, "unsure");
        assert_eq!(predictions[2].label, "false");
        assert_eq!(predictions[3].label, "unsure");
        assert!(predictions[3].facts.is_empty());
        // Canonical-world diagnostics can use a learned estimate, but a partial
        // match must never be described as a proof of the whole conjunction.
        let learned = engine.predict_with_hints(&rows, &hints);
        assert_eq!(learned[1].label, "unsure");
        assert_eq!(learned[3].label, "unsure");
        assert!(!learned[1].reason.contains("entails every"));
        let mut unknown = hints.clone();
        unknown.explicit_unknown.insert("partial-match".into());
        assert_eq!(
            engine.predict_with_hints(&rows, &unknown)[1].label,
            "unsure"
        );
    }

    #[test]
    fn latest_dated_channel_prevents_old_values_outvoting_newer_values() {
        let fact = |n| Fact {
            subject: "Plan".into(),
            attribute: "price".into(),
            value: json!({"kind":"money","value":n,"currency":"EUR","per":"month"}),
        };
        let source = |id: &str, date: &str, n| Evidence {
            row_id: id.into(),
            text: id.into(),
            date: date.into(),
            label: "true".into(),
            fact: fact(n),
        };
        let old = source("old", "2026-01-01", 49);
        let recent = source("recent", "2026-02-01", 59);
        assert_eq!(
            latest_history_judgement(&fact(49), &[&old, &recent]),
            Some(false)
        );
        assert_eq!(
            latest_history_judgement(&fact(59), &[&old, &recent]),
            Some(true)
        );
        let conflicting = source("conflict", "2026-02-01", 49);
        assert_eq!(
            latest_history_judgement(&fact(59), &[&recent, &conflicting]),
            None
        );
        let mut different_channel = source("usd", "2026-03-01", 49);
        different_channel.fact.value["currency"] = json!("USD");
        assert_eq!(
            latest_history_judgement(&fact(59), &[&old, &recent, &different_channel]),
            Some(true)
        );
    }

    #[test]
    fn one_supported_conjunct_cannot_resolve_another_with_only_future_evidence() {
        let lexicon = json!({"subjects":[{"name":"Atlas","attributes":["customers","regions"]}]});
        let f = |a: &str, n| Fact {
            subject: "Atlas".into(),
            attribute: a.into(),
            value: json!({"kind":"quantity","value":n,"unit":"user"}),
        };
        let training = vec![
            InputRow {
                id: "past".into(),
                text: "Atlas customers is 900 users.".into(),
                date: "2026-01-01".into(),
                label: "true".into(),
                form: vec![f("customers", 900)],
            },
            InputRow {
                id: "future".into(),
                text: "Atlas regions is 3 users.".into(),
                date: "2026-03-01".into(),
                label: "true".into(),
                form: vec![f("regions", 3)],
            },
        ];
        let engine = Engine::new(&training, &lexicon).unwrap();
        let query = InputRow {
            id: "q".into(),
            text: "Atlas customers is 900 users and regions is 3 users.".into(),
            date: "2026-02-01".into(),
            form: vec![f("customers", 900), f("regions", 3)],
            ..Default::default()
        };
        let output = engine.predict(&[query]);
        assert_eq!(output[0].label, "unsure");
        assert!(
            output[0]
                .evidence
                .iter()
                .all(|e| e.date <= "2026-02-01".to_owned())
        );
    }

    #[test]
    fn unrecognized_owners_and_empty_parses_do_not_inherit_the_majority_class() {
        let (training, lexicon) = fixtures();
        let engine = Engine::new(&training, &lexicon).unwrap();
        let queries = [
            InputRow {
                id: "foreign".into(),
                text: "Emberkeep serves 900 customers.".into(),
                date: "2026-10-29".into(),
                ..Default::default()
            },
            InputRow {
                id: "unparsed".into(),
                text: "Unknown reference without a factual owner.".into(),
                date: "2026-10-29".into(),
                ..Default::default()
            },
        ];
        for prediction in engine.predict(&queries) {
            assert!(prediction.facts.is_empty());
            assert_eq!(prediction.label, "unsure");
            assert!(prediction.confidence.is_none());
        }
    }

    #[test]
    fn preserves_known_labels_and_never_uses_future_evidence() {
        let (rows, lexicon) = fixtures();
        let engine = Engine::new(&rows, &lexicon).unwrap();
        let known = engine.predict(&rows[..1]);
        assert_eq!(known[0].label, "false");
        assert_eq!(known[0].known_label.as_deref(), Some("false"));
        let row = InputRow {
            id: "past".into(),
            text: "Hooly Cloud serves 900 customers.".into(),
            date: "2025-01-01".into(),
            ..Default::default()
        };
        let result = engine.predict(&[row]);
        assert_eq!(result[0].label, "unsure");
        assert!(result[0].evidence.is_empty());
        assert!(result[0].confidence.is_none());
    }
    #[test]
    fn false_compound_rows_do_not_become_true_evidence() {
        let (rows, lexicon) = fixtures();
        let engine = Engine::new(&rows, &lexicon).unwrap();
        let row = InputRow {
            id: "new".into(),
            text: "Hooly Cloud serves 99 customers.".into(),
            date: "2026-01-01".into(),
            ..Default::default()
        };
        let result = engine.predict(&[row]);
        // Negative constraints are now visible provenance, never positive facts.
        assert!(result[0].evidence.iter().all(|e| e.label == "false"));
        assert!(
            result[0]
                .evidence
                .iter()
                .all(|e| e.fact.value["value"] != 99)
        );
        let scores = &result[0].probabilities;
        assert!((scores.p_true + scores.p_false + scores.p_unsure - 1.0).abs() < 1e-9);
    }

    #[test]
    fn mihai_surface_matching_preserves_boundaries_and_nfkc() {
        let (rows, lexicon) = fixtures();
        let engine = Engine::new(&rows, &lexicon).unwrap();
        assert_eq!(
            engine.entities("Ｈｏｏｌｙ　Ｃｌｏｕｄ"),
            vec!["Hooly Cloud"]
        );
        assert_eq!(engine.entities("HoolyCloud"), vec!["Hooly Cloud"]);
        assert!(engine.entities("HoolyCloudish").is_empty());
        assert_eq!(
            engine.entities("Hooly Cloud and Hooly"),
            vec!["Hooly", "Hooly Cloud"]
        );
    }

    #[test]
    fn holdout_hides_unique_facts_and_removes_duplicate_test_texts() {
        let (mut rows, mut lexicon) = fixtures();
        lexicon["subjects"].as_array_mut().unwrap().push(json!({
            "name":"Secret Entity", "aliases":[], "attributes":["secret_phrase"]
        }));
        let secret = Fact {
            subject: "Secret Entity".into(),
            attribute: "secret_phrase".into(),
            value: json!({"kind":"name","value":"ultramarine-862"}),
        };
        rows[0].text = "Secret Entity uses ultramarine-862 as its secret phrase.".into();
        rows[0].label = "true".into();
        rows[0].form = vec![secret.clone()];
        // An otherwise training-position duplicate must not reveal the test answer.
        rows[1].text = rows[0].text.to_uppercase();
        rows[1].label = "true".into();
        rows[1].form = vec![secret.clone()];
        let report = evaluate_holdout(&rows, &lexicon).unwrap();
        assert_eq!(report.training_rows, 18);
        assert_eq!(report.test_rows, 5);
        let held_ids = ["p-0", "p-5", "p-10", "p-15", "p-20", "p-1"];
        for result in &report.results {
            assert!(result.prediction.known_label.is_none());
            assert!(
                result
                    .prediction
                    .evidence
                    .iter()
                    .all(|e| !held_ids.contains(&e.row_id.as_str()))
            );
            assert!(
                !result
                    .prediction
                    .reason
                    .starts_with("Exact text and date match")
            );
        }
        assert!(!report.results[0].prediction.facts.contains(&secret));
    }

    #[test]
    fn evaluation_metrics_match_visible_predictions_and_training_baseline() {
        let (rows, lexicon) = fixtures();
        let report = evaluate_holdout(&rows, &lexicon).unwrap();
        let mut recomputed = [[0usize; 3]; 3];
        for result in &report.results {
            let prediction = &result.prediction;
            recomputed[class(&result.expected).unwrap()][class(&prediction.label).unwrap()] += 1;
            assert_eq!(result.correct, result.expected == prediction.label);
            assert!(prediction.known_label.is_none());
            let scores = &prediction.probabilities;
            assert!((scores.p_true + scores.p_false + scores.p_unsure - 1.0).abs() < 1e-9);
        }
        assert_eq!(report.confusion, recomputed);
        assert_eq!(
            report.correct,
            report.results.iter().filter(|r| r.correct).count()
        );
        assert_eq!(report.correct + report.incorrect, report.test_rows);
        assert_eq!(
            report.unsure,
            report
                .results
                .iter()
                .filter(|r| r.prediction.label == "unsure")
                .count()
        );
        assert!(
            (report.coverage - (report.test_rows - report.unsure) as f64 / report.test_rows as f64)
                .abs()
                < 1e-9
        );
        assert!((report.accuracy - report.correct as f64 / report.test_rows as f64).abs() < 1e-9);
        assert_eq!(report.majority_label, "true");
        assert!((report.majority_accuracy - 3.0 / 5.0).abs() < 1e-9);
        for (i, metrics) in report.classes.iter().enumerate() {
            let support: usize = recomputed[i].iter().sum();
            let predicted: usize = recomputed.iter().map(|row| row[i]).sum();
            let tp = recomputed[i][i] as f64;
            assert_eq!(metrics.label, label(i));
            assert_eq!(metrics.support, support);
            assert_eq!(
                metrics.precision,
                if predicted == 0 {
                    0.0
                } else {
                    tp / predicted as f64
                }
            );
            assert_eq!(
                metrics.recall,
                if support == 0 {
                    0.0
                } else {
                    tp / support as f64
                }
            );
            assert_eq!(
                metrics.f1,
                if support + predicted == 0 {
                    0.0
                } else {
                    2.0 * tp / (support + predicted) as f64
                }
            );
        }
        assert!(
            (report.macro_f1 - report.classes.iter().map(|c| c.f1).sum::<f64>() / 3.0).abs() < 1e-9
        );
    }
}
