//! Python 3.11 Unicode 14 semantics, frozen independently of Rust's Unicode version.
use std::{collections::HashMap, sync::LazyLock};

use anyhow::{Result, bail};
use fancy_regex::Regex;
use serde::Deserialize;

#[derive(Deserialize)]
struct Unicode {
    casefold: HashMap<char, String>,
    decimal: HashMap<char, u8>,
    word: Vec<[u32; 2]>,
    space: Vec<[u32; 2]>,
    insensitive: HashMap<char, String>,
}

static UNICODE: LazyLock<Unicode> = LazyLock::new(|| {
    serde_json::from_str(include_str!("unicode14.json")).expect("generated Unicode table")
});

pub(crate) fn casefold(text: &str) -> String {
    let mut result = String::with_capacity(text.len());
    for c in text.chars() {
        if let Some(fold) = UNICODE.casefold.get(&c) {
            result.push_str(fold);
        } else {
            result.push(c);
        }
    }
    result
}

fn class(ranges: &[[u32; 2]]) -> String {
    let mut result = String::new();
    for &[a, b] in ranges {
        result.push_str(&format!(r"\x{{{a:x}}}"));
        if b != a {
            result.push_str(&format!(r"-\x{{{b:x}}}"));
        }
    }
    result
}

static WORD: LazyLock<String> = LazyLock::new(|| class(&UNICODE.word));
static SPACE: LazyLock<String> = LazyLock::new(|| class(&UNICODE.space));
static DIGIT: LazyLock<String> = LazyLock::new(|| {
    let mut values: Vec<u32> = UNICODE.decimal.keys().map(|c| *c as u32).collect();
    values.sort_unstable();
    values
        .into_iter()
        .map(|c| format!(r"\x{{{c:x}}}"))
        .collect()
});

fn literal(c: char, insensitive: bool) -> String {
    if insensitive && let Some(group) = UNICODE.insensitive.get(&c) {
        return format!("[{}]", regex::escape(group));
    }
    regex::escape(&c.to_string())
}

/// Translate only the Python regex constructs used by the frozen sources.
/// Explicit character classes avoid Rust/Python disagreements on combining marks,
/// newer Unicode assignments, dotted/dotless I, and Python's four extra spaces.
pub(crate) fn regex(pattern: &str, insensitive: bool) -> Result<Regex> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == '\\' {
            i += 1;
            let escaped = *chars
                .get(i)
                .ok_or_else(|| anyhow::anyhow!("regex escape"))?;
            match escaped {
                'w' => out.push_str(&format!("[{}]", *WORD)),
                'W' => out.push_str(&format!("[^{}]", *WORD)),
                's' => out.push_str(&format!("[{}]", *SPACE)),
                'd' => out.push_str(&format!("[{}]", *DIGIT)),
                'b' => out.push_str(&format!(
                    "(?:(?<=[{w}])(?![{w}])|(?<![{w}])(?=[{w}]))",
                    w = *WORD
                )),
                _ => {
                    out.push('\\');
                    out.push(escaped);
                }
            }
        } else if c == '[' {
            i += 1;
            let mut body = String::new();
            if chars.get(i) == Some(&'^') {
                body.push('^');
                i += 1;
            }
            while i < chars.len() && chars[i] != ']' {
                if chars[i] == '\\' {
                    i += 1;
                    match chars[i] {
                        'w' => body.push_str(&WORD),
                        's' => body.push_str(&SPACE),
                        'd' => body.push_str(&DIGIT),
                        x => {
                            body.push('\\');
                            body.push(x);
                        }
                    }
                } else if insensitive
                    && i + 2 < chars.len()
                    && chars[i + 1] == '-'
                    && chars[i + 2] != ']'
                {
                    for n in chars[i] as u32..=chars[i + 2] as u32 {
                        if let Some(ch) = char::from_u32(n) {
                            body.push_str(&regex::escape(
                                UNICODE
                                    .insensitive
                                    .get(&ch)
                                    .map(String::as_str)
                                    .unwrap_or(&ch.to_string()),
                            ));
                        }
                    }
                    i += 2;
                } else if insensitive && let Some(group) = UNICODE.insensitive.get(&chars[i]) {
                    body.push_str(&regex::escape(group));
                } else {
                    body.push(chars[i]);
                }
                i += 1;
            }
            if i == chars.len() {
                bail!("unclosed class");
            }
            out.push('[');
            out.push_str(&body);
            out.push(']');
        } else if c == '(' && chars.get(i + 1) == Some(&'?') {
            // Group syntax contains literal letters which must not be folded.
            if chars.get(i + 2) == Some(&'P') && chars.get(i + 3) == Some(&'<') {
                while chars[i] != '>' {
                    out.push(chars[i]);
                    i += 1;
                }
                out.push('>');
            } else if chars[i..].starts_with(&['(', '?', '-', 'i', ':', 'M', ')']) {
                out.push('M');
                i += 6;
            } else {
                out.push(c);
            }
        } else if c == '$' {
            out.push_str(r"(?=\n?\z)");
        } else if c.is_alphabetic() {
            out.push_str(&literal(c, insensitive));
        } else {
            out.push(c);
        }
        i += 1;
    }
    Ok(fancy_regex::RegexBuilder::new(&out)
        .backtrack_limit(2_000_000)
        .build()?)
}

pub(crate) fn decimal_ascii(text: &str) -> String {
    text.chars()
        .map(|c| UNICODE.decimal.get(&c).map_or(c, |n| char::from(b'0' + n)))
        .collect()
}

pub(crate) struct Text<'a> {
    pub raw: &'a str,
    offsets: Vec<usize>,
}

impl<'a> Text<'a> {
    pub fn new(raw: &'a str) -> Self {
        Self {
            raw,
            offsets: raw
                .char_indices()
                .map(|(i, _)| i)
                .chain(std::iter::once(raw.len()))
                .collect(),
        }
    }
    pub fn len(&self) -> usize {
        self.offsets.len() - 1
    }
    pub fn char_at_byte(&self, byte: usize) -> usize {
        self.offsets
            .binary_search(&byte)
            .expect("regex matches UTF-8 boundaries")
    }
    pub fn slice(&self, start: usize, end: usize) -> &'a str {
        &self.raw[self.offsets[start.min(self.len())]..self.offsets[end.min(self.len())]]
    }
}

macro_rules! rx {
    ($pattern:expr, $insensitive:expr) => {{
        static RE: std::sync::LazyLock<fancy_regex::Regex> = std::sync::LazyLock::new(|| {
            $crate::python::regex($pattern, $insensitive).expect("frozen grammar regex")
        });
        &*RE
    }};
    ($pattern:expr) => {
        rx!($pattern, false)
    };
}
pub(crate) use rx;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn python_unicode_and_boundaries() -> Result<()> {
        assert_eq!(casefold("Straße İ K"), "strasse i\u{307} k");
        assert!(regex(r"\b[A-Z]+\b", true)?.is_match("ıſİK")?);
        assert_eq!(
            regex(r"\w+", false)?.find("e\u{301}")?.unwrap().as_str(),
            "e"
        );
        assert!(regex(r"^x\s+$", false)?.is_match("x\u{1c}")?);
        assert!(regex(r"x$", false)?.is_match("x\n")?);
        assert!(!regex(r"(?-i:M)", true)?.is_match("m")?);
        Ok(())
    }
}
