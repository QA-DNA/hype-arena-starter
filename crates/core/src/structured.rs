//! Text-only, schema-guided assertion binding layered over frozen value proposals.
//!
//! This module never sees labels, dates of observation, accepted evidence, or gold.
//! Candidate offsets are Unicode scalar (Python character) offsets, not UTF-8 bytes.
use crate::model::Fact;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::ops::Range;
use std::sync::LazyLock;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ValueCandidate {
    pub value: Value,
    pub start: usize,
    pub end: usize,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Parsed {
    pub facts: Vec<Fact>,
    /// All assertion clauses were grounded. Unknown declarations are recognized
    /// but produce no ordinary value; their notes must not be read as booleans.
    pub complete: bool,
    pub notes: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct SchemaParser {
    subjects: Vec<Subject>,
    aliases: BTreeMap<String, Vec<usize>>,
    attributes: BTreeMap<String, String>,
    alias_re: Regex,
    attribute_re: Regex,
    surface_cues: Vec<(String, Regex)>,
}

#[derive(Clone, Debug)]
struct Subject {
    name: String,
    attributes: BTreeSet<String>,
}

#[derive(Clone, Debug)]
struct Mention {
    span: Range<usize>,
    owners: Vec<usize>,
}

#[derive(Clone, Debug)]
struct Field {
    span: Range<usize>,
    name: String,
    literal: bool,
    value_span: Option<Range<usize>>,
}

#[derive(Clone, Debug)]
struct Proposed {
    span: Range<usize>,
    value: Value,
}

fn rx(pattern: &str) -> Regex {
    // Patterns are source constants. Invalid external schemas return errors in compile.
    Regex::new(pattern).expect("source regular expression")
}

static CLAUSE: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i);\s*(?:and\b\s*)?|\b(?:and|but)\b|[.!?]|\n\s*\n"));
static INTERVAL: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^\s*from\s+\d{4}-\d{2}-\d{2}\s+through\s+\d{4}-\d{2}-\d{2}\s*,\s*"));
static DECLARATION: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)^\s*record\s+subject\s*:\s*"));
static IDENTIFIER: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^\s*document\s+reference\s*:\s*\d+\s*\(identifier\s+only\)\s*$"));
static UNKNOWN: LazyLock<Regex> = LazyLock::new(|| {
    rx(r"(?i)\b(?:explicitly\s+)?(?:unrecorded|unknown|not\s+recorded|not\s+known)\b")
});
static DESCRIPTOR: LazyLock<Regex> = LazyLock::new(|| rx(r"\[[^\[\]\r\n]*\]"));
static BOOL: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)\b(?:yes|no|true|false)\b"));
static PRONOUN: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^\s*(?:it|its|he|his|she|her|they|their)\b"));
static NUMBER: LazyLock<Regex> = LazyLock::new(|| rx(r"-?\d[\d,.]*"));
static WORD_NUMBER: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)\b(?:a\s+dozen|a\s+hundred|(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|an|a)\b",
    )
});
static SCALE: LazyLock<Regex> = LazyLock::new(|| rx(r"^\s*(million|billion|thousand|bn|k|M)\b"));
static UNIT: LazyLock<Regex> = LazyLock::new(|| rx(r#"^\s*[-]?\s*([\p{L}]+|[\"″])"#));
static CURRENCY_BEFORE: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)(US\s*\$|€|\$|£|\bEUR|\bUSD|\bGBP|\bCHF|\bRON|\bPLN|\bCZK|\bHUF|\bSEK|\bNOK|\bDKK|\bJPY|\bCNY|\bINR|\bCAD|\bAUD)\s*$",
    )
});
static CURRENCY_AFTER: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)^\s*(US\s*\$|€|\$|£|(?:euros?|dollars?|lei|EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD)\b)",
    )
});
static PERIOD: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)^\s*(?:(?:per\s+(?:user|seat|terabyte)|/\s*(?:user|seat))\s*)?(?:(?:per\s+|a\s+|each\s+|/\s*)(month|mo|mth|year|yr|week|wk|day)|(?P<annual>annually|yearly|per\s+annum)|(?P<monthly>monthly)|(?P<weekly>weekly)|(?P<daily>daily))\b",
    )
});
static PERCENT: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)^\s*(?:%|percent\b|per\s+cent\b)"));
static VERSION: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^(?:(?:version|ver\.)\s*|v)?(\d+(?:\.\d+)*)$"));
static APPROX: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)(?:\b(?:about|around|approximately|approx\.?|roughly|circa|ca\.?|nearly|almost|some|estimated|est\.?|close\s+to|more\s+or\s+less)|[~≈±])\s*$",
    )
});
static NONEXACT_SUFFIX: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^(?:\s*(?:or\s+so|give\s+or\s+take)\b|\s*-ish\b)"));
static NEGATION: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)\b(?:not|never|without|cannot)\b|n't\b"));
static OPERATORS: LazyLock<Vec<(Regex, &'static str)>> = LazyLock::new(|| {
    [
        (r"(?:different\s+from|not\s+equal\s+to|other\s+than|unequal\s+to|!=|≠)", "ne"),
        (r"(?:at\s+least|no\s+less\s+than|not\s+less\s+than|no\s+fewer\s+than|no\s+earlier\s+than|no\s+older\s+than|minimum|min|>=|≥)", "ge"),
        (r"(?:at\s+most|no\s+more\s+than|not\s+more\s+than|no\s+later\s+than|no\s+newer\s+than|up\s+to|within|maximum|max|<=|≤)", "le"),
        (r"(?:more\s+than|greater\s+than|higher\s+than|larger\s+than|over|above|exceeding|in\s+excess\s+of|upwards\s+of|newer\s+than|after|>)", "gt"),
        (r"(?:less\s+than|fewer\s+than|lower\s+than|under|below|older\s+than|before|prior\s+to|<)", "lt"),
        (r"(?:equals?|equal\s+to|exactly|only|just|starting\s+at|from|=)", "eq"),
    ].into_iter().map(|(p, op)| (rx(&format!(r"(?i)(?:^|\b|\s)({p})\s*(?:the\s+)?$")), op)).collect()
});

