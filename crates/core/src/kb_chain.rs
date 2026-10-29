//! F2 per-key temporal chain: exact port of the knowledge-base campaign winner,
//! `labs/kb-campaign/F2/f2var.py:Chain {"d0":0.03,"engine":"viterbi","eps_a":0.0005,
//! "mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}` with the `Std` defaults (isotonic fact
//! map, product over the row's facts, isotonic row map, arena rule).
//!
//! One timeline per observation key (subject, attribute, kind, unit dimension). States are
//! the key's distinct canonical values plus "other". Hazard rates per kind and downward-switch
//! weights are fitted on labelled true anchors; every fact gets the Viterbi max-marginal margin
//! of agreeing over disagreeing states at its date with its own page removed. Two isotonic maps
//! (pool adjacent violators, the same block arithmetic as scipy) turn that into a label and a
//! confidence in [0.5, 1]. Float operations follow the numpy order of the reference so labels
//! and confidences reproduce the Python harness (see docs/handoffs/kb-chain-port.md).
//!
//! Fact semantics are the harness's (`labs/kb-campaign/harness/world.py:Fact`): floats rounded
//! to six decimals for state identity, interval overlap with a 1e-9 relative tolerance for
//! agreement, units folded only for the harness's ten data/time units. This deliberately does
//! not reuse `typed.rs` (exact rationals, wider unit tables): parity needs the harness's rules.
use serde_json::Value;
use std::collections::{BTreeMap, HashMap, HashSet};
use unicode_normalization::UnicodeNormalization;

const EPS_A: f64 = 0.0005;
const EPS_F: f64 = 0.2;
const VOTE_LR: f64 = 48.0;
const PI_O: f64 = 1.0;
const MONO_A: f64 = 10.0;
const D0: f64 = 0.03;
const MIN_PAIRS: usize = 8;

/// Budgets, checked before any dense matrix is built. A key's chain holds S states (distinct
/// equality values plus "other") over n facts and T distinct dates: its S x n agreement matrix
/// lives until the world is scored, scoring it briefly needs about 3*S*n + 3*S*T more floats, and
/// its Viterbi passes cost 2*T*S^2 steps. A key over a per-key cap, or one that would push the
/// world's running sums of S*n or T*S^2 over the world budget, is not scored; rows with a fact
/// on it are `over_budget` and keep the engine's label. Keys are admitted cheapest first (by
/// T*S^2, then S*n, then first appearance), so a few huge keys cannot crowd out ordinary ones.
/// All far above practice and the 20k suite worlds (see docs/handoffs/kb-chain-port.md).
pub const MAX_KEY_STATES: usize = 1024;
/// Cap on S*(n+T) for one key (cells of the S x n and S x T matrices).
pub const MAX_KEY_CELLS: usize = 1 << 22;
/// Cap on T*S^2 for one key (inner steps of one Viterbi pass).
pub const MAX_KEY_STEPS: usize = 1 << 30;
/// World budget on the sum of S*n over scored keys: 2^25 cells, 256 MiB of agreement matrices.
pub const WORLD_CELLS: usize = 1 << 25;
/// World budget on the sum of T*S^2 over scored keys: 2^33 steps, under 30 s at the measured
/// 2 to 3.2 ns per step (both passes).
pub const WORLD_STEPS: usize = 1 << 33;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Label {
    True,
    False,
    Unsure,
}

impl Label {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "true" => Some(Self::True),
            "false" => Some(Self::False),
            "unsure" => Some(Self::Unsure),
            _ => None,
        }
    }
    pub fn as_str(self) -> &'static str {
        match self {
            Self::True => "true",
            Self::False => "false",
            Self::Unsure => "unsure",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum Kind {
    Quantity,
    Money,
    Duration,
    Name,
    Percent,
    Boolean,
    Date,
    Version,
}

impl Kind {
    fn numeric(self) -> bool {
        matches!(
            self,
            Self::Quantity | Self::Money | Self::Duration | Self::Percent
        )
    }
}

/// Canonical value with Python equality: numbers (and booleans) compare as floats, NaN never
/// equals anything, strings by value.
#[derive(Clone, Debug)]
pub enum Canon {
    Num(f64),
    Str(String),
    Null,
}

impl PartialEq for Canon {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Num(a), Self::Num(b)) => a == b,
            (Self::Str(a), Self::Str(b)) => a == b,
            (Self::Null, Self::Null) => true,
            _ => false,
        }
    }
}

/// One parsed stated atom, as `world.py:Fact` sees it.
#[derive(Clone, Debug)]
pub struct KbFact {
    key: (String, String, Kind, String),
    kind: Kind,
    eq: bool,
    canon: Canon,
    /// Interval for numeric and date kinds (`lo`/`hi`), None for the others.
    iv: Option<(f64, f64)>,
}

/// One input row in universe order. `page` comes from [`pages_of`].
#[derive(Clone, Debug)]
pub struct ChainRow {
    pub date: i64,
    pub page: usize,
    pub label: Option<Label>,
    pub facts: Vec<KbFact>,
}

#[derive(Clone, Debug)]
pub struct ChainOutput {
    pub label: Label,
    /// Confidence of the label, in [0.5, 1]; None on unsure.
    pub confidence: Option<f64>,
    /// Isotonic estimate of P(true | decided) of the row (`pc`), fitted on this
    /// world's labelled rows. This is not independently calibrated probability.
    pub p_true: f64,
    /// At least one fact of the row has evidence from another page (a non-NaN score).
    pub evidence: bool,
    /// Per fact, in row order: the chain's most likely value of the fact's key at the row's
    /// date with this page removed (None for the "other" state or no other-page evidence).
    pub best_values: Vec<Option<Canon>>,
    /// Per fact: the chain score (NaN without other-page evidence).
    pub scores: Vec<f64>,
    /// Product of the fact probabilities, before the row map.
    pub p_row: f64,
    /// A fact of the row is on a key over the per-key budget; the router keeps the engine label.
    pub over_budget: bool,
}

/// Lexicon views used by the harness: `truth.alias_map` for subjects and `exp_alias` for names.
pub struct KbLexicon {
    names: HashMap<String, String>,
    alias: HashMap<String, String>,
}

fn name_key(s: &str) -> String {
    s.to_lowercase()
        .chars()
        .filter(|c| !c.is_whitespace())
        .collect()
}

/// Python `str.casefold` for the characters where it differs from lowercase in practice.
fn casefold(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            'ß' | 'ẞ' => out.push_str("ss"),
            'ς' => out.push('σ'),
            'ſ' => out.push('s'),
            'µ' => out.push('μ'),
            _ => out.extend(c.to_lowercase()),
        }
    }
    out
}

impl KbLexicon {
    pub fn new(lexicon: &Value) -> Self {
        let mut names = HashMap::new();
        let mut alias = HashMap::new();
        let empty = Vec::new();
        for s in lexicon["subjects"].as_array().unwrap_or(&empty) {
            let Some(name) = s["name"].as_str() else {
                continue;
            };
            let aliases = s["aliases"].as_array().unwrap_or(&empty);
            for n in std::iter::once(name).chain(aliases.iter().filter_map(Value::as_str)) {
                names.entry(name_key(n)).or_insert_with(|| name.to_owned());
                alias.insert(casefold(n), name.to_owned());
            }
        }
        for e in lexicon["events"].as_array().unwrap_or(&empty) {
            let n = e.as_str().or_else(|| e["name"].as_str());
            if let Some(n) = n {
                if e.is_string() {
                    names.entry(name_key(n)).or_insert_with(|| n.to_owned());
                }
                alias.entry(casefold(n)).or_insert_with(|| n.to_owned());
            }
        }
        Self { names, alias }
    }

    /// `world.py:Fact(a, alias, names)`; None where the harness drops the atom.
    pub fn fact(&self, subject: &Value, attribute: &Value, value: &Value) -> Option<KbFact> {
        let v = value.as_object()?;
        let kind_v = v.get("kind")?;
        let x = v.get("value")?;
        let op = match v.get("op") {
            None => "eq".to_owned(),
            Some(o) if py_falsy(o) => "eq".to_owned(),
            Some(o) => o.as_str()?.to_owned(), // non-string ops fail the dict lookup or never equal "eq"
        };
        let kind = match kind_v.as_str()? {
            "quantity" => Kind::Quantity,
            "money" => Kind::Money,
            "duration" => Kind::Duration,
            "name" => Kind::Name,
            "percent" => Kind::Percent,
            "boolean" => Kind::Boolean,
            "date" => Kind::Date,
            "version" => Kind::Version,
            _ => return None,
        };
        let mut num = None;
        let dim = match kind {
            Kind::Quantity | Kind::Duration => {
                let unit = v.get("unit").unwrap_or(&Value::Null);
                if unit.is_array() || unit.is_object() {
                    return None; // unhashable: `unit in CONV` raises
                }
                match unit.as_str().and_then(conv) {
                    Some((dim, mult, int_mult)) => {
                        num = Some(scaled(x, mult, int_mult)?);
                        format!("s:{dim}")
                    }
                    None => dim_key(unit),
                }
            }
            Kind::Money => format!(
                "{}\u{1f}{}",
                dim_key(v.get("currency").unwrap_or(&Value::Null)),
                dim_key(v.get("per").unwrap_or(&Value::Null))
            ),
            _ => String::new(),
        };
        let subject_text = py_str(subject);
        let subj = self
            .names
            .get(&name_key(&subject_text))
            .cloned()
            .unwrap_or_else(|| subject_text.trim().to_owned());
        let attr = attr_key(&py_str(attribute));
        let (canon, iv) = match kind {
            k if k.numeric() => {
                let x = match num {
                    Some(n) => n,
                    None => py_float(x)?,
                };
                let d = 1e-6 * 1.0f64.max(x.abs());
                let iv = match op.as_str() {
                    "eq" => (x, x),
                    "lt" => (f64::NEG_INFINITY, x - d),
                    "le" => (f64::NEG_INFINITY, x),
                    "gt" => (x + d, f64::INFINITY),
                    "ge" => (x, f64::INFINITY),
                    _ => return None,
                };
                (Canon::Num(round6(x)), Some(iv))
            }
            Kind::Date => {
                let s = x.as_str()?;
                let (lo, hi) = date_interval(s)?;
                (Canon::Str(s.to_owned()), Some((lo as f64, hi as f64)))
            }
            Kind::Name => {
                let c = casefold(&py_str(x));
                (Canon::Str(self.alias.get(&c).cloned().unwrap_or(c)), None)
            }
            Kind::Version => (Canon::Str(casefold(&py_str(x))), None),
            _ => (
                match x {
                    Value::Bool(b) => Canon::Num(f64::from(u8::from(*b))),
                    Value::Number(n) => Canon::Num(n.as_f64()?),
                    Value::String(s) => Canon::Str(s.clone()),
                    Value::Null => Canon::Null,
                    _ => return None, // unhashable in the harness (it would fail, not drop)
                },
                None,
            ),
        };
        Some(KbFact {
            key: (subj, attr, kind, dim),
            kind,
            eq: op == "eq",
            canon,
            iv,
        })
    }

