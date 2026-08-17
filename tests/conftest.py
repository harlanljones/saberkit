"""Shared fixtures.

The reference batting line is hand-computable so tests assert against arithmetic
rather than against the library's own output:

    AB=500  H=150  2B=30  3B=5  HR=25  BB=60  HBP=5  SF=5
    singles = 150 - 30 - 5 - 25 = 90
    TB      = 90 + 60 + 15 + 100 = 265
    OBP     = (150 + 60 + 5) / (500 + 60 + 5 + 5) = 215 / 570
    SLG     = 265 / 500 = 0.530
"""

from __future__ import annotations

import pytest

REFERENCE_LINE = {
    "h": 150,
    "doubles": 30,
    "triples": 5,
    "hr": 25,
    "ab": 500,
    "bb": 60,
    "hbp": 5,
    "sf": 5,
}

REFERENCE_OBP = 215 / 570
REFERENCE_SLG = 0.530


@pytest.fixture
def line() -> dict[str, int]:
    """The reference batting line above, as a dict of counting stats."""
    return dict(REFERENCE_LINE)
