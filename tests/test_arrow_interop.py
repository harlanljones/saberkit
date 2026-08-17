"""Arrow boundary behaviour: dispatch, round-trips, nulls, and errors.

These tests exist to pin down the parts of the design that are easy to break
without noticing — in particular that a ``polars.Series`` (which exposes only
``__arrow_c_stream__``) and a ``pyarrow.Array`` (which exposes only
``__arrow_c_array__``) are *both* accepted.
"""

from __future__ import annotations

import pytest

import saberkit
from conftest import REFERENCE_OBP, REFERENCE_SLG

polars = pytest.importorskip("polars")
pyarrow = pytest.importorskip("pyarrow")


def test_scalar_inputs_return_scalars(line):
    assert saberkit.obp(line["h"], line["bb"], line["hbp"], line["ab"], line["sf"]) == pytest.approx(
        REFERENCE_OBP
    )
    assert saberkit.slg(
        line["h"], line["doubles"], line["triples"], line["hr"], line["ab"]
    ) == pytest.approx(REFERENCE_SLG)


def test_polars_series_round_trip(line):
    """A polars Series is chunked and exposes only __arrow_c_stream__."""
    cols = {k: polars.Series([v]) for k, v in line.items()}
    out = saberkit.obp(cols["h"], cols["bb"], cols["hbp"], cols["ab"], cols["sf"])

    assert polars.Series(out).to_list() == pytest.approx([REFERENCE_OBP])


def test_pyarrow_array_round_trip(line):
    """A pyarrow Array exposes __arrow_c_array__ instead."""
    cols = {k: pyarrow.array([v]) for k, v in line.items()}
    out = saberkit.slg(cols["h"], cols["doubles"], cols["triples"], cols["hr"], cols["ab"])

    assert pyarrow.array(out).to_pylist() == pytest.approx([REFERENCE_SLG])


def test_integer_columns_are_accepted_without_manual_casting():
    """Counting stats arrive as Int64 far more often than Float64."""
    ints = polars.Series([500], dtype=polars.Int32)
    out = saberkit.obp(polars.Series([150]), polars.Series([60]), polars.Series([5]), ints, polars.Series([5]))

    assert polars.Series(out).to_list() == pytest.approx([REFERENCE_OBP])


def test_nulls_propagate_elementwise():
    s = polars.Series
    out = saberkit.obp(s([150, None]), s([60, 60]), s([5, 5]), s([500, 500]), s([5, 5]))

    values = polars.Series(out).to_list()
    assert values[0] == pytest.approx(REFERENCE_OBP)
    assert values[1] is None


def test_zero_denominator_yields_null_not_an_error():
    """A player with no at-bats has no rate stat — that is missing, not an error."""
    s = polars.Series
    out = saberkit.obp(s([0]), s([0]), s([0]), s([0]), s([0]))

    assert polars.Series(out).to_list() == [None]


def test_length_mismatch_raises_saber_error():
    s = polars.Series
    with pytest.raises(saberkit.SaberError, match=r"`h` has 2 elements but `bb` has 1"):
        saberkit.obp(s([150, 150]), s([60]), s([5, 5]), s([500, 500]), s([5, 5]))


def test_saber_error_is_a_value_error():
    """So callers can catch it without importing saberkit-specific types."""
    assert issubclass(saberkit.SaberError, ValueError)


def test_non_numeric_column_raises_type_error():
    """Arrow would happily parse strings into floats; that hides real mistakes."""
    s = polars.Series
    with pytest.raises(TypeError, match="must be a numeric Arrow array"):
        saberkit.obp(s(["oops"]), s([60]), s([5]), s([500]), s([5]))