    /// Facts of the pipeline's parsed form; unreadable atoms dropped.
    pub fn model_facts(&self, form: &[crate::Fact]) -> Vec<KbFact> {
        form.iter()
            .filter_map(|f| {
                self.fact(
                    &Value::String(f.subject.clone()),
                    &Value::String(f.attribute.clone()),
                    &f.value,
                )
            })
            .collect()
    }

    /// Facts of a JSON form (array of {subject, attribute, value}); unreadable atoms dropped.
    pub fn facts(&self, form: &Value) -> Vec<KbFact> {
        let empty = Vec::new();
        form.as_array()
            .unwrap_or(&empty)
            .iter()
            .filter_map(|a| {
                let a = a.as_object()?;
                let subject = a
                    .get("subject")
                    .cloned()
                    .unwrap_or(Value::String(String::new()));
                let attribute = a
                    .get("attribute")
                    .cloned()
                    .unwrap_or(Value::String(String::new()));
                self.fact(&subject, &attribute, a.get("value")?)
            })
            .collect()
    }
}

fn py_falsy(v: &Value) -> bool {
    match v {
        Value::Null => true,
        Value::Bool(b) => !b,
        Value::Number(n) => n.as_f64() == Some(0.0),
        Value::String(s) => s.is_empty(),
        Value::Array(a) => a.is_empty(),
        Value::Object(o) => o.is_empty(),
    }
}

/// `world.py:CONV`: (dimension, factor, factor is a Python int).
fn conv(unit: &str) -> Option<(&'static str, f64, bool)> {
    Some(match unit {
        "KB" => ("data", 1e-3, false),
        "MB" => ("data", 1.0, true),
        "GB" => ("data", 1e3, false),
        "TB" => ("data", 1e6, false),
        "ms" => ("time", 1e-3, false),
        "s" => ("time", 1.0, true),
        "min" => ("time", 60.0, true),
        "h" => ("time", 3600.0, true),
        "day" => ("time", 86400.0, true),
        "week" => ("time", 604800.0, true),
        _ => return None,
    })
}

/// `float(x * mult)` for a JSON number or boolean (strings scaled by a non-unit factor are
/// dropped: Python repeats or rejects them).
fn scaled(x: &Value, mult: f64, int_mult: bool) -> Option<f64> {
    match x {
        Value::Bool(b) => Some(f64::from(u8::from(*b)) * mult),
        Value::Number(n) => match (n.as_i64(), int_mult) {
            (Some(i), true) => Some((i128::from(i) * mult as i128) as f64),
            _ => Some(n.as_f64()? * mult),
        },
        Value::String(_) if int_mult && mult == 1.0 => py_float(x),
        _ => None,
    }
}

/// Python `float(x)` for JSON values.
fn py_float(x: &Value) -> Option<f64> {
    match x {
        Value::Bool(b) => Some(f64::from(u8::from(*b))),
        Value::Number(n) => n.as_f64(),
        Value::String(s) => {
            let t = s.trim();
            let lower = t.to_ascii_lowercase();
            let body = lower.trim_start_matches(['+', '-']);
            if matches!(body, "inf" | "infinity" | "nan")
                || (!t.is_empty() && t.bytes().all(|c| b"0123456789+-.eE".contains(&c)))
            {
                t.parse::<f64>().ok()
            } else {
                None
            }
        }
        _ => None,
    }
}

/// Python `round(x, 6)`: correctly rounded, ties to even on the exact binary value.
fn round6(x: f64) -> f64 {
    if !x.is_finite() {
        return x;
    }
    format!("{x:.6}").parse().unwrap_or(x)
}

/// Python `str()` of a JSON value (floats as `repr`).
fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::Null => "None".into(),
        Value::Number(n) => {
            let text = n.to_string();
            if text.bytes().all(|c| c.is_ascii_digit() || c == b'-') {
                text.parse::<i128>().map_or(text, |i| i.to_string())
            } else {
                n.as_f64().map_or(text, py_repr)
            }
        }
        other => other.to_string(),
    }
}

/// Python float `repr`: shortest round-trip digits, scientific outside 1e-4 <= |x| < 1e16.
fn py_repr(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() {
            "-0.0".into()
        } else {
            "0.0".into()
        };
    }
    let e = format!("{:e}", x.abs());
    let (mant, exp) = e.split_once('e').unwrap_or((&e, "0"));
    let exp: i32 = exp.parse().unwrap_or(0);
    let digits: String = mant.chars().filter(char::is_ascii_digit).collect();
    let sign = if x < 0.0 { "-" } else { "" };
    if (-4..16).contains(&exp) {
        let n = digits.len() as i32;
        let body = if exp >= n - 1 {
            format!("{digits}{}.0", "0".repeat((exp - n + 1) as usize))
        } else if exp >= 0 {
            format!(
                "{}.{}",
                &digits[..=exp as usize],
                &digits[exp as usize + 1..]
            )
        } else {
            format!("0.{}{digits}", "0".repeat((-exp - 1) as usize))
        };
        format!("{sign}{body}")
    } else {
        let m = if digits.len() > 1 {
            format!("{}.{}", &digits[..1], &digits[1..])
        } else {
            digits
        };
        format!(
            "{sign}{m}e{}{:02}",
            if exp < 0 { '-' } else { '+' },
            exp.abs()
        )
    }
}

fn dim_key(v: &Value) -> String {
    match v {
        Value::Null => "n:".into(),
        Value::String(s) => format!("s:{s}"),
        other => format!("j:{other}"),
    }
}

fn attr_key(s: &str) -> String {
    let lower = s.trim().to_lowercase();
    let mut out = String::with_capacity(lower.len());
    let mut run = false;
    for c in lower.chars() {
        if c.is_whitespace() || c == '-' {
            if !run {
                out.push('_');
            }
            run = true;
        } else {
            out.push(c);
            run = false;
        }
    }
    out
}

/// Proleptic Gregorian ordinal, 0001-01-01 = 1 (Python `date.toordinal`).
pub fn ordinal(y: i64, m: i64, d: i64) -> Option<i64> {
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let mdays = [
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
    if !(1..=9999).contains(&y) || !(1..=12).contains(&m) || d < 1 || d > mdays[m as usize - 1] {
        return None;
    }
    let y1 = y - 1;
    let before: i64 = mdays[..m as usize - 1].iter().sum();
    Some(y1 * 365 + y1 / 4 - y1 / 100 + y1 / 400 + before + d)
}

/// Ordinal of a `YYYY-MM-DD` row date (first ten characters, as `truth.ordinal`).
pub fn date_ordinal(s: &str) -> Option<i64> {
    let s = s.get(..10)?;
    let mut p = s.split('-');
    let y = p.next()?.parse().ok()?;
    let m = p.next()?.parse().ok()?;
    let d = p.next()?.parse().ok()?;
    ordinal(y, m, d)
}

fn py_int(s: &str) -> Option<i64> {
    let t = s.trim();
    let body = t.strip_prefix(['+', '-']).unwrap_or(t);
    if body.is_empty() || !body.bytes().all(|c| c.is_ascii_digit()) {
        return None;
    }
    t.parse().ok()
}

/// `world.py:date_interval`: partial ISO date -> inclusive ordinal range.
fn date_interval(s: &str) -> Option<(i64, i64)> {
    let p: Vec<&str> = s.split('-').collect();
    match p.len() {
        3 => {
            let b = s.as_bytes();
            if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
                return None;
            }
            let d = date_ordinal(s)?;
            Some((d, d))
        }
        2 => {
            let (y, m) = (py_int(p[0])?, py_int(p[1])?);
            let a = ordinal(y, m, 1)?;
            let b = ordinal(y + i64::from(m == 12), m % 12 + 1, 1)?;
            Some((a, b - 1))
        }
        _ => {
            let y = py_int(p[0])?;
            Some((ordinal(y, 1, 1)?, ordinal(y, 12, 31)?))
        }
    }
}

/// `world.py:pages_of`: maximal runs of consecutive rows with the same date and labelled status
/// (and, for practice, consecutive numeric ids).
pub fn pages_of(dates: &[i64], labelled: &[bool], ids: Option<&[i64]>) -> Vec<usize> {
    let mut page = Vec::with_capacity(dates.len());
    let mut p = 0usize;
    for i in 0..dates.len() {
        let brk = i > 0
            && (dates[i] != dates[i - 1]
                || labelled[i] != labelled[i - 1]
                || ids.is_some_and(|ids| ids[i] != ids[i - 1] + 1));
        p += usize::from(brk);
        page.push(p);
    }
    page
}

// ------------------------------------------------------------------ numpy-order arithmetic

