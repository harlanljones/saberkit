//! League percentile rankings — the 1–100 "bubbles" on a Baseball Savant
//! player page.
//!
//! # Tie handling is a deliberate parameter, not a guess
//!
//! Savant does not publish how it breaks ties, so this module does not pretend
//! to know. [`TiePolicy`] exposes the choice instead, defaulting to
//! [`TiePolicy::Average`] (the midrank convention, matching SciPy's
//! `"mean"`). If you need to reproduce a specific published number exactly,
//! that is the knob to turn.

use crate::error::{Result, SaberError};

/// Whether a larger value is better or worse for the metric being ranked.
///
/// This is a property of *the metric in context*, not of the metric's name:
/// strikeout rate is bad for a hitter and good for a pitcher.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Direction {
    /// Larger values rank higher — exit velocity, wOBA, strikeout rate for a pitcher.
    #[default]
    HigherIsBetter,
    /// Smaller values rank higher — chase rate, whiff rate, xERA.
    LowerIsBetter,
}

/// How to score a value that appears more than once in the distribution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TiePolicy {
    /// Midpoint of the tied group's span. The usual convention.
    #[default]
    Average,
    /// Fraction of the population strictly below the value.
    Strict,
    /// Fraction of the population at or below the value.
    Weak,
}

/// Output scaling for a percentile.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Scale {
    /// The raw percentile, 0.0 to 100.0.
    #[default]
    Continuous,
    /// Rounded and clamped to 1–100, matching how Savant displays its bubbles.
    Savant,
}

impl Scale {
    /// Apply this scaling to a raw percentile.
    #[inline]
    pub fn apply(self, percentile: f64) -> f64 {
        match self {
            Scale::Continuous => percentile,
            Scale::Savant => percentile.round().clamp(1.0, 100.0),
        }
    }
}

/// A sorted population of values, ready for repeated percentile queries.
///
/// Building this once and querying it many times is the point: construction
/// sorts in `O(n log n)`, after which each lookup is two binary searches.
///
/// `LowerIsBetter` metrics are negated at ingest *and* at query, so the stored
/// vector is always in "larger is better" orientation and the lookup path has a
/// single branch-free form.
#[derive(Debug, Clone)]
pub struct LeagueDistribution {
    sorted: Vec<f64>,
    direction: Direction,
    tie: TiePolicy,
}

impl LeagueDistribution {
    /// Build a distribution from a population of values.
    ///
    /// Nulls and non-finite values are dropped. An empty population is an
    /// error: a percentile against nothing is meaningless, and returning nulls
    /// would hide a filter that matched nobody.
    pub fn new<I>(values: I, direction: Direction, tie: TiePolicy) -> Result<Self>
    where
        I: IntoIterator<Item = Option<f64>>,
    {
        let mut sorted: Vec<f64> = values
            .into_iter()
            .flatten()
            .filter(|v| v.is_finite())
            .map(|v| orient(v, direction))
            .collect();

        if sorted.is_empty() {
            return Err(SaberError::EmptyDistribution {
                reason: "no finite values remained after filtering".to_string(),
            });
        }

        sorted.sort_unstable_by(f64::total_cmp);

        Ok(Self {
            sorted,
            direction,
            tie,
        })
    }

    /// The percentile of `value` within this distribution, 0.0 to 100.0.
    ///
    /// Returns `None` for a non-finite input.
    pub fn percentile_of(&self, value: f64) -> Option<f64> {
        if !value.is_finite() {
            return None;
        }

        let target = orient(value, self.direction);
        let n = self.sorted.len() as f64;

        // Two binary searches give the strictly-below and at-or-below counts,
        // from which every tie policy is simple arithmetic.
        let below = self.sorted.partition_point(|&x| x < target) as f64;
        let at_or_below = self.sorted.partition_point(|&x| x <= target) as f64;

        Some(match self.tie {
            TiePolicy::Strict => 100.0 * below / n,
            TiePolicy::Weak => 100.0 * at_or_below / n,
            TiePolicy::Average => 100.0 * (below + at_or_below) / (2.0 * n),
        })
    }

    /// The value standing at a given percentile — the inverse of
    /// [`Self::percentile_of`].
    pub fn value_at_percentile(&self, percentile: f64) -> Option<f64> {
        if !percentile.is_finite() {
            return None;
        }

        let n = self.sorted.len();
        let position = (percentile.clamp(0.0, 100.0) / 100.0) * (n - 1) as f64;
        let index = (position.round() as usize).min(n - 1);

        Some(orient(self.sorted[index], self.direction))
    }

    /// Number of values in the distribution.
    pub fn len(&self) -> usize {
        self.sorted.len()
    }

    /// Whether the distribution is empty. Always false — construction rejects
    /// empty populations — but present because clippy expects it alongside
    /// `len`.
    pub fn is_empty(&self) -> bool {
        self.sorted.is_empty()
    }

    /// The worst value in the population, in the metric's own units.
    pub fn worst(&self) -> f64 {
        orient(self.sorted[0], self.direction)
    }

