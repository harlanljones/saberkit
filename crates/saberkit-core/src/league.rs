//! League context: the average-performance baselines every "plus" statistic
//! measures a player against.
//!
//! Which population those averages come from is a real methodological choice —
//! whether pitchers' hitting is included in `lgOBP`, whether the baseline is
//! one league or all of MLB. `saberkit` does not guess: league values are
//! *inputs*, either supplied directly or aggregated from counting stats the
//! caller has already filtered.

use crate::error::{Result, SaberError};
use crate::ip::outs_to_innings;
use crate::util::safe_div;

/// Linear-weight run values for each way of reaching base, used by wOBA.
///
/// These change every season. Bundled values are derived from Retrosheet
/// play-by-play; callers may also supply weights from another methodology.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WobaWeights {
    /// Run value of an unintentional walk.
    pub w_bb: f64,
    /// Run value of a hit by pitch.
    pub w_hbp: f64,
    /// Run value of a single.
    pub w_1b: f64,
    /// Run value of a double.
    pub w_2b: f64,
    /// Run value of a triple.
    pub w_3b: f64,
    /// Run value of a home run.
    pub w_hr: f64,
}

/// A season's league-average baselines.
///
/// Every field is optional because different statistics need different
/// subsets — computing OPS+ needs only `lg_obp` and `lg_slg`, and requiring a
/// caller to invent a `woba_scale` they will never use would be hostile.
/// Asking for a statistic whose inputs are missing raises
/// [`SaberError::InvalidConstants`] naming the absent constant, rather than
/// silently returning nulls.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct LeagueContext {
    /// Season these values describe, for provenance.
    pub season: Option<u16>,
    /// League on-base percentage.
    pub lg_obp: Option<f64>,
    /// League slugging percentage.
    pub lg_slg: Option<f64>,
    /// League earned run average.
    pub lg_era: Option<f64>,
    /// League fielding independent pitching.
    pub lg_fip: Option<f64>,
    /// League expected FIP.
    pub lg_xfip: Option<f64>,
    /// League weighted on-base average.
    pub lg_woba: Option<f64>,
    /// wOBA scale factor, converting wOBA points to runs.
    pub woba_scale: Option<f64>,
    /// The FIP constant, which puts FIP on the ERA scale.
    pub c_fip: Option<f64>,
    /// League runs per plate appearance.
    pub lg_r_pa: Option<f64>,
    /// League weighted runs created per plate appearance, excluding pitchers.
    pub lg_wrc_pa: Option<f64>,
    /// League home runs per fly ball, used by xFIP.
    pub lg_hr_per_fb: Option<f64>,
    /// Linear weights for wOBA.
    pub weights: Option<WobaWeights>,
}

impl LeagueContext {
    /// An empty context; fill in only the fields the statistics you need require.
    pub fn new() -> Self {
        Self::default()
    }

    /// Return bundled constants for a completed MLB season.
    ///
    /// The supported range and derivation provenance are documented in
    /// [`crate::season_constants`].
    pub fn for_season(season: u16) -> Result<Self> {
        crate::season_constants::for_season(season)
    }

    /// Fetch a required constant, or explain precisely which one is missing.
    ///
    /// A null player row is ordinary missing data, but a missing or non-finite
    /// league constant poisons every result it touches, so it fails loudly.
    pub fn require(&self, name: &'static str, value: Option<f64>) -> Result<f64> {
        match value {
            Some(v) if v.is_finite() => Ok(v),
            Some(v) => Err(SaberError::InvalidConstants {
                name,
                reason: format!("value {v} is not finite"),
            }),
            None => Err(SaberError::InvalidConstants {
                name,
                reason: "not set on this LeagueContext".to_string(),
            }),
        }
    }

    /// Fetch the wOBA weights, or explain that they are missing.
    pub fn require_weights(&self) -> Result<WobaWeights> {
        self.weights.ok_or(SaberError::InvalidConstants {
            name: "weights",
            reason: "wOBA weights are not set on this LeagueContext".to_string(),
        })
    }
}

/// Running totals of a league's counting stats.
///
/// League rates are computed by **summing the counting stats and then taking
/// the ratio** — never by averaging players' individual rates. Those two give
/// different answers, because the mean of ratios weights a 20-plate-appearance
/// September call-up the same as a 700-plate-appearance regular. Getting this
/// backwards is the most common bug in homemade plus-stat code.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct LeagueTotals {
    /// At-bats.
    pub ab: f64,
    /// Hits.
    pub h: f64,
    /// Doubles.
    pub doubles: f64,
    /// Triples.
    pub triples: f64,
    /// Home runs.
    pub hr: f64,
    /// Walks.
    pub bb: f64,
    /// Intentional walks.
    pub ibb: f64,
    /// Hit by pitch.
    pub hbp: f64,
    /// Sacrifice flies.
    pub sf: f64,
    /// Strikeouts.
    pub k: f64,
    /// Earned runs.
    pub er: f64,
    /// Outs recorded by pitchers, i.e. innings pitched times three.
    pub outs: f64,
    /// Runs scored.
    pub r: f64,
    /// Plate appearances.
    pub pa: f64,
}

impl LeagueTotals {
    /// League on-base percentage from the summed totals.
    pub fn lg_obp(&self) -> Option<f64> {
        crate::rates::obp(self.h, self.bb, self.hbp, self.ab, self.sf)
    }

    /// League slugging percentage from the summed totals.
    pub fn lg_slg(&self) -> Option<f64> {
        crate::rates::slg_from_hits(self.h, self.doubles, self.triples, self.hr, self.ab)
    }

    /// League earned run average from the summed totals.
    pub fn lg_era(&self) -> Option<f64> {
        safe_div(9.0 * self.er, outs_to_innings_f64(self.outs))
    }

