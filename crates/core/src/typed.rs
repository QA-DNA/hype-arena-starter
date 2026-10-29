//! Exact decimal quantities and contract-approved dimensions, independent of ML.
use num_bigint::BigInt;
use num_rational::BigRational;
use serde_json::Value;
use std::cmp::Ordering;

#[derive(Clone, Debug)]
pub(crate) struct Numeric {
    pub dimension: String,
    pub amount: BigRational,
}

/// Parse a JSON decimal lexeme, never its binary floating-point approximation.
/// Bounded lengths/exponents keep malformed external values inexpensive.
pub(crate) fn decimal(text: &str) -> Option<BigRational> {
    if text.len() > 512 {
        return None;
    }
    let mut exponent_parts = text.split(['e', 'E']);
    let mantissa = exponent_parts.next()?;
    let exponent = exponent_parts
        .next()
        .map_or(Some(0i32), |s| s.parse().ok())?;
    if exponent_parts.next().is_some() || exponent.unsigned_abs() > 256 {
        return None;
    }
    let decimals = mantissa
        .split_once('.')
        .map_or(0, |(_, fraction)| fraction.len());
    if decimals > 256 {
        return None;
    }
    let digits = mantissa.replace('.', "");
    let integer = BigInt::parse_bytes(digits.as_bytes(), 10)?;
    let power = exponent - decimals as i32;
    let factor = BigInt::from(10u8).pow(power.unsigned_abs());
    Some(if power >= 0 {
        BigRational::from_integer(integer * factor)
    } else {
        BigRational::new(integer, factor)
    })
}

fn factor(n: i64, d: i64) -> BigRational {
    BigRational::new(BigInt::from(n), BigInt::from(d))
}

pub(crate) fn numeric(value: &Value) -> Option<Numeric> {
    let kind = value["kind"].as_str()?;
    if !matches!(kind, "quantity" | "money" | "percent" | "duration") {
        return None;
    }
    let amount = decimal(&value["value"].as_number()?.to_string())?;
    let unit = value["unit"].as_str().unwrap_or("");
    let (dimension, n, d): (String, i64, i64) = match kind {
        "money" => (
            format!(
                "money:{}:{}",
                value["currency"].as_str()?,
                value["per"].as_str().unwrap_or("once")
            ),
            1,
            1,
        ),
        "percent" => ("percent".into(), 1, 1),
        "duration" => match unit {
            "ms" => ("fixed-time".into(), 1, 1),
            "s" => ("fixed-time".into(), 1000, 1),
            "min" => ("fixed-time".into(), 60000, 1),
            "h" => ("fixed-time".into(), 3600000, 1),
            "day" => ("fixed-time".into(), 86400000, 1),
            "week" => ("fixed-time".into(), 604800000, 1),
            "month" => ("calendar-time".into(), 1, 1),
            "year" => ("calendar-time".into(), 12, 1),
            _ => return None,
        },
        "quantity" => match unit {
            "B" => ("data".into(), 1, 1),
            "KB" | "kB" => ("data".into(), 1000, 1),
            "MB" => ("data".into(), 1000000, 1),
            "GB" => ("data".into(), 1000000000, 1),
            "TB" => ("data".into(), 1000000000000, 1),
            "mm" => ("length".into(), 1, 1),
            "cm" => ("length".into(), 10, 1),
            "m" => ("length".into(), 1000, 1),
            "km" => ("length".into(), 1000000, 1),
            "in" | "inch" => ("length".into(), 127, 5),
            "g" => ("mass".into(), 1, 1),
            "kg" => ("mass".into(), 1000, 1),
            "mAh" => ("charge".into(), 1, 1),
            "Hz" => ("frequency".into(), 1, 1),
            "kHz" => ("frequency".into(), 1000, 1),
            "MHz" => ("frequency".into(), 1000000, 1),
            "GHz" => ("frequency".into(), 1000000000, 1),
            "mW" => ("power".into(), 1, 1),
            "W" => ("power".into(), 1000, 1),
            "kW" => ("power".into(), 1000000, 1),
            other => (format!("count:{other}"), 1, 1),
        },
        _ => return None,
    };
    Some(Numeric {
        dimension: format!("{kind}:{dimension}"),
        amount: amount * factor(n, d),
    })
}