/// numpy `add.reduce` over a contiguous axis (pairwise summation, identity 0).
fn np_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut r = 0.0;
        for &x in a {
            r += x;
        }
        r
    } else if n <= 128 {
        let mut r = [0.0; 8];
        r.copy_from_slice(&a[..8]);
        let mut i = 8;
        while i < n - n % 8 {
            for k in 0..8 {
                r[k] += a[i + k];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        np_sum(&a[..n2]) + np_sum(&a[n2..])
    }
}

fn first_argmax(v: &[f64]) -> usize {
    let mut best = 0;
    for (i, &x) in v.iter().enumerate() {
        if x > v[best] {
            best = i;
        }
    }
    best
}

fn max_of(v: &[f64]) -> f64 {
    v[first_argmax(v)]
}

/// sklearn `IsotonicRegression(out_of_bounds="clip", y_min, y_max)` fitted points.
struct Iso {
    x: Vec<f64>,
    y: Vec<f64>,
}

impl Iso {
    fn fit(xs: &[f64], ys: &[f64], y_min: f64, y_max: f64) -> Self {
        let mut idx: Vec<usize> = (0..xs.len()).collect();
        idx.sort_by(|&a, &b| {
            xs[a]
                .partial_cmp(&xs[b])
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(
                    ys[a]
                        .partial_cmp(&ys[b])
                        .unwrap_or(std::cmp::Ordering::Equal),
                )
        });
        // _make_unique: merge x within np.finfo(float64).resolution of the run's first x
        let eps = 1e-15;
        let (mut ux, mut uy, mut uw) = (Vec::new(), Vec::new(), Vec::new());
        let mut cx = xs[idx[0]];
        let (mut cy, mut cw) = (0.0, 0.0);
        for &j in &idx {
            let x = xs[j];
            if x - cx >= eps {
                ux.push(cx);
                uw.push(cw);
                uy.push(cy / cw);
                cx = x;
                cw = 1.0;
                cy = ys[j];
            } else {
                cw += 1.0;
                cy += ys[j];
            }
        }
        ux.push(cx);
        uw.push(cw);
        uy.push(cy / cw);
        let mut y = pava(uy, uw);
        for v in &mut y {
            *v = v.clamp(y_min, y_max);
        }
        // trim points equal to both neighbours (no effect on the interpolant)
        let n = y.len();
        let keep: Vec<bool> = (0..n)
            .map(|i| i == 0 || i == n - 1 || y[i] != y[i - 1] || y[i] != y[i + 1])
            .collect();
        let x = ux
            .iter()
            .zip(&keep)
            .filter(|p| *p.1)
            .map(|p| *p.0)
            .collect();
        let y = y.iter().zip(&keep).filter(|p| *p.1).map(|p| *p.0).collect();
        Self { x, y }
    }

    /// clip to [X_min, X_max], then `np.interp` (or the constant of a one-point fit).
    fn predict(&self, t: f64) -> f64 {
        let (x, y) = (&self.x, &self.y);
        let n = x.len();
        if n == 1 {
            return y[0];
        }
        let t = t.clamp(x[0], x[n - 1]);
        let j = x.partition_point(|&v| v <= t).saturating_sub(1);
        if j >= n - 1 {
            return y[n - 1];
        }
        if x[j] == t {
            return y[j];
        }
        let slope = (y[j + 1] - y[j]) / (x[j + 1] - x[j]);
        slope * (t - x[j]) + y[j]
    }
}

/// scipy `optimize.isotonic_regression` (Busing 2022 PAVA, increasing), same operation order.
fn pava(mut x: Vec<f64>, mut w: Vec<f64>) -> Vec<f64> {
    let n = x.len();
    let mut r = vec![0usize; n + 1];
    r[0] = 0;
    if n > 0 {
        r[1] = 1;
    }
    let mut b = 0usize;
    let mut xb_prev = x[0];
    let mut wb_prev = w[0];
    let mut i = 1;
    while i < n {
        b += 1;
        let mut xb = x[i];
        let mut wb = w[i];
        if xb_prev >= xb {
            b -= 1;
            let mut sb = wb_prev * xb_prev + wb * xb;
            wb += wb_prev;
            xb = sb / wb;
            while i < n - 1 && xb >= x[i + 1] {
                i += 1;
                sb += w[i] * x[i];
                wb += w[i];
                xb = sb / wb;
            }
            while b > 0 && x[b - 1] >= xb {
                b -= 1;
                sb += w[b] * x[b];
                wb += w[b];
                xb = sb / wb;
            }
        }
        x[b] = xb;
        xb_prev = xb;
        w[b] = wb;
        wb_prev = wb;
        r[b + 1] = i + 1;
        i += 1;
    }
    let mut f = n as isize - 1;
    for k in (0..=b).rev() {
        let t = r[k] as isize;
        let xk = x[k];
        let mut i = f;
        while i >= t {
            x[i as usize] = xk;
            i -= 1;
        }
        f = t - 1;
    }
    x
}

// ------------------------------------------------------------------ per-key structure

#[derive(Clone, Copy, PartialEq, Eq)]
enum Role {
    Anchor,
    FalseSingle,
    FalseMulti,
    Vote,
}

struct Key<'a> {
    g: Vec<usize>,
    date: Vec<i64>,
    page: Vec<usize>,
    role: Vec<Role>,
    eq: Vec<bool>,
    facts: Vec<&'a KbFact>,
    kind: Kind,
    rep: Vec<usize>,
    s: usize,
    ag: Vec<Vec<f64>>, // S x n
    times: Vec<i64>,
    tix: Vec<usize>,
    order: Option<Vec<f64>>,
    votes: bool,
}

fn consistent(a: &KbFact, b: &KbFact) -> bool {
    match (a.iv, b.iv) {
        (Some((alo, ahi)), Some((blo, bhi))) => {
            let tol = 1e-9 * 1.0f64.max(if alo.is_infinite() { 1.0 } else { alo.abs() });
            let lo = if alo.is_nan() || blo.is_nan() {
                f64::NAN
            } else {
                alo.max(blo)
            };
            let hi = if ahi.is_nan() || bhi.is_nan() {
                f64::NAN
            } else {
                ahi.min(bhi)
            };
            lo <= hi + tol
        }
        _ => a.canon == b.canon,
    }
}

fn version_parts(v: &Canon) -> Vec<(usize, String)> {
    let Canon::Str(s) = v else { return Vec::new() };
    let mut out = Vec::new();
    let mut cur = String::new();
    for c in s.chars().chain(std::iter::once(' ')) {
        if c.is_ascii_digit() {
            cur.push(c);
        } else if !cur.is_empty() {
            let t = cur.trim_start_matches('0');
            let t = if t.is_empty() { "0" } else { t };
            out.push((t.len(), t.to_owned()));
            cur.clear();
        }
    }
    out.truncate(4);
    out
}

