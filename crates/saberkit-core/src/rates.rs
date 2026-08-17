//! Rate statistics computed from raw counting stats.
//!
//! Every function returns `Option<f64>`, with `None` meaning "undefined for
//! this input" (typically a zero denominator) rather than an error. Functions
//! taking innings pitched return `Result<Option<f64>>`, because malformed
//! innings notation *is* an error — see [`crate::ip`].

use crate::error::Result;
use crate::ip::ip_to_innings;
use crate::league::WobaWeights;
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
    singles(h, doubles, triples, hr) + 2.0 * doubles + 3.0 * triples + 4.0 * hr
}

/// Singles: total hits less every extra-base hit.
#[inline]
pub fn singles(h: f64, doubles: f64, triples: f64, hr: f64) -> f64 {
    h - doubles - triples - hr
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

/// On-base plus slugging.
#[inline]
pub fn ops(obp: f64, slg: f64) -> Option<f64> {
    crate::util::finite(obp + slg)
}

/// Isolated power: `SLG - AVG`, i.e. extra bases per at-bat.
#[inline]
pub fn iso(slg: f64, avg: f64) -> Option<f64> {
    crate::util::finite(slg - avg)
}

/// Isolated power straight from the hit breakdown.
#[inline]
pub fn iso_from_hits(h: f64, doubles: f64, triples: f64, hr: f64, ab: f64) -> Option<f64> {
    safe_div(total_bases(h, doubles, triples, hr) - h, ab)
}

/// Batting average on balls in play: `(H - HR) / (AB - K - HR + SF)`.
#[inline]
pub fn babip(h: f64, hr: f64, ab: f64, k: f64, sf: f64) -> Option<f64> {
    safe_div(h - hr, ab - k - hr + sf)
}

/// Weighted on-base average.
///
/// `(wBB·uBB + wHBP·HBP + w1B·1B + w2B·2B + w3B·3B + wHR·HR)`
/// `/ (AB + BB - IBB + SF + HBP)`
///
/// Unintentional walks (`BB - IBB`) are what carry weight; intentional walks
/// are excluded from both numerator and denominator because they reflect the
/// situation rather than the batter's performance.
#[allow(clippy::too_many_arguments)]
pub fn woba(
    weights: &WobaWeights,
    singles: f64,
    doubles: f64,
    triples: f64,
    hr: f64,
    bb: f64,
    ibb: f64,
    hbp: f64,
    ab: f64,
    sf: f64,
) -> Option<f64> {
    let ubb = bb - ibb;
    let numerator = weights.w_bb * ubb
        + weights.w_hbp * hbp
        + weights.w_1b * singles
        + weights.w_2b * doubles
        + weights.w_3b * triples
        + weights.w_hr * hr;

    safe_div(numerator, ab + ubb + sf + hbp)
}

/// Fielding independent pitching: `(13·HR + 3·(BB + HBP) - 2·K) / IP + cFIP`.
///
/// `ip` is in baseball notation (`190.2` = 190⅔ innings); see [`crate::ip`].
pub fn fip(hr: f64, bb: f64, hbp: f64, k: f64, ip: f64, c_fip: f64) -> Result<Option<f64>> {
    let innings = ip_to_innings(ip)?;
    Ok(safe_div(13.0 * hr + 3.0 * (bb + hbp) - 2.0 * k, innings).map(|rate| rate + c_fip))
}

/// Expected FIP: FIP with the pitcher's home runs replaced by the league
/// home-run-per-fly-ball rate applied to their own fly balls.
///
/// Uses the same `cFIP` constant as [`fip`].
pub fn xfip(
    fb: f64,
    bb: f64,
    hbp: f64,
    k: f64,
    ip: f64,
    lg_hr_per_fb: f64,
    c_fip: f64,
) -> Result<Option<f64>> {
    fip(fb * lg_hr_per_fb, bb, hbp, k, ip, c_fip)
}

/// Earned run average: `9 · ER / IP`.
pub fn era(er: f64, ip: f64) -> Result<Option<f64>> {
    let innings = ip_to_innings(ip)?;
    Ok(safe_div(9.0 * er, innings))
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
        // singles = 150 - 30 - 5 - 25 = 90; TB = 90 + 60 + 15 + 100 = 265
        assert_eq!(singles(H, DOUBLES, TRIPLES, HR), 90.0);
        assert_eq!(total_bases(H, DOUBLES, TRIPLES, HR), 265.0);
    }

    #[test]
    fn slg_matches_hand_computation() {
        assert!((slg_from_hits(H, DOUBLES, TRIPLES, HR, AB).unwrap() - 0.53).abs() < 1e-12);
    }

    #[test]
    fn avg_matches_hand_computation() {
        assert!((avg(H, AB).unwrap() - 0.30).abs() < 1e-12);
    }

    #[test]
    fn iso_is_slg_minus_avg() {
        let direct = iso_from_hits(H, DOUBLES, TRIPLES, HR, AB).unwrap();
        let derived = iso(
            slg_from_hits(H, DOUBLES, TRIPLES, HR, AB).unwrap(),
            avg(H, AB).unwrap(),
        )
        .unwrap();
        assert!((direct - derived).abs() < 1e-12);
        assert!((direct - 0.23).abs() < 1e-12);
    }

    #[test]
    fn babip_matches_hand_computation() {
        // (150 - 25) / (500 - 100 - 25 + 5) = 125 / 380
        let expected = 125.0 / 380.0;
        assert!((babip(H, HR, AB, 100.0, SF).unwrap() - expected).abs() < 1e-12);
    }

    #[test]
    fn woba_matches_hand_computation() {
        let w = WobaWeights {
            w_bb: 0.69,
            w_hbp: 0.72,
            w_1b: 0.88,
            w_2b: 1.24,
            w_3b: 1.57,
            w_hr: 2.00,
        };
        // uBB = 60 - 10 = 50
        // num = .69*50 + .72*5 + .88*90 + 1.24*30 + 1.57*5 + 2.00*25
        //     = 34.5 + 3.6 + 79.2 + 37.2 + 7.85 + 50 = 212.35
        // den = 500 + 50 + 5 + 5 = 560
        let got = woba(&w, 90.0, DOUBLES, TRIPLES, HR, BB, 10.0, HBP, AB, SF).unwrap();
        assert!((got - 212.35 / 560.0).abs() < 1e-12);
    }

    #[test]
    fn fip_uses_thirds_notation_for_innings() {
        // 200.1 IP = 601 outs = 200.333... innings
        // (13*20 + 3*(50+5) - 2*200) / 200.3333 + 3.10
        let numerator = 13.0 * 20.0 + 3.0 * (50.0 + 5.0) - 2.0 * 200.0;
        let expected = numerator / (601.0 / 3.0) + 3.10;
        let got = fip(20.0, 50.0, 5.0, 200.0, 200.1, 3.10).unwrap().unwrap();
        assert!((got - expected).abs() < 1e-12);
    }

    #[test]
    fn fip_rejects_invalid_innings_notation() {
        assert!(fip(20.0, 50.0, 5.0, 200.0, 200.5, 3.10).is_err());
    }

    #[test]
    fn xfip_equals_fip_with_expected_home_runs() {
        // 100 fly balls at a 12% league rate = 12 expected HR
        let x = xfip(100.0, 50.0, 5.0, 200.0, 200.0, 0.12, 3.10)
            .unwrap()
            .unwrap();
        let f = fip(12.0, 50.0, 5.0, 200.0, 200.0, 3.10).unwrap().unwrap();
        assert!((x - f).abs() < 1e-12);
    }

    #[test]
    fn era_is_nine_earned_runs_per_inning() {
        // 70 ER over 200.1 IP (601 outs)
        let expected = 9.0 * 70.0 / (601.0 / 3.0);
        assert!((era(70.0, 200.1).unwrap().unwrap() - expected).abs() < 1e-12);
    }

    #[test]
    fn zero_denominators_yield_none() {
        assert_eq!(avg(0.0, 0.0), None);
        assert_eq!(slg(0.0, 0.0), None);
        assert_eq!(obp(0.0, 0.0, 0.0, 0.0, 0.0), None);
        assert_eq!(babip(0.0, 0.0, 0.0, 0.0, 0.0), None);
        assert_eq!(fip(0.0, 0.0, 0.0, 0.0, 0.0, 3.1).unwrap(), None);
        assert_eq!(era(0.0, 0.0).unwrap(), None);
    }
}
