//! Bundled, reproducible MLB season constants derived from Retrosheet.
//!
//! The constants use all batters in completed regular-season MLB games. They
//! are generated from Retrosheet play-by-play by
//! `scripts/generate_season_constants.py`; no publisher's constants table is
//! copied. See `NOTICE` for the required Retrosheet attribution.

use crate::error::{Result, SaberError};
use crate::league::{LeagueContext, WobaWeights};

#[derive(Debug, Clone, Copy)]
struct SeasonConstants {
    source_sha256: &'static str,
    season: u16,
    lg_obp: f64,
    lg_slg: f64,
    lg_era: f64,
    lg_fip: f64,
    lg_woba: f64,
    woba_scale: f64,
    c_fip: f64,
    lg_r_pa: f64,
    lg_wrc_pa: f64,
    w_bb: f64,
    w_hbp: f64,
    w_1b: f64,
    w_2b: f64,
    w_3b: f64,
    w_hr: f64,
}

include!("season_constants_generated.rs");

impl SeasonConstants {
    fn context(self) -> LeagueContext {
        LeagueContext {
            season: Some(self.season),
            lg_obp: Some(self.lg_obp),
            lg_slg: Some(self.lg_slg),
            lg_era: Some(self.lg_era),
            lg_fip: Some(self.lg_fip),
            lg_xfip: None,
            lg_woba: Some(self.lg_woba),
            woba_scale: Some(self.woba_scale),
            c_fip: Some(self.c_fip),
            lg_r_pa: Some(self.lg_r_pa),
            lg_wrc_pa: Some(self.lg_wrc_pa),
            lg_hr_per_fb: None,
            weights: Some(WobaWeights {
                w_bb: self.w_bb,
                w_hbp: self.w_hbp,
                w_1b: self.w_1b,
                w_2b: self.w_2b,
                w_3b: self.w_3b,
                w_hr: self.w_hr,
            }),
        }
    }
}

/// Return the completed-season context for `season`.
///
/// Supported seasons are [`FIRST_SEASON`] through [`LAST_SEASON`], inclusive.
/// Values are derived from Retrosheet regular-season play-by-play using all
/// MLB batters as the league population.
pub fn for_season(season: u16) -> Result<LeagueContext> {
    let index = usize::from(season.saturating_sub(FIRST_SEASON));
    SEASONS
        .get(index)
        .filter(|constants| constants.season == season)
        .copied()
        .map(SeasonConstants::context)
        .ok_or_else(|| SaberError::InvalidConstants {
            name: "season",
            reason: format!(
                "{season} is unavailable; supported completed seasons are {FIRST_SEASON}–{LAST_SEASON}"
            ),
        })
}

/// SHA-256 digest of the regular-season Retrosheet event files for `season`.
///
/// This allows generated rows to be audited against the exact source files.
pub fn source_sha256(season: u16) -> Option<&'static str> {
    let index = usize::from(season.checked_sub(FIRST_SEASON)?);
    SEASONS
        .get(index)
        .filter(|constants| constants.season == season)
        .map(|constants| constants.source_sha256)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn supported_range_is_contiguous_and_has_source_digests() {
        assert_eq!(SEASONS.len(), usize::from(LAST_SEASON - FIRST_SEASON + 1));
        for (offset, constants) in SEASONS.iter().enumerate() {
            assert_eq!(usize::from(constants.season - FIRST_SEASON), offset);
            assert_eq!(constants.source_sha256.len(), 64);
            assert!(constants
                .source_sha256
                .bytes()
                .all(|byte| byte.is_ascii_hexdigit()));
            let values = [
                constants.lg_obp,
                constants.lg_slg,
                constants.lg_era,
                constants.lg_fip,
                constants.lg_woba,
                constants.woba_scale,
                constants.c_fip,
                constants.lg_r_pa,
                constants.lg_wrc_pa,
                constants.w_bb,
                constants.w_hbp,
                constants.w_1b,
                constants.w_2b,
                constants.w_3b,
                constants.w_hr,
            ];
            assert!(values.into_iter().all(f64::is_finite));
            assert!(values.into_iter().all(|value| value > 0.0));
        }
    }

    #[test]
    fn league_woba_is_scaled_to_league_obp() {
        for constants in SEASONS {
            assert!((constants.lg_woba - constants.lg_obp).abs() < 1e-12);
            assert_eq!(constants.lg_wrc_pa, constants.lg_r_pa);
            assert_eq!(constants.lg_fip, constants.lg_era);
        }
    }

    #[test]
    fn known_2024_values_are_close_to_published_reference() {
        let context = for_season(2024).unwrap();
        let weights = context.weights.unwrap();
        assert!((context.c_fip.unwrap() - 3.166).abs() < 0.02);
        assert!((context.woba_scale.unwrap() - 1.242).abs() < 0.03);
        assert!((weights.w_bb - 0.689).abs() < 0.05);
        assert!((weights.w_hr - 2.050).abs() < 0.05);
    }

    #[test]
    fn unsupported_or_in_progress_seasons_are_errors() {
        assert!(for_season(FIRST_SEASON - 1).is_err());
        assert!(for_season(LAST_SEASON + 1).is_err());
    }
}
