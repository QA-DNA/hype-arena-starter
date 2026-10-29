//! Literal port of selected-v2/grammar.py; no new extraction heuristics.
use std::collections::{BTreeMap, HashMap};

use anyhow::{Context, Result, anyhow, bail};
use fancy_regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::python::{Text, casefold, decimal_ascii, regex, rx};

pub const KINDS: [&str; 8] = [
    "quantity", "date", "boolean", "money", "percent", "duration", "name", "version",
];
const WORDS: &str = "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety";
const MONTHS: [(&str, u8); 25] = [
    ("january", 1),
    ("jan", 1),
    ("february", 2),
    ("feb", 2),
    ("march", 3),
    ("mar", 3),
    ("april", 4),
    ("apr", 4),
    ("may", 5),
    ("june", 6),
    ("jun", 6),
    ("july", 7),
    ("jul", 7),
    ("august", 8),
    ("aug", 8),
    ("september", 9),
    ("sep", 9),
    ("october", 10),
    ("oct", 10),
    ("november", 11),
    ("nov", 11),
    ("december", 12),
    ("dec", 12),
    ("sept", 9),
    ("", 0),
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Candidate {
    pub start: usize,
    pub end: usize,
    pub value: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lo: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hi: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kind: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub clo: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub chi: Option<usize>,
}

/// Python json.dumps(sort_keys=True, separators=(',', ':')) escaping.
fn ascii_json(value: &Value) -> String {
    let text = serde_json::to_string(value).expect("JSON Value");
    let mut result = String::with_capacity(text.len());
    for c in text.chars() {
        if c.is_ascii() {
            result.push(c);
        } else {
            let mut buf = [0_u16; 2];
            for n in c.encode_utf16(&mut buf) {
                result.push_str(&format!(r"\u{n:04x}"));
            }
        }
    }
    result
}

pub fn canonical(value: &Value) -> String {
    let mut value = value.clone();
    if value.get("op").and_then(Value::as_str) == Some("eq") {
        value.as_object_mut().unwrap().remove("op");
    }
    if let Some(n) = value
        .get("value")
        .filter(|v| v.as_number().is_some_and(serde_json::Number::is_f64))
        .and_then(Value::as_f64)
    {
        let rounded = format!("{n:.9}").parse::<f64>().unwrap_or(n);
        value["value"] = numeric(rounded).unwrap_or_else(|_| value["value"].clone());
    }
    ascii_json(&value)
}

fn numeric(n: f64) -> Result<Value> {
    if !n.is_finite() {
        bail!("Numeric candidate is not finite");
    }
    if n == 0. {
        return Ok(json!(0));
    }
    if n.fract() == 0. {
        return Ok(serde_json::from_str(&format!("{n:.0}"))?);
    }
    Ok(json!(n))
}

pub fn singular(word: &str) -> String {
    let w = casefold(word);
    if w == "people" || w == "persons" {
        return "person".into();
    }
    if let Some(prefix) = w.strip_suffix("ies") {
        return format!("{prefix}y");
    }
    if w.ends_with("ches") {
        return w[..w.len() - 2].into();
    }
    if w.ends_with('s') && !w.ends_with("ss") && w != "ms" && w != "s" {
        return w[..w.len() - 1].into();
    }
    w
}

fn number(text: &str) -> Result<Value> {
    let t = decimal_ascii(&casefold(text).replace(',', ""));
    match t.as_str() {
        "a dozen" => return Ok(json!(12)),
        "a hundred" => return Ok(json!(100)),
        "a" | "an" => return Ok(json!(1)),
        _ => (),
    }
    let unsigned = t.strip_prefix('-').unwrap_or(&t);
    let (whole, fraction) = unsigned.split_once('.').unwrap_or((unsigned, ""));
    if !whole.is_empty()
        && whole.bytes().all(|b| b.is_ascii_digit())
        && fraction.bytes().all(|b| b == b'0')
    {
        let whole = whole.trim_start_matches('0');
        let whole = if whole.is_empty() { "0" } else { whole };
        let sign = if t.starts_with('-') && whole != "0" {
            "-"
        } else {
            ""
        };
        return Ok(serde_json::from_str(&format!("{sign}{whole}"))?);
    }
    if let Ok(n) = t.parse::<f64>() {
        return numeric(n);
    }
    let small = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen";
    let tens = "twenty thirty forty fifty sixty seventy eighty ninety";
    let mut result = 0;
    for w in t.split(['-', ' ']) {
        result += small
            .split(' ')
            .position(|s| s == w)
            .or_else(|| tens.split(' ').position(|s| s == w).map(|i| 20 + i * 10))
            .with_context(|| format!("Unsupported number {text:?}"))?;
    }
    Ok(json!(result))
}

pub fn clauses(text: &str) -> Result<Vec<(usize, usize)>> {
    let t = Text::new(text);
    let mut result = Vec::new();
    let mut start = 0;
    for matched in rx!(r";\s*|[.!?](?=\s+[A-Z]|\s*$)\s*|,?\s+and\s+").find_iter(text) {
        let m = matched?;
        let a = t.char_at_byte(m.start());
        if a > start {
            result.push((start, a));
        }
        start = t.char_at_byte(m.end());
    }
    if start < t.len() {
        result.push((start, t.len()));
    }
    Ok(result)
}

pub struct Grammar {
    names: HashMap<String, String>,
    name_re: Regex,
    number_re: Regex,
    date_re: [Regex; 3],
    operators: Vec<(Regex, &'static str)>,
}

impl Grammar {
    pub fn new(lexicon: &Value, extra_names: &[String]) -> Result<Self> {
        let mut names = HashMap::new();
        let mut order: Vec<String> = Vec::new();
        let mut add_name = |alias: &str, name: &str, only_missing: bool| {
            let key = casefold(alias);
            if !names.contains_key(&key) {
                order.push(key.clone());
            }
            if !only_missing || !names.contains_key(&key) {
                names.insert(key, name.to_owned());
            }
        };
        for s in lexicon["subjects"].as_array().context("lexicon subjects")? {
            let name = s["name"].as_str().context("subject name")?;
            add_name(name, name, false);
            for a in s["aliases"].as_array().into_iter().flatten() {
                add_name(a.as_str().context("alias")?, name, false);
            }
        }
        for key in ["names", "values"] {
            for obj in lexicon[key].as_array().into_iter().flatten() {
                if let Some(name) = obj.as_str() {
                    add_name(name, name, false);
                } else if let Some(name) = obj["name"].as_str() {
                    add_name(name, name, false);
                    for a in obj["aliases"].as_array().into_iter().flatten() {
                        add_name(a.as_str().context("alias")?, name, false);
                    }
                }
            }
        }
        for name in extra_names {
            add_name(name, name, true);
        }
        order.sort_by_key(|s| std::cmp::Reverse(s.chars().count()));
        let alternatives = order
            .iter()
            .map(|s| regex::escape(s))
            .collect::<Vec<_>>()
            .join("|");
        let name_re = regex(&format!(r"(?<!\w)(?:{alternatives})(?!\w)"), true)?;
        let num = format!(
            r"(?:-?\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|-?\d+(?:\.\d+)?|(?:{WORDS})(?:[- ](?:{WORDS}))?|a dozen|a hundred|an|a)"
        );
        let number_re = regex(
            &format!(
                r"(?<![\w.])(?P<n>{num})(?:\s*(?P<scale>million|billion|thousand|bn|k|(?-i:M)))?(?!\w)"
            ),
            true,
        )?;
        let mut months: Vec<&str> = MONTHS
            .iter()
            .filter(|(m, _)| !m.is_empty())
            .map(|(m, _)| *m)
            .collect();
        months.sort_by_key(|m| std::cmp::Reverse(m.len()));
        let month = format!(r"(?:{})\.?", months.join("|"));
        let date_re = [
            regex(
                &format!(
                    r"(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s*(?P<m>{month})\s+(?P<y>\d{{4}})"
                ),
                true,
            )?,
            regex(
                &format!(r"(?P<m>{month})\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(?P<y>\d{{4}})"),
                true,
            )?,
            regex(&format!(r"(?P<m>{month})\s+(?P<y>\d{{4}})"), true)?,
        ];
        let operators = [
            (r"(?:at least|no less than|not less than|no earlier than|no older than|>=|≥)\s*(?:the\s+)?$", "ge"),
            (r"(?:at most|no more than|not more than|no later than|no newer than|up to|within|<=|≤)\s*(?:the\s+)?$", "le"),
            (r"(?:more than|greater than|over|above|newer than|after|>)\s*(?:the\s+)?$", "gt"),
            (r"(?:less than|fewer than|under|below|older than|before|<)\s*(?:the\s+)?$", "lt"),
        ].into_iter().map(|(p, op)| Ok((regex(p, true)?, op))).collect::<Result<_>>()?;
        Ok(Self {
            names,
            name_re,
            number_re,
            date_re,
            operators,
        })
    }

    /// Additional literal candidates for schema binding. The frozen model's
    /// candidate list and encodings remain unchanged.
    pub fn binding_candidates(&self, text: &str) -> Result<Vec<Candidate>> {
        let mut result = self.candidates(text)?;
        for captures in rx!(
            r"(?<![\w.])(?P<n>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+(?:inches|inch|in)(?!\w)",
            true
        )
        .captures_iter(text)
        {
            let captures = captures?;
            let matched = captures.get(0).unwrap();
            let start = text[..matched.start()].chars().count();
            let end = text[..matched.end()].chars().count();
            let value: Value = serde_json::from_str(captures.name("n").unwrap().as_str())?;
            if !result
                .iter()
                .any(|c| c.start == start && c.end == end && c.value["unit"] == "inch")
            {
                result.push(Candidate {
                    start,
                    end,
                    value: json!({"kind":"quantity","value":value,"unit":"inch"}),
                    lo: None,
                    hi: None,
                    kind: None,
                    clo: None,
                    chi: None,
                });
            }
        }
        Ok(result)
    }

    pub fn candidates(&self, text: &str) -> Result<Vec<Candidate>> {
        let t = Text::new(text);
        let mut collector = Collector {
            t: &t,
            grammar: self,
            result: Vec::new(),
            occupied: Vec::new(),
        };
        for matched in rx!(r"(?<!\d)(20\d{2}|19\d{2})-(\d{2})(?:-(\d{2}))?(?!\d)").find_iter(text) {
            let m = matched?;
            collector.add_bytes(
                m.start(),
                m.end(),
                json!({"kind":"date","value":m.as_str()}),
                true,
            )?;
        }
        for (i, re) in self.date_re.iter().enumerate() {
            for captures in re.captures_iter(text) {
                let c = captures?;
                let m = c.get(0).unwrap();
                if collector.overlaps_bytes(m.start(), m.end()) {
                    continue;
                }
                let month = casefold(c.name("m").unwrap().as_str().trim_end_matches('.'));
                let n = MONTHS
                    .iter()
                    .find(|(name, _)| *name == month)
                    .context("month name")?
                    .1;
                let year = c.name("y").unwrap().as_str();
                let value = if i < 2 {
                    let day = decimal_ascii(c.name("d").unwrap().as_str()).parse::<u8>()?;
                    format!("{year}-{n:02}-{day:02}")
                } else {
                    format!("{year}-{n:02}")
                };
                collector.add_bytes(
                    m.start(),
                    m.end(),
                    json!({"kind":"date","value":value}),
                    true,
                )?;
            }
        }
        for captures in rx!(r"(?<!\w)(?:v|version\s+|ver\.\s*)(\d+(?:\.\d+)*)(?!\w)|(?<![\w.])(\d+\.\d+\.\d+(?:\.\d+)*)(?!\w|\.\d)", true).captures_iter(text) {
            let c = captures?;
            let m = c.get(0).unwrap();
            collector.add_bytes(m.start(), m.end(), json!({"kind":"version","value":c.get(1).or_else(|| c.get(2)).unwrap().as_str()}), true)?;
        }
        for matched in rx!(r"(?<![\w.])\d+\.\d+(?!\w|\.\d)").find_iter(text) {
            let m = matched?;
            let before = &text[..m.start()];
            if !collector.overlaps_bytes(m.start(), m.end())
                && rx!(r"\bversion\b[^;.!?]{0,35}$", true).is_match(before)?
            {
                collector.add_bytes(
                    m.start(),
                    m.end(),
                    json!({"kind":"version","value":m.as_str()}),
                    true,
                )?;
            } else if !collector.overlaps_bytes(m.start(), m.end())
                && rx!(r"[A-Z][A-Za-z]*(?:\s+CLI)?\s+$").is_match(before)?
            {
                collector.add_bytes(
                    m.start(),
                    m.end(),
                    json!({"kind":"version","value":m.as_str()}),
                    false,
                )?;
            }
        }
        for matched in self.name_re.find_iter(text) {
            let m = matched?;
            let name = self
                .names
                .get(&casefold(m.as_str()))
                .context("Name matched but has no casefold key (frozen Python behavior)")?;
            collector.add_bytes(
                m.start(),
                m.end(),
                json!({"kind":"name","value":name}),
                false,
            )?;
        }
        let name_spans: Vec<_> = collector
            .result
            .iter()
            .filter(|c| c.value["kind"] == "name")
            .map(|c| (c.start, c.end))
            .collect();
        for matched in
            rx!(r"(?<!\w)[A-Z][a-zA-Z-]+(?:\s+[A-Z][a-zA-Z-]+){0,3}(?!\w)").find_iter(text)
        {
            let m = matched?;
            let start = t.char_at_byte(m.start());
            let end = t.char_at_byte(m.end());
            if name_spans.iter().any(|&(a, b)| start < b && end > a)
                || [
                    "It", "Its", "They", "The", "My", "Anyway", "At", "In", "You", "We", "That",
                    "This", "Please",
                ]
                .contains(&m.as_str())
            {
                continue;
            }
            let skip = rx!(r"^(?:At|In|The|From|To)\s+")
                .find(m.as_str())?
                .map_or(0, |m| m.end());
            collector.add_bytes(
                m.start() + skip,
                m.end(),
                json!({"kind":"name","value":&m.as_str()[skip..]}),
                false,
            )?;
        }
        for captures in self.number_re.captures_iter(text) {
            let c = captures?;
            let m = c.get(0).unwrap();
            if collector.overlaps_bytes(m.start(), m.end()) {
                continue;
            }
            let start = t.char_at_byte(m.start());
            let end = t.char_at_byte(m.end());
            let raw = c.name("n").unwrap().as_str();
            let mut val = number(raw)?;
            if ["a", "an"].contains(&casefold(raw).as_str())
                && !rx!(
                    r"\b(?:under|within|in|for|over|than|least|most|to|only|just|lasting)\s*$",
                    true
                )
                .is_match(t.slice(start.saturating_sub(15), start))?
            {
                continue;
            }
            if let Some(scale) = c.name("scale") {
                let factor = match casefold(scale.as_str()).as_str() {
                    "million" | "m" => 1e6,
                    "billion" | "bn" => 1e9,
                    "thousand" | "k" => 1e3,
                    _ => unreachable!(),
                };
                val = numeric(val.as_f64().context("numeric value")? * factor)?;
            }
            let before = t.slice(start.saturating_sub(8), start);
            let after = t.slice(end, end + 70);
            let cm = rx!(r"(€|\$|£|\bEUR|\bUSD|\bGBP|\bCHF|\bRON|\bPLN|\bCZK|\bHUF|\bSEK|\bNOK|\bDKK|\bJPY|\bCNY|\bINR|\bCAD|\bAUD)\s*$", true).captures(before)?;
            let ca = rx!(r"^\s*(euros?|dollars?|lei|EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD)\b", true).captures(after)?;
            if cm.is_some() || ca.is_some() {
                let curr = cm
                    .as_ref()
                    .or(ca.as_ref())
                    .unwrap()
                    .get(1)
                    .unwrap()
                    .as_str();
                let currency = currency(casefold(curr).trim_end_matches('s'))?;
                let mut value = json!({"kind":"money","value":val,"currency":currency});
                let a = start
                    - cm.as_ref()
                        .map_or(0, |c| c.get(0).unwrap().as_str().chars().count());
                let mut b = end
                    + ca.as_ref()
                        .map_or(0, |c| c.get(0).unwrap().as_str().chars().count());
                if let Some(period) = rx!(r"^\s*(?:(?:per (?:user|terabyte)|/seat)\s*)?(?:(?:per|a|each|/)\s*(month|mo|year|yr|week|day)|(?P<annual>annually|per annum)|(?P<monthly>monthly))\b", true).captures(t.slice(b, t.len()))? {
                    let p = period.get(1).map(|m| casefold(m.as_str())).unwrap_or_else(|| if period.name("annual").is_some() {"year".into()} else {"month".into()});
                    value["per"] = json!(match p.as_str() {"mo"=>"month", "yr"=>"year", _=>&p});
                    b += period.get(0).unwrap().as_str().chars().count();
                }
                collector.add(a, b, value, false)?;
                continue;
            }
            if let Some(pm) = rx!(r"^\s*(%|percent\b|per cent\b)", true).find(after)? {
                collector.add(
                    start,
                    end + pm.as_str().chars().count(),
                    json!({"kind":"percent","value":val}),
                    false,
                )?;
                continue;
            }
            if let Some(unit) = rx!(r#"^(?:[-\s]*)([A-Za-z]+|["″])\b"#).captures(after)? {
                let raw = unit.get(1).unwrap().as_str();
                let u = singular(raw);
                let unit_end = unit.get(0).unwrap().as_str().chars().count();
                if let Some(duration) = duration(&u) {
                    collector.add(
                        start,
                        end + unit_end,
                        json!({"kind":"duration","value":val,"unit":duration}),
                        false,
                    )?;
                } else if ![
                    "of", "in", "on", "is", "and", "or", "down", "a", "the", "from", "at", "per",
                    "for",
                ]
                .contains(&raw)
                {
                    let normalized =
                        unit_name(&u).unwrap_or(if u == "meeting" { "sitting" } else { &u });
                    collector.add(
                        start,
                        end + unit_end,
                        json!({"kind":"quantity","value":val,"unit":normalized}),
                        false,
                    )?;
                    if unit_name(&u).is_none() {
                        let words = rx!(r"[A-Za-z]+")
                            .find_iter(after)
                            .take(3)
                            .collect::<std::result::Result<Vec<_>, _>>()?;
                        for extra in words.into_iter().skip(1) {
                            // Python negative slice intervals produce the empty string.
                            let between = &after
                                [unit.get(0).unwrap().end().min(extra.start())..extra.start()];
                            if rx!(r"[^A-Za-z\s-]").is_match(between)? {
                                break;
                            }
                            let noun = singular(extra.as_str());
                            if [
                                "is", "has", "ha", "and", "or", "in", "at", "for", "per", "on",
                                "a", "of", "the", "it", "its", "down", "to", "with", "from",
                            ]
                            .contains(&noun.as_str())
                            {
                                break;
                            }
                            collector.add(start,end+after[..extra.end()].chars().count(),json!({"kind":"quantity","value":val,"unit":unit_name(&noun).unwrap_or(&noun)}),false)?;
                        }
                    }
                }
            }
            if let Some(n) = val.as_i64()
                && (1900..=2099).contains(&n)
                && c.name("scale").is_none()
                && !raw.contains(',')
            {
                collector.add(
                    start,
                    end,
                    json!({"kind":"date","value":n.to_string()}),
                    false,
                )?;
            }
        }
        for (start, end) in clauses(text)? {
            for val in [true, false] {
                collector.add(start, end, json!({"kind":"boolean","value":val}), false)?;
            }
        }
        let mut unique = BTreeMap::new();
        for candidate in collector.result {
            unique.insert(
                (candidate.start, candidate.end, canonical(&candidate.value)),
                candidate,
            );
        }
        Ok(unique.into_values().collect())
    }
}

struct Collector<'a, 'b> {
    t: &'a Text<'b>,
    grammar: &'a Grammar,
    result: Vec<Candidate>,
    occupied: Vec<(usize, usize)>,
}
impl Collector<'_, '_> {
    fn overlaps_bytes(&self, a: usize, b: usize) -> bool {
        let a = self.t.char_at_byte(a);
        let b = self.t.char_at_byte(b);
        self.occupied.iter().any(|&(s, e)| a < e && b > s)
    }
    fn add_bytes(&mut self, a: usize, b: usize, value: Value, priority: bool) -> Result<()> {
        self.add(
            self.t.char_at_byte(a),
            self.t.char_at_byte(b),
            value,
            priority,
        )
    }
    fn add(&mut self, start: usize, end: usize, mut value: Value, priority: bool) -> Result<()> {
        let kind = value["kind"].as_str().context("candidate kind")?.to_owned();
        if [
            "money", "percent", "quantity", "duration", "date", "version",
        ]
        .contains(&kind.as_str())
        {
            let before = self.t.slice(start.saturating_sub(28), start);
            for (pattern, op) in &self.grammar.operators {
                if let Some(m) = pattern.find(before)? {
                    if kind != "date"
                        && rx!(r"\b(after|before|earlier|later)\b").is_match(m.as_str())?
                    {
                        continue;
                    }
                    if kind != "version" && rx!(r"\b(newer|older)\b").is_match(m.as_str())? {
                        continue;
                    }
                    value["op"] = json!(op);
                    break;
                }
            }
            if rx!(r"\bgoes up to\s*$", true).is_match(before)? {
                value.as_object_mut().unwrap().remove("op");
            }
            if kind == "percent" && rx!(r"^\s+SLA\b").is_match(self.t.slice(end, self.t.len()))? {
                value.as_object_mut().unwrap().remove("op");
            }
        }
        self.result.push(Candidate {
            start,
            end,
            value,
            lo: None,
            hi: None,
            kind: None,
            clo: None,
            chi: None,
        });
        if priority {
            self.occupied.push((start, end));
        }
        Ok(())
    }
}

fn currency(s: &str) -> Result<&'static str> {
    Ok(match s {
        "€" | "eur" | "euro" => "EUR",
        "$" | "usd" | "dollar" => "USD",
        "£" | "gbp" => "GBP",
        "lei" | "ron" => "RON",
        "chf" => "CHF",
        "cad" => "CAD",
        "aud" => "AUD",
        "jpy" => "JPY",
        "cny" => "CNY",
        "inr" => "INR",
        "pln" => "PLN",
        "czk" => "CZK",
        "huf" => "HUF",
        "sek" => "SEK",
        "nok" => "NOK",
        "dkk" => "DKK",
        _ => return Err(anyhow!("Unknown currency {s}")),
    })
}
fn duration(s: &str) -> Option<&'static str> {
    Some(match s {
        "ms" | "millisecond" => "ms",
        "s" | "sec" | "second" => "s",
        "min" | "minute" => "min",
        "h" | "hr" | "hour" => "h",
        "d" | "day" => "day",
        "wk" | "week" => "week",
        "mo" | "month" => "month",
        "yr" | "year" => "year",
        _ => return None,
    })
}
fn unit_name(s: &str) -> Option<&'static str> {
    Some(match s {
        "gb" | "gigabyte" | "gig" => "GB",
        "mb" | "megabyte" => "MB",
        "tb" | "terabyte" => "TB",
        "kb" | "kilobyte" => "KB",
        "b" | "byte" => "B",
        "mah" => "mAh",
        "w" | "watt" => "W",
        "g" | "gram" => "g",
        "kg" | "kilogram" => "kg",
        "km" | "kilometre" | "kilometer" => "km",
        "m" | "metre" | "meter" => "m",
        "in" | "inch" => "inch",
        "hz" | "hertz" => "Hz",
        "ghz" => "GHz",
        "mhz" => "MHz",
        _ => return None,
    })
}
