"""Tests for ``saberkit.ingest`` — canonicalization and conversion.

All tests are offline: pandas/pyarrow frames are fabricated in-process, and
the pybaseball path is exercised only through its failure mode.
"""

from __future__ import annotations

import pytest

import saberkit
from saberkit.ingest import normalize


def _pandas():
    pd = pytest.importorskip("pandas")
    return pd


# ------------------------------------------------------------------- normalize


def test_normalize_maps_fangraphs_names_to_canonical() -> None:
    pd = _pandas()
    frame = pd.DataFrame(
        {
            "Name": ["A"],
            "AB": [500],
            "H": [150],
            "2B": [30],
            "3B": [5],
            "HR": [25],
            "BB": [60],
            "IBB": [3],
            "HBP": [5],
            "SF": [4],
            "SO": [100],
        }
    )

    out = normalize(frame)

    import polars as pl

    assert isinstance(out, pl.DataFrame)
    assert out.columns == [
        "name", "ab", "h", "doubles", "triples", "hr",
        "bb", "ibb", "hbp", "sf", "k",
    ]
    assert out["doubles"][0] == 30
    assert out["k"][0] == 100


def test_normalize_prefers_so_over_k_regardless_of_column_order() -> None:
    """Mirrors the data.py precedent: SO is tried before K."""
    pd = _pandas()
    k_first = pd.DataFrame({"K": [111], "SO": [100]})
    so_first = pd.DataFrame({"SO": [100], "K": [111]})

    assert normalize(k_first, kind="batting")["k"][0] == 100
    assert normalize(so_first, kind="batting")["k"][0] == 100


def test_normalize_is_idempotent_on_canonical_frames() -> None:
    import polars as pl

    frame = pl.read_csv("tests/fixtures/batters.csv")
    out = normalize(frame)
    assert out.columns[: len(frame.columns)] == frame.columns
    assert out.equals(frame)


def test_normalize_leaves_unknown_columns_untouched() -> None:
    pd = _pandas()
    frame = pd.DataFrame({"AB": [1], "Team": ["AAA"], "War (weird)": [9]})

    out = normalize(frame)

    assert "Team" in out.columns
    assert "War (weird)" in out.columns
    assert "ab" in out.columns


def test_normalize_pitching_kind_maps_ip_and_so() -> None:
    pd = _pandas()
    frame = pd.DataFrame({"Name": ["P"], "IP": [190.2], "SO": [200],
                          "BF": [780]})

    out = normalize(frame, kind="pitching")

    assert out.columns == ["name", "ip", "k", "bf"]


def test_normalize_rejects_unknown_kind() -> None:
    with pytest.raises(saberkit.SaberError, match="unknown kind"):
        normalize({}, kind="fielding")


def test_normalize_rejects_unsupported_types() -> None:
    with pytest.raises(saberkit.SaberError, match="cannot interpret"):
        normalize([{"ab": 1}], kind="batting")


def test_normalize_accepts_arrow_pycapsule_producers() -> None:
    pa = pytest.importorskip("pyarrow")
    table = pa.table({"AB": pa.array([500]), "H": pa.array([150])})

    out = normalize(table)

    assert out.columns == ["ab", "h"]


# ------------------------------------------------------- pybaseball loaders


def test_load_batting_explains_missing_pybaseball_offline() -> None:
    """The error names the install extra; no network is touched."""
    pytest.importorskip("polars")

    try:
        import pybaseball  # noqa: F401

        pytest.skip("pybaseball installed; nothing to test offline")
    except ImportError:
        pass

    with pytest.raises(ImportError, match=r"saberkit\[data\]"):
        saberkit.ingest.load_batting(2024)


def test_load_pitching_delegates_through_data_layer(monkeypatch) -> None:
    import polars as pl

    stub = pl.DataFrame({"Name": ["P"], "IP": [100.0], "ER": [40]})

    monkeypatch.setattr(
        "saberkit.data.pitching_stats", lambda season, qual=1: stub
    )

    out = saberkit.ingest.load_pitching(2024)

    assert out.columns == ["name", "ip", "er"]