impl<'a> Key<'a> {
    fn new(
        g: Vec<usize>,
        flat: &[&'a KbFact],
        frow: &[usize],
        rows: &[ChainRow],
        nf: &[usize],
        votes: bool,
    ) -> Self {
        let n = g.len();
        let facts: Vec<&KbFact> = g.iter().map(|&x| flat[x]).collect();
        let row: Vec<usize> = g.iter().map(|&x| frow[x]).collect();
        let date: Vec<i64> = row.iter().map(|&r| rows[r].date).collect();
        let page: Vec<usize> = row.iter().map(|&r| rows[r].page).collect();
        let role = row
            .iter()
            .map(|&r| match rows[r].label {
                Some(Label::True) => Role::Anchor,
                Some(Label::False) if nf[r] == 1 => Role::FalseSingle,
                Some(Label::False) => Role::FalseMulti,
                _ => Role::Vote,
            })
            .collect();
        let eq: Vec<bool> = facts.iter().map(|f| f.eq).collect();
        let mut rep: Vec<usize> = Vec::new();
        for (b, f) in facts.iter().enumerate() {
            if f.eq && !rep.iter().any(|&r| facts[r].canon == f.canon) {
                rep.push(b);
            }
        }
        let s = rep.len() + 1;
        let mut ag = vec![vec![0.0; n]; s];
        for (si, &r) in rep.iter().enumerate() {
            for b in 0..n {
                ag[si][b] = if consistent(facts[r], facts[b]) {
                    1.0
                } else {
                    0.0
                };
            }
        }
        for (x, &e) in ag[s - 1].iter_mut().zip(&eq) {
            *x = if e { 0.0 } else { 0.5 };
        }
        let mut times = date.clone();
        times.sort_unstable();
        times.dedup();
        let tix = date
            .iter()
            .map(|d| times.binary_search(d).unwrap_or(0))
            .collect();
        let kind = facts[0].kind;
        let vals: Vec<&Canon> = rep.iter().map(|&r| &facts[r].canon).collect();
        let order = if kind.numeric() {
            Some(
                vals.iter()
                    .map(|v| if let Canon::Num(x) = v { *x } else { f64::NAN })
                    .collect(),
            )
        } else if kind == Kind::Date && !rep.is_empty() {
            Some(
                rep.iter()
                    .map(|&r| facts[r].iv.map_or(f64::NAN, |iv| iv.0))
                    .collect(),
            )
        } else if kind == Kind::Version && !rep.is_empty() {
            let parts: Vec<_> = vals.iter().map(|v| version_parts(v)).collect();
            if parts.iter().all(|p| !p.is_empty()) {
                let mut uniq = parts.clone();
                uniq.sort();
                uniq.dedup();
                Some(
                    parts
                        .iter()
                        .map(|p| uniq.binary_search(p).unwrap_or(0) as f64)
                        .collect(),
                )
            } else {
                None
            }
        } else {
            None
        };
        Key {
            g,
            date,
            page,
            role,
            eq,
            facts,
            kind,
            rep,
            s,
            ag,
            times,
            tix,
            order,
            votes,
        }
    }

    fn loglik(&self) -> Vec<Vec<f64>> {
        let (ea, ef, r) = (EPS_A, EPS_F, VOTE_LR);
        let mut seen = HashSet::new();
        let vote_on: Vec<_> = self
            .facts
            .iter()
            .enumerate()
            .map(|(b, fact)| {
                self.votes
                    || seen.insert((
                        self.date[b],
                        format!("{:?}", fact.canon),
                        fact.eq,
                        fact.iv.map(|(a, b)| (a.to_bits(), b.to_bits())),
                    ))
            })
            .collect();
        let mut out = vec![vec![0.0; self.g.len()]; self.s];
        for (si, row) in out.iter_mut().enumerate() {
            for (b, o) in row.iter_mut().enumerate() {
                let a = self.ag[si][b];
                *o = match self.role[b] {
                    Role::Anchor => (ea + (1.0 - ea) * a).ln(),
                    Role::FalseSingle => (1.0 - (1.0 - ef) * a).ln(),
                    Role::FalseMulti => 0.0,
                    Role::Vote if vote_on[b] => (1.0 - (1.0 - 1.0 / r) * (1.0 - a)).ln(),
                    Role::Vote => 0.0,
                };
            }
        }
        out
    }

    fn switch_log(&self, d: f64) -> Vec<Vec<f64>> {
        let s = self.s;
        if s == 1 {
            return vec![vec![0.0]];
        }
        let mut w = vec![vec![1.0; s]; s];
        for row in &mut w {
            row[s - 1] = PI_O;
        }
        if let Some(v) = &self.order
            && d != 1.0
            && s > 2
        {
            for i in 0..s - 1 {
                for j in 0..s - 1 {
                    w[i][j] = if v[j] < v[i] { d } else { 1.0 };
                }
            }
        }
        for (i, row) in w.iter_mut().enumerate() {
            row[i] = 0.0;
            let tot = np_sum(row);
            for x in row.iter_mut() {
                *x = (*x / tot).ln();
            }
        }
        w
    }

    /// Viterbi max-marginals at each (page, time) without that page's observations.
    fn scores(&self, lam: f64, d: f64) -> (Vec<f64>, Vec<Option<usize>>) {
        let n = self.g.len();
        let (s, t_n) = (self.s, self.times.len());
        let ll = self.loglik();
        let wlog = self.switch_log(d);
        let mut log_stay = Vec::with_capacity(t_n.saturating_sub(1));
        let mut log_sw = Vec::with_capacity(t_n.saturating_sub(1));
        for w in self.times.windows(2) {
            let stay = (-lam * (w[1] - w[0]) as f64).exp();
            log_stay.push(stay.ln());
            log_sw.push((1.0 - stay).clamp(1e-300, 1.0).ln());
        }
        let mut log_e = vec![vec![0.0; s]; t_n];
        for b in 0..n {
            for (e, l) in log_e[self.tix[b]].iter_mut().zip(&ll) {
                *e += l[b];
            }
        }
        let mut pred = vec![vec![0.0; s]; t_n];
        let mut a = vec![0.0; s];
        let mut col = vec![0.0; s];
        for t in 0..t_n {
            pred[t].clone_from(&a);
            if t + 1 < t_n {
                let dd: Vec<f64> = (0..s).map(|i| a[i] + log_e[t][i]).collect();
                for (j, aj) in a.iter_mut().enumerate() {
                    for i in 0..s {
                        col[i] = if i == j {
                            dd[i] + log_stay[t]
                        } else {
                            dd[i] + log_sw[t] + wlog[i][j]
                        };
                    }
                    *aj = max_of(&col);
                }
                let m = max_of(&a);
                for x in &mut a {
                    *x -= m;
                }
            }
        }
        let mut back = vec![vec![0.0; s]; t_n];
        let mut row = vec![0.0; s];
        for t in (0..t_n.saturating_sub(1)).rev() {
            let v: Vec<f64> = (0..s).map(|j| log_e[t + 1][j] + back[t + 1][j]).collect();
            let mut bvec = vec![0.0; s];
            for i in 0..s {
                for j in 0..s {
                    row[j] = if i == j {
                        v[j] + log_stay[t]
                    } else {
                        v[j] + log_sw[t] + wlog[i][j]
                    };
                }
                bvec[i] = max_of(&row);
            }
            let m = max_of(&bvec);
            back[t] = bvec.iter().map(|x| x - m).collect();
        }
        let mut local: HashMap<(usize, usize), Vec<f64>> = HashMap::new();
        for b in 0..n {
            let e = local
                .entry((self.page[b], self.tix[b]))
                .or_insert_with(|| vec![0.0; s]);
            for si in 0..s {
                e[si] += ll[si][b];
            }
        }
        let mut mm_of: HashMap<(usize, usize), Vec<f64>> = HashMap::new();
        let mut score = Vec::with_capacity(n);
        let mut best = Vec::with_capacity(n);
        for b in 0..n {
            let key = (self.page[b], self.tix[b]);
            let t = self.tix[b];
            let mm = mm_of.entry(key).or_insert_with(|| {
                let loc = &local[&key];
                (0..s)
                    .map(|i| pred[t][i] + log_e[t][i] - loc[i] + back[t][i])
                    .collect()
            });
            let (mut ag_max, mut dis_max) = (None::<f64>, None::<f64>);
            for (si, &m) in mm.iter().enumerate() {
                let x = self.ag[si][b];
                if x > 0.5 {
                    ag_max = Some(ag_max.map_or(m, |c| if m > c { m } else { c }));
                } else if x < 0.5 {
                    dis_max = Some(dis_max.map_or(m, |c| if m > c { m } else { c }));
                }
            }
            score.push((ag_max.unwrap_or(-1e9) - dis_max.unwrap_or(-1e9)).clamp(-60.0, 60.0));
            let top = first_argmax(mm);
            best.push((top < s - 1).then_some(top));
        }
        (score, best)
    }
}

/// (S, n, T) of a key, or None when S exceeds [`MAX_KEY_STATES`] (counted with an early exit).
fn key_size(
    g: &[usize],
    flat: &[&KbFact],
    frow: &[usize],
    rows: &[ChainRow],
) -> Option<(usize, usize, usize)> {
    let mut vals: Vec<&Canon> = Vec::new();
    for f in g.iter().map(|&x| flat[x]).filter(|f| f.eq) {
        if !vals.contains(&&f.canon) {
            vals.push(&f.canon);
            if vals.len() >= MAX_KEY_STATES {
                return None;
            }
        }
    }
    let mut times: Vec<i64> = g.iter().map(|&x| rows[frow[x]].date).collect();
    times.sort_unstable();
    times.dedup();
    Some((vals.len() + 1, g.len(), times.len()))
}

/// Which keys are scored: within the per-key caps and, cheapest first, within the world budgets.
/// Returns the flags and the admitted sums of S*n and T*S^2.
fn admit(sizes: &[Option<(usize, usize, usize)>]) -> (Vec<bool>, usize, usize) {
    let cost = |(s, n, t): (usize, usize, usize)| (t * s * s, s * n);
    let mut order: Vec<usize> = (0..sizes.len())
        .filter(|&k| {
            sizes[k]
                .is_some_and(|(s, n, t)| s * (n + t) <= MAX_KEY_CELLS && t * s * s <= MAX_KEY_STEPS)
        })
        .collect();
    order.sort_by_key(|&k| sizes[k].map(cost));
    let mut ok = vec![false; sizes.len()];
    let (mut cells, mut steps) = (0, 0);
    for k in order {
        let (st, c) = sizes[k].map(cost).unwrap_or_default();
        if cells + c <= WORLD_CELLS && steps + st <= WORLD_STEPS {
            ok[k] = true;
            cells += c;
            steps += st;
        }
    }
    (ok, cells, steps)
}

// ------------------------------------------------------------------ hazard

fn lam_grid() -> Vec<f64> {
    let (start, stop) = (1e-4f64.ln(), 0.2f64.ln());
    let step = (stop - start) / 159.0;
    (0..160)
        .map(|i| {
            if i == 159 {
                stop.exp()
            } else {
                (i as f64 * step + start).exp()
            }
        })
        .collect()
}

fn mle_lambda(gaps: &[f64], same: &[bool], prior_lam: f64, prior_n: f64, grid: &[f64]) -> f64 {
    let g0 = 1.0 / prior_lam;
    let mut best = (f64::NAN, f64::NEG_INFINITY);
    let mut terms = vec![0.0; gaps.len()];
    for &lam in grid {
        for (k, (&g, &s)) in gaps.iter().zip(same).enumerate() {
            terms[k] = if s {
                -lam * g
            } else {
                (1.0 - (-lam * g).exp()).clamp(1e-12, 1.0).ln()
            };
        }
        let q0 = (-lam * g0).exp();
        let ll = np_sum(&terms)
            + (prior_n * 0.5 * (-lam * g0) + prior_n * 0.5 * (1.0 - q0).max(1e-12).ln());
        if ll > best.1 {
            best = (lam, ll);
        }
    }
    best.0
}

struct Hazard {
    glob: f64,
    by_kind: HashMap<Kind, f64>,
    down: HashMap<Kind, f64>,
}

impl Hazard {
    fn fit(keys: &[Key]) -> Self {
        let mut pairs: Vec<(f64, bool, Kind, Option<bool>)> = Vec::new();
        for k in keys {
            let a: Vec<usize> = (0..k.g.len())
                .filter(|&b| k.role[b] == Role::Anchor && k.eq[b])
                .collect();
            if a.len() < 2 {
                continue;
            }
            let mut last: Option<usize> = None;
            for &b in &a {
                if let Some(l) = last
                    && k.date[b] > k.date[l]
                {
                    let same = consistent(k.facts[b], k.facts[l]);
                    let mut up = None;
                    if !same && let Some(order) = &k.order {
                        let col =
                            |x: usize| -> Vec<f64> { (0..k.s - 1).map(|si| k.ag[si][x]).collect() };
                        let (sb, sl) = (first_argmax(&col(b)), first_argmax(&col(l)));
                        if order[sb] != order[sl] {
                            up = Some(order[sb] > order[sl]);
                        }
                    }
                    pairs.push(((k.date[b] - k.date[l]) as f64, same, k.kind, up));
                }
                if last.is_none_or(|l| k.date[b] > k.date[l]) {
                    last = Some(b);
                }
            }
        }
        let mut hz = Hazard {
            glob: 1.0 / 200.0,
            by_kind: HashMap::new(),
            down: HashMap::new(),
        };
        if pairs.is_empty() {
            return hz;
        }
        let grid = lam_grid();
        let gaps: Vec<f64> = pairs.iter().map(|p| p.0).collect();
        let same: Vec<bool> = pairs.iter().map(|p| p.1).collect();
        hz.glob = mle_lambda(&gaps, &same, 1.0 / 200.0, 2.0, &grid);
        let mut kinds: Vec<Kind> = Vec::new();
        for p in &pairs {
            if !kinds.contains(&p.2) {
                kinds.push(p.2);
            }
        }
        for kind in kinds {
            let ps: Vec<_> = pairs.iter().filter(|p| p.2 == kind).collect();
            let ups = ps.iter().filter(|p| p.3 == Some(true)).count() as f64;
            let dns = ps.iter().filter(|p| p.3 == Some(false)).count() as f64;
            let pd = (dns + MONO_A * D0 / (1.0 + D0)) / (ups + dns + MONO_A);
            hz.down.insert(kind, (pd / (1.0 - pd)).clamp(0.01, 1.0));
            if ps.len() >= MIN_PAIRS {
                let g: Vec<f64> = ps.iter().map(|p| p.0).collect();
                let s: Vec<bool> = ps.iter().map(|p| p.1).collect();
                hz.by_kind
                    .insert(kind, mle_lambda(&g, &s, hz.glob, 4.0, &grid));
            }
        }
        hz
    }
}

// ------------------------------------------------------------------ fit and decide

/// Per-fact chain scores of one world (rows in input order).
struct Scored {
    nf: Vec<usize>,
    fstart: Vec<usize>,
    frow: Vec<usize>,
    score: Vec<f64>,
    best: Vec<Option<Canon>>,
    /// Rows with a fact on a key over the budget (see [`MAX_KEY_STATES`]).
    skipped: Vec<bool>,
    max_states: usize,
    /// Sums of S*n and T*S^2 over the scored keys.
    cells: usize,
    steps: usize,
}

/// Scores every fact; fits the hazard on this world's anchors when `hz` is None.
fn score_world(rows: &[ChainRow], hz: Option<&Hazard>) -> (Scored, Option<Hazard>) {
    score_world_with_votes(rows, hz, true)
}

fn score_world_with_votes(
    rows: &[ChainRow],
    hz: Option<&Hazard>,
    votes: bool,
) -> (Scored, Option<Hazard>) {
    let nf: Vec<usize> = rows.iter().map(|r| r.facts.len()).collect();
    let mut flat: Vec<&KbFact> = Vec::new();
    let mut frow = Vec::new();
    let mut fstart = Vec::with_capacity(rows.len());
    for (i, r) in rows.iter().enumerate() {
        fstart.push(flat.len());
        for f in &r.facts {
            flat.push(f);
            frow.push(i);
        }
    }
    let mut order: Vec<usize> = (0..rows.len()).collect();
    order.sort_by_key(|&i| rows[i].date);
    let mut key_ix: HashMap<&(String, String, Kind, String), usize> = HashMap::new();
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for &i in &order {
        for (j, f) in rows[i].facts.iter().enumerate() {
            let k = *key_ix.entry(&f.key).or_insert_with(|| {
                groups.push(Vec::new());
                groups.len() - 1
            });
            groups[k].push(fstart[i] + j);
        }
    }
    let sizes: Vec<_> = groups
        .iter()
        .map(|g| key_size(g, &flat, &frow, rows))
        .collect();
    let (ok, cells, steps) = admit(&sizes);
    let mut keys: Vec<Key> = Vec::new();
    let mut skipped = vec![false; rows.len()];
    for (g, ok) in groups.into_iter().zip(ok) {
        if ok {
            keys.push(Key::new(g, &flat, &frow, rows, &nf, votes));
        } else {
            g.iter().for_each(|&x| skipped[frow[x]] = true);
        }
    }
    let max_states = keys.iter().map(|k| k.s).max().unwrap_or(0);
    let fitted = hz.is_none().then(|| Hazard::fit(&keys));
    let hz = hz.or(fitted.as_ref()).expect("hazard");
    let mut score = vec![f64::NAN; flat.len()];
    let mut best: Vec<Option<Canon>> = vec![None; flat.len()];
    for k in &keys {
        let mut pages = k.page.clone();
        pages.sort_unstable();
        pages.dedup();
        if pages.len() < 2 {
            continue;
        }
        let lam = *hz.by_kind.get(&k.kind).unwrap_or(&hz.glob);
        let d = *hz.down.get(&k.kind).unwrap_or(&1.0);
        let (sc, bs) = k.scores(lam, d);
        for (b, &x) in k.g.iter().enumerate() {
            score[x] = sc[b];
            best[x] = bs[b].map(|si| k.facts[k.rep[si]].canon.clone());
        }
    }
    let scored = Scored {
        nf,
        fstart,
        frow,
        score,
        best,
        skipped,
        max_states,
        cells,
        steps,
    };
    (scored, fitted)
}

/// Everything `Std.fit` learns: hazard, fact map, row map, unsure share, true share.
struct Model {
    hz: Hazard,
    fmap: Option<Iso>,
    base: f64,
    nan_p: f64,
    rmap: Option<Iso>,
    u: f64,
    rate: f64,
}

impl Model {
    fn pf(&self, s: &Scored) -> Vec<f64> {
        s.score
            .iter()
            .map(|&x| {
                let p = if x.is_nan() {
                    self.nan_p
                } else {
                    self.fmap.as_ref().map_or(self.base, |m| m.predict(x))
                };
                p.clamp(1e-4, 1.0 - 1e-4)
            })
            .collect()
    }

