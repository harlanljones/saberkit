"""Quick ingestion: MLB data into Arrow-native polars frames.

This module is the front door for live notebooks: one call turns a season's
batted or pitched lines into a `polars.DataFrame` whose columns already use
saberkit's canonical names, so feeding it to `saberkit.compute` takes no
plumbing::

    df = saberkit.ingest.load_batting(2024)
    table = saberkit.compute.batting_table(df, league="season", season=2024)

Fetching is delegated to `saberkit.data` (pybaseball, optional); everything
here does is *reshape*. Publisher column conventions -- ``AB``, ``2B``, ``SO``
-- are translated once, here, into the lowercase names every saberkit function
speaks. Unknown columns are passed through untouched rather than dropped, so
nothing you fetched silently disappears.

`normalize` works entirely offline: hand it any polars, pandas, or Arrow
PyCapsule-producing frame (a Savant or FanGraphs CSV read with your own
tooling) and get the same canonical shape back.

polars itself is imported lazily inside each function. The base ``saberkit``
install has no required dependencies, and importing this module never changes
that.
"""

from __future__ import annotations

from typing import Any

from ._core import SaberError

__all__ = [
    "BATTING_ALIASES",
    "PITCHING_ALIASES",
    "load_batting",
    "load_pitching",
    "normalize",
]

_POLARS_HINT = (
    "polars is required for saberkit.ingest. Install it with:\n"
    '    pip install "saberkit[marimo]"'
)


def _polars() -> Any:
    """Import polars, or explain how to get it."""
    try:
        import polars
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(_POLARS_HINT) from exc
    return polars


# Canonical batting columns saberkit computes from, mapped from the common
# publisher spellings. Table order is priority: when two source columns map
# to one target (FanGraphs' ``SO`` vs Savant's ``K``), the first match in
# this table claims it and any other keeps its original name.
BATTING_ALIASES: dict[str, str] = {
    "name": "name",
    "playername": "name",
    "ab": "ab",
    "h": "h",
    "2b": "doubles",
    "doubles": "doubles",
    "3b": "triples",
    "triples": "triples",
    "hr": "hr",
    "bb": "bb",
    "ibb": "ibb",
    "hbp": "hbp",
    "sf": "sf",
    "so": "k",
    "k": "k",
}

PITCHING_ALIASES: dict[str, str] = {
    "name": "name",
    "playername": "name",
    "er": "er",
    "ip": "ip",
    "hr": "hr",
    "bb": "bb",
    "hbp": "hbp",
    "so": "k",
    "k": "k",
    "fb": "fb",
    "bf": "bf",
}


def _canonical_renames(columns: Any, aliases: dict[str, str]) -> dict[str, str]:
    """Resolve source columns to canonical names, alias-table order wins."""
    renames: dict[str, str] = {}
    claimed: set[str] = set()
    remaining = list(columns)
    for key, target in aliases.items():
        if target in claimed:
            continue
        match = next(
            (c for c in remaining if str(c).strip().lower() == key), None
        )
        if match is not None:
            renames[str(match)] = target
            claimed.add(target)
            remaining.remove(match)
    return renames


def _from_capsule(polars: Any, frame: Any) -> Any:
    """Build a polars frame from an Arrow PyCapsule producer."""
    if hasattr(frame, "__arrow_c_stream__"):
        return polars.DataFrame(frame)
    if hasattr(frame, "__arrow_c_array__"):
        return polars.DataFrame(frame)
    return None


def _from_pandas(polars: Any, frame: Any) -> Any:
    """Convert a pandas frame without making pyarrow a requirement."""
    try:
        return polars.from_pandas(frame)
    except ImportError:
        # Zero-copy via pyarrow is unavailable; a column-wise round trip is
        # fine at season scale (a thousand rows, not a million).
        return polars.DataFrame(
            {str(col): list(frame[col]) for col in frame.columns}
        )


def _to_polars(frame: Any) -> Any:
    """Coerce any supported tabular input into a polars DataFrame."""
    pl = _polars()

    if isinstance(frame, pl.DataFrame):
        return frame
    if isinstance(frame, pl.Series):
        raise SaberError(
            "cannot interpret a polars.Series as a table; pass a DataFrame"
        )

    converted = _from_capsule(pl, frame)
    if converted is not None:
        return converted

    if hasattr(frame, "columns") and hasattr(frame, "__getitem__"):
        return _from_pandas(pl, frame)

    raise SaberError(
        f"cannot interpret `{type(frame).__name__}` as a table: expected a "
        "polars or pandas DataFrame, a pyarrow Table/Array, or any object "
        "producing an Arrow PyCapsule (__arrow_c_stream__/__arrow_c_array__)"
    )


def normalize(frame: Any, *, kind: str = "batting") -> Any:
    """Return ``frame`` as a polars DataFrame with canonical column names.

    ``kind`` selects the alias table, ``"batting"`` (default) or
    ``"pitching"``. Known-but-duplicated sources resolve by table priority --
    a FanGraphs ``SO`` beats a stray ``K`` -- and unknown columns survive
    untouched. The original frame is never mutated.
    """
    if kind == "batting":
        aliases = BATTING_ALIASES
    elif kind == "pitching":
        aliases = PITCHING_ALIASES
    else:
        raise SaberError(
            f"unknown kind `{kind}`: expected \"batting\" or \"pitching\""
        )

    df = _to_polars(frame)
    renames = _canonical_renames(df.columns, aliases)
    return df.rename(renames) if renames else df


def load_batting(season: int, *, qual: int = 1) -> Any:
    """Season batting lines as a canonically-named polars DataFrame.

    Fetches through `saberkit.data.batting_stats`, which requires the
    optional ``pybaseball`` dependency (install extra ``data``). ``qual=1``
    keeps everyone who batted: percentile ranks apply playing-time thresholds
    themselves and want the full population.
    """
    from .data import batting_stats

    return normalize(batting_stats(season, qual=qual), kind="batting")


def load_pitching(season: int, *, qual: int = 1) -> Any:
    """Season pitching lines as a canonically-named polars DataFrame."""
    from .data import pitching_stats

    return normalize(pitching_stats(season, qual=qual), kind="pitching")
