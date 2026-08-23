"""Tests for ``saberkit.compute`` — the one-call table layer.

Values are cross-checked against direct calls into the function-level API,
so a wiring bug here cannot hide behind the core being right.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import saberkit


# ------------------------------------------------------- import hygiene


def test_import_saberkit_pulls_no_optional_dependency() -> None:
    """The zero-dependency guarantee survives the new interactive layers."""
    code = (
        "import sys, saberkit; "
        "heavy = {'polars', 'pyarrow', 'pandas', 'numpy', 'marimo', "
        "'pybaseball', 'altair'}; "
        "loaded = heavy & set(sys.modules); "
        "assert not loaded, loaded"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------------------ season table


def test_seasons_all_have_bundled_constants() -> None:
    """SEASONS must never advertise a year `for_season` rejects."""
    for year in saberkit.compute.SEASONS:
        ctx = saberkit.LeagueContext.for_season(year)
        assert ctx.lg_obp is not None


@pytest.fixture
def batters():
    pl = pytest.importorskip("polars")
    return pl.read_csv("tests/fixtures/batters.csv")


@pytest.fixture
def pitchers():
    pl = pytest.importorskip("polars")
    return pl.read_csv("tests/fixtures/pitchers.csv")


def test_batting_table_season_mode_matches_direct_calls(batters) -> None:
    table = saberkit.compute.batting_table(
        batters, league="season", season=2024, park_factor=102.0
    )

    league = saberkit.LeagueContext.for_season(2024)
    for i in range(batters.height):
        row = batters[i]
        obp = saberkit.obp(row["h"][0], row["bb"][0], row["hbp"][0],
                           row["ab"][0], row["sf"][0])
        slg = saberkit.slg(row["h"][0], row["doubles"][0], row["triples"][0],
                           row["hr"][0], row["ab"][0])
        assert table["obp"][i] == pytest.approx(obp)
        assert table["slg"][i] == pytest.approx(slg)

        expected_ops_plus = saberkit.ops_plus(
            obp, slg, ctx=league, park_factor=102.0
        )
        assert table["ops_plus"][i] == pytest.approx(expected_ops_plus)


def test_batting_table_season_mode_has_full_schema(batters) -> None:
    table = saberkit.compute.batting_table(
        batters, league="season", season=2024
    )
    for col in ("pa", "obp", "slg", "avg", "iso", "babip", "k_rate",
                "woba", "ops_plus", "wrc_plus",
                "obp_pct", "k_rate_pct", "ops_plus_pct", "wrc_plus_pct"):
        assert col in table.columns, col


def test_batting_table_sample_mode_omits_wrc_plus_and_matches_direct(
    batters,
) -> None:
    table = saberkit.compute.batting_table(batters, league="sample")

    assert "woba" not in table.columns
    assert "wrc_plus" not in table.columns
    assert "ops_plus" in table.columns

    league = saberkit.LeagueContext.from_totals(
        ab=batters["ab"].sum(),
        h=batters["h"].sum(),
        doubles=batters["doubles"].sum(),
        triples=batters["triples"].sum(),
        hr=batters["hr"].sum(),
        bb=batters["bb"].sum(),
        ibb=batters["ibb"].sum(),
        hbp=batters["hbp"].sum(),
        sf=batters["sf"].sum(),
        k=batters["k"].sum(),
    )
    expected = saberkit.ops_plus(table["obp"][0], table["slg"][0], ctx=league)
    assert table["ops_plus"][0] == pytest.approx(expected)


def test_batting_table_accepts_explicit_context(batters) -> None:
    ctx = saberkit.LeagueContext.for_season(2024).replace(season=None)
    table = saberkit.compute.batting_table(
        batters, league=ctx, park_factor=95.0
    )
    assert "wrc_plus" in table.columns
    expected = saberkit.wrc_plus(
        table["woba"][0], ctx=ctx, park_factor=95.0
    )
    assert table["wrc_plus"][0] == pytest.approx(expected)


def test_batting_table_rejects_unknown_league(batters) -> None:
    with pytest.raises(saberkit.SaberError, match="unknown league"):
        saberkit.compute.batting_table(batters, league="nope")


def test_batting_table_season_mode_requires_season(batters) -> None:
    with pytest.raises(saberkit.SaberError, match="season="):
        saberkit.compute.batting_table(batters, league="season")


def test_batting_table_names_all_missing_columns(batters) -> None:
    broken = batters.drop("bb", "sf")
    with pytest.raises(saberkit.SaberError, match=r"\['bb', 'sf'\]"):
        saberkit.compute.batting_table(broken, league="sample")


def test_batting_table_input_is_never_mutated(batters) -> None:
    before = batters.columns
    saberkit.compute.batting_table(batters, league="sample")
    assert batters.columns == before


# --------------------------------------------------- undefined & thresholds


def test_zero_pa_row_yields_nulls_not_nan() -> None:
    pl = pytest.importorskip("polars")
    frame = pl.DataFrame(
        {
            "name": ["Zero"],
            "ab": [0], "h": [0], "doubles": [0], "triples": [0],
            "hr": [0], "bb": [0], "ibb": [0], "hbp": [0], "sf": [0],
            "k": [0],
        }
    )

    table = saberkit.compute.batting_table(frame, league="sample")

    for col in ("obp", "slg", "babip", "ops_plus", "obp_pct"):
        value = table[col][0]
        assert value is None or value != value, col  # null, not NaN


def test_below_threshold_row_gets_null_percentile_only() -> None:
    pl = pytest.importorskip("polars")
    regular = {"name": "Big", "ab": 500, "h": 150, "doubles": 30,
               "triples": 5, "hr": 25, "bb": 60, "ibb": 3, "hbp": 5,
               "sf": 4, "k": 100}
    callup = {**regular, "name": "Small", "ab": 50, "h": 12, "doubles": 2,
              "triples": 0, "hr": 1, "bb": 6, "ibb": 0, "hbp": 0,
              "sf": 1, "k": 15}

    table = saberkit.compute.batting_table(pl.DataFrame([regular, callup]),
                                           league="sample")

    assert table["obp_pct"][0] is not None
    assert table["obp_pct"][1] is None
    assert table["obp"][1] is not None  # rates still compute


# ----------------------------------------------------------------- pitching


def test_pitching_table_season_mode_matches_direct_calls(pitchers) -> None:
    table = saberkit.compute.pitching_table(
        pitchers, league="season", season=2024, park_factor=104.0
    )

    league = saberkit.LeagueContext.for_season(2024)
    for i in range(pitchers.height):
        row = pitchers[i]
        expected_era = saberkit.era(row["er"][0], row["ip"][0])
        expected_fip = saberkit.fip(row["hr"][0], row["bb"][0],
                                    row["hbp"][0], row["k"][0],
                                    row["ip"][0], ctx=league)
        assert table["era"][i] == pytest.approx(expected_era)
        assert table["fip"][i] == pytest.approx(expected_fip)

        outs = saberkit.ip_to_outs(row["ip"][0])
        assert table["k_rate"][i] == pytest.approx(27.0 * row["k"][0] / outs)


def test_pitching_table_sample_mode_is_rates_only(pitchers) -> None:
    table = saberkit.compute.pitching_table(pitchers, league="sample")

    assert "fip" not in table.columns
    assert "era_minus" not in table.columns
    assert "era" in table.columns and "k_rate" in table.columns


def test_pitching_table_xfip_unlocked_by_explicit_context(pitchers) -> None:
    ctx = saberkit.LeagueContext.for_season(2024).replace(
        lg_hr_per_fb=0.043, lg_xfip=4.05
    )
    table = saberkit.compute.pitching_table(pitchers, league=ctx)

    assert "xfip" in table.columns
    assert "xfip_minus" in table.columns
    expected = saberkit.xfip(pitchers["fb"][0], pitchers["bb"][0],
                             pitchers["hbp"][0], pitchers["k"][0],
                             pitchers["ip"][0], ctx=ctx)
    assert table["xfip"][0] == pytest.approx(expected)


def test_pitching_table_qualifies_on_batters_faced_when_present(
    pitchers,
) -> None:
    pl = pytest.importorskip("polars")

    table = saberkit.compute.pitching_table(pitchers, league="sample")
    # Every fixture pitcher clears the Savant BF threshold.
    assert table["era_pct"].null_count() == 0

    zero_bf = pitchers.with_columns(pl.col("bf") * 0)
    starved = saberkit.compute.pitching_table(zero_bf, league="sample")
    assert starved["era_pct"].null_count() == zero_bf.height