    fn fit(rows: &[ChainRow]) -> (Self, Scored) {
        Self::fit_with_votes(rows, true)
    }

    fn fit_with_votes(rows: &[ChainRow], votes: bool) -> (Self, Scored) {
        let (s, hz) = score_world_with_votes(rows, None, votes);
        let (nf, score) = (&s.nf, &s.score);
        let y: Vec<i8> = s
            .frow
            .iter()
            .map(|&r| match rows[r].label {
                Some(Label::True) => 1,
                Some(Label::False) if nf[r] == 1 => 0,
                _ => -1,
            })
            .collect();
        let labelled: Vec<usize> = (0..y.len()).filter(|&n| y[n] >= 0).collect();
        let base = if labelled.is_empty() {
            0.85
        } else {
            labelled.iter().map(|&n| f64::from(y[n])).sum::<f64>() / labelled.len() as f64
        };
        let nan: Vec<usize> = labelled
            .iter()
            .copied()
            .filter(|&n| score[n].is_nan())
            .collect();
        let nan_p = (nan.iter().map(|&n| f64::from(y[n])).sum::<f64>() + 4.0 * base.max(0.9))
            / (nan.len() as f64 + 4.0);
        let ok: Vec<usize> = labelled
            .iter()
            .copied()
            .filter(|&n| !score[n].is_nan())
            .collect();
        let classes = ok.iter().any(|&n| y[n] == 1) && ok.iter().any(|&n| y[n] == 0);
        let fmap = (ok.len() >= 5 && classes).then(|| {
            let xs: Vec<f64> = ok.iter().map(|&n| score[n]).collect();
            let ys: Vec<f64> = ok.iter().map(|&n| f64::from(y[n])).collect();
            Iso::fit(&xs, &ys, 0.005, 0.995)
        });
        let mut model = Model {
            hz: hz.expect("fitted"),
            fmap,
            base,
            nan_p,
            rmap: None,
            u: 0.0,
            rate: 0.0,
        };
        let prow = row_prob(&s, &model.pf(&s), rows.len());
        let tr: Vec<usize> = (0..rows.len())
            .filter(|&i| rows[i].label.is_some() && nf[i] > 0)
            .collect();
        if !tr.is_empty() {
            let unsure = tr
                .iter()
                .filter(|&&i| rows[i].label == Some(Label::Unsure))
                .count();
            model.u = unsure as f64 / tr.len() as f64;
        }
        let m: Vec<usize> = tr
            .iter()
            .copied()
            .filter(|&i| rows[i].label != Some(Label::Unsure))
            .collect();
        let ym: Vec<f64> = m
            .iter()
            .map(|&i| f64::from(u8::from(rows[i].label == Some(Label::True))))
            .collect();
        let pos = ym.iter().filter(|&&v| v == 1.0).count();
        model.rmap = (m.len() >= 5 && pos > 0 && pos < m.len()).then(|| {
            let xs: Vec<f64> = m.iter().map(|&i| prow[i]).collect();
            Iso::fit(&xs, &ym, 0.0, 1.0)
        });
        let lab: Vec<&ChainRow> = rows.iter().filter(|r| r.label.is_some()).collect();
        let trues = lab.iter().filter(|r| r.label == Some(Label::True)).count();
        model.rate = trues as f64 / lab.len().max(1) as f64;
        (model, s)
    }

    fn predict(&self, rows: &[ChainRow], s: &Scored) -> Vec<ChainOutput> {
        let prow = row_prob(s, &self.pf(s), rows.len());
        let band = ((1.0 + self.u) / (2.0 * (1.0 - self.u)) - 0.5).max(0.0);
        let q = 1.0 - self.u;
        (0..rows.len())
            .map(|i| {
                let pc = self.rmap.as_ref().map_or(prow[i], |m| m.predict(prow[i]));
                let mut label = if pc >= 0.5 { Label::True } else { Label::False };
                if (pc - 0.5).abs() < band || s.nf[i] == 0 {
                    label = Label::Unsure;
                }
                let raw = q * if label == Label::True { pc } else { 1.0 - pc };
                let facts = s.fstart[i]..s.fstart[i] + s.nf[i];
                ChainOutput {
                    label,
                    confidence: (label != Label::Unsure).then(|| raw.max(0.5)),
                    p_true: pc,
                    evidence: facts.clone().any(|n| !s.score[n].is_nan()),
                    best_values: facts.clone().map(|n| s.best[n].clone()).collect(),
                    scores: facts.map(|n| s.score[n]).collect(),
                    p_row: prow[i],
                    over_budget: s.skipped[i],
                }
            })
            .collect()
    }
}

fn row_prob(s: &Scored, pf: &[f64], n: usize) -> Vec<f64> {
    let mut prow = vec![1.0; n];
    for (k, &r) in s.frow.iter().enumerate() {
        prow[r] *= pf[k];
    }
    prow
}

fn two_class(rows: &[ChainRow]) -> bool {
    let has = |l| rows.iter().any(|r| r.label == Some(l));
    has(Label::True) && has(Label::False)
}

/// Chain labels for every row plus the true share of the labelled rows the model was fitted on.
pub struct ChainRun {
    pub rows: Vec<ChainOutput>,
    pub rate: f64,
    /// Largest state count S among the keys scored on `rows` (budget: [`MAX_KEY_STATES`]).
    pub max_states: usize,
    /// Sum of S*n over the scored keys (budget: [`WORLD_CELLS`]).
    pub cells: usize,
    /// Sum of T*S^2 over the scored keys (budget: [`WORLD_STEPS`]).
    pub steps: usize,
}

/// `Std.run`: fit on the labelled rows and label every row. When the labelled rows do not hold
/// both true and false, the model is fitted on `fallback` (practice, every row labelled) and
/// applied to `rows`, as `Std.fit` does. None when neither is two-class.
pub fn run(rows: &[ChainRow], fallback: Option<&[ChainRow]>) -> Option<ChainRun> {
    if two_class(rows) {
        let (model, s) = Model::fit(rows);
        return Some(ChainRun {
            rows: model.predict(rows, &s),
            rate: model.rate,
            max_states: s.max_states,
            cells: s.cells,
            steps: s.steps,
        });
    }
    let fallback = fallback.filter(|f| two_class(f))?;
    let (model, _) = Model::fit(fallback);
    let (s, _) = score_world(rows, Some(&model.hz));
    Some(ChainRun {
        rows: model.predict(rows, &s),
        rate: model.rate,
        max_states: s.max_states,
        cells: s.cells,
        steps: s.steps,
    })
}

/// Confidence scale of the shipped labeller: accuracy over mean confidence of the guarded
/// chain's decided rows, fitted once on practice P80 (T2 SPEC-G1, `rfac.json`). Constant by
/// design: the hidden rows of a competition run have no labels to refit it.
pub const CONF_SCALE: f64 = 0.972343066499685;

/// The shipped labeller (T2 SPEC-G1): the chain, then G1 (an unlabelled row with no parsed
/// fact is true with confidence max(0.5, rate)), then every decided confidence scaled by
/// [`CONF_SCALE`] and clipped to [0.5, 1]. Labelled rows keep the chain's output. A row with
/// a fact on a key over the per-key budget is None: the caller keeps its own label.
pub fn guarded(rows: &[ChainRow], fallback: Option<&[ChainRow]>) -> Option<Labels> {
    Some(guard(rows, run(rows, fallback)?))
}

fn guard(rows: &[ChainRow], run: ChainRun) -> Labels {
    rows.iter()
        .zip(run.rows)
        .map(|(row, out)| {
            let (label, conf) = if out.over_budget {
                return None;
            } else if row.label.is_none() && row.facts.is_empty() {
                (Label::True, Some(run.rate.max(0.5)))
            } else {
                (out.label, out.confidence)
            };
            Some((label, conf.map(|c| (c * CONF_SCALE).clamp(0.5, 1.0))))
        })
        .collect()
}

/// Router rule NOEVID: an unlabelled row with facts none of which has evidence from another page
/// (every chain score NaN) becomes unsure instead of taking the smoothed no-evidence rate.
/// One-line switch, off: measured on P390 it only hit gold-true rows (-0.041 points). The router
/// path only, `run` and `guarded` are unaffected.
pub const NOEVID_UNSURE: bool = false;

/// Per row: the guarded label and confidence, or None to keep the caller's label.
pub type Labels = Vec<Option<(Label, Option<f64>)>>;

/// Rows of a labelled practice file in id order with `pages_of` pages (consecutive numeric ids),
/// as `world.py:_practice` builds the transfer world.
pub fn practice_rows(practice: &[crate::InputRow], lex: &KbLexicon) -> Vec<ChainRow> {
    let num = |id: &str| id.rsplit('-').next().and_then(|n| n.parse::<i64>().ok());
    let mut sorted: Vec<&crate::InputRow> = practice.iter().collect();
    if sorted.iter().all(|r| num(&r.id).is_some()) {
        sorted.sort_by_key(|r| num(&r.id));
    }
    let ids: Option<Vec<i64>> = sorted.iter().map(|r| num(&r.id)).collect();
    universe_rows(&sorted, ids.as_deref(), |r| lex.model_facts(&r.form))
}

fn universe_rows<F>(rows: &[&crate::InputRow], ids: Option<&[i64]>, facts: F) -> Vec<ChainRow>
where
    F: Fn(&crate::InputRow) -> Vec<KbFact>,
{
    let dates: Vec<i64> = rows
        .iter()
        .map(|r| date_ordinal(&r.date).unwrap_or(0))
        .collect();
    let labels: Vec<Option<Label>> = rows.iter().map(|r| Label::parse(&r.label)).collect();
    let labelled: Vec<bool> = labels.iter().map(Option::is_some).collect();
    let page = pages_of(&dates, &labelled, ids);
    rows.iter()
        .enumerate()
        .map(|(i, r)| ChainRow {
            date: dates[i],
            page: page[i],
            label: labels[i],
            facts: facts(r),
        })
        .collect()
}

/// Which labeller the pipeline router chose, and why.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Routed {
    /// Rows protected by exact evidence, logical programs or parser guards keep
    /// the engine's prediction. Other rows receive statistical scores or abstain.
    Chain {
        relabelled: usize,
        kept: usize,
        /// FOREIGN rows set to unsure (counted apart from `relabelled`).
        foreign: usize,
        /// Largest key state count and the world sums of S*n and T*S^2 of the scored keys.
        load: (usize, usize, usize),
    },
    /// The engine's labels are kept untouched; the reason is for the log.
    Engine(String),
}

