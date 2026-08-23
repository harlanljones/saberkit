"""One-call compute: annotated stat tables for live notebooks.

`saberkit.compute.batting_table` and `saberkit.compute.pitching_table` turn a
canonically-named DataFrame -- see `saberkit.ingest` -- into one polars frame
carrying rate statistics, plus/minus ratings, and Savant-style percentile
ranks side by side::

    table = saberkit.compute.batting_table(
        saberkit.ingest.load_batting(2024),
        league="season",
        season=2024,
        park_factor=park_slider.value,   # any scalar or array you like
    )

This module contains **no statistical formulas**. Every number comes from the
existing Rust-backed functions (`saberkit.obp`, `saberkit.wrc_plus`,
`saberkit.percentile_ranks`, ...); what lives here is only wiring -- which
columns feed which function, and how results reattach to the frame. The one
exception, mirroring shipped-example precedent, is ``k_rate``: a plain ratio
of counting stats expressed as a polars expression, with a zero denominator
yielding null rather than NaN, exactly like the core's own rate stats.

League baselines are an argument, never a guess:

* ``league="season"`` -- bundled Retrosheet-derived constants for a completed
  season (requires ``season=``). Enables the wOBA/wRC+ family and, for
  pitchers, FIP/xFIP and the minus family.
* ``league="sample"`` -- constants derived from the *shown* population's
  summed totals, so a filtered dashboard stays self-consistent. Omits
  statistics whose run-expectancy inputs counting stats cannot produce.
* a `LeagueContext` instance -- used verbatim; a statistic whose constant is
  absent raises `SaberError` naming it, exactly like the function-level API.

Undefined stays undefined: a zero-plate-appearance row produces null rates,
null ratings, and null percentiles -- never NaN -- and players below the
playing-time threshold get no percentile rather than distorting anyone
else's. When *nobody* qualifies (a dashboard mid-filter), percentile columns
come back all-null instead of raising; that is a state, not a
misconfiguration.

polars is imported lazily; importing this module never adds a runtime
dependency to the base install.
"""

from __future__ import annotations

from typing import Any

from . import NEUTRAL_PARK, LeagueContext, SaberError, WobaWeights

__all__ = [
    "SEASONS",
    "batting_table",
    "pitching_table",
]

#: Completed seasons with bundled league constants. Provenance lives in
#: ``season_constants_generated.rs``; `LeagueContext.for_season` remains the
#: authority and rejects anything this tuple would wrongly include.
SEASONS = tuple(range(2010, 2026))

_POLARS_HINT = (
    "polars is required for saberkit.compute. Install it with:\n"
    '    pip install "saberkit[marimo]"'
)


def _polars() -> Any:
    """Import polars, or explain how to get it."""
    try:
        import polars
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(_POLARS_HINT) from exc
    return polars


# ------------------------------------------------------------------- plumbing


def _as_frame(source: Any, *, kind: str, season: int | None) -> Any:
    """Accept a season number or any tabular frame; return canonical polars."""
    if isinstance(source, int):
        from .ingest import load_batting, load_pitching

        load = load_batting if kind == "batting" else load_pitching
        return load(source)

    from .ingest import normalize

    return normalize(source, kind=kind)


def _require(frame: Any, names: list[str], purpose: str) -> None:
    """Fail early, naming every missing column at once."""
    missing = [n for n in names if n not in frame.columns]
    if missing:
        raise SaberError(
            f"{purpose} needs column(s) {missing}, which the frame lacks; "
            "canonical names are listed in saberkit.ingest"
        )


def _resolve_full_context(
    league: Any,
    *,
    season: int | None,
) -> LeagueContext:
    """Turn a ``"season"`` or explicit-LeagueContext argument into a context."""
    if isinstance(league, LeagueContext):
        return league
    if season is None:
        raise SaberError(
            'league="season" needs the season= to read bundled constants for'
        )
    return LeagueContext.for_season(season)