impl SchemaParser {
    pub fn compile(lexicon: &Value) -> Result<Self, String> {
        let rows = lexicon
            .get("subjects")
            .and_then(Value::as_array)
            .ok_or("lexicon.subjects must be an array")?;
        let mut subjects = Vec::new();
        let mut aliases = BTreeMap::<String, Vec<usize>>::new();
        let mut attributes = BTreeMap::new();
        let mut alias_forms = BTreeMap::new();
        let mut attribute_forms = BTreeMap::new();
        let mut names = BTreeSet::new();
        if rows.len() > 100_000 {
            return Err("too many schema subjects".into());
        }
        for row in rows {
            let name = row
                .get("name")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .ok_or("every subject requires a nonempty name")?;
            if !names.insert(name.to_owned()) {
                return Err(format!("duplicate subject {name}"));
            }
            let attrs = row
                .get("attributes")
                .and_then(Value::as_array)
                .ok_or_else(|| format!("attributes for {name} must be an array"))?;
            let mut fields = BTreeSet::new();
            for a in attrs {
                let a = a
                    .as_str()
                    .filter(|s| !key(s).is_empty())
                    .ok_or("attributes must be nonempty strings")?;
                let k = key(a);
                if attributes.get(&k).is_some_and(|old| old != a) {
                    return Err(format!("ambiguous normalized attribute {a}"));
                }
                attributes.insert(k.clone(), a.to_owned());
                attribute_forms.insert(k, phrase(a));
                fields.insert(a.to_owned());
            }
            let owner = subjects.len();
            let mut forms = vec![name];
            if let Some(extra) = row.get("aliases") {
                for a in extra.as_array().ok_or("aliases must be an array")? {
                    forms.push(a.as_str().ok_or("aliases must be strings")?);
                }
            }
            for a in forms {
                let k = key(a);
                if k.is_empty() {
                    return Err("empty normalized alias".into());
                }
                aliases.entry(k.clone()).or_default().push(owner);
                alias_forms.insert(k, phrase(a));
            }
            subjects.push(Subject {
                name: name.to_owned(),
                attributes: fields,
            });
        }
        for owners in aliases.values_mut() {
            owners.sort_unstable();
            owners.dedup();
        }
        // Reuse the project's language cues, never graph values. A cue only
        // proposes a field: literal text, a legal explicit owner and a unique
        // typed value must still license the actual binding.
        let cues: BTreeMap<String, Vec<String>> =
            serde_json::from_str(include_str!("extraction/attribute-cues.json"))
                .map_err(|e| format!("bundled attribute cues: {e}"))?;
        let mut surface_cues = Vec::new();
        for (name, patterns) in cues {
            if subjects.iter().any(|s| s.attributes.contains(&name)) {
                let pattern = format!("(?i)(?:{})", patterns.join("|"));
                surface_cues.push((name, Regex::new(&pattern).map_err(|e| e.to_string())?));
            }
        }
        if subjects
            .iter()
            .any(|s| s.attributes.contains("would_recommend"))
        {
            surface_cues.push((
                "would_recommend".into(),
                rx(r"(?i)\brecommend(?:ation)?(?:\s+rate)?\b"),
            ));
        }
        Ok(Self {
            subjects,
            aliases,
            attributes,
            alias_re: alternatives(alias_forms)?,
            attribute_re: alternatives(attribute_forms)?,
            surface_cues,
        })
    }

    pub fn parse(&self, text: &str, candidates: &[ValueCandidate], neural: &[Fact]) -> Parsed {
        if text.chars().count() > 65_536 || candidates.len() > 4096 {
            return Parsed {
                facts: neural.to_vec(),
                complete: false,
                notes: vec!["input_limit; neural fallback retained".into()],
            };
        }
        let mut boundaries: Vec<_> = text.char_indices().map(|(b, _)| b).collect();
        boundaries.push(text.len());
        let mut invalid = 0;
        let descriptors: Vec<_> = DESCRIPTOR.find_iter(text).map(|m| m.range()).collect();
        let proposals: Vec<_> = candidates
            .iter()
            .filter_map(|c| {
                if c.start >= c.end || c.end >= boundaries.len() {
                    invalid += 1;
                    return None;
                }
                let span = boundaries[c.start]..boundaries[c.end];
                if descriptors.iter().any(|d| overlap(d, &span)) {
                    return None;
                }
                Some(Proposed {
                    span,
                    value: c.value.clone(),
                })
            })
            .collect();
        let mentions = self.mentions(text);
        let fields = self.fields(text, &mentions, &proposals);
        let spans = clauses(text, &mentions, &fields, &proposals);
        let mut result = Parsed {
            complete: true,
            ..Parsed::default()
        };
        if invalid > 0 {
            result.notes.push(format!(
                "ignored {invalid} invalid candidate character spans"
            ));
        }
        let mut antecedent: Option<Vec<usize>> = None;
        let mut structured = 0;
        let mut unknown = 0;
        let mut unresolved = Vec::new();
        let mut last_end = 0;
        let mut assertions = 0;
        for mut span in spans {
            if rx_blank_line(&text[last_end..span.start]) {
                antecedent = None;
            }
            last_end = span.end;
            let clause = &text[span.clone()];
            if let Some(d) = DECLARATION.find(clause) {
                let entities: Vec<_> = mentions
                    .iter()
                    .filter(|m| inside(&m.span, &span) && m.span.start >= span.start + d.end())
                    .collect();
                antecedent = if entities.len() == 1
                    && text[span.start + d.end()..entities[0].span.start]
                        .trim()
                        .is_empty()
                    && text[entities[0].span.end..span.end]
                        .trim_matches(|c: char| c.is_whitespace() || c == '.')
                        .is_empty()
                {
                    Some(entities[0].owners.clone())
                } else {
                    None
                };
                if antecedent.is_none() {
                    result
                        .notes
                        .push("unresolved Record subject declaration".into());
                    result.complete = false;
                    assertions += 1;
                }
                continue;
            }
            if IDENTIFIER.is_match(clause) {
                continue;
            }
            if let Some(m) = INTERVAL.find(clause) {
                span.start += m.end();
            }
            if text[span.clone()].trim().is_empty() {
                continue;
            }
            assertions += 1;
            let mut local_fields: Vec<_> =
                fields.iter().filter(|f| inside(&f.span, &span)).collect();
            // A count noun may itself be a schema field ("29 seats"). When
            // an explicit field is also written, that noun is part of its
            // value, not a second assertion about some other schema owner.
            let embedded = |f: &&Field| {
                proposals.iter().any(|p| {
                    matches!(
                        p.value["kind"].as_str(),
                        Some("quantity" | "duration" | "money" | "percent")
                    ) && inside(&f.span, &p.span)
                        && NUMBER
                            .find(&text[p.span.clone()])
                            .or_else(|| WORD_NUMBER.find(&text[p.span.clone()]))
                            .is_some_and(|n| p.span.start + n.start() < f.span.start)
                })
            };
            if local_fields.iter().any(|f| !embedded(f)) {
                local_fields.retain(|f| !embedded(f));
            }
            let version_marker = |f: &&Field| {
                f.name == "version"
                    && proposals
                        .iter()
                        .any(|p| p.value["kind"] == "version" && inside(&f.span, &p.span))
            };
            if local_fields.iter().any(|f| {
                !version_marker(f) && (f.name == "version" || f.name.ends_with("_version"))
            }) {
                local_fields.retain(|f| !version_marker(f));
            }
            let local_mentions: Vec<_> =
                mentions.iter().filter(|m| inside(&m.span, &span)).collect();
            let mut count = 0;
            let mut consumed = Vec::new();
            let mut owners = BTreeSet::new();
            let initial_unknown = unknown;
            for field in &local_fields {
                let Some(subject) =
                    self.subject(text, field, &local_mentions, &span, antecedent.as_deref())
                else {
                    result
                        .notes
                        .push(format!("unresolved subject for {}", field.name));
                    continue;
                };
                owners.insert(subject);
                let declares_unknown = UNKNOWN
                    .find_iter(&text[span.clone()])
                    .map(|m| span.start + m.start()..span.start + m.end())
                    .any(|u| {
                        !local_mentions.iter().any(|m| overlap(&m.span, &u))
                            && !proposals
                                .iter()
                                .any(|p| p.value["kind"] == "name" && inside(&u, &p.span))
                            && !local_fields.iter().any(|f| overlap(&f.span, &u))
                            && !local_fields.iter().any(|f| {
                                f.span != field.span
                                    && distance(&f.span, &u) < distance(&field.span, &u)
                            })
                    });
                if declares_unknown {
                    unknown += 1;
                    count += 1;
                    result.notes.push(format!(
                        "explicit_unknown:{}:{}",
                        self.subjects[subject].name, field.name
                    ));
                    continue;
                }
                match self.value(
                    text,
                    field,
                    &local_fields,
                    &local_mentions,
                    &proposals,
                    &span,
                    subject,
                ) {
                    Some(value) => {
                        consumed.push(value.span);
                        let fact = Fact {
                            subject: self.subjects[subject].name.clone(),
                            attribute: field.name.clone(),
                            value: value.value,
                        };
                        if !result.facts.contains(&fact) {
                            result.facts.push(fact);
                        }
                        count += 1;
                        structured += 1;
                        if !field.literal {
                            result.complete = false;
                            result.notes.push(format!(
                                "surface_binding:{}:{}; coverage remains incomplete",
                                self.subjects[subject].name, field.name
                            ));
                        }
                    }
                    None => result.notes.push(format!(
                        "unresolved value for {}:{}",
                        self.subjects[subject].name, field.name
                    )),
                }
            }
            // A field/value binding does not cover another written number or
            // date in the same clause. Nested weak grammar proposals are
            // covered by their containing value, but unrelated values remain
            // available to the measured neural fallback.
            let uncovered = proposals.iter().any(|p| {
                inside(&p.span, &span)
                    && p.value["kind"] != "boolean"
                    && !mentions.iter().any(|m| {
                        overlap(&m.span, &p.span)
                            && (p.value["kind"] != "name"
                                || m.owners.iter().any(|s| owners.contains(s)))
                    })
                    && !local_fields.iter().any(|f| inside(&p.span, &f.span))
                    && repair_value(text, p, &span)
                        .is_some_and(|v| !consumed.iter().any(|s| overlap(s, &v.span)))
                    && unknown == initial_unknown
            });
            if count == 0 || count < local_fields.len() || uncovered {
                result.complete = false;
                unresolved.push(span.clone());
                if uncovered {
                    result
                        .notes
                        .push("unparsed value in assertion clause".into());
                }
            }
            // Explicitly bound subjects establish row-local focus. Named
            // values never steal focus; two grammatical owners clear it.
            // Ordinary omitted subjects remain unresolved without a pronoun.
            if owners.len() == 1 {
                antecedent = Some(owners.into_iter().collect());
            } else if owners.len() > 1 || !local_mentions.is_empty() {
                antecedent = None;
            }
        }
        if assertions == 0 {
            result.facts.clear();
            result.notes.push("metadata_only".into());
        } else if structured == 0 && unknown == 0 {
            result.facts = neural.to_vec();
            result.complete = false;
            result
                .notes
                .push("neural_fallback:no reliable schema binding".into());
        } else {
            // Keep neural proposals from unresolved clauses, never from a clause
            // whose explicit schema binding has replaced their subject/field.
            for span in unresolved {
                for fact in neural {
                    let present = mentions.iter().any(|m| {
                        inside(&m.span, &span)
                            && m.owners
                                .iter()
                                .any(|&i| self.subjects[i].name == fact.subject)
                    });
                    // A later natural-language conjunct can omit the subject.
                    // Preserve the measured neural fallback when its exact
                    // typed value proposal occurs in that unresolved clause;
                    // this does not invent an antecedent or claim completion.
                    let proposed_here = proposals
                        .iter()
                        .any(|p| inside(&p.span, &span) && p.value == fact.value);
                    if (present || proposed_here) && !result.facts.contains(fact) {
                        result.facts.push(fact.clone());
                        result.notes.push(format!(
                            "neural_clause_fallback:{}:{}",
                            fact.subject, fact.attribute
                        ));
                    }
                }
            }
        }
        result
    }

