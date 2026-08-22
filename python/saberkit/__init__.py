"""Fast batch sabermetrics, backed by Rust.

``saberkit`` computes the "plus" family of baseball statistics (OPS+, sOPS+,
tOPS+, ERA+, wRC+), the FanGraphs "minus" family (ERA-, FIP-, xFIP-), and
Baseball-Savant-style league percentile rankings.

Every argument of every statistic accepts either a plain number or an Arrow
array, and the two mix freely — a column of rates against scalar league
constants, with a per-row park factor::

    >>> import polars as pl, saberkit
    >>> lg = saberkit.LeagueContext(lg_obp=0.312, lg_slg=0.399)
    >>> saberkit.ops_plus(0.400, 0.550, ctx=lg)              # doctest: +SKIP
    215.4

Pass Arrow arrays and you get an Arrow array back, with no copy in either
direction; pass numbers and you get a number.

Conventions
-----------
Undefined results are ``None`` (an Arrow null in batch mode), never NaN or an
exception -- a player with no at-bats has no batting average. Misconfiguration,
such as a mismatched array length or an unknown option, raises `SaberError`.

Park factors are on the 100-scale throughout, where 100 is neutral.

Innings pitched use baseball's ``.1``/``.2`` notation for thirds, so ``190.2``
means 190 and two-thirds innings. Reading those as decimals is a real and
easy-to-miss bug; `ip_to_outs` will reject anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from . import _core
from ._core import (
    LeagueDistribution,
    SaberError,
    batter_qualifier,
    ip_to_outs,
    outs_to_innings,
    percentile_ranks,
    pitcher_qualifier,
)

__all__ = [
    "LeagueContext",
    "NEUTRAL_PARK",
    "LeagueDistribution",
    "SaberError",
    "WobaWeights",
    "avg",
    "babip",
    "batter_qualifier",
    "era",
    "era_minus",
    "era_plus",
    "fip",
    "fip_minus",
    "ip_to_outs",
    "iso",
    "obp",
    "ops",
    "ops_plus",
    "outs_to_innings",
    "percentile_ranks",
    "pitcher_qualifier",
    "singles",
    "slg",
    "sops_plus",
    "tops_plus",
    "total_bases",
    "woba",
    "wraa",
    "wrc",
    "wrc_plus",
    "xfip",
    "xfip_minus",
    "__version__",
]

__version__: str = _core.__version__

#: A park factor that applies no adjustment.
NEUTRAL_PARK = 100.0


@dataclass(frozen=True, slots=True)
class WobaWeights:
    """Linear-weight run values for each way of reaching base.

    These change every season; FanGraphs publishes them in its "Guts!" table.
    """

    w_bb: float
    w_hbp: float
    w_1b: float
    w_2b: float
    w_3b: float
    w_hr: float


@dataclass(frozen=True, slots=True)
class LeagueContext:
    """A season's league-average baselines.

    Every field is optional, because different statistics need different
    subsets: OPS+ needs only ``lg_obp`` and ``lg_slg``, and requiring a caller
    to invent a ``woba_scale`` they will never use would be hostile. Asking for
    a statistic whose inputs are missing raises `SaberError` naming the absent
    constant.

    Which population these averages describe -- whether pitchers' hitting is
    included, whether the baseline is one league or all of MLB -- is a real
    methodological choice, and it stays with you. `from_totals` aggregates from
    counting stats you have already filtered.
    """

    season: int | None = None
    lg_obp: float | None = None
    lg_slg: float | None = None
    lg_era: float | None = None
    lg_fip: float | None = None
    lg_xfip: float | None = None
    lg_woba: float | None = None
    woba_scale: float | None = None
    c_fip: float | None = None
    lg_r_pa: float | None = None
    lg_wrc_pa: float | None = None
    lg_hr_per_fb: float | None = None
    weights: WobaWeights | None = None

    def require(self, name: str) -> float:
        """Return a constant, or explain precisely which one is missing."""
        value = getattr(self, name, None)
        if value is None:
            raise SaberError(
                f"invalid league constant `{name}`: not set on this LeagueContext"
            )
        return value

    def replace(self, **changes: Any) -> LeagueContext:
        """Return a copy with some fields changed."""
        return replace(self, **changes)

    @classmethod
    def from_totals(
        cls,
        *,
        season: int | None = None,
        ab: float = 0.0,
        h: float = 0.0,
        doubles: float = 0.0,
        triples: float = 0.0,
        hr: float = 0.0,
        bb: float = 0.0,
        ibb: float = 0.0,
        hbp: float = 0.0,
        sf: float = 0.0,
        k: float = 0.0,
        er: float = 0.0,
        ip: float | None = None,
        r: float = 0.0,
        pa: float = 0.0,
        weights: WobaWeights | None = None,
    ) -> LeagueContext:
        """Build a context from a league's summed counting stats.

        League rates are computed by **summing the counting stats and then
        taking the ratio**, never by averaging players' individual rates. Those
        give different answers, because a mean of ratios weights a
        20-plate-appearance September call-up the same as a 700-plate-appearance
        regular.

        All rate derivations — including ``c_fip``, ``lg_era``, and ``lg_woba`` —
        are delegated to the Rust core, so the formula has a single source of
        truth.

        ``woba_scale`` is not derivable from counting stats -- it comes from a
        run-expectancy model -- so it is left unset and must be supplied for
        wRC+.
        """
        outs = float(ip_to_outs(ip)) if ip is not None else 0.0
        totals = _core.LeagueTotals(
            ab=ab,
            h=h,
            doubles=doubles,
            triples=triples,
            hr=hr,
            bb=bb,
            ibb=ibb,
            hbp=hbp,
            sf=sf,
            k=k,
            er=er,
            outs=outs,
            r=r,
            pa=pa,
        )

        ctx = cls(
            season=season,
            lg_obp=totals.lg_obp,
            lg_slg=totals.lg_slg,
            lg_era=totals.lg_era,
            c_fip=totals.c_fip,
            lg_r_pa=totals.lg_r_pa,
            weights=weights,
        )

        if weights is not None:
            ctx = ctx.replace(
                lg_woba=totals.lg_woba(
                    weights.w_bb,
                    weights.w_hbp,
                    weights.w_1b,
                    weights.w_2b,
                    weights.w_3b,
                    weights.w_hr,
                )
            )

        return ctx


def _constant(ctx: LeagueContext | None, name: str, explicit: Any) -> Any:
    """Resolve a league constant from an explicit argument or the context."""
    if explicit is not None:
        return explicit
    if ctx is None:
        raise SaberError(
            f"invalid league constant `{name}`: pass it directly or supply a "
            f"LeagueContext via ctx="
        )
    return ctx.require(name)


# --------------------------------------------------------------- rate statistics


def obp(h: Any, bb: Any, hbp: Any, ab: Any, sf: Any) -> Any:
    """On-base percentage: ``(H + BB + HBP) / (AB + BB + HBP + SF)``.

    Sacrifice bunts and catcher's interference are excluded from the
    denominator, per the standard definition.
    """
    return _core.obp(h, bb, hbp, ab, sf)


def slg(h: Any, doubles: Any, triples: Any, hr: Any, ab: Any) -> Any:
    """Slugging percentage: total bases per at-bat.

    ``h`` is *total* hits; singles are derived as ``h - doubles - triples - hr``.
    """
    return _core.slg(h, doubles, triples, hr, ab)


def avg(h: Any, ab: Any) -> Any:
    """Batting average: ``H / AB``."""
    return _core.avg(h, ab)


def ops(obp: Any, slg: Any) -> Any:
    """On-base plus slugging."""
    return _core.ops(obp, slg)


def iso(slg: Any, avg: Any) -> Any:
    """Isolated power: ``SLG - AVG``, i.e. extra bases per at-bat."""
    return _core.iso(slg, avg)


def total_bases(h: Any, doubles: Any, triples: Any, hr: Any) -> Any:
    """Total bases: ``1B + 2*2B + 3*3B + 4*HR``."""
    return _core.total_bases(h, doubles, triples, hr)


def singles(h: Any, doubles: Any, triples: Any, hr: Any) -> Any:
    """Singles: total hits less every extra-base hit."""
    return _core.singles(h, doubles, triples, hr)


def babip(h: Any, hr: Any, ab: Any, k: Any, sf: Any) -> Any:
    """Batting average on balls in play: ``(H - HR) / (AB - K - HR + SF)``."""
    return _core.babip(h, hr, ab, k, sf)


def woba(
    singles: Any,
    doubles: Any,
    triples: Any,
    hr: Any,
    bb: Any,
    ibb: Any,
    hbp: Any,
    ab: Any,
    sf: Any,
    *,
    weights: WobaWeights | None = None,
    ctx: LeagueContext | None = None,
) -> Any:
    """Weighted on-base average.

    Unintentional walks (``BB - IBB``) carry the weight; intentional walks are
    excluded from both numerator and denominator, because they reflect the
    situation rather than the batter.
    """
    if weights is None:
        if ctx is None or ctx.weights is None:
            raise SaberError(
                "invalid league constant `weights`: pass weights= or a "
                "LeagueContext carrying them"
            )
        weights = ctx.weights

    return _core.woba(
        singles,
        doubles,
        triples,
        hr,
        bb,
        ibb,
        hbp,
        ab,
        sf,
        weights.w_bb,
        weights.w_hbp,
        weights.w_1b,
        weights.w_2b,
        weights.w_3b,
        weights.w_hr,
    )


def era(er: Any, ip: Any) -> Any:
    """Earned run average: ``9 * ER / IP``.

    ``ip`` is in baseball notation, where ``190.2`` means 190 and two-thirds.
    """
    return _core.era(er, ip)


def fip(
    hr: Any,
    bb: Any,
    hbp: Any,
    k: Any,
    ip: Any,
    *,
    c_fip: float | None = None,
    ctx: LeagueContext | None = None,
) -> Any:
    """Fielding independent pitching.

    ``(13*HR + 3*(BB + HBP) - 2*K) / IP + cFIP``. The constant puts FIP on the
    ERA scale, so a 3.50 FIP reads like a 3.50 ERA.
    """
    return _core.fip(hr, bb, hbp, k, ip, _constant(ctx, "c_fip", c_fip))


def xfip(
    fb: Any,
    bb: Any,
    hbp: Any,
    k: Any,
    ip: Any,
    *,
    lg_hr_per_fb: float | None = None,
    c_fip: float | None = None,
    ctx: LeagueContext | None = None,
) -> Any:
    """Expected FIP: FIP with home runs replaced by league-rate fly balls."""
    return _core.xfip(
        fb,
        bb,
        hbp,
        k,
        ip,
        _constant(ctx, "lg_hr_per_fb", lg_hr_per_fb),
        _constant(ctx, "c_fip", c_fip),
    )


# ------------------------------------------------------------------ plus family


def ops_plus(
    obp: Any,
    slg: Any,
    *,
    lg_obp: Any = None,
    lg_slg: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """OPS+: on-base plus slugging against league average, park-adjusted.

    ``100 * (OBP/lgOBP + SLG/lgSLG - 1) / (PF/100)``

    Note this is *not* ``OPS/lgOPS`` -- on-base and slugging are normalized
    separately, which is why a high-OBP hitter rates better here than raw OPS
    suggests. 100 is league average and higher is better.

    Approximate: Baseball-Reference park-adjusts the league components inside
    its own pipeline, so expect agreement to within a point or two.
    """
    return _core.ops_plus(
        obp,
        slg,
        _constant(ctx, "lg_obp", lg_obp),
        _constant(ctx, "lg_slg", lg_slg),
        park_factor,
    )


def sops_plus(
    split_obp: Any, split_slg: Any, lg_split_obp: Any, lg_split_slg: Any
) -> Any:
    """sOPS+: a split against the **league's** average in that same split.

    Answers "how did this player do against left-handers, compared to how
    hitters generally do against left-handers?". No park adjustment: both sides
    of the ratio come from the same split.
    """
    return _core.sops_plus(split_obp, split_slg, lg_split_obp, lg_split_slg)


def tops_plus(split_obp: Any, split_slg: Any, total_obp: Any, total_slg: Any) -> Any:
    """tOPS+: a split against the **player's own** overall line.

    Answers "how did this player do against left-handers compared to himself?".
    100 means the split matched his overall performance.
    """
    return _core.tops_plus(split_obp, split_slg, total_obp, total_slg)


def era_plus(
    era: Any,
    *,
    lg_era: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """ERA+: earned run average against league average, park-adjusted.

    Inverted relative to ERA itself, so higher is better. A pitcher in a
    hitter's park (park factor above 100) is credited for the environment.
    """
    return _core.era_plus(era, _constant(ctx, "lg_era", lg_era), park_factor)


def wraa(
    woba: Any,
    pa: Any,
    *,
    lg_woba: Any = None,
    woba_scale: Any = None,
    ctx: LeagueContext | None = None,
) -> Any:
    """Weighted runs above average: ``((wOBA - lgwOBA) / wOBAScale) * PA``."""
    return _core.wraa(
        woba,
        pa,
        _constant(ctx, "lg_woba", lg_woba),
        _constant(ctx, "woba_scale", woba_scale),
    )


def wrc(
    woba: Any,
    pa: Any,
    *,
    lg_woba: Any = None,
    woba_scale: Any = None,
    lg_r_pa: Any = None,
    ctx: LeagueContext | None = None,
) -> Any:
    """Weighted runs created."""
    return _core.wrc(
        woba,
        pa,
        _constant(ctx, "lg_woba", lg_woba),
        _constant(ctx, "woba_scale", woba_scale),
        _constant(ctx, "lg_r_pa", lg_r_pa),
    )


def wrc_plus(
    woba: Any,
    *,
    lg_woba: Any = None,
    woba_scale: Any = None,
    lg_r_pa: Any = None,
    lg_wrc_pa: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """wRC+: weighted runs created against league average, park-adjusted.

    Plate appearances are deliberately absent: the published formula divides
    wRAA by PA and wRAA is itself proportional to PA, so the term cancels.
    wRC+ is a pure rate.

    ``lg_wrc_pa`` should exclude pitchers hitting, per FanGraphs' definition.

    Approximate: FanGraphs applies a further league adjustment beyond the
    published formula.
    """
    return _core.wrc_plus(
        woba,
        _constant(ctx, "lg_woba", lg_woba),
        _constant(ctx, "woba_scale", woba_scale),
        _constant(ctx, "lg_r_pa", lg_r_pa),
        _constant(ctx, "lg_wrc_pa", lg_wrc_pa),
        park_factor,
    )


# ----------------------------------------------------------------- minus family


def era_minus(
    era: Any,
    *,
    lg_era: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """ERA-: earned run average against league average, where **lower is better**.

    ``lg_era`` should be the pitcher's own league, not all of MLB.
    """
    return _core.era_minus(era, _constant(ctx, "lg_era", lg_era), park_factor)


def fip_minus(
    fip: Any,
    *,
    lg_fip: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """FIP-: fielding independent pitching against league average, lower is better."""
    return _core.fip_minus(fip, _constant(ctx, "lg_fip", lg_fip), park_factor)


def xfip_minus(
    xfip: Any,
    *,
    lg_xfip: Any = None,
    park_factor: Any = NEUTRAL_PARK,
    ctx: LeagueContext | None = None,
) -> Any:
    """xFIP-: expected FIP against league average, lower is better."""
    return _core.xfip_minus(xfip, _constant(ctx, "lg_xfip", lg_xfip), park_factor)
