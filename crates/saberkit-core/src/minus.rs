//! The "minus" family: FanGraphs' pitching statistics normalized so that 100 is
//! league average and **lower is better**.
//!
//! These are the mirror image of [`crate::plus::era_plus`] in intent, but not
//! in arithmetic — FanGraphs applies the park adjustment additively to the
//! pitcher's own rate rather than multiplicatively to the league's, so the two
//! do not reduce to reciprocals except in a neutral park.

use crate::util::{pf_ratio, safe_div};

/// The shared shape of every "minus" statistic:
/// `100 · (stat + (stat - stat·PF/100)) / lgStat`.
///
/// Written the long way rather than algebraically simplified to
/// `100 · stat · (2 - PF/100) / lgStat` so it can be checked line-for-line
/// against FanGraphs' published form.
#[inline]
fn minus(stat: f64, lg_stat: f64, park_factor: f64) -> Option<f64> {
    let park_adjusted = stat + (stat - stat * pf_ratio(park_factor));
    safe_div(100.0 * park_adjusted, lg_stat)
}

/// ERA-: earned run average against league average, park-adjusted.
///
/// `lg_era` should be the pitcher's own league (AL or NL), not all of MLB.
pub fn era_minus(era: f64, lg_era: f64, park_factor: f64) -> Option<f64> {
    minus(era, lg_era, park_factor)
}

/// FIP-: fielding independent pitching against league average, park-adjusted.
pub fn fip_minus(fip: f64, lg_fip: f64, park_factor: f64) -> Option<f64> {
    minus(fip, lg_fip, park_factor)
}

/// xFIP-: expected FIP against league average, park-adjusted.
pub fn xfip_minus(xfip: f64, lg_xfip: f64, park_factor: f64) -> Option<f64> {
    minus(xfip, lg_xfip, park_factor)
}

#[cfg(test)]
mod tests {
    use super::*;

    const NEUTRAL: f64 = 100.0;

    #[test]
    fn a_league_average_pitcher_rates_exactly_one_hundred() {
        assert_eq!(era_minus(4.00, 4.00, NEUTRAL), Some(100.0));
        assert_eq!(fip_minus(3.90, 3.90, NEUTRAL), Some(100.0));
        assert_eq!(xfip_minus(4.10, 4.10, NEUTRAL), Some(100.0));
    }

    #[test]
    fn lower_is_better() {
        let good = era_minus(2.50, 4.00, NEUTRAL).unwrap();
        let bad = era_minus(5.50, 4.00, NEUTRAL).unwrap();
        assert!(good < 100.0);
        assert!(bad > 100.0);
    }

    #[test]
    fn a_hitters_park_improves_the_pitchers_rating() {
        // PF above 100 means a tougher park, so the same ERA rates better
        // (a lower ERA-).
        let neutral = era_minus(3.00, 4.00, NEUTRAL).unwrap();
        let hitters_park = era_minus(3.00, 4.00, 108.0).unwrap();
        assert!(hitters_park < neutral);
    }

    /// The published long form and its algebraic simplification must agree.
    #[test]
    fn matches_the_simplified_algebraic_form() {
        for pf in [90.0, 100.0, 112.0] {
            let published = era_minus(3.25, 4.10, pf).unwrap();
            let simplified = 100.0 * 3.25 * (2.0 - pf / 100.0) / 4.10;
            assert!((published - simplified).abs() < 1e-9);
        }
    }

    /// In a neutral park ERA- and ERA+ are reciprocal about 100; away from
    /// neutral they diverge, because the two systems adjust different sides.
    #[test]
    fn is_reciprocal_to_era_plus_only_in_a_neutral_park() {
        let minus = era_minus(3.00, 4.00, NEUTRAL).unwrap();
        let plus = crate::plus::era_plus(3.00, 4.00, NEUTRAL).unwrap();
        assert!((minus * plus - 10_000.0).abs() < 1e-6);

        let minus_park = era_minus(3.00, 4.00, 110.0).unwrap();
        let plus_park = crate::plus::era_plus(3.00, 4.00, 110.0).unwrap();
        assert!((minus_park * plus_park - 10_000.0).abs() > 1.0);
    }

    #[test]
    fn zero_league_value_yields_none() {
        assert_eq!(era_minus(3.00, 0.0, NEUTRAL), None);
    }
}