    fn mentions(&self, text: &str) -> Vec<Mention> {
        self.alias_re
            .find_iter(text)
            .filter(|m| whole(text, &m.range()))
            .filter_map(|m| {
                self.aliases.get(&key(m.as_str())).map(|owners| Mention {
                    span: m.range(),
                    owners: owners.clone(),
                })
            })
            .collect()
    }

    fn fields(&self, text: &str, mentions: &[Mention], proposals: &[Proposed]) -> Vec<Field> {
        // Mask names before matching. Otherwise "AI Pro: price" first
        // matches the unrelated longer field pro_price, and filtering that
        // overlap afterwards loses the real price match permanently.
        let mut masked = text.as_bytes().to_vec();
        for span in mentions.iter().map(|m| &m.span) {
            masked[span.clone()].fill(b' ');
        }
        for p in proposals.iter().filter(|p| p.value["kind"] == "version") {
            // "version 2.3" contains both a field word and its value. Mask
            // digits without erasing that explicit language cue.
            let start = NUMBER
                .find(&text[p.span.clone()])
                .map_or(p.span.start, |m| p.span.start + m.start());
            masked[start..p.span.end].fill(b' ');
        }
        for m in DESCRIPTOR.find_iter(text) {
            masked[m.range()].fill(b' ');
        }
        let masked = String::from_utf8(masked).expect("whole UTF-8 spans replaced with ASCII");
        let mut fields: Vec<_> = self
            .attribute_re
            .find_iter(&masked)
            .filter(|m| whole(text, &m.range()))
            .filter_map(|m| {
                self.attributes.get(&key(m.as_str())).map(|name| Field {
                    span: m.range(),
                    name: name.clone(),
                    literal: true,
                    value_span: None,
                })
            })
            .collect();
        // An alias can also be a word *inside* a literal field: the alias
        // "Cloud" must not hide cloud_provider. Restore only whole fields
        // that contain those shorter aliases, never a tail of a longer name.
        for m in self
            .attribute_re
            .find_iter(text)
            .filter(|m| whole(text, &m.range()))
        {
            if DESCRIPTOR
                .find_iter(text)
                .any(|d| overlap(&d.range(), &m.range()))
                || mentions.iter().any(|n| {
                    overlap(&n.span, &m.range())
                        && (!inside(&n.span, &m.range()) || n.span == m.range())
                })
            {
                continue;
            }
            if let Some(name) = self.attributes.get(&key(m.as_str())) {
                fields.push(Field {
                    span: m.range(),
                    name: name.clone(),
                    literal: true,
                    value_span: None,
                });
            }
        }
        let local_mentions: Vec<_> = mentions.iter().collect();
        let mut cues = Vec::new();
        for (name, re) in &self.surface_cues {
            for m in re.find_iter(text).filter(|m| whole(text, &m.range())) {
                if fields.iter().any(|f| overlap(&f.span, &m.range())) {
                    continue;
                }
                // Value-shaped cues (a currency symbol alone, bare digits,
                // or a unit) cannot invent a field. Keep a lexical anchor
                // outside all frozen values and entity aliases.
                let mut anchor = text.as_bytes()[m.range()].to_vec();
                for s in mentions.iter().map(|n| &n.span).chain(
                    proposals
                        .iter()
                        .filter(|p| p.value["kind"] != "boolean")
                        .map(|p| &p.span),
                ) {
                    if overlap(s, &m.range()) {
                        anchor[s.start.max(m.start()) - m.start()..s.end.min(m.end()) - m.start()]
                            .fill(b' ');
                    }
                }
                let anchor = String::from_utf8(anchor).ok();
                let Some(anchor) = anchor else { continue };
                let Some(first) = anchor.find(|c: char| c.is_alphabetic()) else {
                    continue;
                };
                let last = anchor
                    .char_indices()
                    .rfind(|(_, c)| c.is_alphabetic())
                    .map(|(i, c)| i + c.len_utf8())
                    .unwrap_or(first);
                let field = Field {
                    span: m.start() + first..m.start() + last,
                    name: name.clone(),
                    literal: false,
                    value_span: proposals
                        .iter()
                        .any(|p| {
                            !matches!(p.value["kind"].as_str(), Some("boolean" | "name"))
                                && inside(&p.span, &m.range())
                        })
                        .then(|| m.range()),
                };
                // Numeric comparators alone express a bound, not which
                // schema field the bound describes.
                if field.span.len() < 3
                    || OPERATORS
                        .iter()
                        .any(|(p, _)| p.find(anchor.trim()).is_some_and(|m| m.start() == 0))
                    || self
                        .subject(text, &field, &local_mentions, &(0..text.len()), None)
                        .is_none()
                {
                    continue;
                }
                cues.push(field);
            }
        }
        // Equal textual support for distinct legal fields is unresolved.
        // Sorting by attribute name must never settle a semantic ambiguity.
        fields.extend(
            cues.iter()
                .filter(|f| {
                    !cues
                        .iter()
                        .any(|other| other.name != f.name && overlap(&other.span, &f.span))
                })
                .cloned(),
        );
        // A written interface marker determines the version channel. Bare
        // numeric identity cannot choose API versus product by value.
        static INTERFACE: LazyLock<Regex> =
            LazyLock::new(|| rx(r"(?i)^\s+of\s+(?:the\s+)?(?:api|interface)\b"));
        for f in &mut fields {
            if f.name == "version"
                && proposals.iter().any(|p| {
                    p.value["kind"] == "version"
                        && f.span.start <= p.span.end
                        && f.span.end <= p.span.end
                        && INTERFACE.is_match(&text[p.span.end..])
                })
            {
                f.name = "api_version".into();
                f.literal = false;
            }
        }
        // Product-number adjacency is usable only when exactly one version
        // field is legal. API/product alternatives deliberately stay open.
        for p in proposals.iter().filter(|p| p.value["kind"] == "version") {
            if fields.iter().any(|f| overlap(&f.span, &p.span)) {
                continue;
            }
            let nearby: Vec<_> = mentions
                .iter()
                .filter(|m| {
                    m.span.end <= p.span.start && text[m.span.end..p.span.start].trim().is_empty()
                })
                .collect();
            if nearby.len() != 1 || nearby[0].owners.len() != 1 {
                continue;
            }
            static VERSION_PREDICATE: LazyLock<Regex> = LazyLock::new(|| {
                rx(
                    r"(?i)^\s*(?:is|are|was|were|brings?|ships?|arrives?|keeps?|runs?|offers?|supports?)\b",
                )
            });
            if !VERSION_PREDICATE.is_match(&text[p.span.end..])
                && proposals.iter().any(|other| {
                    matches!(
                        other.value["kind"].as_str(),
                        Some("money" | "quantity" | "duration" | "percent")
                    ) && overlap(&other.span, &p.span)
                        && repair_value(text, other, &(0..text.len())).is_some()
                })
            {
                continue;
            }
            let versions: Vec<_> = self.subjects[nearby[0].owners[0]]
                .attributes
                .iter()
                .filter(|a| a.as_str() == "version" || a.ends_with("_version"))
                .collect();
            if versions.len() == 1 {
                fields.push(Field {
                    span: p.span.clone(),
                    name: versions[0].clone(),
                    literal: false,
                    value_span: Some(p.span.clone()),
                });
            }
        }
        // "Product is still EUR 17/month" is a monetary predicate with an
        // explicit owner. It licenses only that owner's generic price field;
        // no missing currency, period or tier is supplied from the schema.
        static MONEY_COPULA: LazyLock<Regex> = LazyLock::new(|| {
            rx(r"(?i)^\s+(?:is|remains|stays)(?:\s+(?:still|now|currently))?\s*$")
        });
        let monetary_clauses = clauses(text, mentions, &fields, proposals);
        for p in proposals.iter().filter(|p| p.value["kind"] == "money") {
            if fields.iter().any(|f| {
                overlap(&f.span, &p.span)
                    || (f.name == "price"
                        && monetary_clauses
                            .iter()
                            .any(|s| inside(&p.span, s) && inside(&f.span, s)))
            }) {
                continue;
            }
            for m in mentions.iter().filter(|m| {
                m.owners.len() == 1
                    && m.span.end <= p.span.start
                    && self.subjects[m.owners[0]].attributes.contains("price")
                    && MONEY_COPULA.is_match(&text[m.span.end..p.span.start])
            }) {
                let gap = &text[m.span.end..p.span.start];
                let first = gap.find(|c: char| !c.is_whitespace()).unwrap_or(0);
                fields.push(Field {
                    span: m.span.end + first..p.span.start,
                    name: "price".into(),
                    literal: false,
                    value_span: Some(p.span.clone()),
                });
            }
        }
        fields.sort_by_key(|f| (std::cmp::Reverse(f.span.len()), f.span.start));
        let mut longest = Vec::<Field>::new();
        for f in fields {
            if !longest.iter().any(|a| overlap(&a.span, &f.span)) {
                longest.push(f);
            }
        }
        longest.sort_by_key(|f| f.span.start);
        longest
    }