    /// League runs per plate appearance.
    pub fn lg_r_pa(&self) -> Option<f64> {
        safe_div(self.r, self.pa)
    }

    /// League wOBA from the summed totals, given a season's weights.
    pub fn lg_woba(&self, weights: &WobaWeights) -> Option<f64> {
        let singles = crate::rates::singles(self.h, self.doubles, self.triples, self.hr);
        crate::rates::woba(
            weights,
            singles,
            self.doubles,
            self.triples,
            self.hr,
            self.bb,
            self.ibb,
            self.hbp,
            self.ab,
            self.sf,
        )
    }

    /// The FIP constant: `lgERA - (13·lgHR + 3·(lgBB + lgHBP) - 2·lgK) / lgIP`.
    ///
    /// This is what puts FIP on the same scale as ERA, so a 3.50 FIP reads like
    /// a 3.50 ERA.
    pub fn c_fip(&self) -> Option<f64> {
        let innings = outs_to_innings_f64(self.outs);
        let raw = safe_div(
            13.0 * self.hr + 3.0 * (self.bb + self.hbp) - 2.0 * self.k,
            innings,
        )?;
        Some(self.lg_era()? - raw)
    }

    /// Build a [`LeagueContext`] from these totals.
    ///
    /// `weights` is required to derive `lg_woba`; without it that field is left
    /// unset. `woba_scale` cannot be derived from counting stats at all — it
    /// comes from a run-expectancy model — so it is never populated here and
    /// must be supplied by the caller for wRC+.
    pub fn to_context(&self, season: Option<u16>, weights: Option<WobaWeights>) -> LeagueContext {
        LeagueContext {
            season,
            lg_obp: self.lg_obp(),
            lg_slg: self.lg_slg(),
            lg_era: self.lg_era(),
            lg_r_pa: self.lg_r_pa(),
            c_fip: self.c_fip(),
            lg_woba: weights.as_ref().and_then(|w| self.lg_woba(w)),
            weights,
            ..LeagueContext::default()
        }
    }
}

/// Convert a raw out count (possibly fractional after summing) to innings.
fn outs_to_innings_f64(outs: f64) -> f64 {
    if outs.fract() == 0.0 && outs >= 0.0 && outs <= f64::from(u32::MAX) {
        outs_to_innings(outs as u32)
    } else {
        outs / 3.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn totals() -> LeagueTotals {
        LeagueTotals {
            ab: 1000.0,
            h: 250.0,
            doubles: 50.0,
            triples: 5.0,
            hr: 30.0,
            bb: 100.0,
            ibb: 10.0,
            hbp: 10.0,
            sf: 8.0,
            k: 220.0,
            er: 120.0,
            outs: 810.0, // 270 innings
            r: 130.0,
            pa: 1120.0,
        }
    }

    #[test]
    fn league_rates_come_from_summed_totals() {
        let t = totals();
        assert!((t.lg_obp().unwrap() - 360.0 / 1118.0).abs() < 1e-12);
        // singles = 250 - 50 - 5 - 30 = 165; TB = 165 + 100 + 15 + 120 = 400
        assert!((t.lg_slg().unwrap() - 0.400).abs() < 1e-12);
        assert!((t.lg_era().unwrap() - 9.0 * 120.0 / 270.0).abs() < 1e-12);
    }

    /// The distinction that matters: summing then dividing is not the same as
    /// averaging per-player rates, because the latter ignores playing time.
    #[test]
    fn summing_totals_differs_from_averaging_player_rates() {
        // A regular who hits .300 in 600 AB and a call-up who hits .100 in 10.
        let regular_avg = 180.0 / 600.0;
        let callup_avg = 1.0 / 10.0;
        let mean_of_rates = (regular_avg + callup_avg) / 2.0;

        let pooled = LeagueTotals {
            ab: 610.0,
            h: 181.0,
            ..Default::default()
        };
        let pooled_avg = crate::rates::avg(pooled.h, pooled.ab).unwrap();

        assert!((pooled_avg - 181.0 / 610.0).abs() < 1e-12);
        // The mean of rates is far lower — it gives the call-up equal weight.
        assert!((mean_of_rates - pooled_avg).abs() > 0.09);
    }

    #[test]
    fn c_fip_puts_fip_on_the_era_scale() {
        let t = totals();
        let c = t.c_fip().unwrap();
        // A pitcher with exactly league-average peripherals over league-average
        // innings should post a FIP equal to the league ERA.
        let f = crate::rates::fip(t.hr, t.bb, t.hbp, t.k, 270.0, c)
            .unwrap()
            .unwrap();
        assert!((f - t.lg_era().unwrap()).abs() < 1e-9);
    }

    #[test]
    fn missing_constants_are_reported_by_name() {
        let ctx = LeagueContext::new();
        let err = ctx.require("lg_obp", ctx.lg_obp).unwrap_err();
        assert!(matches!(
            err,
            SaberError::InvalidConstants { name: "lg_obp", .. }
        ));
        assert!(err.to_string().contains("lg_obp"));
    }

    #[test]
    fn non_finite_constants_are_rejected() {
        let ctx = LeagueContext {
            lg_obp: Some(f64::NAN),
            ..Default::default()
        };
        assert!(ctx.require("lg_obp", ctx.lg_obp).is_err());
    }

    #[test]
    fn to_context_leaves_underivable_fields_unset() {
        let ctx = totals().to_context(Some(2024), None);
        assert!(ctx.lg_obp.is_some());
        // wOBA scale needs a run-expectancy model, not counting stats.
        assert!(ctx.woba_scale.is_none());
        // lg_woba needs weights, which were not supplied.
        assert!(ctx.lg_woba.is_none());
    }
}