def _sample_context(
    *, season: int | None, frame: Any, totals: list[str],
    weights: WobaWeights | None,
) -> LeagueContext:
    """Derive baselines from the shown population's summed counting stats."""
    sums = {name: float(frame[name].sum()) for name in totals}
    return LeagueContext.from_totals(season=season, weights=weights, **sums)


def _series(values: Any) -> Any:
    """Wrap anything Arrow-shaped into a polars Series."""
    pl = _polars()

    import polars as pl_mod

    if isinstance(values, pl_mod.Series):
        return values
    return pl.Series(values)


def _outs_of(ip: Any) -> Any:
    """Convert a column of baseball-notation innings into outs.

    `ip_to_outs` is exposed as a scalar function, so this maps row-wise;
    pitching staffs are hundreds of rows, not millions. Invalid notation
    (``190.4``) raises `SaberError` exactly as the scalar API does.
    """
    from . import ip_to_outs

    return [None if v is None else float(ip_to_outs(v)) for v in ip.to_list()]


def _attach_percentiles(
    frame: Any,
    metrics: dict[str, str],
    *,
    qualifier: Any,
    qualifier_min: float,
) -> Any:
    """Add one ``<metric>_pct`` column per metric; direction is per-metric.

    When nobody clears the playing-time threshold -- a normal state for a
    reactive dashboard mid-filter, not a misconfiguration -- the percentile
    column is attached as all-null instead of raising, mirroring the
    per-row rule that unqualified players get no rank. The core remains the
    authority whenever a population exists.
    """
    from . import percentile_ranks

    pl = _polars()

    for metric, direction in metrics.items():
        if not _any_qualified(frame[metric], qualifier, qualifier_min):
            frame = frame.with_columns(
                pl.lit(None, dtype=pl.Float64).alias(f"{metric}_pct")
            )
            continue

        ranks = percentile_ranks(
            frame[metric],
            direction=direction,
            qualifier=qualifier,
            qualifier_min=qualifier_min,
            scale="savant",
        )
        frame = frame.with_columns(_series(ranks).alias(f"{metric}_pct"))
    return frame


def _any_qualified(values: Any, qualifier: Any, minimum: float) -> bool:
    """True if at least one row carries a finite value past the threshold."""
    vals = values.to_list()
    if qualifier is None:
        return any(v is not None for v in vals)
    thresholds = qualifier.to_list()
    return any(
        q is not None and q >= minimum and v is not None
        for v, q in zip(vals, thresholds)
    )


_BATTING_TOTALS = ["ab", "h", "doubles", "triples", "hr", "bb", "ibb",
                   "hbp", "sf", "k"]
_PITCHING_REQUIRED = ["er", "ip", "hr", "bb", "hbp", "k"]


# -------------------------------------------------------------------- batting