    fn subject(
        &self,
        text: &str,
        field: &Field,
        mentions: &[&Mention],
        clause: &Range<usize>,
        antecedent: Option<&[usize]>,
    ) -> Option<usize> {
        let mut choices = Vec::new();
        for m in mentions {
            if mentions.iter().any(|other| {
                other.span != m.span
                    && m.span.end <= other.span.start
                    && other.span.end <= field.span.start
            }) {
                continue;
            }
            let mut owners = m
                .owners
                .iter()
                .copied()
                .filter(|&s| self.subjects[s].attributes.contains(&field.name));
            let Some(owner) = owners.next() else {
                continue;
            };
            if owners.next().is_some() {
                continue;
            }
            let score = if m.span.end <= field.span.start {
                let gap = text[m.span.end..field.span.start].trim().to_lowercase();
                let before = text[clause.start..m.span.start].trim().to_lowercase();
                if gap.is_empty() || gap == "'s" || gap == "’s" {
                    0
                } else if gap.starts_with("'s")
                    || gap.starts_with("’s")
                    || gap.starts_with(':')
                    || gap.starts_with(',')
                    || (before.ends_with("gives") && gap == "a")
                    || [
                        "has", "has a", "has the", "have", "had", "reports", "records",
                    ]
                    .contains(&gap.as_str())
                {
                    1
                } else if before.is_empty()
                    || before == "for"
                    || before == "concerning"
                    || before.ends_with("check of")
                    || before.ends_with("recorded for")
                    || before.ends_with("register gives")
                    || ["for", "on", "at", "in"]
                        .iter()
                        .any(|p| before == *p || before.ends_with(&format!(" {p}")))
                {
                    2
                } else {
                    continue;
                }
            } else if field.span.end <= m.span.start {
                let gap = without_annotation(&text[field.span.end..m.span.start])
                    .trim()
                    .to_lowercase();
                if ["of", "for", "of the", "for the", "at", "in", "on"].contains(&gap.as_str()) {
                    0
                } else {
                    continue;
                }
            } else {
                continue;
            };
            choices.push((score, distance(&field.span, &m.span), owner));
        }
        choices.sort_unstable();
        if let Some(&(score, dist, owner)) = choices.first() {
            if choices
                .iter()
                .any(|&(s, d, o)| s == score && d == dist && o != owner)
            {
                return None;
            }
            return Some(owner);
        }
        if PRONOUN.is_match(&text[clause.clone()]) {
            let owners: Vec<_> = antecedent?
                .iter()
                .copied()
                .filter(|&s| self.subjects[s].attributes.contains(&field.name))
                .collect();
            if owners.len() == 1 {
                return Some(owners[0]);
            }
        }
        None
    }

