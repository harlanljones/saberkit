"""The plus and minus families, and the league context that feeds them."""

from __future__ import annotations

import pytest

import saberkit

polars = pytest.importorskip("polars")


@pytest.fixture
def nl_2002() -> saberkit.LeagueContext:
    """Roughly the 2002 National League, for the Bonds reproduction below."""
    return saberkit.LeagueContext(season=2002, lg_obp=0.331, lg_slg=0.410)


def test_league_average_rates_exactly_one_hundred(nl_2002):
    assert saberkit.ops_plus(0.331, 0.410, ctx=nl_2002) == pytest.approx(100.0)
    assert saberkit.era_plus(4.00, lg_era=4.00) == pytest.approx(100.0)
    assert saberkit.era_minus(4.00, lg_era=4.00) == pytest.approx(100.0)


def test_reproduces_bonds_2002_ops_plus(nl_2002):
    """Baseball-Reference lists OPS+ 268 for Bonds in 2002."""
    got = saberkit.ops_plus(0.582, 0.799, ctx=nl_2002, park_factor=101.0)
    assert got == pytest.approx(268.0, abs=3.0)


def test_reproduces_pedro_2000_era_plus():
    """Baseball-Reference lists ERA+ 291, the qualified-starter record."""
    got = saberkit.era_plus(1.74, lg_era=4.91, park_factor=103.0)
    assert got == pytest.approx(291.0, abs=5.0)


def test_minus_family_runs_the_other_way():
    assert saberkit.era_minus(2.50, lg_era=4.00) < 100.0
    assert saberkit.era_minus(5.50, lg_era=4.00) > 100.0


def test_split_statistics_compare_against_different_baselines():
    """sOPS+ measures against the league; tOPS+ against the player himself."""
    versus_league = saberkit.sops_plus(0.300, 0.450, 0.320, 0.410)
    versus_self = saberkit.tops_plus(0.300, 0.450, 0.350, 0.550)

    assert versus_league > 100.0  # better than the league in that split
    assert versus_self < 100.0  # but worse than his own overall line


def test_batch_and_scalar_agree():
    """The same call vectorized must give the same answers element by element."""
    obps = [0.582, 0.400, 0.300]
    slgs = [0.799, 0.500, 0.350]

    batched = polars.Series(
        saberkit.ops_plus(
            polars.Series(obps), polars.Series(slgs), lg_obp=0.331, lg_slg=0.410
        )
    ).to_list()
    one_at_a_time = [
        saberkit.ops_plus(o, s, lg_obp=0.331, lg_slg=0.410) for o, s in zip(obps, slgs)
    ]

    assert batched == pytest.approx(one_at_a_time)


def test_park_factor_may_vary_per_row():
    """Park factor is a property of the player's home park, not the league."""
    out = polars.Series(
        saberkit.ops_plus(
            polars.Series([0.400, 0.400]),
            polars.Series([0.500, 0.500]),
            lg_obp=0.320,
            lg_slg=0.410,
            park_factor=polars.Series([95.0, 105.0]),
        )
    ).to_list()

    # Identical lines in different parks must not rate identically.
    assert out[0] > out[1]


def test_missing_league_constant_is_reported_by_name():
    with pytest.raises(saberkit.SaberError, match="lg_obp"):
        saberkit.ops_plus(0.400, 0.500)


def test_missing_constant_on_a_context_is_reported_by_name():
    partial = saberkit.LeagueContext(lg_obp=0.320)
    with pytest.raises(saberkit.SaberError, match="lg_slg"):
        saberkit.ops_plus(0.400, 0.500, ctx=partial)


def test_innings_use_thirds_notation():
    assert saberkit.ip_to_outs(190.2) == 572
    assert saberkit.outs_to_innings(572) == pytest.approx(190 + 2 / 3)


def test_invalid_innings_notation_is_rejected():
    """`.3` is not a third of an inning -- it is not valid notation at all."""
    with pytest.raises(saberkit.SaberError, match="innings"):
        saberkit.ip_to_outs(0.3)

    with pytest.raises(saberkit.SaberError, match="innings"):
        saberkit.fip(20, 50, 5, 200, 200.5, c_fip=3.10)


def test_fip_denominator_uses_true_innings_not_the_decimal_reading():
    """200.1 IP is 200 1/3 innings, not 200.1."""
    got = saberkit.fip(20, 50, 5, 200, 200.1, c_fip=3.10)
    expected = (13 * 20 + 3 * (50 + 5) - 2 * 200) / (601 / 3) + 3.10
    assert got == pytest.approx(expected)

    naive = (13 * 20 + 3 * (50 + 5) - 2 * 200) / 200.1 + 3.10
    assert got != pytest.approx(naive)


def test_league_context_from_totals_sums_before_dividing():
    """The distinction that separates a correct league average from a wrong one."""
    ctx = saberkit.LeagueContext.from_totals(ab=610, h=181)

    assert ctx.lg_obp == pytest.approx(181 / 610)

    # Averaging the two players' rates instead would give a very different answer.
    mean_of_rates = ((180 / 600) + (1 / 10)) / 2
    assert ctx.lg_obp != pytest.approx(mean_of_rates, abs=0.05)


def test_league_context_leaves_underivable_constants_unset():
    ctx = saberkit.LeagueContext.from_totals(ab=610, h=181)
    # wOBA scale needs a run-expectancy model, not counting stats.
    assert ctx.woba_scale is None


def test_woba_requires_weights():
    with pytest.raises(saberkit.SaberError, match="weights"):
        saberkit.woba(90, 30, 5, 25, 60, 10, 5, 500, 5)


def test_woba_matches_hand_computation():
    w = saberkit.WobaWeights(
        w_bb=0.69, w_hbp=0.72, w_1b=0.88, w_2b=1.24, w_3b=1.57, w_hr=2.00
    )
    # uBB = 50; num = 34.5 + 3.6 + 79.2 + 37.2 + 7.85 + 50 = 212.35; den = 560
    got = saberkit.woba(90, 30, 5, 25, 60, 10, 5, 500, 5, weights=w)
    assert got == pytest.approx(212.35 / 560)


def test_nulls_propagate_through_plus_stats():
    out = polars.Series(
        saberkit.ops_plus(
            polars.Series([0.400, None]),
            polars.Series([0.500, 0.500]),
            lg_obp=0.320,
            lg_slg=0.410,
        )
    ).to_list()

    assert out[0] is not None
    assert out[1] is None
