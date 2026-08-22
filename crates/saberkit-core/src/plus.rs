//! The "plus" family: statistics normalized so that 100 is league average and
//! **higher is better**.
//!
//! Park factors are on the 100-scale throughout (100 = neutral), matching how
//! Baseball-Reference and FanGraphs publish them. Some of the source formulas
//! are written in terms of a decimal ratio instead; the conversion happens here
//! so callers never have to track which convention a given statistic wants.

use crate::util::{finite, pf_ratio, safe_div};

/// OPS+: on-base plus slugging against league average, park-adjusted.
///
/// `100 · (OBP/lgOBP + SLG/lgSLG - 1) / (PF/100)`
///
/// Note this is *not* simply `OPS/lgOPS` — on-base and slugging are normalized
/// separately, which is why a high-OBP player rates better here than raw OPS
/// suggests.
///
/// Approximate: Baseball-Reference park-adjusts the league components
/// individually inside its pipeline, so expect agreement to within a point or
/// two rather than exactly.
pub fn ops_plus(obp: f64, slg: f64, lg_obp: f64, lg_slg: f64, park_factor: f64) -> Option<f64> {
    let on_base = safe_div(obp, lg_obp)?;
    let slugging = safe_div(slg, lg_slg)?;
    safe_div(100.0 * (on_base + slugging - 1.0), pf_ratio(park_factor))
}

/// sOPS+: a split measured against the **league's** average in that same split.
///
/// `100 · (splitOBP/lgSplitOBP + splitSLG/lgSplitSLG - 1)`
///
/// Answers "how good was this player against left-handers, compared to how
/// hitters generally do against left-handers?". No park adjustment: both sides
/// of the ratio already come from the same split.
pub fn sops_plus(
    split_obp: f64,
    split_slg: f64,
    lg_split_obp: f64,
    lg_split_slg: f64,
) -> Option<f64> {
    let on_base = safe_div(split_obp, lg_split_obp)?;
    let slugging = safe_div(split_slg, lg_split_slg)?;
    finite(100.0 * (on_base + slugging - 1.0))
}

/// tOPS+: a split measured against the **player's own** overall performance.
///
/// `100 · (splitOBP/totalOBP + splitSLG/totalSLG - 1)`
///
/// Answers "how did this player do against left-handers compared to himself?".
/// 100 means the split matched his overall line.
pub fn tops_plus(split_obp: f64, split_slg: f64, total_obp: f64, total_slg: f64) -> Option<f64> {
    let on_base = safe_div(split_obp, total_obp)?;
    let slugging = safe_div(split_slg, total_slg)?;
    finite(100.0 * (on_base + slugging - 1.0))
}

/// ERA+: earned run average against league average, park-adjusted.
///
/// `100 · lgERA · (PF/100) / ERA`
///
/// Inverted relative to ERA itself, so higher is better. A pitcher in a hitter's
/// park (PF above 100) is credited for the tougher environment.
///
/// Approximate: Baseball-Reference uses multi-year regressed park factors that
/// the caller must supply to match published figures.
pub fn era_plus(era: f64, lg_era: f64, park_factor: f64) -> Option<f64> {
    safe_div(100.0 * lg_era * pf_ratio(park_factor), era)
}

/// Weighted runs above average: `((wOBA - lgwOBA) / wOBAScale) · PA`.
pub fn wraa(woba: f64, pa: f64, lg_woba: f64, woba_scale: f64) -> Option<f64> {
    let rate = safe_div(woba - lg_woba, woba_scale)?;
    finite(rate * pa)
}

/// Weighted runs created: `((wOBA - lgwOBA)/wOBAScale + lgR/PA) · PA`.
pub fn wrc(woba: f64, pa: f64, lg_woba: f64, woba_scale: f64, lg_r_pa: f64) -> Option<f64> {
    let rate = safe_div(woba - lg_woba, woba_scale)?;
    finite((rate + lg_r_pa) * pa)
}

/// wRC+: weighted runs created against league average, park-adjusted.
///
/// `(((wRAA/PA + lgR/PA) + (lgR/PA - PF·lgR/PA)) / lgwRC/PA) · 100`
///
/// `lg_wrc_pa` should exclude pitchers hitting, per FanGraphs' definition.
///
/// Note the park term uses the park factor as a **decimal ratio** in FanGraphs'
/// published formula while ERA- uses the 100-scale; `park_factor` is taken on
/// the 100-scale here and converted internally, so both behave consistently.
///
/// Approximate: FanGraphs applies a further league adjustment beyond the
/// published formula.
///
/// Plate appearances are deliberately absent from the signature: the published
/// formula divides `wRAA` by `PA` and `wRAA` is itself proportional to `PA`, so
/// the term cancels. wRC+ is a pure rate.
pub fn wrc_plus(
    woba: f64,
    lg_woba: f64,
    woba_scale: f64,
    lg_r_pa: f64,
    lg_wrc_pa: f64,
    park_factor: f64,
) -> Option<f64> {
    let wraa_per_pa = safe_div(woba - lg_woba, woba_scale)?;
    let park_term = lg_r_pa - pf_ratio(park_factor) * lg_r_pa;
    safe_div(100.0 * (wraa_per_pa + lg_r_pa + park_term), lg_wrc_pa)
}