impl std::fmt::Display for Routed {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Chain {
                relabelled,
                kept,
                foreign,
                load: (states, cells, steps),
            } => write!(
                f,
                "KB temporal chain (canonical practice seed present, labelled rows hold true and false); relabelled {relabelled} rows, {foreign} unresolved-name rows unsure, kept {kept} engine rows (exact evidence, logical program, parser guard or over-budget key); max key states {states}, cells {cells}, steps {steps}; scores are not calibrated three-class probabilities"
            ),
            Self::Engine(why) => write!(f, "evidence engine ({why})"),
        }
    }
}

/// Production router, enabled by `VERIDYCT_KB_CHAIN=1`. The canonical-seed and
/// two-class gates and all-or-nothing validation remain in place. Reference
/// [`run`] / [`guarded`] semantics, including G1, are preserved for parity only.
/// Production never uses G1 to assert an empty extraction. Labelled typed proofs,
/// conflicts, logical programs and unresolved clauses take priority over scores.
/// Historical continuity is an estimate, never an inferred validity interval.
pub fn relabel(
    rows: &[crate::InputRow],
    predictions: &mut [crate::Prediction],
    lexicon: &Value,
    hints: &crate::ExtractionHints,
    canonical_seed: bool,
    practice_match: &dyn Fn(&crate::InputRow) -> bool,
) -> Routed {
    let mut load = (0, 0, 0);
    let routed = relabel_with(
        rows,
        predictions,
        lexicon,
        Keep {
            hints,
            practice_match,
        },
        canonical_seed,
        |r| {
            let run = router_run(r)?;
            load = (run.max_states, run.cells, run.steps);
            Some(guard(r, run))
        },
    );
    match routed {
        Routed::Chain {
            relabelled,
            kept,
            foreign,
            ..
        } => Routed::Chain {
            relabelled,
            kept,
            foreign,
            load,
        },
        engine => engine,
    }
}

/// Production caps repeated predicates to one statistical vote per key/date.
/// Votes are model inputs, never authoritative typed evidence. Reference F2
/// retains every vote for parity. The page guard excludes same-date copies.
fn router_run(rows: &[ChainRow]) -> Option<ChainRun> {
    if !two_class(rows) {
        return None;
    }
    let (model, scored) = Model::fit_with_votes(rows, false);
    Some(ChainRun {
        rows: model.predict(rows, &scored),
        rate: model.rate,
        max_states: scored.max_states,
        cells: scored.cells,
        steps: scored.steps,
    })
}

fn router_text(text: &str) -> String {
    casefold(&text.nfkc().collect::<String>())
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// Conservative unresolved-name signal, not an entity recognizer or a proof of
/// the dataset's unsure label. Vocabulary comes only from schema names and
/// labelled text. A known-name distractor cannot license a different owner.
/// NFKC normalization and Unicode letters avoid the old ASCII-only mismatch.
struct Foreign {
    caps: HashSet<String>,
    low: HashSet<String>,
}

fn words(t: &str) -> impl Iterator<Item = &str> {
    t.split(|c: char| !(c.is_alphanumeric() || c == '_'))
        .filter(|w| w.chars().count() >= 3 && w.chars().all(char::is_alphabetic))
}

fn caps(t: &str) -> impl Iterator<Item = &str> {
    words(t).filter(|w| w.chars().next().is_some_and(char::is_uppercase))
}

fn lexicon_names(v: &Value, out: &mut Vec<String>) {
    for group in ["subjects", "events"] {
        if let Some(entries) = v[group].as_array() {
            for entry in entries {
                if let Some(name) = entry.as_str().or_else(|| entry["name"].as_str()) {
                    out.push(name.nfkc().collect());
                }
                if let Some(aliases) = entry["aliases"].as_array() {
                    for alias in aliases.iter().filter_map(Value::as_str) {
                        out.push(alias.nfkc().collect());
                    }
                }
            }
        }
    }
}

impl Foreign {
    fn new<'t>(
        lexicon: &Value,
        labelled: impl Iterator<Item = &'t str>,
        _universe: impl Iterator<Item = &'t str>,
    ) -> Self {
        let mut names = Vec::new();
        lexicon_names(lexicon, &mut names);
        let (mut known_caps, mut low) = (HashSet::new(), HashSet::new());
        let mut add = |t: &str| {
            let normalized: String = t.nfkc().collect();
            known_caps.extend(caps(&normalized).map(casefold));
            low.extend(words(&normalized).map(casefold));
        };
        labelled.for_each(&mut add);
        names.iter().for_each(|n| add(n));
        Foreign {
            caps: known_caps,
            low,
        }
    }

    fn unknown(&self, w: &str) -> bool {
        let l = casefold(w);
        !self.caps.contains(&l)
            && !self.low.contains(&l)
            && l.strip_suffix('s').is_none_or(|x| !self.low.contains(x))
    }

    fn is_foreign(&self, t: &str) -> bool {
        caps(&t.nfkc().collect::<String>()).any(|w| self.unknown(w))
    }
}

/// Rows whose engine prediction the router keeps whatever the chain says.
struct Keep<'a> {
    hints: &'a crate::ExtractionHints,
    practice_match: &'a dyn Fn(&crate::InputRow) -> bool,
}

enum RowGuard {
    Keep,
    Unsure(&'static str),
    Statistical { can_true: bool, can_false: bool },
}

/// The exact path uses original typed values, independently of the chain's
/// rounded float states. Normalized text is used internally for duplicate-query
/// exclusion only; original Prediction facts and provenance are never replaced.
struct RouterEvidence {
    graph: crate::knowledge::KnowledgeGraph,
    sources: BTreeMap<(String, String), Vec<crate::InputRow>>,
}

impl RouterEvidence {
    fn new(
        rows: &[crate::InputRow],
        forms: &[Vec<crate::Fact>],
        hints: &crate::ExtractionHints,
    ) -> Self {
        let mut accepted = Vec::new();
        let mut seen = HashSet::new();
        for (row, form) in rows.iter().zip(forms) {
            if !matches!(row.label.as_str(), "true" | "false")
                || !valid_observation_date(&row.date)
                || hints.recognized_empty.contains(&row.id)
                || hints.explicit_unknown.contains(&row.id)
                || hints.incomplete.contains(&row.id)
                || hints.programs.contains_key(&row.id)
                // A partial extraction of a false compound is not a safe negative.
                || row.label == "false" && row.form.is_empty()
                || !seen.insert((router_text(&row.text), row.date.clone(), row.label.clone()))
            {
                continue;
            }
            let mut source = row.clone();
            source.text = router_text(&source.text);
            source.form = form.clone();
            accepted.push(source);
        }
        let graph = crate::knowledge::KnowledgeGraph::compile(&accepted);
        let mut sources: BTreeMap<_, Vec<_>> = BTreeMap::new();
        for row in accepted {
            for fact in &row.form {
                sources
                    .entry((fact.subject.clone(), fact.attribute.clone()))
                    .or_default()
                    .push(row.clone());
            }
        }
        Self { graph, sources }
    }

