//! Conventions specific to Baseball Savant's percentile leaderboards.
//!
//! Savant qualifies players more loosely than MLB's official rate-stat
//! thresholds, deliberately widening the population its bubbles are drawn
//! against: 2.1 plate appearances per team game for batters against MLB's
//! official 3.1, and 1.25 per team game for pitchers.
//!
//! # What is not encoded here
//!
//! Savant does not publish its tie-breaking rule, nor definitively whether the
//! displayed scale is 0–100 or 1–100 (the bubbles are widely observed to bottom
//! out at 1, which suggests a display clamp). Rather than guess, those are
//! parameters — see [`crate::percentile::TiePolicy`] and
//! [`crate::percentile::Scale`].
//!
//! Which metrics are inverted is also not hardcoded, because direction is a
//! property of the metric *in context*: strikeout rate is bad for a hitter and
//! good for a pitcher. Callers pass [`crate::percentile::Direction`]
//! explicitly.

/// Games in a modern full MLB season.
pub const FULL_SEASON_GAMES: f64 = 162.0;

/// Plate appearances per team game required for a batter to qualify.
pub const BATTER_PA_PER_GAME: f64 = 2.1;

/// Plate appearances faced per team game required for a pitcher to qualify.
pub const PITCHER_PA_PER_GAME: f64 = 1.25;

/// Minimum plate appearances for a batter to appear on a Savant leaderboard.
///
/// About 340 over a 162-game season, against MLB's official 502.
pub fn batter_qualifier(team_games: f64) -> f64 {
    BATTER_PA_PER_GAME * team_games
}

/// Minimum batters faced for a pitcher to appear on a Savant leaderboard.
///
/// About 203 over a 162-game season.
pub fn pitcher_qualifier(team_games: f64) -> f64 {
    PITCHER_PA_PER_GAME * team_games
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_season_thresholds_match_the_published_figures() {
        assert!((batter_qualifier(FULL_SEASON_GAMES) - 340.2).abs() < 1e-9);
        assert!((pitcher_qualifier(FULL_SEASON_GAMES) - 202.5).abs() < 1e-9);
    }

    #[test]
    fn savant_qualifies_more_players_than_the_official_rate_stat_threshold() {
        // MLB's official batting-title threshold is 3.1 PA per team game.
        let official = 3.1 * FULL_SEASON_GAMES;
        assert!(batter_qualifier(FULL_SEASON_GAMES) < official);
    }

    #[test]
    fn shortened_seasons_scale_down() {
        // The 2020 season ran 60 games.
        assert!((batter_qualifier(60.0) - 126.0).abs() < 1e-9);
    }
}
