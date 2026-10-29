//! Frozen text tokenization, metadata encoding and bounded tensor preparation.
use std::collections::HashMap;

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};

use crate::{
    grammar::{Candidate, Grammar, KINDS, clauses},
    python::{Text, casefold, rx},
};

pub const MAX_TOKENS: usize = 384;
pub const MAX_CHARS: usize = 24;
pub const MAX_CANDIDATES: usize = 256;
pub const MAX_TEXT_CHARS: usize = 65536;
pub const MAX_ASSERTIONS: usize = 64;

#[derive(Debug, Deserialize)]
pub struct Metadata {
    pub pairs: Vec<[String; 2]>,
    pub vocab: HashMap<String, i64>,
    pub chars: HashMap<String, i64>,
    pub extra_names: Vec<String>,
    pub max_tokens: usize,
    pub max_chars: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Token {
    pub word: String,
    pub start: usize,
    pub end: usize,
}

pub fn tokens(text: &str) -> Result<Vec<Token>> {
    let t = Text::new(text);
    rx!(r"\d+(?:[.,]\d+)*|[\w]+(?:[-’'][\w]+)*|[^\w\s]")
        .find_iter(text)
        .map(|matched| {
            let m = matched?;
            Ok(Token {
                word: casefold(m.as_str()),
                start: t.char_at_byte(m.start()),
                end: t.char_at_byte(m.end()),
            })
        })
        .collect()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EncodedRow {
    pub id: String,
    pub text: String,
    pub previous_text: String,
    pub tokens: Vec<i64>,
    pub chars: Vec<Vec<i64>>,
    pub candidates: Vec<Candidate>,
    pub current_offset: usize,
    pub has_context: bool,
}

pub fn encode_input(
    text: &str,
    previous: &str,
    meta: &Metadata,
    grammar: &Grammar,
    id: &str,
) -> Result<EncodedRow> {
    ensure!(
        text.chars().count() <= MAX_TEXT_CHARS,
        "Text exceeds {MAX_TEXT_CHARS} characters"
    );
    ensure!(
        meta.max_tokens == MAX_TOKENS && meta.max_chars == MAX_CHARS,
        "Unsupported metadata dimensions"
    );
    let ct = tokens(previous)?;
    let tt = tokens(text)?;
    let ct = &ct[ct.len().saturating_sub(96)..];
    let offset = ct.len() + 2;
    ensure!(
        offset + tt.len() <= MAX_TOKENS,
        "Input exceeds the supported 384 tokens; no silent truncation"
    );
    let seq: Vec<&str> = std::iter::once("<ctx>")
        .chain(ct.iter().map(|t| t.word.as_str()))
        .chain(std::iter::once("<current>"))
        .chain(tt.iter().map(|t| t.word.as_str()))
        .collect();
    let mut candidates = grammar.candidates(text)?;
    ensure!(
        candidates.len() <= MAX_CANDIDATES,
        "Input exceeds {MAX_CANDIDATES} value candidates"
    );
    let cs = clauses(text)?;
    for c in &mut candidates {
        let (lo, hi) = span(&tt, c.start, c.end, offset).context("Candidate has no token span")?;
        c.lo = Some(lo);
        c.hi = Some(hi);
        c.kind = Some(if c.value["kind"] == "boolean" {
            8 + i64::from(c.value["value"].as_bool().context("boolean value")?)
        } else {
            KINDS
                .iter()
                .position(|k| c.value["kind"] == *k)
                .context("candidate kind")? as i64
        });
        let (a, b) = cs
            .iter()
            .copied()
            .find(|&(a, b)| a <= c.start && c.start < b)
            .unwrap_or((0, text.chars().count()));
        let (lo, hi) = span(&tt, a, b, offset).context("Candidate has no clause span")?;
        c.clo = Some(lo);
        c.chi = Some(hi);
    }
    Ok(EncodedRow {
        id: id.into(),
        text: text.into(),
        previous_text: previous.into(),
        tokens: seq
            .iter()
            .map(|w| *meta.vocab.get(*w).unwrap_or(&1))
            .collect(),
        chars: seq
            .iter()
            .map(|w| {
                w.chars()
                    .take(MAX_CHARS)
                    .map(|c| *meta.chars.get(&c.to_string()).unwrap_or(&1))
                    .collect()
            })
            .collect(),
        candidates,
        current_offset: offset,
        has_context: !previous.is_empty(),
    })
}

fn span(tokens: &[Token], start: usize, end: usize, offset: usize) -> Option<(usize, usize)> {
    let mut found = tokens
        .iter()
        .enumerate()
        .filter(|(_, t)| t.start < end && t.end > start)
        .map(|(i, _)| i + offset);
    let first = found.next()?;
    Some((first, found.next_back().unwrap_or(first) + 1))
}

pub(crate) struct Tensors {
    pub b: usize,
    pub t: usize,
    pub c: usize,
    pub words: Vec<i64>,
    pub chars: Vec<i64>,
    pub spans: Vec<f32>,
    pub clauses: Vec<f32>,
    pub kinds: Vec<i64>,
}

impl Tensors {
    pub fn from_rows(rows: &[&EncodedRow]) -> Result<Self> {
        ensure!(
            !rows.is_empty() && rows.len() <= 64,
            "Inference batch must contain 1..64 rows"
        );
        let b = rows.len();
        let t = rows.iter().map(|r| r.tokens.len()).max().unwrap();
        let c = rows
            .iter()
            .map(|r| r.candidates.len())
            .max()
            .unwrap()
            .max(1);
        ensure!(
            (2..=MAX_TOKENS).contains(&t) && c <= MAX_CANDIDATES,
            "Tensor dimensions exceed limits"
        );
        let mut batch = Self {
            b,
            t,
            c,
            words: vec![0; b * t],
            chars: vec![0; b * t * MAX_CHARS],
            spans: vec![0.; b * c * t],
            clauses: vec![0.; b * c * t],
            kinds: vec![0; b * c],
        };
        for (i, r) in rows.iter().enumerate() {
            ensure!(
                r.chars.len() == r.tokens.len(),
                "Token/character lengths differ"
            );
            batch.words[i * t..i * t + r.tokens.len()].copy_from_slice(&r.tokens);
            for (j, word) in r.chars.iter().enumerate() {
                ensure!(word.len() <= MAX_CHARS, "Token character array exceeds 24");
                batch.chars[(i * t + j) * MAX_CHARS..(i * t + j) * MAX_CHARS + word.len()]
                    .copy_from_slice(word);
            }
            for (j, v) in r.candidates.iter().enumerate() {
                for (dst, lo, hi) in [
                    (&mut batch.spans, v.lo, v.hi),
                    (&mut batch.clauses, v.clo, v.chi),
                ] {
                    let lo = lo.context("missing span")?;
                    let hi = hi.context("missing span")?;
                    if lo >= hi || hi > r.tokens.len() {
                        bail!("Invalid candidate span");
                    }
                    // Python computes division as f64 then stores float32.
                    dst[(i * c + j) * t + lo..(i * c + j) * t + hi]
                        .fill((1.0_f64 / (hi - lo) as f64) as f32);
                }
                let kind = v.kind.context("missing kind")?;
                ensure!((0..=9).contains(&kind), "Invalid candidate kind");
                batch.kinds[i * c + j] = kind;
            }
        }
        Ok(batch)
    }
}