    #[allow(clippy::too_many_arguments)] // Read-only spans share one clause; no parser/global state.
    fn value(
        &self,
        text: &str,
        field: &Field,
        fields: &[&Field],
        mentions: &[&Mention],
        proposals: &[Proposed],
        clause: &Range<usize>,
        subject: usize,
    ) -> Option<Proposed> {
        let mut values = Vec::new();
        for p in proposals {
            if !inside(&p.span, clause) || p.value["kind"] == "boolean" {
                continue;
            }
            if ((field.name == "version" || field.name.ends_with("_version"))
                && p.value["kind"] != "version")
                || field
                    .value_span
                    .as_ref()
                    .is_some_and(|s| !overlap(s, &p.span))
            {
                continue;
            }
            if mentions.iter().any(|m| {
                inside(&p.span, &m.span)
                    && (m.owners.contains(&subject) || p.value["kind"] != "name")
            }) {
                continue;
            }
            if matches!(
                p.value["kind"].as_str(),
                Some("quantity" | "duration" | "percent" | "money")
            ) && let Some(n) = NUMBER.find(&text[p.span.clone()])
            {
                let digit = p.span.start + n.start();
                if mentions.iter().any(|m| m.span.contains(&digit))
                    || fields.iter().any(|f| f.span.contains(&digit))
                {
                    continue;
                }
            }
            let Some(mut v) = repair_value(text, p, clause) else {
                continue;
            };
            if v.value["kind"] == "name"
                && let Some(m) = mentions
                    .iter()
                    .find(|m| m.span == v.span && m.owners.len() == 1)
            {
                v.value["value"] = json!(self.subjects[m.owners[0]].name);
            }
            if !inside(&v.span, clause) {
                continue;
            }
            if !value_attachment(text, field, &v.span) {
                continue;
            }
            if field.span.end <= v.span.start
                && proposals.iter().any(|other| {
                    !matches!(other.value["kind"].as_str(), Some("boolean" | "name"))
                        && field.span.end <= other.span.start
                        && other.span.end <= v.span.start
                        && other.span != p.span
                        && repair_value(text, other, clause).is_some()
                        && {
                            let gap = text[other.span.end..v.span.start].trim();
                            !gap.is_empty()
                                && !["to", "or", "and", "through", "-", "–", "—"]
                                    .iter()
                                    .any(|s| gap.eq_ignore_ascii_case(s))
                        }
                })
            {
                continue;
            }
            if fields.iter().any(|other| {
                other.span != field.span
                    && distance(&other.span, &v.span) < distance(&field.span, &v.span)
                    && value_attachment(text, other, &v.span)
            }) {
                continue;
            }
            if v.value["kind"] == "name"
                && (overlap(&v.span, &field.span)
                    || mentions
                        .iter()
                        .any(|m| m.owners.contains(&subject) && overlap(&m.span, &v.span)))
            {
                continue;
            }
            let local = predicate_scope(text, field, &v.span, fields, proposals, clause);
            let Some(mut op) = operator(
                text,
                &v.span,
                &local,
                v.value["kind"].as_str().unwrap_or(""),
            ) else {
                continue;
            };
            if op == "eq" && v.value["op"] == "ge" {
                op = "ge";
            }
            if op == "eq" {
                v.value.as_object_mut()?.remove("op");
            } else {
                v.value["op"] = json!(op);
            }
            values.push(v);
        }
        // Frozen grammar proposes both boolean polarities over the entire
        // clause. Only an actual boolean literal licenses this schema repair.
        for m in BOOL.find_iter(&text[clause.clone()]) {
            let s = clause.start + m.start();
            let e = clause.start + m.end();
            if m.as_str().eq_ignore_ascii_case("no")
                && text[e..clause.end]
                    .split_whitespace()
                    .next()
                    .is_some_and(|w| {
                        matches!(
                            w.to_lowercase().as_str(),
                            "more" | "less" | "fewer" | "earlier" | "later" | "older" | "newer"
                        )
                    })
            {
                continue;
            }
            let span = s..e;
            if mentions.iter().any(|n| overlap(&n.span, &span))
                || proposals
                    .iter()
                    .any(|p| p.value["kind"] == "name" && inside(&span, &p.span))
                || !value_attachment(text, field, &span)
            {
                continue;
            }
            if fields.iter().any(|f| {
                f.span != field.span
                    && distance(&f.span, &span) < distance(&field.span, &span)
                    && value_attachment(text, f, &span)
            }) {
                continue;
            }
            let local = predicate_scope(text, field, &span, fields, proposals, clause);
            let op = operator(text, &span, &local, "boolean")?;
            if !matches!(op, "eq" | "ne") {
                continue;
            }
            let mut value = json!({"kind":"boolean","value": matches!(m.as_str().to_lowercase().as_str(), "yes" | "true")});
            if op != "eq" {
                value["op"] = json!(op);
            }
            values.push(Proposed { span, value });
        }
        values.sort_by_key(|p| (p.span.start, p.span.end, p.value.to_string()));
        values.dedup_by(|a, b| a.value == b.value && overlap(&a.span, &b.span));
        // A duplicate version reading of a price/count is a weak lexical
        // proposal, not a second assertion. Explicit v/version markers survive.
        let stronger: Vec<_> = values
            .iter()
            .filter(|p| {
                matches!(
                    p.value["kind"].as_str(),
                    Some("money" | "percent" | "duration" | "quantity")
                )
            })
            .map(|p| p.span.clone())
            .collect();
        values.retain(|p| {
            p.value["kind"] != "version"
                || !stronger.iter().any(|s| overlap(s, &p.span))
                || text[p.span.clone()].to_lowercase().starts_with('v')
        });
        let numeric_values: Vec<_> = values
            .iter()
            .filter(|p| {
                matches!(
                    p.value["kind"].as_str(),
                    Some("money" | "percent" | "duration")
                )
            })
            .map(|p| p.span.clone())
            .collect();
        values.retain(|p| {
            p.value["kind"] != "date" || !numeric_values.iter().any(|span| inside(&p.span, span))
        });
        let typed: Vec<_> = values
            .iter()
            .filter(|p| p.value["kind"] != "name")
            .map(|p| p.span.clone())
            .collect();
        values.retain(|p| {
            p.value["kind"] != "name" || !typed.iter().any(|span| inside(&p.span, span))
        });
        let mut unique = Vec::<Proposed>::new();
        for p in values {
            if !unique.iter().any(|u| u.value == p.value) {
                unique.push(p);
            }
        }
        if unique.len() == 1 {
            unique.pop()
        } else {
            None
        }
    }
}

fn key(s: &str) -> String {
    s.chars()
        .filter(|c| c.is_alphanumeric())
        .flat_map(char::to_lowercase)
        .collect()
}

fn phrase(s: &str) -> String {
    let mut parts = Vec::<String>::new();
    let mut part = String::new();
    let mut digit = None;
    for c in s.chars() {
        if c.is_alphanumeric() {
            if digit.is_some_and(|d| d != c.is_numeric()) && !part.is_empty() {
                parts.push(std::mem::take(&mut part));
            }
            digit = Some(c.is_numeric());
            part.push(c);
        } else if !part.is_empty() {
            parts.push(std::mem::take(&mut part));
            digit = None;
        }
    }
    if !part.is_empty() {
        parts.push(part);
    }
    parts
        .iter()
        .map(|p| regex::escape(p))
        .collect::<Vec<_>>()
        .join(r"[\s_\p{P}]*")
}

fn alternatives(forms: BTreeMap<String, String>) -> Result<Regex, String> {
    let mut forms: Vec<_> = forms.into_iter().collect();
    forms.sort_by(|(a, _), (b, _)| b.len().cmp(&a.len()).then(a.cmp(b)));
    let pattern = if forms.is_empty() {
        r"\b\B".into()
    } else {
        format!(
            "(?i)(?:{})",
            forms
                .into_iter()
                .map(|(_, p)| p)
                .collect::<Vec<_>>()
                .join("|")
        )
    };
    Regex::new(&pattern).map_err(|e| format!("schema expression: {e}"))
}