/// A source exact version can decide numeric inequalities. Equality remains
/// written equality: the contract explicitly distinguishes 2.3 from 2.3.0.
pub(crate) fn version_against_exact(query: &Value, source: &Value, negate: bool) -> Option<bool> {
    let q = query["value"].as_str()?;
    let s = source["value"].as_str()?;
    let qo = query["op"].as_str().unwrap_or("eq");
    let so = source["op"].as_str().unwrap_or("eq");
    if so != "eq" && so != "ne" {
        return None;
    }
    let source_is_negative = (so == "ne") ^ negate;
    if source_is_negative {
        return match (qo, q == s) {
            ("eq", true) => Some(false),
            ("ne", true) => Some(true),
            _ => None,
        };
    }
    if qo == "eq" {
        return Some(q == s);
    }
    if qo == "ne" {
        return Some(q != s);
    }
    let parts = |v: &str| -> Option<Vec<u64>> {
        if v.len() > 256 {
            return None;
        }
        v.split('.').map(|p| p.parse::<u64>().ok()).collect()
    };
    // The source is the actual version; the query is the comparison boundary.
    let order = parts(s)?.cmp(&parts(q)?);
    if order == Ordering::Equal && q != s {
        return None;
    }
    match qo {
        "gt" => Some(order == Ordering::Greater),
        "ge" => Some(order != Ordering::Less),
        "lt" => Some(order == Ordering::Less),
        "le" => Some(order != Ordering::Greater),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn decimal_arithmetic_and_large_integer_distinctions_are_exact() {
        assert_eq!(
            decimal("0.1").unwrap() + decimal("0.2").unwrap(),
            decimal("0.3").unwrap()
        );
        assert_ne!(decimal("9007199254740992"), decimal("9007199254740993"));
        assert_eq!(decimal("4.9e-2"), decimal("0.049"));
        assert!(decimal("1e999999").is_none());
    }
    #[test]
    fn physical_units_convert_but_currency_and_calendar_dimensions_stay_distinct() {
        let q = |v, u| json!({"kind":"quantity","value":v,"unit":u});
        assert_eq!(
            numeric(&q(1.2, "GB")).unwrap().amount,
            numeric(&q(1200.0, "MB")).unwrap().amount
        );
        let d = |v, u| json!({"kind":"duration","value":v,"unit":u});
        assert_eq!(
            numeric(&d(1, "year")).unwrap().amount,
            numeric(&d(12, "month")).unwrap().amount
        );
        assert_ne!(
            numeric(&d(1, "year")).unwrap().dimension,
            numeric(&d(365, "day")).unwrap().dimension
        );
        let m = |c, p| json!({"kind":"money","value":79,"currency":c,"per":p});
        assert_ne!(
            numeric(&m("EUR", "month")).unwrap().dimension,
            numeric(&m("USD", "month")).unwrap().dimension
        );
        assert_ne!(
            numeric(&m("EUR", "year")).unwrap().dimension,
            numeric(&m("EUR", "month")).unwrap().dimension
        );
    }
    #[test]
    fn versions_follow_written_equality_and_numeric_component_order() {
        let v = |s, op| json!({"kind":"version","value":s,"op":op});
        assert_eq!(
            version_against_exact(&v("2.3", "eq"), &v("2.3.0", "eq"), false),
            Some(false)
        );
        assert_eq!(
            version_against_exact(&v("2.10", "gt"), &v("2.9", "eq"), false),
            Some(false)
        );
        assert_eq!(
            version_against_exact(&v("2.9", "gt"), &v("2.10", "eq"), false),
            Some(true)
        );
        assert_eq!(
            version_against_exact(&v("20.9.2", "lt"), &v("19.9.2", "eq"), false),
            Some(true)
        );
        assert_eq!(
            version_against_exact(&v("20.9.2", "le"), &v("21.9.2", "eq"), false),
            Some(false)
        );
        for (op, expected) in [
            ("eq", false),
            ("ne", true),
            ("lt", false),
            ("le", false),
            ("gt", true),
            ("ge", true),
        ] {
            assert_eq!(
                version_against_exact(&v("2.9", op), &v("2.10", "eq"), false),
                Some(expected),
                "{op}"
            );
        }
    }
}
