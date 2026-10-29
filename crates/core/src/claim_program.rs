//! Bounded, text-only claim programs over the existing schema assertion binder.
//!
//! Parsing has no access to evidence, row dates, labels, or accepted values. All
//! public spans are half-open Unicode scalar offsets, like `ValueCandidate`.
//! Boolean evaluation delegates atoms and slot comparisons to caller callbacks.
use crate::model::Fact;
use crate::structured::{SchemaParser, ValueCandidate};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::ops::Range;
use std::sync::LazyLock;

pub const MAX_INPUT_CHARS: usize = 65_536;
pub const MAX_CANDIDATES: usize = 4096;
pub const MAX_PROGRAM_DEPTH: usize = 32;
pub const MAX_PROGRAM_NODES: usize = 512;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CharSpan {
    pub start: usize,
    pub end: usize,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct SlotReference {
    pub subject: String,
    pub attribute: String,
    /// Only an explicitly written ISO date, retaining its precision. `None`
    /// means the caller chooses its query date; parsing never looks one up.
    pub date: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ComparisonOp {
    Eq,
    Ne,
    Lt,
    Le,
    Gt,
    Ge,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TruthValue {
    True,
    False,
    Unknown,
}

impl TruthValue {
    fn inverted(self) -> Self {
        match self {
            Self::True => Self::False,
            Self::False => Self::True,
            Self::Unknown => Self::Unknown,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum ClaimExpr {
    Atom(Fact),
    All(Vec<ClaimExpr>),
    Any(Vec<ClaimExpr>),
    Not(Box<ClaimExpr>),
    Compare {
        left: SlotReference,
        op: ComparisonOp,
        right: SlotReference,
    },
    Unknown {
        span: CharSpan,
        reason: String,
    },
    Unsupported {
        span: CharSpan,
        reason: String,
    },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ClaimProgram {
    pub expression: ClaimExpr,
    pub complete: bool,
    pub notes: Vec<String>,
    /// The caller must retain program semantics, including incomplete logical
    /// branches. `false` allows the existing ordinary-prose parser path.
    pub structured: bool,
}

impl ClaimProgram {
    pub fn evaluate<A, C>(&self, atom: &mut A, comparison: &mut C) -> TruthValue
    where
        A: FnMut(&Fact) -> TruthValue,
        C: FnMut(&SlotReference, ComparisonOp, &SlotReference) -> TruthValue,
    {
        self.expression.evaluate(atom, comparison)
    }

    /// A whole-program projection only. OR, NOT, slot comparisons, unresolved
    /// clauses, and incomplete legacy parses never become a positive fact bag.
    pub fn legacy_facts(&self) -> Option<Vec<Fact>> {
        if !self.complete {
            return None;
        }
        let mut result = Vec::new();
        self.expression.positive_facts(&mut result, 0)?;
        (!result.is_empty()).then_some(result)
    }
}

impl ClaimExpr {
    /// Strong Kleene three-valued logic. In particular, false dominates ALL,
    /// true dominates ANY, and negating unknown still yields unknown. Empty
    /// groups are unknown. Callbacks must return unknown for missing evidence
    /// or incomparable currency, billing period, unit, or date precision.
    pub fn evaluate<A, C>(&self, atom: &mut A, comparison: &mut C) -> TruthValue
    where
        A: FnMut(&Fact) -> TruthValue,
        C: FnMut(&SlotReference, ComparisonOp, &SlotReference) -> TruthValue,
    {
        self.eval(atom, comparison, 0, &mut 0)
    }

    fn eval<A, C>(
        &self,
        atom: &mut A,
        comparison: &mut C,
        depth: usize,
        visited: &mut usize,
    ) -> TruthValue
    where
        A: FnMut(&Fact) -> TruthValue,
        C: FnMut(&SlotReference, ComparisonOp, &SlotReference) -> TruthValue,
    {
        *visited += 1;
        if depth > MAX_PROGRAM_DEPTH || *visited > MAX_PROGRAM_NODES {
            return TruthValue::Unknown;
        }
        match self {
            Self::Atom(f) => atom(f),
            Self::Compare { left, op, right } => comparison(left, *op, right),
            Self::Not(child) => child.eval(atom, comparison, depth + 1, visited).inverted(),
            Self::All(children) | Self::Any(children) => {
                if children.is_empty() || children.len() > MAX_PROGRAM_NODES {
                    return TruthValue::Unknown;
                }
                let all = matches!(self, Self::All(_));
                let mut unknown = false;
                for child in children {
                    let value = child.eval(atom, comparison, depth + 1, visited);
                    if (all && value == TruthValue::False) || (!all && value == TruthValue::True) {
                        return value;
                    }
                    unknown |= value == TruthValue::Unknown;
                }
                if unknown {
                    TruthValue::Unknown
                } else if all {
                    TruthValue::True
                } else {
                    TruthValue::False
                }
            }
            Self::Unknown { .. } | Self::Unsupported { .. } => TruthValue::Unknown,
        }
    }

    fn positive_facts(&self, result: &mut Vec<Fact>, depth: usize) -> Option<()> {
        if depth > MAX_PROGRAM_DEPTH || result.len() >= MAX_PROGRAM_NODES {
            return None;
        }
        match self {
            Self::Atom(f) => {
                result.push(f.clone());
                Some(())
            }
            Self::All(children) if !children.is_empty() && children.len() <= MAX_PROGRAM_NODES => {
                for child in children {
                    child.positive_facts(result, depth + 1)?;
                }
                Some(())
            }
            _ => None,
        }
    }
}

#[derive(Clone, Debug)]
pub struct ProgramParser {
    schema: SchemaParser,
    subjects: Vec<Subject>,
    aliases: BTreeMap<String, Vec<usize>>,
    attributes: BTreeMap<String, String>,
    alias_re: Regex,
    attribute_re: Regex,
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
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum TokenKind {
    Open,
    Close,
    And,
    Or,
    Nor,
    Comma,
}

#[derive(Clone, Debug)]
struct Token {
    span: Range<usize>,
    kind: TokenKind,
}

fn rx(pattern: &str) -> Regex {
    Regex::new(pattern).expect("source regular expression")
}

static TOKENS: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)\b(?:and|or|nor|but)\b|[(),;]|&&|\|\|"));
static CONDITIONAL: LazyLock<Regex> = LazyLock::new(|| {
    rx(r"(?i)\b(?:if|unless|when|whenever|assuming|provided\s+that|implies|iff)\b|=>|→")
});
static PREFIX: LazyLock<Regex> = LazyLock::new(|| {
    rx(
        r"(?i)^(?:(?P<not>not\b)|(?P<neither>neither\b)|(?P<all>all\b)|(?P<any>any\b)|(?P<both>both\b)|(?P<either>either\b))",
    )
});
static PREFIX_FILLER: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^\s*(?:of\s+)?(?:the\s+following\s*)?:?\s*"));
static NEGATION: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)\b(?:not|never|without)\b|n['’]t\b"));
static NEGATION_EXCEPTION: LazyLock<Regex> = LazyLock::new(|| {
    rx(r"(?i)^\s*(?:less|more|fewer|equal|earlier|later|older|newer|recorded|known)\b")
});
static ONLY: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)^\s*only\b"));
static EXPLICIT_UNKNOWN: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)\b(?:unknown|unrecorded|unresolved|not\s+known|not\s+recorded)\b"));
static BOOLEAN_LITERAL: LazyLock<Regex> = LazyLock::new(|| rx(r"(?i)\b(?:true|false|yes|no)\b"));
static REFERENCE: LazyLock<Regex> =
    LazyLock::new(|| rx(r"(?i)^\s*(?:it|its|this|that|their|theirs|his|her|hers)\b"));
static COMPARE: LazyLock<Regex> = LazyLock::new(|| {
    rx(concat!(
        r"(?i)(?:\b(?P<ge>not\s+less\s+than|no\s+less\s+than|at\s+least|no\s+earlier\s+than|no\s+older\s+than)\b|",
        r"\b(?P<le>not\s+more\s+than|no\s+more\s+than|at\s+most|no\s+later\s+than|no\s+newer\s+than)\b|",
        r"\b(?P<ne>not\s+equal\s+to|different\s+from|unequal\s+to)\b|",
        r"\b(?P<gt>greater\s+than|more\s+than|higher\s+than|larger\s+than|newer\s+than|later\s+than|after)\b|",
        r"\b(?P<lt>less\s+than|fewer\s+than|lower\s+than|older\s+than|earlier\s+than|before)\b|",
        r"\b(?P<eq>equal\s+to|equals?)\b|(?P<symbol>>=|<=|!=|==|[=<>≥≤≠]))"
    ))
});
static DATE: LazyLock<Regex> = LazyLock::new(|| rx(r"\b[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?\b"));
static SLOT_FILLER: LazyLock<Regex> = LazyLock::new(|| {
    rx(r"(?i)^(?:\s|[\x22'‘’“”:,.]|\b(?:the|of|is|was|are|were|has|had|on|at|in|as|s)\b)*$")
});
static SUFFIX_COMPARISON: LazyLock<Regex> = LazyLock::new(|| {
    rx(r"(?i)^\s*(?:more|less|fewer|higher|lower|above|below|over|under|longer|shorter)\b")
});

impl ProgramParser {
    pub fn compile(lexicon: &Value) -> Result<Self, String> {
        let schema = SchemaParser::compile(lexicon)?;
        // SchemaParser validated the shape; inspect only schema names/aliases
        // and attribute identifiers, never schema values or other metadata.
        let rows = lexicon["subjects"].as_array().ok_or("missing subjects")?;
        let mut subjects = Vec::new();
        let mut aliases = BTreeMap::<String, Vec<usize>>::new();
        let mut attributes = BTreeMap::new();
        let mut alias_forms = BTreeMap::new();
        let mut attribute_forms = BTreeMap::new();
        for row in rows {
            let name = row["name"].as_str().ok_or("missing name")?;
            let mut attrs = BTreeSet::new();
            for attribute in row["attributes"].as_array().ok_or("missing attributes")? {
                let a = attribute.as_str().ok_or("invalid attribute")?;
                attributes.insert(key(a), a.to_owned());
                attribute_forms.insert(key(a), phrase(a));
                attrs.insert(a.to_owned());
            }
            let owner = subjects.len();
            let mut forms = vec![name];
            if let Some(extra) = row.get("aliases").and_then(Value::as_array) {
                forms.extend(extra.iter().filter_map(Value::as_str));
            }
            for alias in forms {
                aliases.entry(key(alias)).or_default().push(owner);
                alias_forms.insert(key(alias), phrase(alias));
            }
            subjects.push(Subject {
                name: name.to_owned(),
                attributes: attrs,
            });
        }
        for owners in aliases.values_mut() {
            owners.sort_unstable();
            owners.dedup();
        }
        Ok(Self {
            schema,
            subjects,
            aliases,
            attributes,
            alias_re: alternatives(alias_forms)?,
            attribute_re: alternatives(attribute_forms)?,
        })
    }

    pub fn parse(
        &self,
        text: &str,
        candidates: &[ValueCandidate],
        neural: &[Fact],
    ) -> ClaimProgram {
        let char_count = text.chars().take(MAX_INPUT_CHARS + 1).count();
        let whole_span = CharSpan {
            start: 0,
            end: char_count,
        };
        if char_count > MAX_INPUT_CHARS
            || candidates.len() > MAX_CANDIDATES
            || neural.len() > MAX_CANDIDATES
        {
            return rejected(whole_span, "input_limit");
        }
        let mut boundaries: Vec<_> = text.char_indices().map(|(b, _)| b).collect();
        boundaries.push(text.len());
        let mentions = self.mentions(text);
        let fields = self.fields(text, &mentions, candidates, &boundaries);
        if mentions.len() + fields.len() > MAX_PROGRAM_NODES * 4 {
            return rejected(whole_span, "schema_mention_limit");
        }
        let mut protected: Vec<_> = mentions
            .iter()
            .map(|m| m.span.clone())
            .chain(fields.iter().map(|f| f.span.clone()))
            .collect();
        let (quotes, unclosed_quote) = quote_spans(text);
        protected.extend(quotes);
        // Literal names can themselves contain conjunctions or parentheses.
        // Numeric proposals do not license shielding arbitrary claim syntax.
        for c in candidates {
            if c.value["kind"] == "name" && c.start < c.end && c.end < boundaries.len() {
                protected.push(boundaries[c.start]..boundaries[c.end]);
            }
        }
        protected.sort_by_key(|p| (p.start, p.end));
        let mut merged = Vec::<Range<usize>>::new();
        for span in protected {
            if let Some(last) = merged.last_mut().filter(|p| span.start <= p.end) {
                last.end = last.end.max(span.end);
            } else {
                merged.push(span);
            }
        }
        let protected = merged;
        if CONDITIONAL
            .find_iter(text)
            .any(|m| !overlaps_any(&m.range(), &protected))
        {
            return rejected(whole_span, "unsupported conditional");
        }
        let tokens: Vec<_> = TOKENS
            .find_iter(text)
            .filter(|m| !overlaps_any(&m.range(), &protected))
            .filter(|m| {
                !matches!(
                    m.as_str().to_lowercase().as_str(),
                    "and" | "or" | "nor" | "but"
                ) || !(lexical_join(text, &m.range())
                    || (m.as_str().eq_ignore_ascii_case("or")
                        && SUFFIX_COMPARISON.is_match(&text[m.end()..])))
            })
            .map(|m| Token {
                span: m.range(),
                kind: match m.as_str().to_lowercase().as_str() {
                    "(" => TokenKind::Open,
                    ")" => TokenKind::Close,
                    "and" | "but" | "&&" => TokenKind::And,
                    "or" | "||" => TokenKind::Or,
                    "nor" => TokenKind::Nor,
                    _ => TokenKind::Comma,
                },
            })
            .collect();
        let span = trim(text, 0..text.len());
        let meaningful = !fields.is_empty()
            || EXPLICIT_UNKNOWN
                .find_iter(text)
                .any(|m| !overlaps_any(&m.range(), &protected));
        let strong_literal = BOOLEAN_LITERAL
            .find_iter(text)
            .any(|m| !overlaps_any(&m.range(), &protected))
            || candidates.iter().any(|c| {
                c.start < c.end
                    && c.end < boundaries.len()
                    && matches!(
                        c.value["kind"].as_str(),
                        Some("money" | "quantity" | "duration" | "percent" | "version" | "date")
                    )
            });
        let leading = prefix(&text[span.clone()])
            .filter(|(_, size)| !overlaps_any(&(span.start..span.start + size), &protected));
        let mut structured = (meaningful
            && (fields.len() > 1 || strong_literal)
            && tokens
                .iter()
                .any(|t| matches!(t.kind, TokenKind::And | TokenKind::Or | TokenKind::Nor)))
            || leading.is_some_and(|(_, size)| {
                meaningful
                    || text[span.start + size..span.end]
                        .trim_start()
                        .starts_with('(')
            });
        let mut depth = 0usize;
        for token in &tokens {
            match token.kind {
                TokenKind::Open => {
                    depth += 1;
                    if depth > MAX_PROGRAM_DEPTH {
                        return rejected(whole_span, "depth_limit");
                    }
                }
                TokenKind::Close => {
                    if depth == 0 && meaningful {
                        return rejected(whole_span, "unmatched closing parenthesis");
                    }
                    depth = depth.saturating_sub(1);
                }
                _ => {}
            }
        }
        if depth != 0 && meaningful {
            return rejected(whole_span, "unmatched opening parenthesis");
        }
        if tokens.len() > MAX_PROGRAM_NODES * 4 {
            return rejected(whole_span, "token_limit");
        }
        if meaningful && encloses(&span, &tokens) {
            structured = true;
        }
        if unclosed_quote && meaningful {
            return rejected(whole_span, "unclosed quotation");
        }
        let mut state = ParseState {
            parser: self,
            text,
            candidates,
            neural,
            boundaries: &boundaries,
            mentions: &mentions,
            fields: &fields,
            protected: &protected,
            tokens: &tokens,
            nodes: 0,
            structured,
            complete: true,
            notes: Vec::new(),
        };
        let expression = if structured {
            state.expression(span, 0)
        } else {
            // Slot comparisons and atomic lexical negation can establish
            // structured routing even without a boolean connective.
            state.leaf(span, true)
        };
        match expression {
            Ok(expression) => ClaimProgram {
                expression,
                complete: state.complete,
                notes: state.notes,
                structured: state.structured,
            },
            Err(reason) => rejected(whole_span, &reason),
        }
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

    fn fields(
        &self,
        text: &str,
        mentions: &[Mention],
        candidates: &[ValueCandidate],
        boundaries: &[usize],
    ) -> Vec<Field> {
        let versions: Vec<_> = candidates
            .iter()
            .filter(|c| c.value["kind"] == "version" && c.start < c.end && c.end < boundaries.len())
            .map(|c| boundaries[c.start]..boundaries[c.end])
            .collect();
        let mut masked = text.as_bytes().to_vec();
        for span in mentions.iter().map(|m| &m.span).chain(versions.iter()) {
            masked[span.clone()].fill(b' ');
        }
        let masked = String::from_utf8(masked).expect("whole UTF-8 spans masked");
        let mut fields: Vec<_> = self
            .attribute_re
            .find_iter(&masked)
            .filter(|m| whole(&masked, &m.range()))
            .filter_map(|m| {
                self.attributes.get(&key(m.as_str())).map(|name| Field {
                    span: m.range(),
                    name: name.clone(),
                })
            })
            .collect();
        // An alias inside a longer field (Cloud in cloud_provider) must not
        // erase that field. A field inside a complete name still stays masked.
        for m in self
            .attribute_re
            .find_iter(text)
            .filter(|m| whole(text, &m.range()))
        {
            if versions.iter().any(|v| overlaps(v, &m.range()))
                || mentions.iter().any(|n| {
                    overlaps(&n.span, &m.range())
                        && (!inside(&n.span, &m.range()) || n.span == m.range())
                })
            {
                continue;
            }
            if let Some(name) = self.attributes.get(&key(m.as_str())) {
                fields.push(Field {
                    span: m.range(),
                    name: name.clone(),
                });
            }
        }
        fields.sort_by_key(|f| (std::cmp::Reverse(f.span.len()), f.span.start));
        let mut longest = Vec::<Field>::new();
        for field in fields {
            if !longest.iter().any(|f| overlaps(&field.span, &f.span)) {
                longest.push(field);
            }
        }
        longest.sort_by_key(|f| f.span.start);
        longest
    }
}

struct ParseState<'a> {
    parser: &'a ProgramParser,
    text: &'a str,
    candidates: &'a [ValueCandidate],
    neural: &'a [Fact],
    boundaries: &'a [usize],
    mentions: &'a [Mention],
    fields: &'a [Field],
    protected: &'a [Range<usize>],
    tokens: &'a [Token],
    nodes: usize,
    structured: bool,
    complete: bool,
    notes: Vec<String>,
}

impl ParseState<'_> {
    fn count(&mut self, expression: ClaimExpr) -> Result<ClaimExpr, String> {
        self.nodes += 1;
        if self.nodes > MAX_PROGRAM_NODES {
            Err("node_limit".into())
        } else {
            Ok(expression)
        }
    }

    fn unknown(&mut self, span: Range<usize>, reason: &str) -> Result<ClaimExpr, String> {
        self.complete = false;
        self.notes.push(reason.to_owned());
        let span = self.char_span(&span);
        self.count(ClaimExpr::Unknown {
            span,
            reason: reason.to_owned(),
        })
    }

    fn unsupported(&mut self, span: Range<usize>, reason: &str) -> Result<ClaimExpr, String> {
        self.structured = true;
        self.complete = false;
        self.notes.push(reason.to_owned());
        let span = self.char_span(&span);
        self.count(ClaimExpr::Unsupported {
            span,
            reason: reason.to_owned(),
        })
    }

    fn char_span(&self, span: &Range<usize>) -> CharSpan {
        CharSpan {
            start: self.boundaries.partition_point(|&b| b < span.start),
            end: self.boundaries.partition_point(|&b| b < span.end),
        }
    }

    fn expression(&mut self, span: Range<usize>, depth: usize) -> Result<ClaimExpr, String> {
        if depth > MAX_PROGRAM_DEPTH {
            return Err("depth_limit".into());
        }
        let span = trim(self.text, span);
        if span.is_empty() {
            return self.unknown(span, "empty logical operand");
        }
        // A leading natural-language quantifier scopes its written list:
        // "not all A and B" means NOT(ALL(A,B)). Function-style quantifiers
        // followed by an outer connective are handled by normal precedence.
        let leading = self.prefix_at(&span);
        if let Some(("not", size)) = leading {
            let remainder = trim(self.text, span.start + size..span.end);
            if self
                .prefix_at(&remainder)
                .is_some_and(|(kind, _)| matches!(kind, "all" | "any" | "both" | "either"))
                && !self.quantifier_function_followed_by_operator(&remainder)
            {
                let child = self.expression(remainder, depth + 1)?;
                return self.count(ClaimExpr::Not(Box::new(child)));
            }
        }
        // OR has lower precedence than AND. Prefix NOT otherwise binds only
        // its own term. Neither/nor is a single explicitly scoped negated list.
        for kind in [TokenKind::Or, TokenKind::And] {
            if leading.is_some_and(|(prefix, _)| {
                prefix == "neither"
                    || (matches!(prefix, "all" | "any" | "both" | "either")
                        && !self.quantifier_function_followed_by_operator(&span))
            }) {
                break;
            }
            let cuts = self.top_level(&span, |k| k == kind);
            if !cuts.is_empty() {
                let children = self.parts(span, &cuts, depth)?;
                return self.count(if kind == TokenKind::Or {
                    ClaimExpr::Any(children)
                } else {
                    ClaimExpr::All(children)
                });
            }
        }
        if let Some((kind, size)) = leading {
            let remainder = trim(self.text, span.start + size..span.end);
            if kind == "not" {
                if NEGATION_EXCEPTION.is_match(&self.text[remainder.clone()]) {
                    return self.leaf(span, false);
                }
                if ONLY.is_match(&self.text[remainder.clone()]) {
                    return self.unsupported(span, "unsupported not-only construction");
                }
                let child = self.expression(remainder, depth + 1)?;
                return self.count(ClaimExpr::Not(Box::new(child)));
            }
            let filler = PREFIX_FILLER
                .find(&self.text[remainder.clone()])
                .map_or(0, |m| m.end());
            let mut remainder = trim(self.text, remainder.start + filler..remainder.end);
            let neither = kind == "neither";
            let all = matches!(kind, "all" | "both");
            if encloses(&remainder, self.tokens) {
                remainder = trim(self.text, remainder.start + 1..remainder.end - 1);
            }
            let cuts = self.top_level(&remainder, |k| {
                k == TokenKind::Comma
                    || (neither && k == TokenKind::Nor)
                    || (all && k == TokenKind::And)
                    || (!all && !neither && k == TokenKind::Or)
            });
            let children = if cuts.is_empty() {
                vec![self.expression(remainder, depth + 1)?]
            } else {
                self.parts(remainder, &cuts, depth)?
            };
            let group = self.count(if all {
                ClaimExpr::All(children)
            } else {
                ClaimExpr::Any(children)
            })?;
            return if neither {
                self.count(ClaimExpr::Not(Box::new(group)))
            } else {
                Ok(group)
            };
        }
        if encloses(&span, self.tokens) {
            return self.expression(span.start + 1..span.end - 1, depth + 1);
        }
        if !self.top_level(&span, |k| k == TokenKind::Nor).is_empty() {
            return self.unsupported(span, "nor requires an explicit neither scope");
        }
        if self
            .tokens
            .iter()
            .any(|t| inside(&t.span, &span) && matches!(t.kind, TokenKind::Open | TokenKind::Close))
        {
            return self.unsupported(span, "unresolved parenthesis scope");
        }
        self.leaf(span, false)
    }

    fn prefix_at(&self, span: &Range<usize>) -> Option<(&'static str, usize)> {
        prefix(&self.text[span.clone()])
            .filter(|(_, size)| !overlaps_any(&(span.start..span.start + size), self.protected))
    }

    fn quantifier_function_followed_by_operator(&self, span: &Range<usize>) -> bool {
        let Some((_, size)) = self.prefix_at(span) else {
            return false;
        };
        let remainder = trim(self.text, span.start + size..span.end);
        self.text[remainder.clone()].starts_with('(')
            && !self
                .top_level(&remainder, |k| matches!(k, TokenKind::And | TokenKind::Or))
                .is_empty()
    }

    fn top_level(
        &self,
        span: &Range<usize>,
        accept: impl Fn(TokenKind) -> bool,
    ) -> Vec<Range<usize>> {
        let mut nesting = 0usize;
        let mut cuts = Vec::new();
        for token in self.tokens.iter().filter(|t| inside(&t.span, span)) {
            match token.kind {
                TokenKind::Open => nesting += 1,
                TokenKind::Close => nesting = nesting.saturating_sub(1),
                kind if nesting == 0 && accept(kind) => cuts.push(token.span.clone()),
                _ => {}
            }
        }
        cuts
    }

    fn parts(
        &mut self,
        span: Range<usize>,
        cuts: &[Range<usize>],
        depth: usize,
    ) -> Result<Vec<ClaimExpr>, String> {
        if cuts.len() >= MAX_PROGRAM_NODES {
            return Err("node_limit".into());
        }
        let mut children = Vec::new();
        let mut start = span.start;
        for cut in cuts {
            children.push(self.expression(start..cut.start, depth + 1)?);
            start = cut.end;
        }
        children.push(self.expression(start..span.end, depth + 1)?);
        Ok(children)
    }

    fn leaf(&mut self, span: Range<usize>, legacy: bool) -> Result<ClaimExpr, String> {
        let text = &self.text[span.clone()];
        let comparisons: Vec<_> = COMPARE
            .captures_iter(text)
            .filter(|c| {
                let m = c.get(0).expect("whole capture");
                !overlaps_any(
                    &(span.start + m.start()..span.start + m.end()),
                    self.protected,
                )
            })
            .collect();
        if let Some(c) = comparisons.first() {
            let m = c.get(0).expect("whole capture");
            let left_span = span.start..span.start + m.start();
            let right_span = span.start + m.end()..span.end;
            let left_fields = self.fields.iter().any(|f| inside(&f.span, &left_span));
            let right_fields = self.fields.iter().any(|f| inside(&f.span, &right_span));
            let right_nominal = self.candidates.iter().any(|v| {
                v.value["kind"] == "name"
                    && v.start < v.end
                    && v.end < self.boundaries.len()
                    && inside(
                        &(self.boundaries[v.start]..self.boundaries[v.end]),
                        &right_span,
                    )
            });
            let right_reference = REFERENCE.is_match(&self.text[right_span.clone()])
                || self.mentions.iter().any(|n| inside(&n.span, &right_span));
            if left_fields && !right_nominal && (right_fields || right_reference)
                || (!left_fields && !right_fields && c.name("symbol").is_some())
            {
                self.structured = true;
                if comparisons.len() != 1 {
                    return self.unsupported(span, "chained slot comparison");
                }
                if let (Some(left), Some(right)) = (self.slot(left_span), self.slot(right_span)) {
                    return self.count(ClaimExpr::Compare {
                        left,
                        op: comparison_op(c),
                        right,
                    });
                }
                return self.unsupported(span, "unresolved slot comparison reference");
            }
        }
        let negations: Vec<_> = NEGATION
            .find_iter(text)
            .filter(|m| {
                let protected = overlaps_any(
                    &(span.start + m.start()..span.start + m.end()),
                    self.protected,
                );
                let comparator_or_unknown = m.as_str().eq_ignore_ascii_case("not")
                    && NEGATION_EXCEPTION.is_match(&text[m.end()..]);
                !(protected || comparator_or_unknown)
            })
            .map(|m| m.range())
            .collect();
        if negations.len() > MAX_PROGRAM_DEPTH {
            return Err("depth_limit".into());
        }
        for negation in &negations {
            if ONLY.is_match(&text[negation.end..]) {
                return self.unsupported(span, "unsupported not-only construction");
            }
        }
        let masked: String = text
            .char_indices()
            .map(|(offset, c)| {
                if negations.iter().any(|n| n.contains(&offset)) {
                    ' '
                } else {
                    c
                }
            })
            .collect();
        let char_span = self.char_span(&span);
        let candidates: Vec<_> = self
            .candidates
            .iter()
            .filter(|c| c.start >= char_span.start && c.start < c.end && c.end <= char_span.end)
            .map(|c| ValueCandidate {
                start: c.start - char_span.start,
                end: c.end - char_span.start,
                value: c.value.clone(),
            })
            .collect();
        let masked = unquote(&masked);
        let (masked, nominal_spellings) = shield_nominals(&masked, &candidates, |c| {
            let a = char_span.start + c.start;
            let b = char_span.start + c.end;
            let bytes = self.boundaries[a]..self.boundaries[b];
            !self.mentions.iter().any(|m| overlaps(&bytes, &m.span))
                && !self.fields.iter().any(|f| overlaps(&bytes, &f.span))
        });
        // Whole-row neural output has no leaf alignment. Retain it only in
        // the ordinary-prose route, never broadcast it across logical terms.
        let neural = if legacy && negations.is_empty() {
            self.neural
        } else {
            &[]
        };
        let parsed = self.parser.schema.parse(&masked, &candidates, neural);
        self.notes.extend(parsed.notes.clone());
        let mut children = Vec::new();
        for mut fact in parsed.facts {
            if fact.value["kind"] == "name"
                && let Some(raw) = fact.value["value"].as_str()
                && let Some(original) = nominal_spellings.get(raw)
            {
                fact.value["value"] = original.clone();
            }
            children.push(self.count(ClaimExpr::Atom(fact))?);
        }
        if !parsed.complete || children.is_empty() {
            children.push(self.unknown(span.clone(), "unresolved assertion leaf")?);
        }
        let mut expression = if children.len() == 1 {
            children.remove(0)
        } else {
            self.count(ClaimExpr::All(children))?
        };
        if !negations.is_empty() {
            self.structured = true;
            if !matches!(expression, ClaimExpr::Atom(_)) {
                return self.unsupported(span, "unresolved atomic negation scope");
            }
            for _ in negations {
                expression = self.count(ClaimExpr::Not(Box::new(expression)))?;
            }
        }
        Ok(expression)
    }

    fn slot(&self, span: Range<usize>) -> Option<SlotReference> {
        let mentions: Vec<_> = self
            .mentions
            .iter()
            .filter(|m| {
                inside(&m.span, &span) && !self.fields.iter().any(|f| inside(&m.span, &f.span))
            })
            .collect();
        let fields: Vec<_> = self
            .fields
            .iter()
            .filter(|f| inside(&f.span, &span))
            .collect();
        if mentions.len() != 1 || mentions[0].owners.len() != 1 || fields.len() != 1 {
            return None;
        }
        let subject = &self.parser.subjects[mentions[0].owners[0]];
        if !subject.attributes.contains(&fields[0].name) {
            return None;
        }
        let mut rest = self.text.as_bytes()[span.clone()].to_vec();
        for part in [&mentions[0].span, &fields[0].span] {
            rest[part.start - span.start..part.end - span.start].fill(b' ');
        }
        let rest_text = String::from_utf8(rest).ok()?;
        let dates: Vec<_> = DATE.find_iter(&rest_text).collect();
        if dates.len() > 1 {
            return None;
        }
        let date = dates.first().map(|m| m.as_str().to_owned());
        if date.as_ref().is_some_and(|d| !valid_date(d)) {
            return None;
        }
        let mut rest = rest_text.into_bytes();
        if let Some(date) = &date {
            let start = rest
                .windows(date.len())
                .position(|s| s == date.as_bytes())?;
            rest[start..start + date.len()].fill(b' ');
        }
        if !SLOT_FILLER.is_match(&String::from_utf8(rest).ok()?) {
            return None;
        }
        Some(SlotReference {
            subject: subject.name.clone(),
            attribute: fields[0].name.clone(),
            date,
        })
    }
}

fn comparison_op(c: &regex::Captures<'_>) -> ComparisonOp {
    if c.name("ge").is_some() {
        ComparisonOp::Ge
    } else if c.name("le").is_some() {
        ComparisonOp::Le
    } else if c.name("ne").is_some() {
        ComparisonOp::Ne
    } else if c.name("gt").is_some() {
        ComparisonOp::Gt
    } else if c.name("lt").is_some() {
        ComparisonOp::Lt
    } else {
        match c.name("symbol").map(|m| m.as_str()).unwrap_or("=") {
            ">=" | "≥" => ComparisonOp::Ge,
            "<=" | "≤" => ComparisonOp::Le,
            "!=" | "≠" => ComparisonOp::Ne,
            ">" => ComparisonOp::Gt,
            "<" => ComparisonOp::Lt,
            _ => ComparisonOp::Eq,
        }
    }
}

fn rejected(span: CharSpan, reason: &str) -> ClaimProgram {
    ClaimProgram {
        expression: ClaimExpr::Unsupported {
            span,
            reason: reason.to_owned(),
        },
        complete: false,
        structured: true,
        notes: vec![reason.to_owned()],
    }
}

fn prefix(text: &str) -> Option<(&'static str, usize)> {
    // Avoid regex look-around: prefix words require a real lexical boundary.
    let c = PREFIX.captures(text)?;
    for kind in ["not", "neither", "all", "any", "both", "either"] {
        if let Some(m) = c.name(kind) {
            return Some((kind, m.end()));
        }
    }
    None
}

fn trim(text: &str, mut span: Range<usize>) -> Range<usize> {
    let body = &text[span.clone()];
    span.start += body.len() - body.trim_start().len();
    span.end -= text[span.clone()]
        .len()
        .saturating_sub(text[span.clone()].trim_end().len());
    if text[span.clone()].ends_with('.') {
        span.end -= 1;
        while span.end > span.start && text[..span.end].ends_with(char::is_whitespace) {
            span.end -= text[..span.end]
                .chars()
                .next_back()
                .map_or(0, char::len_utf8);
        }
    }
    span
}

fn encloses(span: &Range<usize>, tokens: &[Token]) -> bool {
    let mut depth = 0usize;
    let local: Vec<_> = tokens.iter().filter(|t| inside(&t.span, span)).collect();
    if !local
        .first()
        .is_some_and(|t| t.kind == TokenKind::Open && t.span.start == span.start)
        || !local
            .last()
            .is_some_and(|t| t.kind == TokenKind::Close && t.span.end == span.end)
    {
        return false;
    }
    for (i, token) in local.iter().enumerate() {
        match token.kind {
            TokenKind::Open => depth += 1,
            TokenKind::Close => {
                depth = depth.saturating_sub(1);
                if depth == 0 && i + 1 < local.len() {
                    return false;
                }
            }
            _ => {}
        }
    }
    depth == 0
}

fn quote_spans(text: &str) -> (Vec<Range<usize>>, bool) {
    let mut spans = Vec::new();
    let mut open: Option<(usize, char)> = None;
    for (offset, c) in text.char_indices() {
        if let Some((start, close)) = open {
            if c == close && !escaped(text, offset) {
                spans.push(start..offset + c.len_utf8());
                open = None;
            }
        } else {
            let close = match c {
                '"' if text[..offset]
                    .chars()
                    .next_back()
                    .is_some_and(|p| p.is_ascii_digit())
                    && text[offset + 1..].chars().next().is_none_or(|n| {
                        n.is_whitespace() || matches!(n, '.' | ',' | ';' | ')')
                    }) =>
                {
                    None
                }
                '"' | '“' if !escaped(text, offset) => Some(if c == '“' { '”' } else { '"' }),
                '\'' | '‘'
                    if !text[..offset]
                        .chars()
                        .next_back()
                        .is_some_and(char::is_alphanumeric)
                        && !text[offset + c.len_utf8()..].starts_with("s ")
                        && !text[offset + c.len_utf8()..].starts_with("s:") =>
                {
                    Some(if c == '‘' { '’' } else { '\'' })
                }
                _ => None,
            };
            if let Some(close) = close {
                open = Some((offset, close));
            }
        }
    }
    (spans, open.is_some())
}

fn escaped(text: &str, offset: usize) -> bool {
    text[..offset]
        .chars()
        .rev()
        .take_while(|&c| c == '\\')
        .count()
        % 2
        == 1
}

fn unquote(text: &str) -> String {
    let (quotes, _) = quote_spans(text);
    let delimiters: BTreeSet<_> = quotes
        .iter()
        .flat_map(|q| {
            let last = text[..q.end]
                .char_indices()
                .next_back()
                .map_or(q.start, |(b, _)| b);
            [q.start, last]
        })
        .collect();
    text.char_indices()
        .map(
            |(offset, c)| {
                if delimiters.contains(&offset) { ' ' } else { c }
            },
        )
        .collect()
}

fn shield_nominals(
    text: &str,
    candidates: &[ValueCandidate],
    eligible: impl Fn(&ValueCandidate) -> bool,
) -> (String, BTreeMap<String, Value>) {
    let mut chars: Vec<_> = text.chars().collect();
    let mut spellings = BTreeMap::new();
    let mut occupied = BTreeSet::new();
    for c in candidates {
        if c.value["kind"] != "name"
            || !eligible(c)
            || c.end > chars.len()
            || (c.start..c.end).any(|i| occupied.contains(&i))
        {
            continue;
        }
        let original: String = chars[c.start..c.end].iter().collect();
        for (i, ch) in chars.iter_mut().enumerate().take(c.end).skip(c.start) {
            // Full-width ASCII is one scalar per original scalar, so supplied
            // offsets stay exact. It hides lexical AND/UNKNOWN and punctuation
            // inside an opaque name from SchemaParser's clause splitter.
            if ch.is_ascii_graphic() {
                *ch = char::from_u32(*ch as u32 + 0xfee0).expect("full-width ASCII");
            }
            occupied.insert(i);
        }
        let shielded: String = chars[c.start..c.end].iter().collect();
        let value = c.value["value"]
            .as_str()
            .filter(|v| key(v) == key(&original))
            .map_or_else(|| Value::String(original), |v| Value::String(v.to_owned()));
        spellings.insert(shielded, value);
    }
    (chars.into_iter().collect(), spellings)
}

fn lexical_join(text: &str, span: &Range<usize>) -> bool {
    text[..span.start].ends_with(['-', '_', '/']) || text[span.end..].starts_with(['-', '_', '/'])
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
    Regex::new(&pattern).map_err(|e| format!("program schema expression: {e}"))
}

fn whole(text: &str, span: &Range<usize>) -> bool {
    !text[..span.start]
        .chars()
        .next_back()
        .is_some_and(|c| c.is_alphanumeric() || c == '_')
        && !text[span.end..]
            .chars()
            .next()
            .is_some_and(|c| c.is_alphanumeric() || c == '_')
}

fn inside(a: &Range<usize>, b: &Range<usize>) -> bool {
    b.start <= a.start && a.end <= b.end
}

fn overlaps_any(a: &Range<usize>, spans: &[Range<usize>]) -> bool {
    // All protection spans are sorted and merged once before scanning.
    let next = spans.partition_point(|b| b.end <= a.start);
    spans.get(next).is_some_and(|b| b.start < a.end)
}

fn overlaps(a: &Range<usize>, b: &Range<usize>) -> bool {
    a.start < b.end && b.start < a.end
}

fn valid_date(date: &str) -> bool {
    let parts: Vec<_> = date.split('-').collect();
    let Ok(year) = parts[0].parse::<u32>() else {
        return false;
    };
    if parts.len() == 1 {
        return true;
    }
    let Ok(month) = parts[1].parse::<u32>() else {
        return false;
    };
    if !(1..=12).contains(&month) {
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
    (1..=max).contains(&day)
}
