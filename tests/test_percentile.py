"""The percentile engine — Savant-style league "bubbles"."""

from __future__ import annotations

import pytest

import saberkit

polars = pytest.importorskip("polars")


@pytest.fixture
def values() -> polars.Series:
    return polars.Series([1.0, 2.0, 3.0, 4.0, 5.0])


def test_percentiles_increase_with_value(values):
    d = saberkit.LeagueDistribution(values)
    assert d.percentile_of(2.0) < d.percentile_of(4.0)


def test_direction_mirrors_the_ranking(values):
    high = saberkit.LeagueDistribution(values, direction="higher_is_better")
    low = saberkit.LeagueDistribution(values, direction="lower_is_better")

    # Under the default midrank convention the two are exact mirrors about 50.
    for v in [1.0, 3.0, 5.0]:
        assert high.percentile_of(v) + low.percentile_of(v) == pytest.approx(100.0)


def test_lower_is_better_ranks_the_smallest_value_best():
    """Chase rate, whiff rate, and xERA all read this way."""
    eras = polars.Series([2.50, 3.50, 4.50, 5.50])
    d = saberkit.LeagueDistribution(eras, direction="lower_is_better")

    assert d.percentile_of(2.50) > d.percentile_of(5.50)
    assert d.best == pytest.approx(2.50)
    assert d.worst == pytest.approx(5.50)


def test_tie_policies_bracket_each_other():
    tied = polars.Series([1.0, 2.0, 2.0, 2.0, 3.0])

    strict = saberkit.LeagueDistribution(tied, tie="strict").percentile_of(2.0)
    average = saberkit.LeagueDistribution(tied, tie="average").percentile_of(2.0)
    weak = saberkit.LeagueDistribution(tied, tie="weak").percentile_of(2.0)

    assert strict == pytest.approx(20.0)  # 1 of 5 strictly below
    assert weak == pytest.approx(80.0)  # 4 of 5 at or below
    assert average == pytest.approx(50.0)  # the midpoint
    assert strict < average < weak


def test_savant_scale_rounds_and_clamps_to_one_through_hundred(values):
    d = saberkit.LeagueDistribution(values)
    bubbles = [d.percentile_of(v, scale="savant") for v in [1.0, 3.0, 5.0]]

    assert all(1 <= b <= 100 for b in bubbles)
    assert all(float(b).is_integer() for b in bubbles)


def test_percentile_of_accepts_an_array(values):
    d = saberkit.LeagueDistribution(values)
    out = polars.Series(d.percentile_of(polars.Series([1.0, 5.0])))

    assert out.to_list() == pytest.approx([10.0, 90.0])


def test_value_at_percentile_inverts_percentile_of(values):
    d = saberkit.LeagueDistribution(values)
    for v in [1.0, 3.0, 5.0]:
        assert d.value_at_percentile(d.percentile_of(v)) == pytest.approx(v)


def test_percentiles_stay_within_bounds(values):
    d = saberkit.LeagueDistribution(values)
    for v in [-100.0, 0.0, 3.0, 100.0]:
        assert 0.0 <= d.percentile_of(v) <= 100.0


def test_qualifier_excludes_players_without_ranking_them():
    """A 5-PA call-up should neither get a bubble nor distort anyone else's."""
    ranks = polars.Series(
        saberkit.percentile_ranks(
            polars.Series([1.0, 2.0, 3.0, 999.0]),
            qualifier=polars.Series([600.0, 600.0, 600.0, 5.0]),
            qualifier_min=100.0,
        )
    ).to_list()

    assert ranks[3] is None

    unfiltered = polars.Series(
        saberkit.percentile_ranks(polars.Series([1.0, 2.0, 3.0]))
    ).to_list()
    assert ranks[:3] == pytest.approx(unfiltered)


def test_savant_qualifier_thresholds():
    """Savant qualifies more loosely than MLB's official rate-stat threshold."""
    assert saberkit.batter_qualifier(162) == pytest.approx(340.2)
    assert saberkit.pitcher_qualifier(162) == pytest.approx(202.5)
    assert saberkit.batter_qualifier(162) < 3.1 * 162  # the official cutoff
    assert saberkit.batter_qualifier(60) == pytest.approx(126.0)  # 2020


def test_nulls_are_dropped_from_the_population():
    d = saberkit.LeagueDistribution(polars.Series([1.0, None, 3.0]))
    assert len(d) == 2
    assert d.n == 2


def test_an_empty_population_is_an_error_not_a_null():
    with pytest.raises(saberkit.SaberError, match="empty distribution"):
        saberkit.LeagueDistribution(polars.Series([None, None], dtype=polars.Float64))


def test_a_qualifier_matching_nobody_is_an_error():
    """Silently returning all-nulls would hide a filter typo."""
    with pytest.raises(saberkit.SaberError, match="empty distribution"):
        saberkit.LeagueDistribution(
            polars.Series([1.0, 2.0]),
            qualifier=polars.Series([5.0, 5.0]),
            qualifier_min=500.0,
        )


def test_unknown_options_are_rejected_with_the_valid_choices():
    values = polars.Series([1.0, 2.0])

    with pytest.raises(saberkit.SaberError, match="higher_is_better"):
        saberkit.LeagueDistribution(values, direction="ascending")

    with pytest.raises(saberkit.SaberError, match="average"):
        saberkit.LeagueDistribution(values, tie="midrank")


def test_qualifier_length_mismatch_is_an_error():
    with pytest.raises(saberkit.SaberError, match="length mismatch"):
        saberkit.LeagueDistribution(
            polars.Series([1.0, 2.0, 3.0]),
            qualifier=polars.Series([600.0]),
            qualifier_min=100.0,
        )


def test_all_tied_population_ranks_everyone_at_the_midpoint():
    d = saberkit.LeagueDistribution(polars.Series([7.0] * 10))
    assert d.percentile_of(7.0) == pytest.approx(50.0)


def test_repr_is_informative():
    d = saberkit.LeagueDistribution(polars.Series([1.0, 2.0, 3.0]))
    text = repr(d)
    assert "LeagueDistribution" in text
    assert "n=3" in text