    fn guard(
        &self,
        row: &crate::InputRow,
        facts: &[crate::Fact],
        hints: &crate::ExtractionHints,
        foreign: bool,
    ) -> RowGuard {
        use crate::knowledge::Status;
        if facts.is_empty() || hints.recognized_empty.contains(&row.id) {
            return RowGuard::Unsure(
                "No grounded assertion was extracted; an empty fact set cannot establish truth.",
            );
        }
        if !valid_observation_date(&row.date) {
            return RowGuard::Unsure(
                "The observation date is invalid; a temporal score cannot establish a verdict.",
            );
        }
        if foreign {
            return RowGuard::Unsure(
                "Owner grounding is unresolved: the text contains a name outside the schema and labelled vocabulary.",
            );
        }
        let text = router_text(&row.text);
        let statuses: Vec<_> = facts
            .iter()
            .map(|f| self.graph.resolve(f, &row.date, &row.id, &text).status)
            .collect();
        // False dominates an unknown conjunct. Exact conjunction proofs are
        // protected even when the chain would abstain or pick the other label.
        if statuses.contains(&Status::Contradicted) {
            return RowGuard::Keep;
        }
        if hints.explicit_unknown.contains(&row.id) || hints.incomplete.contains(&row.id) {
            return RowGuard::Unsure(
                "An asserted clause is unresolved; matching a subset cannot establish the conjunction.",
            );
        }
        if statuses.iter().all(|s| *s == Status::Supported) {
            return RowGuard::Keep;
        }
        if statuses.contains(&Status::Conflict) {
            return RowGuard::Unsure(
                "Conflicting labelled observations prevent a unique exact verdict on this date.",
            );
        }
        // Availability is not temporal proof. F2 may use earlier/later labelled
        // observations statistically, but neither a missing key nor votes can
        // supply a positive or negative assertion. Explicit validity limits
        // are never extrapolated outside their stated range.
        let mut can_true = true;
        let mut can_false = false;
        for fact in facts {
            let candidates = self
                .sources
                .get(&(fact.subject.clone(), fact.attribute.clone()));
            let mut supported = false;
            let mut contradicted = false;
            if let Some(candidates) = candidates {
                let mut dates = HashSet::new();
                for source in candidates {
                    if source.id == row.id
                        || source.text == text
                        || crate::temporal::explicit_scope(&source.text)
                            .is_some_and(|s| !s.contains(&row.date))
                        || !dates.insert(&source.date)
                    {
                        continue;
                    }
                    match self
                        .graph
                        .resolve(fact, &source.date, &row.id, &text)
                        .status
                    {
                        Status::Supported => supported = true,
                        Status::Contradicted => contradicted = true,
                        Status::Unknown | Status::Conflict => {}
                    }
                }
            }
            can_true &= supported;
            can_false |= contradicted;
        }
        RowGuard::Statistical {
            can_true,
            can_false,
        }
    }
}

fn valid_observation_date(date: &str) -> bool {
    date.len() == 10 && date_ordinal(date).is_some()
}

/// Production-only pages coalesce a date regardless of input order or label
/// runs. Same-date copies of a source/query cannot count as another page.
fn router_rows(
    rows: &[crate::InputRow],
    forms: &[Vec<crate::Fact>],
    hints: &crate::ExtractionHints,
    lex: &KbLexicon,
) -> Vec<ChainRow> {
    let queries: HashSet<_> = rows
        .iter()
        .filter(|r| r.label.is_empty())
        .map(|r| router_text(&r.text))
        .collect();
    let mut seen = HashSet::new();
    let mut pages = HashMap::new();
    rows.iter()
        .zip(forms)
        .map(|(row, form)| {
            let next = pages.len();
            let page = *pages.entry(&row.date).or_insert(next);
            let label = Label::parse(&row.label);
            let key = (router_text(&row.text), &row.date, &row.label);
            let suppress = !valid_observation_date(&row.date)
                || hints.recognized_empty.contains(&row.id)
                || hints.explicit_unknown.contains(&row.id)
                || hints.incomplete.contains(&row.id)
                || hints.programs.contains_key(&row.id)
                || label == Some(Label::Unsure)
                || label == Some(Label::False) && row.form.is_empty()
                || label.is_some() && (queries.contains(&key.0) || !seen.insert(key));
            ChainRow {
                date: date_ordinal(&row.date).unwrap_or(0),
                page,
                label,
                facts: if suppress {
                    Vec::new()
                } else {
                    lex.model_facts(form)
                },
            }
        })
        .collect()
}

fn relabel_with<F>(
    rows: &[crate::InputRow],
    predictions: &mut [crate::Prediction],
    lexicon: &Value,
    keep: Keep,
    canonical_seed: bool,
    chain: F,
) -> Routed
where
    F: FnOnce(&[ChainRow]) -> Option<Labels>,
{
    if !canonical_seed {
        return Routed::Engine("canonical practice seed absent".into());
    }
    let has = |l: &str| rows.iter().any(|r| r.label == l);
    if !has("true") || !has("false") {
        return Routed::Engine("labelled rows do not hold both true and false".into());
    }
    let unique_rows: HashSet<_> = rows.iter().map(|r| &r.id).collect();
    let unique_predictions: HashSet<_> = predictions.iter().map(|p| &p.id).collect();
    if unique_rows.len() != rows.len() || unique_predictions.len() != predictions.len() {
        return Routed::Engine("duplicate row IDs make source provenance ambiguous".into());
    }
    let attempt = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let lex = KbLexicon::new(lexicon);
        let by_id: HashMap<&str, &crate::Prediction> =
            predictions.iter().map(|p| (p.id.as_str(), p)).collect();
        let forms: Vec<_> = rows
            .iter()
            .map(|r| {
                let form = if Label::parse(&r.label).is_some() && !r.form.is_empty() {
                    &r.form
                } else {
                    by_id.get(r.id.as_str()).map_or(&r.form, |p| &p.facts)
                };
                form.clone()
            })
            .collect();
        let chain_rows = router_rows(rows, &forms, keep.hints, &lex);
        let fr = Foreign::new(
            lexicon,
            rows.iter()
                .filter(|r| Label::parse(&r.label).is_some())
                .map(|r| r.text.as_str()),
            rows.iter().map(|r| r.text.as_str()),
        );
        let foreign: Vec<bool> = rows
            .iter()
            .map(|r| r.label.is_empty() && fr.is_foreign(&r.text))
            .collect();
        let evidence = RouterEvidence::new(rows, &forms, keep.hints);
        chain(&chain_rows).map(|labels| {
            let guards = rows
                .iter()
                .enumerate()
                .map(|(i, r)| {
                    if !r.label.is_empty()
                        || keep.hints.programs.contains_key(&r.id)
                        || (keep.practice_match)(r)
                        || labels.get(i).is_some_and(Option::is_none)
                    {
                        RowGuard::Keep
                    } else {
                        evidence.guard(r, &forms[i], keep.hints, foreign[i])
                    }
                })
                .collect::<Vec<_>>();
            (labels, guards, foreign)
        })
    }));
    let (labels, guards, foreign) = match attempt {
        Ok(Some(x)) => x,
        Ok(None) => return Routed::Engine("chain found no two-class fit".into()),
        Err(_) => return Routed::Engine("chain failed".into()),
    };
    let valid = labels.len() == rows.len()
        && labels.iter().flatten().all(|(l, c)| match (l, c) {
            (Label::Unsure, None) => true,
            (Label::True | Label::False, Some(c)) => c.is_finite() && (0.5..=1.0).contains(c),
            _ => false,
        });
    if !valid {
        return Routed::Engine("chain output failed validation".into());
    }
    let index: HashMap<&str, usize> = rows
        .iter()
        .enumerate()
        .map(|(i, r)| (r.id.as_str(), i))
        .collect();
    let (mut relabelled, mut kept, mut foreign_n) = (0, 0, 0);
    for p in predictions.iter_mut() {
        if p.known_label.as_deref().is_some_and(|l| !l.is_empty()) {
            continue;
        }
        let Some(&i) = index.get(p.id.as_str()) else {
            continue;
        };
        let Some((label, conf)) = labels[i] else {
            kept += 1;
            continue;
        };
        let (label, conf, reason) = match &guards[i] {
            RowGuard::Keep => {
                kept += 1;
                continue;
            }
            RowGuard::Unsure(reason) => {
                // Retain the core's uncertainty weights and provenance when it
                // already abstained. Do not rewrite its scores as fake certainty.
                if p.label == "unsure" && p.confidence.is_none() {
                    kept += 1;
                    continue;
                }
                if foreign[i] {
                    foreign_n += 1;
                }
                (Label::Unsure, None, *reason)
            }
            RowGuard::Statistical {
                can_true,
                can_false,
            } => {
                if label == Label::True && !can_true || label == Label::False && !can_false {
                    (
                        Label::Unsure,
                        None,
                        "No labelled typed comparison supports this verdict for the full claim; absence is not false and target votes are not proof.",
                    )
                } else {
                    (
                        label,
                        conf,
                        "Statistical temporal estimate from labelled observations, with the query page and matching source text excluded. Earlier/later observations do not prove a validity boundary; scores are not calibrated three-class probabilities.",
                    )
                }
            }
        };
        p.label = label.as_str().into();
        p.confidence = conf;
        let c = conf.unwrap_or(1.0);
        p.probabilities = match label {
            Label::True => crate::Probabilities {
                p_true: c,
                p_false: 1.0 - c,
                p_unsure: 0.0,
            },
            Label::False => crate::Probabilities {
                p_true: 1.0 - c,
                p_false: c,
                p_unsure: 0.0,
            },
            Label::Unsure => crate::Probabilities {
                p_true: 0.0,
                p_false: 0.0,
                p_unsure: 1.0,
            },
        };
        p.reason = format!("KB temporal chain: {reason}");
        relabelled += 1;
    }
    Routed::Chain {
        relabelled,
        kept,
        foreign: foreign_n,
        load: (0, 0, 0),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_helpers_match_reference_semantics() {
        assert_eq!(round6(0.0078125), 0.007812);
        assert_eq!(round6(1.23456789), 1.234568);
        assert_eq!(py_repr(1.1), "1.1");
        assert_eq!(py_repr(2.0), "2.0");
        assert_eq!(py_repr(1e16), "1e+16");
        assert_eq!(py_repr(1.5e-5), "1.5e-05");
        assert_eq!(py_repr(0.0001), "0.0001");
        assert_eq!(py_repr(123456.789), "123456.789");
        assert_eq!(attr_key("  Reliability - Lead "), "reliability_lead");
        assert_eq!(ordinal(2026, 1, 12), Some(739628));
        assert_eq!(date_interval("2024-02"), Some((738917, 738945)));
        assert_eq!(
            pages_of(&[1, 1, 2, 2], &[true, true, true, false], None),
            vec![0, 0, 1, 2]
        );
        assert_eq!(
            pava(vec![1.0, 3.0, 2.0, 4.0], vec![1.0; 4]),
            vec![1.0, 2.5, 2.5, 4.0]
        );
        assert_eq!(
            np_sum(&[1e16, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]),
            1.0000000000000008e16
        );
    }
}