def batting_table(
    source: Any,
    *,
    season: int | None = None,
    league: Any = "sample",
    park_factor: Any = NEUTRAL_PARK,
    weights: WobaWeights | None = None,
    team_games: float = 162.0,
) -> Any:
    """Attach rate stats, ratings, and percentile ranks to batting lines.

    ``source`` is a canonically-named frame or a season int (fetched via
    `saberkit.ingest.load_batting`). Returns a **new** polars DataFrame; the
    input is never mutated, and unknown columns ride along untouched.

    With ``league="season"`` (recommended; requires ``season=``) the frame
    gains::

        pa obp slg avg iso babip k_rate     rate stats
        woba ops_plus wrc_plus              weighted / park-adjusted ratings
        *_pct                               Savant-scale percentiles

    ``league="sample"`` derives baselines from the frame's own totals and
    omits the wOBA/wRC+ family, whose run-expectancy inputs counting stats
    cannot supply. Passing a `LeagueContext` as ``league`` uses it verbatim;
    its ``weights`` must be set for the wOBA columns, and any other absent
    constant raises `SaberError` naming itself.

    ``park_factor`` accepts scalars or arrays (100-scale) and flows straight
    through to the park-adjusted ratings -- bind a slider to it. Rows below
    the Savant playing-time threshold (`batter_qualifier(team_games)`,
    qualified on plate appearances) receive null percentiles.
    """
    pl = _polars()
    df = _as_frame(source, kind="batting", season=season)
    _require(df, ["ab", "h", "doubles", "triples", "hr", "bb", "hbp", "sf"],
             "batting_table")

    if league == "sample":
        ctx = _sample_context(
            season=season, frame=df, totals=_BATTING_TOTALS, weights=weights,
        )
        full_mode = False
    elif league == "season" or isinstance(league, LeagueContext):
        ctx = _resolve_full_context(league, season=season)
        full_mode = True
    else:
        raise SaberError(
            f'unknown league `{league}`: expected "sample", "season", or a '
            "LeagueContext"
        )

    if full_mode and ctx.weights is None:
        raise SaberError(
            "the wOBA columns need a LeagueContext carrying `weights`; "
            'league="season" supplies bundled ones'
        )

    from . import avg, babip, iso, obp, ops_plus, slg

    h, doubles, triples, hr = df["h"], df["doubles"], df["triples"], df["hr"]
    ab, bb, hbp, sf, k = df["ab"], df["bb"], df["hbp"], df["sf"], df["k"]

    df = df.with_columns(
        (pl.col("ab") + pl.col("bb") + pl.col("hbp") + pl.col("sf"))
        .alias("pa"),
        _series(obp(h, bb, hbp, ab, sf)).alias("obp"),
        _series(slg(h, doubles, triples, hr, ab)).alias("slg"),
        _series(avg(h, ab)).alias("avg"),
        _series(babip(h, hr, ab, k, sf)).alias("babip"),
    )
    df = df.with_columns(
        _series(iso(df["slg"], df["avg"])).alias("iso"),
    )
    df = df.with_columns(
        pl.when(pl.col("pa") > 0)
        .then(pl.col("k") / pl.col("pa"))
        .alias("k_rate"),
    )

    metrics = {
        "obp": "higher_is_better",
        "slg": "higher_is_better",
        "iso": "higher_is_better",
        "babip": "higher_is_better",
        "k_rate": "lower_is_better",
        "ops_plus": "higher_is_better",
    }

    if full_mode:
        # wOBA/wRC+ need run-expectancy constants only bundled seasons (or an
        # explicit context) can carry.
        from . import singles, woba, wrc_plus

        _require(df, ["ibb"], "the wOBA columns")
        df = df.with_columns(
            _series(woba(
                singles(h, doubles, triples, hr),
                doubles, triples, hr, bb, df["ibb"], hbp, ab, sf,
                weights=ctx.weights,
            )).alias("woba"),
        )
        df = df.with_columns(
            _series(ops_plus(df["obp"], df["slg"], ctx=ctx,
                             park_factor=park_factor)).alias("ops_plus"),
            _series(wrc_plus(df["woba"], ctx=ctx,
                             park_factor=park_factor)).alias("wrc_plus"),
        )
        metrics.update({"woba": "higher_is_better",
                        "wrc_plus": "higher_is_better"})
    else:
        # A filtered-to-nothing selection has no league averages to rate
        # against; degrade to a null column like percentiles do.
        if ctx.lg_obp is None or ctx.lg_slg is None:
            df = df.with_columns(
                pl.lit(None, dtype=pl.Float64).alias("ops_plus")
            )
        else:
            df = df.with_columns(
                _series(ops_plus(df["obp"], df["slg"], ctx=ctx,
                                 park_factor=park_factor)).alias("ops_plus"),
            )

    from . import batter_qualifier

    return _attach_percentiles(
        df,
        metrics,
        qualifier=df["pa"],
        qualifier_min=batter_qualifier(team_games),
    )


# ------------------------------------------------------------------ pitching