fn whole(text: &str, s: &Range<usize>) -> bool {
    !text[..s.start]
        .chars()
        .next_back()
        .is_some_and(|c| c.is_alphanumeric() || c == '_')
        && !text[s.end..]
            .chars()
            .next()
            .is_some_and(|c| c.is_alphanumeric() || c == '_')
}
fn overlap(a: &Range<usize>, b: &Range<usize>) -> bool {
    a.start < b.end && b.start < a.end
}
fn rx_blank_line(s: &str) -> bool {
    static BLANK: LazyLock<Regex> = LazyLock::new(|| rx(r"\n\s*\n"));
    BLANK.is_match(s)
}
fn inside(a: &Range<usize>, b: &Range<usize>) -> bool {
    b.start <= a.start && a.end <= b.end
}
fn distance(a: &Range<usize>, b: &Range<usize>) -> usize {
    if a.end <= b.start {
        b.start - a.end
    } else {
        a.start.saturating_sub(b.end)
    }
}
fn without_annotation(s: &str) -> String {
    let mut depth = 0;
    s.chars()
        .filter(|&c| {
            if c == '[' {
                depth += 1;
                return false;
            }
            if c == ']' {
                depth -= 1;
                return false;
            }
            depth == 0
        })
        .collect()
}

// Before-field values require an actual inverse copula or an overlapping
// count noun. Mere proximity across a verb does not license a binding.
fn value_attachment(text: &str, field: &Field, value: &Range<usize>) -> bool {
    static INVERSE: LazyLock<Regex> = LazyLock::new(|| {
        rx(
            r"(?i)^\s*(?:(?:is|are|was|were|as|for)\s+(?:(?:the|its|his|her|their|recorded|reported|current)\s+)*)?$",
        )
    });
    value.end > field.span.start
        || INVERSE.is_match(&without_annotation(&text[value.end..field.span.start]))
}

fn predicate_scope(
    text: &str,
    field: &Field,
    value: &Range<usize>,
    fields: &[&Field],
    proposals: &[Proposed],
    clause: &Range<usize>,
) -> Range<usize> {
    let left = field.span.start.min(value.start);
    let right = field.span.end.max(value.end);
    let mut scope = clause.clone();
    for (offset, c) in text[clause.clone()].char_indices() {
        let at = clause.start + offset;
        if c != ','
            || proposals
                .iter()
                .any(|p| p.value["kind"] != "boolean" && p.span.start <= at && at < p.span.end)
        {
            continue;
        }
        if at < left {
            scope.start = at + 1;
        } else if at >= right {
            scope.end = at;
            break;
        }
    }
    let previous = fields
        .iter()
        .filter(|f| f.span != field.span && scope.start <= f.span.end && f.span.end <= left)
        .map(|f| f.span.end)
        .max();
    if let Some(previous) = previous {
        scope.start = previous;
        for p in proposals {
            if p.value["kind"] != "boolean" && previous <= p.span.start && p.span.end <= left {
                scope.start = scope.start.max(p.span.end);
            }
        }
        if let Some(m) = BOOL.find_iter(&text[previous..left]).last() {
            scope.start = scope.start.max(previous + m.end());
        }
    }
    for f in fields {
        if f.span != field.span && right <= f.span.start {
            scope.end = scope.end.min(f.span.start);
        }
    }
    scope
}

fn clauses(
    text: &str,
    mentions: &[Mention],
    fields: &[Field],
    proposals: &[Proposed],
) -> Vec<Range<usize>> {
    let mut spans = Vec::new();
    let mut start = 0;
    for m in CLAUSE.find_iter(text) {
        if mentions.iter().any(|n| inside(&m.range(), &n.span))
            || fields.iter().any(|f| inside(&m.range(), &f.span))
            || proposals.iter().any(|p| {
                matches!(p.value["kind"].as_str(), Some("date" | "version" | "name"))
                    && inside(&m.range(), &p.span)
            })
            || (matches!(m.as_str().to_lowercase().as_str(), "and" | "but")
                && (text[..m.start()].ends_with(['-', '_', '/'])
                    || text[m.end()..].starts_with(['-', '_', '/'])))
        {
            continue;
        }
        if m.as_str() == "." {
            let next = text[m.end()..].chars().next();
            if next.is_some_and(|c| !c.is_whitespace()) {
                continue;
            }
            let token = text[..m.start()]
                .split(|c: char| !c.is_alphanumeric())
                .next_back()
                .unwrap_or("");
            let declaration_end =
                DECLARATION.is_match(&text[start..m.start()]) && PRONOUN.is_match(&text[m.end()..]);
            let initial = token.len() == 1
                && token.chars().all(char::is_alphabetic)
                && text[..m.start() - token.len()]
                    .chars()
                    .next_back()
                    .is_none_or(char::is_whitespace)
                && !proposals.iter().any(|p| {
                    p.span.end == m.start()
                        && matches!(p.value["kind"].as_str(), Some("quantity" | "duration"))
                });
            if !declaration_end
                && (initial
                    || [
                        "e.g", "i.e", "vs", "approx", "inc", "ltd", "co", "corp", "dr", "mr",
                        "mrs", "ms", "prof", "st", "no", "ver", "jan", "feb", "mar", "apr", "jun",
                        "jul", "aug", "sep", "sept", "oct", "nov", "dec",
                    ]
                    .contains(&token.to_lowercase().as_str()))
            {
                continue;
            }
        }
        if m.start() > start {
            spans.push(start..m.start());
        }
        start = m.end();
    }
    if start < text.len() {
        spans.push(start..text.len());
    }
    spans
}

fn operator(
    text: &str,
    value: &Range<usize>,
    clause: &Range<usize>,
    kind: &str,
) -> Option<&'static str> {
    let before = &text[clause.start..value.start];
    static RANGE_BEFORE: LazyLock<Regex> =
        LazyLock::new(|| rx(r"(?i)\d[\d,.]*\s*(?:[-–—]|to|or|and)\s*$"));
    static RANGE_AFTER: LazyLock<Regex> =
        LazyLock::new(|| rx(r"(?i)^\s*(?:[-–—]|to|or)\s*(?:[€$£]|(?:EUR|USD|GBP)\s*)?\d"));
    if APPROX.is_match(before) || NONEXACT_SUFFIX.is_match(&text[value.end..clause.end]) {
        return None;
    }
    if RANGE_BEFORE.is_match(before) || RANGE_AFTER.is_match(&text[value.end..clause.end]) {
        return None;
    }
    for (pattern, op) in OPERATORS.iter() {
        if let Some(m) = pattern.find(before) {
            let phrase = m.as_str().to_lowercase();
            if (phrase.contains("before")
                || phrase.contains("after")
                || phrase.contains("earlier")
                || phrase.contains("later"))
                && kind != "date"
            {
                continue;
            }
            if (phrase.contains("older") || phrase.contains("newer")) && kind != "version" {
                continue;
            }
            if phrase.trim() == "within" && kind != "duration" {
                continue;
            }
            let preceding = before[..m.start()].trim_end();
            if preceding.to_lowercase().ends_with("not")
                && preceding[..preceding.len() - 3]
                    .chars()
                    .next_back()
                    .is_none_or(|c| !c.is_alphanumeric())
            {
                return match *op {
                    "eq" => Some("ne"),
                    "ne" => Some("eq"),
                    "lt" => Some("ge"),
                    "le" => Some("gt"),
                    "gt" => Some("le"),
                    "ge" => Some("lt"),
                    _ => None,
                };
            }
            if NEGATION.is_match(preceding) {
                return None;
            }
            return Some(op);
        }
    }
    let after = text[value.end..clause.end].trim_start().to_lowercase();
    if ["or more", "or higher", "or above", "or longer", "or over"]
        .iter()
        .any(|s| after.starts_with(s))
    {
        return Some("ge");
    }
    if [
        "or less",
        "or fewer",
        "or under",
        "or below",
        "or lower",
        "or shorter",
    ]
    .iter()
    .any(|s| after.starts_with(s))
    {
        return Some("le");
    }
    if kind == "date" && before.trim_end().to_lowercase().ends_with(" by") {
        return Some("le");
    }
    if NEGATION.is_match(before) {
        static DIRECT_NOT: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)\bnot\s*$"));
        return DIRECT_NOT.is_match(before).then_some("ne");
    }
    Some("eq")
}