    /// The best value in the population, in the metric's own units.
    pub fn best(&self) -> f64 {
        orient(self.sorted[self.sorted.len() - 1], self.direction)
    }

    /// The arithmetic mean of the population.
    pub fn mean(&self) -> f64 {
        let sum: f64 = self.sorted.iter().sum();
        orient(sum / self.sorted.len() as f64, self.direction)
    }

    /// Direction this distribution was built with.
    pub fn direction(&self) -> Direction {
        self.direction
    }

    /// Tie policy this distribution was built with.
    pub fn tie(&self) -> TiePolicy {
        self.tie
    }
}

/// Flip a value so that "better" is always "larger".
#[inline]
fn orient(value: f64, direction: Direction) -> f64 {
    match direction {
        Direction::HigherIsBetter => value,
        Direction::LowerIsBetter => -value,
    }
}

/// Rank a population against itself, honouring a playing-time qualifier.
///
/// Players below `qualifier_min` are excluded from the distribution *and*
/// receive `None` — they neither get a rank nor distort anyone else's. This is
/// what makes the result comparable to a Savant leaderboard, where a
/// 20-plate-appearance call-up does not shift the population.
pub fn percentile_ranks(
    values: &[Option<f64>],
    qualifier: Option<(&[Option<f64>], f64)>,
    direction: Direction,
    tie: TiePolicy,
    scale: Scale,
) -> Result<Vec<Option<f64>>> {
    if let Some((q, _)) = qualifier {
        if q.len() != values.len() {
            return Err(SaberError::LengthMismatch {
                left_name: "values",
                left: values.len(),
                right_name: "qualifier",
                right: q.len(),
            });
        }
    }

    let qualifies = |i: usize| match qualifier {
        None => true,
        Some((q, min)) => q[i].is_some_and(|v| v >= min),
    };

    let population = (0..values.len())
        .filter(|&i| qualifies(i))
        .map(|i| values[i]);

    let distribution = LeagueDistribution::new(population, direction, tie)?;

    Ok((0..values.len())
        .map(|i| {
            if !qualifies(i) {
                return None;
            }
            values[i]
                .and_then(|v| distribution.percentile_of(v))
                .map(|p| scale.apply(p))
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn some(values: &[f64]) -> Vec<Option<f64>> {
        values.iter().copied().map(Some).collect()
    }

    #[test]
    fn percentiles_increase_with_value_when_higher_is_better() {
        let d = LeagueDistribution::new(
            some(&[1.0, 2.0, 3.0, 4.0, 5.0]),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();

        let a = d.percentile_of(2.0).unwrap();
        let b = d.percentile_of(4.0).unwrap();
        assert!(a < b, "{a} should rank below {b}");
    }

    #[test]
    fn direction_inverts_the_ranking() {
        let values = some(&[1.0, 2.0, 3.0, 4.0, 5.0]);
        let high = LeagueDistribution::new(
            values.clone(),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        let low =
            LeagueDistribution::new(values, Direction::LowerIsBetter, TiePolicy::Average).unwrap();

        // Under the midrank convention the two are exact mirrors about 50.
        for v in [1.0, 2.0, 3.0, 4.0, 5.0] {
            let h = high.percentile_of(v).unwrap();
            let l = low.percentile_of(v).unwrap();
            assert!((h + l - 100.0).abs() < 1e-9, "{v}: {h} + {l} != 100");
        }
    }

    /// The mirror identity holds for `Average` but not for the one-sided
    /// policies — worth pinning so the semantics do not drift.
    #[test]
    fn the_mirror_identity_is_specific_to_the_average_policy() {
        let values = some(&[1.0, 2.0, 2.0, 3.0]);
        let high =
            LeagueDistribution::new(values.clone(), Direction::HigherIsBetter, TiePolicy::Strict)
                .unwrap();
        let low =
            LeagueDistribution::new(values, Direction::LowerIsBetter, TiePolicy::Strict).unwrap();

        let h = high.percentile_of(2.0).unwrap();
        let l = low.percentile_of(2.0).unwrap();
        assert!((h + l - 100.0).abs() > 1e-9);
    }

    #[test]
    fn tie_policies_bracket_each_other() {
        let d_strict = LeagueDistribution::new(
            some(&[1.0, 2.0, 2.0, 2.0, 3.0]),
            Direction::HigherIsBetter,
            TiePolicy::Strict,
        )
        .unwrap();
        let d_avg = LeagueDistribution::new(
            some(&[1.0, 2.0, 2.0, 2.0, 3.0]),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        let d_weak = LeagueDistribution::new(
            some(&[1.0, 2.0, 2.0, 2.0, 3.0]),
            Direction::HigherIsBetter,
            TiePolicy::Weak,
        )
        .unwrap();

        let strict = d_strict.percentile_of(2.0).unwrap();
        let average = d_avg.percentile_of(2.0).unwrap();
        let weak = d_weak.percentile_of(2.0).unwrap();

        assert_eq!(strict, 20.0); // 1 of 5 below
        assert_eq!(weak, 80.0); // 4 of 5 at or below
        assert_eq!(average, 50.0); // midpoint
        assert!(strict < average && average < weak);
    }

    #[test]
    fn percentiles_stay_within_bounds() {
        let d = LeagueDistribution::new(
            some(&[1.0, 2.0, 3.0]),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        for v in [-100.0, 0.0, 1.0, 2.0, 3.0, 100.0] {
            let p = d.percentile_of(v).unwrap();
            assert!((0.0..=100.0).contains(&p), "{v} gave {p}");
        }
    }

    #[test]
    fn nulls_and_non_finite_values_are_dropped_from_the_population() {
        let d = LeagueDistribution::new(
            vec![Some(1.0), None, Some(f64::NAN), Some(3.0)],
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        assert_eq!(d.len(), 2);
    }

    #[test]
    fn an_empty_population_is_an_error_not_a_null() {
        let err = LeagueDistribution::new(
            vec![None, None],
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap_err();
        assert!(matches!(err, SaberError::EmptyDistribution { .. }));
    }

    #[test]
    fn value_at_percentile_inverts_percentile_of() {
        let d = LeagueDistribution::new(
            some(&[10.0, 20.0, 30.0, 40.0, 50.0]),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        for v in [10.0, 30.0, 50.0] {
            let p = d.percentile_of(v).unwrap();
            assert_eq!(d.value_at_percentile(p), Some(v));
        }
    }

    #[test]
    fn best_and_worst_report_in_the_metrics_own_units() {
        let d = LeagueDistribution::new(
            some(&[2.5, 3.5, 4.5]),
            Direction::LowerIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        // Lower is better, so 2.5 is the best ERA in the group.
        assert_eq!(d.best(), 2.5);
        assert_eq!(d.worst(), 4.5);
        assert!((d.mean() - 3.5).abs() < 1e-12);
    }

    #[test]
    fn savant_scale_rounds_and_clamps_to_one_through_hundred() {
        assert_eq!(Scale::Savant.apply(0.0), 1.0);
        assert_eq!(Scale::Savant.apply(0.4), 1.0);
        assert_eq!(Scale::Savant.apply(50.6), 51.0);
        assert_eq!(Scale::Savant.apply(100.0), 100.0);
    }

    #[test]
    fn unqualified_players_get_no_rank_and_do_not_shift_the_population() {
        let values = some(&[1.0, 2.0, 3.0, 999.0]);
        let playing_time = some(&[600.0, 600.0, 600.0, 5.0]);

        let with_qualifier = percentile_ranks(
            &values,
            Some((&playing_time, 100.0)),
            Direction::HigherIsBetter,
            TiePolicy::Average,
            Scale::Continuous,
        )
        .unwrap();

        // The 5-PA outlier is excluded entirely.
        assert_eq!(with_qualifier[3], None);

        // And the qualified players rank exactly as they would on their own.
        let without = percentile_ranks(
            &some(&[1.0, 2.0, 3.0]),
            None,
            Direction::HigherIsBetter,
            TiePolicy::Average,
            Scale::Continuous,
        )
        .unwrap();
        assert_eq!(&with_qualifier[..3], &without[..]);
    }

    #[test]
    fn a_qualifier_that_excludes_nobody_changes_nothing() {
        let values = some(&[1.0, 2.0, 3.0]);
        let playing_time = some(&[600.0, 700.0, 800.0]);

        let filtered = percentile_ranks(
            &values,
            Some((&playing_time, 100.0)),
            Direction::HigherIsBetter,
            TiePolicy::Average,
            Scale::Continuous,
        )
        .unwrap();
        let unfiltered = percentile_ranks(
            &values,
            None,
            Direction::HigherIsBetter,
            TiePolicy::Average,
            Scale::Continuous,
        )
        .unwrap();

        assert_eq!(filtered, unfiltered);
    }

    #[test]
    fn qualifier_length_mismatch_is_an_error() {
        let values = some(&[1.0, 2.0, 3.0]);
        let playing_time = some(&[600.0]);
        let err = percentile_ranks(
            &values,
            Some((&playing_time, 100.0)),
            Direction::HigherIsBetter,
            TiePolicy::Average,
            Scale::Continuous,
        )
        .unwrap_err();
        assert!(matches!(err, SaberError::LengthMismatch { .. }));
    }

    #[test]
    fn a_single_element_population_is_the_hundredth_percentile() {
        let d =
            LeagueDistribution::new(some(&[42.0]), Direction::HigherIsBetter, TiePolicy::Average)
                .unwrap();
        assert_eq!(d.percentile_of(42.0), Some(50.0)); // midrank of a lone value
        assert_eq!(d.percentile_of(43.0), Some(100.0));
        assert_eq!(d.percentile_of(41.0), Some(0.0));
    }

    #[test]
    fn an_all_tied_population_ranks_everyone_at_the_midpoint() {
        let d = LeagueDistribution::new(
            some(&[7.0; 10]),
            Direction::HigherIsBetter,
            TiePolicy::Average,
        )
        .unwrap();
        assert_eq!(d.percentile_of(7.0), Some(50.0));
    }
}