def pitching_table(
    source: Any,
    *,
    season: int | None = None,
    league: Any = "sample",
    park_factor: Any = NEUTRAL_PARK,
    team_games: float = 162.0,
) -> Any:
    """Attach pitching rates, minus-family ratings, and percentile ranks.

    Same contract as `batting_table`. With ``league="season"`` the frame
    gains::

        era fip k_rate                      rates (IP in baseball .1/.2 notation)
        era_minus fip_minus                 FanGraphs minus family
        *_pct                               percentiles; low ERA/FIP/K-rate score high

    xFIP/xFIP- appear only when the context supplies ``lg_hr_per_fb`` (bundled
    seasons do not; pass a `LeagueContext` carrying it, plus an ``fb``
    column). ``league="sample"`` covers ERA and K-rate only: FIP needs
    ``c_fip``, which counting stats cannot derive.

    xFIP/xFIP- appear only when the context supplies both ``lg_hr_per_fb``
    and ``lg_xfip`` (bundled seasons carry neither; pass a `LeagueContext`
    with them set, plus an ``fb`` column). ``league="sample"`` covers ERA and
    K-rate only: FIP needs ``c_fip``, which counting stats cannot derive.

    Percentile qualifiers use batters faced against
    `pitcher_qualifier(team_games)` when the frame carries a ``bf`` column;
    without one, every pitcher is ranked (no unit-guessing proxies).
    """
    pl = _polars()
    df = _as_frame(source, kind="pitching", season=season)
    _require(df, _PITCHING_REQUIRED, "pitching_table")

    if league == "sample":
        ctx = _sample_context(
            season=season, frame=df,
            totals=["er", "hr", "bb", "hbp", "k"],
            weights=None,
        )
        full_mode = False
    elif league == "season" or isinstance(league, LeagueContext):
        ctx = _resolve_full_context(league, season=season)
        full_mode = True
    else:
        raise SaberError(
            f'unknown league `{league}`: expected "sample", "season", or a '
            "LeagueContext"
        )

    from . import era

    er, ip = df["er"], df["ip"]

    outs = _series(_outs_of(ip))
    df = df.with_columns(
        _series(era(er, ip)).alias("era"),
        outs.alias("outs"),
    )
    df = df.with_columns(
        pl.when(pl.col("outs") > 0)
        .then(pl.lit(27.0) * pl.col("k") / pl.col("outs"))
        .alias("k_rate"),
    )
    df = df.drop("outs")

    metrics = {
        "era": "lower_is_better",
        "k_rate": "lower_is_better",
    }

    if full_mode:
        from . import fip, era_minus, fip_minus

        df = df.with_columns(
            _series(fip(df["hr"], df["bb"], df["hbp"], df["k"], df["ip"],
                        ctx=ctx)).alias("fip"),
            _series(era_minus(df["era"], ctx=ctx,
                              park_factor=park_factor)).alias("era_minus"),
        )
        df = df.with_columns(
            _series(fip_minus(df["fip"], ctx=ctx,
                              park_factor=park_factor)).alias("fip_minus"),
        )
        metrics.update({"fip": "lower_is_better"})

        # xFIP needs the league HR-per-fly-ball rate and xFIP- needs
        # ``lg_xfip`` itself; counting stats derive neither and bundled
        # seasons carry neither. An explicit context supplying both unlocks
        # the pair.
        if ctx.lg_hr_per_fb is not None and ctx.lg_xfip is not None:
            from . import xfip, xfip_minus

            _require(df, ["fb"], "xFIP")
            fb = df["fb"]
            df = df.with_columns(
                _series(xfip(fb, df["bb"], df["hbp"], df["k"], df["ip"],
                             ctx=ctx)).alias("xfip"),
            )
            df = df.with_columns(
                _series(xfip_minus(df["xfip"], ctx=ctx,
                                   park_factor=park_factor)).alias("xfip_minus"),
            )
            metrics.update({"xfip": "lower_is_better"})

    from . import pitcher_qualifier

    # The Savant threshold counts batters faced; qualify on `bf` when the
    # frame carries it, and otherwise rank everyone rather than invent a
    # proxy in the wrong units.
    has_bf = "bf" in df.columns
    return _attach_percentiles(
        df,
        metrics,
        qualifier=df["bf"] if has_bf else None,
        qualifier_min=pitcher_qualifier(team_games),
    )