fn repair_value(text: &str, p: &Proposed, clause: &Range<usize>) -> Option<Proposed> {
    let kind = p.value["kind"].as_str()?;
    let raw = &text[p.span.clone()];
    match kind {
        "date" => {
            static ISO_DATE: LazyLock<Regex> =
                LazyLock::new(|| rx(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$"));
            static NUMERIC_DATE: LazyLock<Regex> =
                LazyLock::new(|| rx(r"^\d{1,2}\.\d{1,2}\.\d{4}$"));
            let raw = raw.trim();
            if raw.contains('/') || NUMERIC_DATE.is_match(raw) {
                return None;
            }
            let value = if ISO_DATE.is_match(raw) {
                raw
            } else {
                p.value["value"].as_str()?
            };
            if !valid_date(value) {
                return None;
            }
            Some(Proposed {
                span: p.span.clone(),
                value: json!({"kind":"date","value":value}),
            })
        }
        "version" => {
            let c = VERSION.captures(raw.trim())?;
            Some(Proposed {
                span: p.span.clone(),
                value: json!({"kind":"version","value":c.get(1)?.as_str()}),
            })
        }
        "name" => {
            let value = p.value["value"].as_str()?;
            if [
                "a",
                "an",
                "the",
                "as",
                "for",
                "from",
                "to",
                "concerning",
                "record",
                "record subject",
                "document",
                "document reference",
                "a check",
                "check",
                "the register",
                "register",
                "its",
                "it",
                "in",
                "at",
                "us",
                "eur",
                "usd",
            ]
            .contains(&raw.trim().to_lowercase().as_str())
            {
                return None;
            }
            Some(Proposed {
                span: p.span.clone(),
                value: json!({"kind":"name","value":if key(value) == key(raw) { value } else { raw }}),
            })
        }
        "money" | "quantity" | "percent" | "duration" => repair_numeric(text, p, clause),
        _ => None,
    }
}

fn repair_numeric(text: &str, p: &Proposed, clause: &Range<usize>) -> Option<Proposed> {
    let kind = p.value["kind"].as_str()?;
    let word_number = NUMBER.find(&text[p.span.clone()]).is_none();
    let found = NUMBER
        .find(&text[p.span.clone()])
        .or_else(|| WORD_NUMBER.find(&text[p.span.clone()]))?;
    let mut a = p.span.start + found.start();
    let mut b = p.span.start + found.end();
    while a > clause.start
        && (text.as_bytes()[a - 1].is_ascii_digit()
            || matches!(text.as_bytes()[a - 1], b',' | b'.'))
    {
        a -= 1;
    }
    if a > clause.start && text.as_bytes()[a - 1] == b'-' {
        if a > clause.start + 1 && text.as_bytes()[a - 2].is_ascii_digit() {
            return None; // ASCII range, not a negative singleton.
        }
        a -= 1;
    }
    while b < clause.end
        && (text.as_bytes()[b].is_ascii_digit() || matches!(text.as_bytes()[b], b',' | b'.'))
    {
        b += 1;
    }
    // A terminal sentence dot is punctuation, not a decimal point.
    if text.as_bytes().get(b.wrapping_sub(1)) == Some(&b'.') {
        b -= 1;
    }
    // Word-number arithmetic remains owned by the frozen grammar. Its
    // numeric proposal is reused; only the written unit/operator is repaired.
    let mut number = if word_number {
        decimal_spelling(&p.value["value"].as_number()?.to_string(), false)?
    } else {
        decimal_spelling(&text[a..b], kind == "money")?
    };
    // The public value grammar leaves a lone three-place decimal ambiguous
    // with thousands grouping. Percentages explicitly permit that precision.
    if !word_number && kind != "percent" {
        let raw = &text[a..b];
        if !raw.contains(',') && raw.split_once('.').is_some_and(|(_, f)| f.len() == 3) {
            return None;
        }
    }
    let mut end = b;
    if let Some(c) = SCALE.captures(&text[b..clause.end]) {
        let scale = c.get(1)?.as_str();
        let shift = match scale {
            "million" | "M" => 6,
            "billion" | "bn" => 9,
            "thousand" | "k" => 3,
            _ => return None,
        };
        if !word_number {
            number = shift_decimal(&number, shift)?;
        }
        end += c.get(0)?.end();
    }
    let numeric: Value = serde_json::from_str(&number).ok()?;
    if !numeric.is_number() {
        return None;
    }
    // Avoid silently rounding a spelling that serde_json cannot represent.
    if decimal_spelling(&numeric.to_string(), false)? != number {
        return None;
    }
    let mut value = json!({"kind":kind,"value":numeric});
    let mut start = a;
    match kind {
        "money" => {
            let left = CURRENCY_BEFORE.captures(&text[clause.start..a]);
            let right = CURRENCY_AFTER.captures(&text[end..clause.end]);
            if let (Some(l), Some(r)) = (&left, &right)
                && currency(l.get(1)?.as_str()) != currency(r.get(1)?.as_str())
            {
                return None;
            }
            let currency = if let Some(c) = &left {
                start = clause.start + c.get(0)?.start();
                currency(c.get(1)?.as_str())?
            } else if let Some(c) = &right {
                let code = currency(c.get(1)?.as_str())?;
                end += c.get(0)?.end();
                code
            } else {
                return None;
            };
            if left.is_some()
                && let Some(c) = &right
            {
                end += c.get(0)?.end();
            }
            value["currency"] = json!(currency);
            if let Some(c) = PERIOD.captures(&text[end..clause.end]) {
                let per = if let Some(p) = c.get(1) {
                    match p.as_str().to_lowercase().as_str() {
                        "mo" | "mth" | "month" => "month",
                        "yr" | "year" => "year",
                        "wk" | "week" => "week",
                        "day" => "day",
                        _ => return None,
                    }
                } else if c.name("annual").is_some() {
                    "year"
                } else if c.name("monthly").is_some() {
                    "month"
                } else if c.name("weekly").is_some() {
                    "week"
                } else {
                    "day"
                };
                value["per"] = json!(per);
                end += c.get(0)?.end();
            } else {
                static UNRESOLVED_PERIOD: LazyLock<Regex> =
                    LazyLock::new(|| rx(r"(?i)^\s*(?:/|per\b|each\b|hourly\b|quarterly\b)"));
                if UNRESOLVED_PERIOD.is_match(&text[end..clause.end]) {
                    return None;
                }
            }
            if value.get("per").is_some()
                && (PERIOD.is_match(&text[end..clause.end])
                    || text[end..clause.end].trim_start().starts_with('/'))
            {
                return None;
            }
        }
        "percent" => {
            end += PERCENT.find(&text[end..clause.end])?.end();
        }
        "quantity" | "duration" => {
            // The first written unit wins; later nouns never overwrite it.
            if text[end..clause.end].starts_with('+') {
                end += 1;
                value["op"] = json!("ge");
            }
            let mut c = UNIT.captures(&text[end..clause.end])?;
            let mut raw_unit = c.get(1)?.as_str();
            static COUNT_MODIFIER: LazyLock<Regex> = LazyLock::new(|| {
                rx(
                    r"(?i)^(?:active|paying|paid|registered|concurrent|simultaneous|supported|included|monthly|daily|annual|new|full|of|our|the|their)$",
                )
            });
            let mut modifiers = 0;
            while COUNT_MODIFIER.is_match(raw_unit) && modifiers < 2 {
                end += c.get(0)?.end();
                c = UNIT.captures(&text[end..clause.end])?;
                raw_unit = c.get(1)?.as_str();
                modifiers += 1;
            }
            // Modifiers cannot be guessed away to a nonexistent noun. The
            // frozen proposal's unit must actually be written after them.
            if modifiers > 0
                && canonical_unit(raw_unit) != canonical_unit(p.value["unit"].as_str()?)
            {
                return None;
            }
            let (unit_kind, unit) = canonical_unit(raw_unit);
            if unit_kind == "invalid" {
                return None;
            }
            value["kind"] = json!(unit_kind);
            value["unit"] = json!(unit);
            end += c.get(0)?.end();
        }
        _ => return None,
    }
    Some(Proposed {
        span: start..end,
        value,
    })
}

fn decimal_spelling(raw: &str, money: bool) -> Option<String> {
    if let Some((base, exponent)) = raw.split_once(['e', 'E']) {
        let exponent: i32 = exponent.parse().ok()?;
        if exponent.unsigned_abs() > 256 {
            return None;
        }
        return shift_decimal(&decimal_spelling(base, money)?, exponent);
    }
    let negative = raw.starts_with('-');
    let raw = raw.strip_prefix('-').unwrap_or(raw);
    let n = if raw.contains(',') {
        let parts: Vec<_> = raw.split(',').collect();
        if parts.len() == 2 && money && !raw.contains('.') && (1..=2).contains(&parts[1].len()) {
            format!("{}.{}", parts[0], parts[1])
        } else {
            if !(1..=3).contains(&parts[0].len())
                || !parts[0].bytes().all(|c| c.is_ascii_digit())
                || parts[1..].iter().enumerate().any(|(i, s)| {
                    let whole = if i + 2 == parts.len() {
                        s.split('.').next().unwrap_or("")
                    } else {
                        s
                    };
                    whole.len() != 3 || !whole.bytes().all(|c| c.is_ascii_digit())
                })
            {
                return None;
            }
            raw.replace(',', "")
        }
    } else {
        raw.to_owned()
    };
    let mut parts = n.split('.');
    let integer = parts.next()?;
    let fraction = parts.next().unwrap_or("");
    if integer.is_empty()
        || !integer.bytes().all(|c| c.is_ascii_digit())
        || !fraction.bytes().all(|c| c.is_ascii_digit())
        || parts.next().is_some()
    {
        return None;
    }
    let integer = integer.trim_start_matches('0');
    let integer = if integer.is_empty() { "0" } else { integer };
    let fraction = fraction.trim_end_matches('0');
    let body = if fraction.is_empty() {
        integer.to_owned()
    } else {
        format!("{integer}.{fraction}")
    };
    Some(if negative && body != "0" {
        format!("-{body}")
    } else {
        body
    })
}

fn shift_decimal(n: &str, shift: i32) -> Option<String> {
    let neg = n.starts_with('-');
    let n = n.strip_prefix('-').unwrap_or(n);
    let (whole, fraction) = n.split_once('.').unwrap_or((n, ""));
    let mut digits = format!("{whole}{fraction}");
    let position = whole.len() as i32 + shift;
    if position <= 0 {
        digits = format!("0.{}{digits}", "0".repeat((-position) as usize));
    } else {
        let position = position as usize;
        if digits.len() < position {
            digits.extend(std::iter::repeat_n('0', position - digits.len()));
        }
        if position < digits.len() {
            digits.insert(position, '.');
        }
    }
    decimal_spelling(&format!("{}{digits}", if neg { "-" } else { "" }), false)
}

fn currency(raw: &str) -> Option<&'static str> {
    match raw.to_lowercase().replace(' ', "").as_str() {
        "€" | "eur" | "euro" | "euros" => Some("EUR"),
        "$" | "us$" | "usd" | "dollar" | "dollars" => Some("USD"),
        "£" | "gbp" => Some("GBP"),
        "lei" | "ron" => Some("RON"),
        "chf" => Some("CHF"),
        "pln" => Some("PLN"),
        "czk" => Some("CZK"),
        "huf" => Some("HUF"),
        "sek" => Some("SEK"),
        "nok" => Some("NOK"),
        "dkk" => Some("DKK"),
        "jpy" => Some("JPY"),
        "cny" => Some("CNY"),
        "inr" => Some("INR"),
        "cad" => Some("CAD"),
        "aud" => Some("AUD"),
        _ => None,
    }
}

fn canonical_unit(raw: &str) -> (&'static str, String) {
    if [
        "B", "KB", "kB", "MB", "GB", "TB", "mAh", "W", "mW", "kW", "MW", "Hz", "kHz", "MHz", "GHz",
        "g", "kg", "mm", "cm", "m", "km",
    ]
    .contains(&raw)
    {
        return ("quantity", raw.into());
    }
    if let Some(unit) = match raw {
        "ms" => Some("ms"),
        "s" => Some("s"),
        "min" => Some("min"),
        "h" | "hr" => Some("h"),
        "d" => Some("day"),
        "wk" => Some("week"),
        "mo" | "mth" => Some("month"),
        "yr" => Some("year"),
        _ => None,
    } {
        return ("duration", unit.into());
    }
    let lower = raw.to_lowercase();
    let noun = singular(&lower);
    if let Some(unit) = match noun.as_str() {
        "millisecond" => Some("ms"),
        "second" | "sec" => Some("s"),
        "minute" => Some("min"),
        "hour" => Some("h"),
        "day" => Some("day"),
        "week" => Some("week"),
        "month" => Some("month"),
        "year" => Some("year"),
        _ => None,
    } {
        return ("duration", unit.into());
    }
    let unit = match noun.as_str() {
        "byte" => "B",
        "kilobyte" => "KB",
        "megabyte" => "MB",
        "gigabyte" | "gig" => "GB",
        "terabyte" => "TB",
        "watt" => "W",
        "milliwatt" => "mW",
        "kilowatt" => "kW",
        "megawatt" => "MW",
        "hertz" => "Hz",
        "kilohertz" => "kHz",
        "megahertz" => "MHz",
        "gigahertz" => "GHz",
        "gram" => "g",
        "kilogram" => "kg",
        "millimetre" | "millimeter" => "mm",
        "centimetre" | "centimeter" => "cm",
        "metre" | "meter" => "m",
        "kilometre" | "kilometer" => "km",
        "in" | "inch" | "\"" | "″" => "inch",
        "meeting" => "sitting",
        "of" | "in_the" | "on" | "is" | "and" | "or" | "a" | "the" | "from" | "at" | "per"
        | "for" | "to" | "as" => return ("invalid", noun),
        _ => {
            return (
                "quantity",
                if raw.len() <= 3 && raw.chars().any(char::is_uppercase) {
                    raw.to_owned()
                } else {
                    noun
                },
            );
        }
    };
    ("quantity", unit.into())
}

fn singular(s: &str) -> String {
    if matches!(s, "people" | "persons") {
        "person".into()
    } else if let Some(base) = s.strip_suffix("ies") {
        format!("{base}y")
    } else if let Some(base) = s.strip_suffix("ches") {
        format!("{base}ch")
    } else if s.ends_with('s') && !s.ends_with("ss") && !matches!(s, "ms" | "s" | "hertz") {
        s[..s.len() - 1].into()
    } else {
        s.into()
    }
}

fn valid_date(s: &str) -> bool {
    let parts: Vec<_> = s.split('-').collect();
    if parts.is_empty()
        || parts.len() > 3
        || parts[0].len() != 4
        || !parts.iter().all(|p| p.bytes().all(|c| c.is_ascii_digit()))
    {
        return false;
    }
    let Ok(year) = parts[0].parse::<u32>() else {
        return false;
    };
    if parts.len() == 1 {
        return true;
    }
    let Ok(month) = parts[1].parse::<u32>() else {
        return false;
    };
    if parts[1].len() != 2 || !(1..=12).contains(&month) {
        return false;
    }
    if parts.len() == 2 {
        return true;
    }
    let Ok(day) = parts[2].parse::<u32>() else {
        return false;
    };
    let max = match month {
        2 if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    parts[2].len() == 2 && (1..=max).contains(&day)
}
