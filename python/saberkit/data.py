"""Optional helpers for fetching data with ``pybaseball``.

Install with::

    pip install "saberkit[data]"

This module is deliberately thin and entirely optional. The Rust core performs
no I/O and no network access at all: it takes numbers and returns numbers.
Keeping fetching here means the compute path stays deterministic, offline, and
trivially testable, and that ``saberkit`` itself has no required runtime
dependencies.

``pybaseball`` is imported lazily inside each function rather than at module
scope, so ``import saberkit.data`` succeeds without it and the error only
arrives if you actually call something.

.. warning::

   ``pybaseball`` scrapes Baseball-Reference, FanGraphs, and Baseball Savant.
   Those sites change without notice, and the package's release cadence has
   been slow. Treat this module as a convenience, not a stable interface, and
   pin your own data snapshots for anything reproducible.
"""

from __future__ import annotations

from typing import Any

from . import LeagueContext, WobaWeights

__all__ = ["batting_stats", "league_context_for_season", "pitching_stats"]

_INSTALL_HINT = (
    "pybaseball is required for saberkit.data. Install it with:\n"
    '    pip install "saberkit[data]"'
)


def _pybaseball() -> Any:
    """Import pybaseball, or explain how to get it."""
    try:
        import pybaseball
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(_INSTALL_HINT) from exc
    return pybaseball


def batting_stats(season: int, *, qual: int = 1) -> Any:
    """Season batting lines from FanGraphs, as a pandas DataFrame.

    ``qual=1`` returns everyone who batted, leaving the qualifying decision to
    you — `saberkit.percentile_ranks` applies playing-time thresholds itself,
    and it needs the full population to do that correctly.
    """
    return _pybaseball().batting_stats(season, qual=qual)


def pitching_stats(season: int, *, qual: int = 1) -> Any:
    """Season pitching lines from FanGraphs, as a pandas DataFrame."""
    return _pybaseball().pitching_stats(season, qual=qual)


def league_context_for_season(season: int, *, qual: int = 1) -> LeagueContext:
    """Aggregate a season's batting lines into a `LeagueContext`.

    League rates are computed by summing the counting stats and then dividing,
    never by averaging players' rates.

    .. note::

       ``woba_scale``, ``lg_wrc_pa`` and the wOBA weights come from FanGraphs'
       "Guts!" table, which is derived from a run-expectancy model rather than
       from counting stats. They cannot be recovered here, so the returned
       context leaves them unset and wRC+ will report them as missing. Supply
       them yourself via :meth:`LeagueContext.replace`.
    """
    frame = batting_stats(season, qual=qual)

    def total(*candidates: str) -> float:
        for column in candidates:
            if column in frame.columns:
                return float(frame[column].sum())
        raise KeyError(
            f"none of {candidates} found in the FanGraphs response; "
            "pybaseball's column names may have changed"
        )

    return LeagueContext.from_totals(
        season=season,
        ab=total("AB"),
        h=total("H"),
        doubles=total("2B"),
        triples=total("3B"),
        hr=total("HR"),
        bb=total("BB"),
        ibb=total("IBB"),
        hbp=total("HBP"),
        sf=total("SF"),
        k=total("SO", "K"),
        r=total("R"),
        pa=total("PA"),
    )


def woba_weights(**values: float) -> WobaWeights:
    """Construct wOBA weights from FanGraphs' "Guts!" column names.

    A small convenience so a row of that table can be splatted in directly::

        woba_weights(wBB=0.689, wHBP=0.720, w1B=0.883,
                     w2B=1.244, w3B=1.569, wHR=2.004)
    """
    mapping = {
        "wBB": "w_bb",
        "wHBP": "w_hbp",
        "w1B": "w_1b",
        "w2B": "w_2b",
        "w3B": "w_3b",
        "wHR": "w_hr",
    }
    return WobaWeights(**{mapping.get(k, k): v for k, v in values.items()})