#[cfg(test)]
mod router_tests {
    use super::*;
    use crate::{ExtractionHints, Fact, InputRow, Prediction, Probabilities};

    /// Practice with every fifth row unlabelled; engine predictions carry the gold forms.
    fn world() -> (Vec<InputRow>, Vec<Prediction>, Value) {
        let lexicon = serde_json::from_str(include_str!("../../../data/lexicon.json")).unwrap();
        let mut rows = crate::read_csv(include_str!("../../../data/practice.csv")).unwrap();
        for row in rows.iter_mut().skip(2).step_by(5) {
            row.label.clear();
        }
        let predictions = rows.iter().map(engine_prediction).collect();
        (rows, predictions, lexicon)
    }

    fn engine_prediction(row: &InputRow) -> Prediction {
        Prediction {
            id: row.id.clone(),
            text: row.text.clone(),
            date: row.date.clone(),
            known_label: (!row.label.is_empty()).then(|| row.label.clone()),
            label: "unsure".into(),
            probabilities: Probabilities::default(),
            confidence: None,
            facts: row.form.clone(),
            evidence: Vec::new(),
            reason: "engine".into(),
        }
    }

    fn snapshot(p: &[Prediction]) -> String {
        serde_json::to_string(p).unwrap()
    }

    fn no_hints() -> ExtractionHints {
        ExtractionHints::default()
    }

    #[test]
    fn router_uses_the_chain_with_the_seed_and_two_classes() {
        let (rows, mut predictions, lexicon) = world();
        let targets = rows.iter().filter(|r| r.label.is_empty()).count();
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        let Routed::Chain {
            relabelled,
            kept,
            foreign,
            load: (states, cells, steps),
        } = routed
        else {
            panic!("{routed}")
        };
        assert_eq!(relabelled + kept, targets);
        assert!(foreign <= relabelled);
        assert!((2..=MAX_KEY_STATES).contains(&states));
        assert!(cells > 0 && cells <= WORLD_CELLS && steps > 0 && steps <= WORLD_STEPS);
        let decided = predictions
            .iter()
            .filter(|p| p.known_label.is_none() && p.label != "unsure")
            .count();
        assert!(decided <= targets);
        assert!(predictions.iter().all(|p| {
            p.confidence
                .is_none_or(|c| c.is_finite() && (0.5..=1.0).contains(&c))
        }));
    }

    #[test]
    fn router_keeps_the_engine_without_seed_or_with_one_class() {
        let (rows, mut predictions, lexicon) = world();
        let before = snapshot(&predictions);
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            false,
            &|_| false,
        );
        assert_eq!(
            routed,
            Routed::Engine("canonical practice seed absent".into())
        );
        assert_eq!(snapshot(&predictions), before);

        let mut one_class = rows.clone();
        for row in &mut one_class {
            if row.label == "false" || row.label == "unsure" {
                row.label.clear();
            }
        }
        let mut predictions: Vec<Prediction> = one_class.iter().map(engine_prediction).collect();
        let before = snapshot(&predictions);
        let routed = relabel(
            &one_class,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        assert!(matches!(routed, Routed::Engine(_)), "{routed}");
        assert_eq!(snapshot(&predictions), before);
    }

    #[test]
    fn router_falls_back_to_the_engine_on_chain_failure() {
        let (rows, mut predictions, lexicon) = world();
        let before = snapshot(&predictions);
        type Chain = Box<dyn FnOnce(&[ChainRow]) -> Option<Labels>>;
        let failures: [Chain; 4] = [
            Box::new(|_| panic!("injected chain failure")),
            Box::new(|_| None),
            Box::new(|r| Some(vec![Some((Label::True, Some(0.3))); r.len()])),
            Box::new(|_| Some(Vec::new())),
        ];
        let hints = no_hints();
        for chain in failures {
            let keep = Keep {
                hints: &hints,
                practice_match: &|_| false,
            };
            let routed = relabel_with(&rows, &mut predictions, &lexicon, keep, true, chain);
            assert!(matches!(routed, Routed::Engine(_)), "{routed}");
            assert_eq!(snapshot(&predictions), before);
        }
    }

    #[test]
    fn explicit_unknowns_and_incomplete_rows_keep_the_engine() {
        let (rows, mut predictions, lexicon) = world();
        // Repro of the review: an explicit unknown with no fact would be true under G1.
        let unknown = rows.iter().position(|r| r.label.is_empty()).unwrap();
        predictions[unknown].facts.clear();
        let fresh = predictions.clone();
        relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        assert_eq!(predictions[unknown].label, "unsure");
        let incomplete = (0..rows.len())
            .find(|&i| i != unknown && rows[i].label.is_empty())
            .unwrap();

        let mut hints = no_hints();
        hints.explicit_unknown.insert(rows[unknown].id.clone());
        hints.incomplete.insert(rows[incomplete].id.clone());
        let mut predictions = fresh.clone();
        let routed = relabel(&rows, &mut predictions, &lexicon, &hints, true, &|_| false);
        assert!(
            matches!(routed, Routed::Chain { kept: 2.., .. }),
            "{routed}"
        );
        for i in [unknown, incomplete] {
            assert_eq!(snapshot(&predictions[i..=i]), snapshot(&fresh[i..=i]));
        }
    }

    #[test]
    fn a_high_cardinality_key_keeps_the_engine_and_finishes_fast() {
        let (mut rows, _, lexicon) = world();
        let n = 18_000;
        for k in 0..n {
            let users = 100_001 + k;
            rows.push(InputRow {
                id: format!("h-{k}"),
                text: format!("Hooly Docs has {users} users a month."),
                date: "2026-10-29".into(),
                label: String::new(),
                form: vec![Fact {
                    subject: "Hooly Docs".into(),
                    attribute: "active_users".into(),
                    value: serde_json::json!({"kind": "quantity", "value": users, "unit": "user"}),
                }],
            });
        }
        let mut predictions: Vec<Prediction> = rows.iter().map(engine_prediction).collect();
        let before = predictions.clone();
        let started = std::time::Instant::now();
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        let elapsed = started.elapsed().as_secs_f64();
        let Routed::Chain {
            relabelled, kept, ..
        } = routed
        else {
            panic!("{routed}")
        };
        assert!(kept >= n && relabelled > 0, "{relabelled} {kept}");
        let synthetic = rows.len() - n..rows.len();
        assert_eq!(
            snapshot(&predictions[synthetic.clone()]),
            snapshot(&before[synthetic])
        );
        assert!(elapsed < 30.0, "{elapsed}s");
    }

    #[test]
    fn exact_practice_matches_keep_the_engine() {
        let (rows, mut predictions, lexicon) = world();
        let before = snapshot(&predictions);
        let targets = rows.iter().filter(|r| r.label.is_empty()).count();
        // Every target is a practice row, so the engine's exact-match lookup knows its label.
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| true,
        );
        assert!(
            matches!(routed, Routed::Chain { relabelled: 0, kept, .. } if kept == targets),
            "{routed}"
        );
        assert_eq!(snapshot(&predictions), before);
    }

    #[test]
    fn world_budgets_skip_the_later_of_many_large_keys() {
        // Review scenario: 200 keys, each 1,023 values over 365 dates, every one within the
        // per-key caps. Equal costs are admitted in first-appearance order until a world sum
        // would overflow; an ordinary key that appears last is still admitted (cheapest first).
        let mut sizes = vec![Some((MAX_KEY_STATES, MAX_KEY_STATES - 1, 365)); 200];
        sizes.push(Some((8, 40, 30)));
        sizes.push(None);
        let (ok, cells, steps) = admit(&sizes);
        let per_key = 365 * MAX_KEY_STATES * MAX_KEY_STATES;
        let fit = WORLD_STEPS / per_key;
        assert!(fit < 200);
        assert!(ok[..fit].iter().all(|&x| x) && ok[fit..200].iter().all(|&x| !x));
        assert!(ok[200] && !ok[201]);
        assert_eq!(steps, fit * per_key + 30 * 8 * 8);
        assert!(steps <= WORLD_STEPS && cells <= WORLD_CELLS);
    }

    #[test]
    fn foreign_vocabulary_is_normalized_and_not_licensed_by_distractors() {
        let lexicon = serde_json::json!({"subjects":[{"name":"Audit Cloud","aliases":["Audít"]}]});
        let fr = Foreign::new(
            &lexicon,
            ["Audit Cloud offers seats."].into_iter(),
            ["zephyrvault rose"].into_iter(),
        );
        assert!(!fr.is_foreign("Ａｕｄｉｔ Cloud offers seats."));
        assert!(!fr.is_foreign("Audít offers seats."));
        assert!(fr.is_foreign("Zephyrvault offers seats on Audit Cloud."));
    }
    #[test]
    fn foreign_unlabelled_rows_become_unsure() {
        let (mut rows, _, lexicon) = world();
        rows.push(InputRow {
            id: "s-08".into(),
            text: "Today Paskwright offers a free plan.".into(),
            date: "2026-09-07".into(),
            ..InputRow::default()
        });
        let mut predictions: Vec<Prediction> = rows.iter().map(engine_prediction).collect();
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        assert!(matches!(routed, Routed::Chain { .. }), "{routed}");
        let p = predictions.last().unwrap();
        assert_eq!((p.label.as_str(), p.confidence), ("unsure", None));
        assert_eq!(p.confidence, None);
    }

    #[test]
    fn rows_without_other_page_evidence_become_unsure() {
        let (mut rows, _, lexicon) = world();
        // A fact on a key no other row has: its chain score is NaN.
        rows.push(InputRow {
            id: "noevid".into(),
            text: "Hooly Docs has 7 widgets.".into(),
            date: "2026-10-29".into(),
            label: String::new(),
            form: vec![Fact {
                subject: "Hooly Docs".into(),
                attribute: "widget_count_nowhere_else".into(),
                value: serde_json::json!({"kind": "quantity", "value": 7, "unit": "widget"}),
            }],
        });
        let mut predictions: Vec<Prediction> = rows.iter().map(engine_prediction).collect();
        let routed = relabel(
            &rows,
            &mut predictions,
            &lexicon,
            &no_hints(),
            true,
            &|_| false,
        );
        assert!(matches!(routed, Routed::Chain { .. }), "{routed}");
        let p = predictions.last().unwrap();
        let want = if NOEVID_UNSURE {
            "unsure"
        } else {
            p.label.as_str()
        };
        assert_eq!(p.label, want);
        assert_eq!(p.confidence.is_none(), p.label == "unsure");
        assert_eq!(p.label, "unsure");
    }
}
