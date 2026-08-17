//! Rate statistics computed from raw counting stats.
//!
//! Every function returns `Option<f64>`, with `None` meaning "undefined for
//! this input" (typically a zero denominator) rather than an error.

use crate::util::safe_div;

/// On-base percentage: `(H + BB + HBP) / (AB + BB + HBP + SF)`.
///
/// Sacrifice *bunts* and catcher's interference are excluded from the
/// denominator even though they count as plate appearances — this is the
/// standard definition, not an oversight.
#[inline]
pub fn obp(h: f64, bb: f64, hbp: f64, ab: f64, sf: f64) -> Option<f64> {
    safe_div(h + bb + hbp, ab + bb + hbp + sf)
}

/// Total bases: `1B + 2·2B + 3·3B + 4·HR`, derived from hits and extra-base hits.
///
/// `h` is *total* hits, so singles are computed as `h - 2B - 3B - HR`.
#[inline]
pub fn total_bases(h: f64, doubles: f64, triples: f64, hr: f64) -> f64 {
    let singles = h - doubles - triples - hr;
    singles + 2.0 * doubles + 3.0 * triples + 4.0 * hr
}

/// Slugging percentage from a pre-computed total-bases figure: `TB / AB`.
#[inline]
pub fn slg(tb: f64, ab: f64) -> Option<f64> {
    safe_div(tb, ab)
}

/// Slugging percentage straight from the hit breakdown.
#[inline]
pub fn slg_from_hits(h: f64, doubles: f64, triples: f64, hr: f64, ab: f64) -> Option<f64> {
    slg(total_bases(h, doubles, triples, hr), ab)
}

/// Batting average: `H / AB`.
#[inline]
pub fn avg(h: f64, ab: f64) -> Option<f64> {
    safe_div(h, ab)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A single reference batting line, hand-computed, reused across tests.
    ///
    /// AB=500, H=150, 2B=30, 3B=5, HR=25, BB=60, HBP=5, SF=5
    const AB: f64 = 500.0;
    const H: f64 = 150.0;
    const DOUBLES: f64 = 30.0;
    const TRIPLES: f64 = 5.0;
    const HR: f64 = 25.0;
    const BB: f64 = 60.0;
    const HBP: f64 = 5.0;
    const SF: f64 = 5.0;

    #[test]
    fn obp_matches_hand_computation() {
        // (150 + 60 + 5) / (500 + 60 + 5 + 5) = 215 / 570
        let expected = 215.0 / 570.0;
        assert!((obp(H, BB, HBP, AB, SF).unwrap() - expected).abs() < 1e-12);
    }

    #[test]
    fn total_bases_counts_singles_correctly() {
        // singles = 150 - 30 - 5 - 25 = 90
        // TB = 90 + 60 + 15 + 100 = 265
        assert_eq!(total_bases(H, DOUBLES, TRIPLES, HR), 265.0);
    }

    #[test]
    fn slg_matches_hand_computation() {
        // 265 / 500 = 0.53
        assert!((slg_from_hits(H, DOUBLES, TRIPLES, HR, AB).unwrap() - 0.53).abs() < 1e-12);
    }

    #[test]
    fn avg_matches_hand_computation() {
        assert!((avg(H, AB).unwrap() - 0.30).abs() < 1e-12);
    }

    #[test]
    fn zero_denominators_yield_none() {
        assert_eq!(avg(0.0, 0.0), None);
        assert_eq!(slg(0.0, 0.0), None);
        assert_eq!(obp(0.0, 0.0, 0.0, 0.0, 0.0), None);
    }
}
