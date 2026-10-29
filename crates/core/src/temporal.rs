//! Explicit validity qualifiers; page dates never imply a validity interval.
use regex::Regex;
use serde::Serialize;
use std::sync::OnceLock;

#[derive(Clone, Debug, Serialize)]
pub struct ValidityScope {
    pub start_inclusive: String,
    pub end_inclusive: String,
    pub body_offset_bytes: usize,
}
impl ValidityScope {
    pub fn contains(&self, date: &str) -> bool {
        self.start_inclusive.as_str() <= date && date <= self.end_inclusive.as_str()
    }
}

/// Only explicit inclusive "From ... through ..." with two complete dates.
/// Ambiguous "until/to", missing years and reversed/invalid ranges are unresolved.
pub fn explicit_scope(text: &str) -> Option<ValidityScope> {
    static PREFIX: OnceLock<Option<Regex>> = OnceLock::new();
    let prefix = PREFIX.get_or_init(|| {
        let month = "(?:January|February|March|April|May|June|July|August|September|October|November|December)";
        let date = format!(r"(?:20[0-9]{{2}}-[0-9]{{2}}-[0-9]{{2}}|(?:the\s+)?[0-9]{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{month}\s*,?\s*20[0-9]{{2}}|{month}\s+[0-9]{{1,2}}(?:st|nd|rd|th)?\s*,?\s*20[0-9]{{2}})");
        Regex::new(&format!(r"(?i)^\s*From\s+(?P<start>{date})\s+through\s+(?P<end>{date})\s*,\s*")).ok()
    }).as_ref()?;
    let c = prefix.captures(text)?;
    let start = full_date(c.name("start")?.as_str())?;
    let end = full_date(c.name("end")?.as_str())?;
    if start > end {
        return None;
    }
    Some(ValidityScope {
        start_inclusive: start,
        end_inclusive: end,
        body_offset_bytes: c.get(0)?.end(),
    })
}

fn full_date(text: &str) -> Option<String> {
    let cleaned = text.trim().to_lowercase();
    let (year, month, day) = if cleaned.contains('-') {
        let p: Vec<_> = cleaned.split('-').collect();
        if p.len() != 3 {
            return None;
        }
        (
            p[0].parse::<u32>().ok()?,
            p[1].parse::<u32>().ok()?,
            p[2].parse::<u32>().ok()?,
        )
    } else {
        let months = [
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
        ];
        let p: Vec<_> = cleaned
            .split(|c: char| !c.is_alphanumeric())
            .filter(|p| !p.is_empty() && *p != "the" && *p != "of")
            .collect();
        if p.len() != 3 {
            return None;
        }
        let mi = p.iter().position(|p| months.contains(p))?;
        let m = months.iter().position(|m| *m == p[mi])? as u32 + 1;
        let di = if mi == 0 {
            1
        } else if mi == 1 {
            0
        } else {
            return None;
        };
        let d = p[di]
            .trim_end_matches(|c: char| c.is_ascii_alphabetic())
            .parse::<u32>()
            .ok()?;
        (p[2].parse::<u32>().ok()?, m, d)
    };
    if !(2000..=2099).contains(&year) || !(1..=12).contains(&month) {
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
    if day == 0 || day > days[month as usize - 1] {
        return None;
    }
    Some(format!("{year:04}-{month:02}-{day:02}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ordinal_us_and_iso_dates_have_same_inclusive_scope() {
        for text in [
            "From the 1st of February 2026 through the 30th of June 2026, Cloud costs €4.",
            "From February 1, 2026 through June 30, 2026, Cloud costs €4.",
            "From 2026-02-01 through 2026-06-30, Cloud costs €4.",
        ] {
            let s = explicit_scope(text).unwrap();
            assert!(s.contains("2026-02-01"));
            assert!(s.contains("2026-06-30"));
            assert!(!s.contains("2026-07-01"));
            assert!(!s.contains("2026-01-31"));
            assert_eq!(&text[s.body_offset_bytes..], "Cloud costs €4.");
        }
    }
    #[test]
    fn invalid_or_ambiguous_ranges_establish_no_interval() {
        for text in [
            "Cloud costs €4.",
            "From February through June, Cloud costs €4.",
            "From February 30, 2026 through June 30, 2026, Cloud costs €4.",
            "From July 1, 2026 through June 30, 2026, Cloud costs €4.",
            "From February 1, 2026 until June 30, 2026, Cloud costs €4.",
        ] {
            assert!(explicit_scope(text).is_none(), "{text}");
        }
    }
}
