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
use std::collections::HashMap;

const EPS_A: f64 = 0.0005;
const EPS_F: f64 = 0.2;
const VOTE_LR: f64 = 48.0;
const PI_O: f64 = 1.0;
const MONO_A: f64 = 10.0;
const D0: f64 = 0.03;
const MIN_PAIRS: usize = 8;

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
    /// Calibrated P(true | decided) of the row (`pc`).
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
        }
    }

    fn loglik(&self) -> Vec<Vec<f64>> {
        let (ea, ef, r) = (EPS_A, EPS_F, VOTE_LR);
        let mut out = vec![vec![0.0; self.g.len()]; self.s];
        for (si, row) in out.iter_mut().enumerate() {
            for (b, o) in row.iter_mut().enumerate() {
                let a = self.ag[si][b];
                *o = match self.role[b] {
                    Role::Anchor => (ea + (1.0 - ea) * a).ln(),
                    Role::FalseSingle => (1.0 - (1.0 - ef) * a).ln(),
                    Role::FalseMulti => 0.0,
                    Role::Vote => (1.0 - (1.0 - 1.0 / r) * (1.0 - a)).ln(),
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
}

/// Scores every fact; fits the hazard on this world's anchors when `hz` is None.
fn score_world(rows: &[ChainRow], hz: Option<&Hazard>) -> (Scored, Option<Hazard>) {
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
    let keys: Vec<Key> = groups
        .into_iter()
        .map(|g| Key::new(g, &flat, &frow, rows, &nf))
        .collect();
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
        let (s, hz) = score_world(rows, None);
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
        });
    }
    let fallback = fallback.filter(|f| two_class(f))?;
    let (model, _) = Model::fit(fallback);
    let (s, _) = score_world(rows, Some(&model.hz));
    Some(ChainRun {
        rows: model.predict(rows, &s),
        rate: model.rate,
    })
}

/// Confidence scale of the shipped labeller: accuracy over mean confidence of the guarded
/// chain's decided rows, fitted once on practice P80 (T2 SPEC-G1, `rfac.json`). Constant by
/// design: the hidden rows of a competition run have no labels to refit it.
pub const CONF_SCALE: f64 = 0.972343066499685;

/// The shipped labeller (T2 SPEC-G1): the chain, then G1 (an unlabelled row with no parsed
/// fact is true with confidence max(0.5, rate)), then every decided confidence scaled by
/// [`CONF_SCALE`] and clipped to [0.5, 1]. Labelled rows keep the chain's output.
pub fn guarded(
    rows: &[ChainRow],
    fallback: Option<&[ChainRow]>,
) -> Option<Vec<(Label, Option<f64>)>> {
    let run = run(rows, fallback)?;
    Some(
        rows.iter()
            .zip(run.rows)
            .map(|(row, out)| {
                let (label, conf) = if row.label.is_none() && row.facts.is_empty() {
                    (Label::True, Some(run.rate.max(0.5)))
                } else {
                    (out.label, out.confidence)
                };
                (label, conf.map(|c| (c * CONF_SCALE).clamp(0.5, 1.0)))
            })
            .collect(),
    )
}

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

/// Pipeline adapter (switch `VERIDYCT_KB_CHAIN=1` in the CLI): relabel the unlabelled
/// predictions with [`guarded`]. Facts: a labelled row's own form (the embedded practice gold
/// form for practice texts), else the facts the pipeline used for that row. Pages follow input
/// order. `practice` is the one-class fallback. Returns the number of relabelled rows, or None
/// (predictions untouched) when no two-class fit exists.
pub fn relabel(
    rows: &[crate::InputRow],
    predictions: &mut [crate::Prediction],
    lexicon: &Value,
    practice: &[crate::InputRow],
) -> Option<usize> {
    let lex = KbLexicon::new(lexicon);
    let by_id: HashMap<&str, &crate::Prediction> =
        predictions.iter().map(|p| (p.id.as_str(), p)).collect();
    let refs: Vec<&crate::InputRow> = rows.iter().collect();
    let chain_rows = universe_rows(&refs, None, |r| {
        let form = if Label::parse(&r.label).is_some() && !r.form.is_empty() {
            &r.form
        } else {
            by_id.get(r.id.as_str()).map_or(&r.form, |p| &p.facts)
        };
        lex.model_facts(form)
    });
    let fallback = practice_rows(practice, &lex);
    let labels = guarded(&chain_rows, Some(&fallback))?;
    let index: HashMap<&str, usize> = rows
        .iter()
        .enumerate()
        .map(|(i, r)| (r.id.as_str(), i))
        .collect();
    let mut changed = 0;
    for p in predictions.iter_mut() {
        if p.known_label.as_deref().is_some_and(|l| !l.is_empty()) {
            continue;
        }
        let Some(&i) = index.get(p.id.as_str()) else {
            continue;
        };
        let (label, conf) = labels[i];
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
        p.reason = format!(
            "KB temporal chain (F2) over labelled anchors and other-page statements{}.",
            if chain_rows[i].facts.is_empty() {
                "; no parsed fact, empty-extraction guard"
            } else {
                ""
            }
        );
        changed += 1;
    }
    Some(changed)
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