#[cfg(test)]
mod tests {
    use super::*;

    const NEUTRAL: f64 = 100.0;

    #[test]
    fn a_league_average_hitter_rates_exactly_one_hundred() {
        assert_eq!(ops_plus(0.320, 0.410, 0.320, 0.410, NEUTRAL), Some(100.0));
        assert_eq!(sops_plus(0.320, 0.410, 0.320, 0.410), Some(100.0));
        assert_eq!(tops_plus(0.320, 0.410, 0.320, 0.410), Some(100.0));
    }

    #[test]
    fn a_league_average_pitcher_rates_exactly_one_hundred() {
        assert_eq!(era_plus(4.00, 4.00, NEUTRAL), Some(100.0));
    }

    #[test]
    fn wrc_plus_is_one_hundred_for_a_league_average_hitter() {
        // wOBA == lgwOBA means wRAA/PA is zero, leaving lgR/PA over lgwRC/PA.
        let got = wrc_plus(0.320, 0.320, 1.25, 0.120, 0.120, NEUTRAL).unwrap();
        assert!((got - 100.0).abs() < 1e-9);
    }

    #[test]
    fn wrc_plus_is_a_rate_and_ignores_playing_time() {
        // Two hitters with the same wOBA rate identically regardless of PA,
        // which is why PA is not a parameter.
        let a = wrc_plus(0.400, 0.320, 1.25, 0.120, 0.120, NEUTRAL).unwrap();
        assert!(a > 100.0);
    }

    #[test]
    fn ops_plus_normalizes_on_base_and_slugging_separately() {
        // Two players with identical OPS but different shapes do not tie:
        // OPS+ rewards the one whose strength is in the scarcer component.
        let lg_obp = 0.320;
        let lg_slg = 0.410;
        let on_base_heavy = ops_plus(0.400, 0.410, lg_obp, lg_slg, NEUTRAL).unwrap();
        let power_heavy = ops_plus(0.320, 0.490, lg_obp, lg_slg, NEUTRAL).unwrap();
        assert!(on_base_heavy > power_heavy);
    }

    #[test]
    fn park_factor_raises_ops_plus_in_a_pitchers_park() {
        let neutral = ops_plus(0.400, 0.500, 0.320, 0.410, NEUTRAL).unwrap();
        // A pitcher-friendly park (PF below 100) makes the same line look better.
        let pitchers_park = ops_plus(0.400, 0.500, 0.320, 0.410, 95.0).unwrap();
        assert!(pitchers_park > neutral);
    }

    #[test]
    fn park_factor_raises_era_plus_in_a_hitters_park() {
        let neutral = era_plus(3.00, 4.00, NEUTRAL).unwrap();
        let hitters_park = era_plus(3.00, 4.00, 105.0).unwrap();
        assert!(hitters_park > neutral);
    }

    /// Barry Bonds, 2002: OBP .582, SLG .799 against an NL that posted roughly
    /// .331/.410, in a near-neutral park. Baseball-Reference lists OPS+ 268.
    ///
    /// Tolerance is wide because the league components and park factor here are
    /// approximations of B-Ref's internal values.
    #[test]
    fn reproduces_bonds_2002_ops_plus() {
        let got = ops_plus(0.582, 0.799, 0.331, 0.410, 101.0).unwrap();
        assert!(
            (got - 268.0).abs() < 2.0,
            "expected roughly 268, got {got:.1}"
        );
    }

    /// Pedro Martínez, 2000: a 1.74 ERA against an AL around 4.91, in Fenway.
    /// Baseball-Reference lists ERA+ 291, the highest ever by a qualified
    /// starter.
    #[test]
    fn reproduces_pedro_2000_era_plus() {
        let got = era_plus(1.74, 4.91, 103.0).unwrap();
        assert!(
            (got - 291.0).abs() < 2.0,
            "expected roughly 291, got {got:.1}"
        );
    }

    #[test]
    fn split_measures_differ_in_what_they_compare_against() {
        // A player who hits .350/.550 overall but .300/.450 versus lefties,
        // in a league that hits .320/.410 versus lefties.
        let versus_league = sops_plus(0.300, 0.450, 0.320, 0.410).unwrap();
        let versus_self = tops_plus(0.300, 0.450, 0.350, 0.550).unwrap();
        // He is still above the league in that split, but below his own norm.
        assert!(versus_league > 100.0);
        assert!(versus_self < 100.0);
    }

    #[test]
    fn wraa_is_zero_at_league_average() {
        assert_eq!(wraa(0.320, 600.0, 0.320, 1.25), Some(0.0));
    }

    #[test]
    fn wrc_equals_league_rate_at_league_average() {
        let got = wrc(0.320, 600.0, 0.320, 1.25, 0.120).unwrap();
        assert!((got - 72.0).abs() < 1e-9); // 0.120 * 600
    }

    #[test]
    fn zero_denominators_yield_none() {
        assert_eq!(ops_plus(0.320, 0.410, 0.0, 0.410, NEUTRAL), None);
        assert_eq!(era_plus(0.0, 4.00, NEUTRAL), None);
        assert_eq!(wraa(0.320, 600.0, 0.320, 0.0), None);
    }
}
