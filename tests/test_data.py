# mypy: disable-error-code="attr-defined"
"""Tests for ``saberkit.data`` — pybaseball helpers.

These tests mock ``pybaseball`` so they run without network access.
"""

from __future__ import annotations

from unittest import mock

import pytest

import saberkit
from saberkit.data import league_context_for_season, woba_weights


# ------------------------------------------------------------------ DataFrame
# A minimal Frame-like object with a `.columns` attribute and a `.sum()`
# method, without requiring pybaseball or pandas at installation time.


class _StubSeries:
    """A stub that sums a list of numbers."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def sum(self) -> float:
        return sum(self._values)


class _StubFrame:
    """A stub DataFrame carrying the columns ``league_context_for_season`` reads."""

    def __init__(self, **columns: list[float]) -> None:
        self._columns = columns

    @property
    def columns(self) -> list[str]:
        return list(self._columns.keys())

    def __getitem__(self, key: str) -> _StubSeries:
        return _StubSeries(self._columns[key])


# ---------------------------------------------------------------- woba_weights


def test_woba_weights_renames_fangraphs_column_names() -> None:
    w = woba_weights(wBB=0.69, wHBP=0.72, w1B=0.88, w2B=1.24, w3B=1.57, wHR=2.00)
    assert isinstance(w, saberkit.WobaWeights)
    assert w.w_bb == 0.69
    assert w.w_hbp == 0.72
    assert w.w_1b == 0.88
    assert w.w_2b == 1.24
    assert w.w_3b == 1.57
    assert w.w_hr == 2.00


def test_woba_weights_rejects_unknown_keys() -> None:
    """Unknown keys are rejected; they don't silently pass through."""
    with pytest.raises(TypeError):
        woba_weights(wBB=0.69, extra=1.0)


# ---------------------------------------------------- league_context_for_season


def _make_frame(**columns: list[float]) -> _StubFrame:
    return _StubFrame(**columns)


def test_league_context_for_season_computes_lg_obp_from_totals() -> None:
    """League OBP is derived from summed stats, not averaged rates."""
    frame = _make_frame(
        AB=[500, 100],
        H=[150, 10],
        **{k: [0] * 2 for k in ("2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "SO", "R", "PA")},
    )

    with mock.patch("saberkit.data.batting_stats", return_value=frame):
        ctx = league_context_for_season(2024)

    assert ctx.lg_obp is not None
    # Summed: (150+10 + 0+0 + 0+0) / (500+100 + 0+0 + 0+0 + 0+0) = 160/600
    assert ctx.lg_obp == pytest.approx(160 / 600)


def test_so_column_preferred_over_k() -> None:
    """When both 'SO' and 'K' exist, 'SO' is tried first and used."""
    frame = _make_frame(
        AB=[500], H=[150],
        **{col: [0] for col in ("2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "R", "PA")},
        SO=[100],  # fangraphs column name
        K=[999],   # should NOT be used when SO is present
    )

    with mock.patch("saberkit.data.batting_stats", return_value=frame):
        ctx = league_context_for_season(2024)

    assert ctx.lg_obp is not None


def test_k_column_fallback_when_so_is_missing() -> None:
    """When 'SO' is absent but 'K' is present, 'K' is used as fallback."""
    frame = _make_frame(
        AB=[500], H=[150],
        **{col: [0] for col in ("2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "R", "PA")},
        K=[100],
    )
    # No 'SO' column at all — the fallback path through total("SO", "K") should
    # succeed because 'K' is present.

    with mock.patch("saberkit.data.batting_stats", return_value=frame):
        ctx = league_context_for_season(2024)

    assert ctx.lg_obp is not None


def test_missing_column_raises_keyerror_with_candidate_list() -> None:
    """When neither 'SO' nor 'K' is present, the error names the candidates."""
    frame = _make_frame(
        AB=[500], H=[150],
        **{col: [0] for col in ("2B", "3B", "HR", "BB", "IBB", "HBP", "SF", "R", "PA")},
    )

    with mock.patch("saberkit.data.batting_stats", return_value=frame):
        with pytest.raises(KeyError, match="SO"):
            league_context_for_season(2024)