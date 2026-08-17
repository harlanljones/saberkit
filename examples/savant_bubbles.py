"""Build Savant-style percentile "bubbles" for a league of hitters.

Run with:

    python examples/savant_bubbles.py

Reads a small committed fixture rather than fetching, so it works offline.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

import saberkit

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "batters.csv"

# Direction is a property of the metric *in context*, not of its name: strikeout
# rate is bad for a hitter and good for a pitcher. Savant pre-inverts the
# lower-is-better metrics so every bubble reads "right is good".
DIRECTIONS = {
    "woba": "higher_is_better",
    "iso": "higher_is_better",
    "babip": "higher_is_better",
    "k_rate": "lower_is_better",
}

WEIGHTS = saberkit.WobaWeights(
    w_bb=0.690, w_hbp=0.720, w_1b=0.880, w_2b=1.240, w_3b=1.570, w_hr=2.000
)


def add_rate_stats(df: pl.DataFrame) -> pl.DataFrame:
    """Attach the rate statistics the bubbles are drawn from."""
    obp = saberkit.obp(df["h"], df["bb"], df["hbp"], df["ab"], df["sf"])
    slg = saberkit.slg(df["h"], df["doubles"], df["triples"], df["hr"], df["ab"])
    avg = saberkit.avg(df["h"], df["ab"])

    return df.with_columns(
        pa=pl.col("ab") + pl.col("bb") + pl.col("hbp") + pl.col("sf"),
        k_rate=pl.col("k") / (pl.col("ab") + pl.col("bb") + pl.col("hbp") + pl.col("sf")),
        obp=pl.Series(obp),
        slg=pl.Series(slg),
        iso=pl.Series(saberkit.iso(slg, avg)),
        babip=pl.Series(saberkit.babip(df["h"], df["hr"], df["ab"], df["k"], df["sf"])),
        woba=pl.Series(
            saberkit.woba(
                saberkit.singles(df["h"], df["doubles"], df["triples"], df["hr"]),
                df["doubles"],
                df["triples"],
                df["hr"],
                df["bb"],
                df["ibb"],
                df["hbp"],
                df["ab"],
                df["sf"],
                weights=WEIGHTS,
            )
        ),
    )


def league_context(df: pl.DataFrame) -> saberkit.LeagueContext:
    """League baselines from the summed counting stats — never a mean of rates."""
    return saberkit.LeagueContext.from_totals(
        season=2024,
        ab=df["ab"].sum(),
        h=df["h"].sum(),
        doubles=df["doubles"].sum(),
        triples=df["triples"].sum(),
        hr=df["hr"].sum(),
        bb=df["bb"].sum(),
        ibb=df["ibb"].sum(),
        hbp=df["hbp"].sum(),
        sf=df["sf"].sum(),
        weights=WEIGHTS,
    )


def main() -> None:
    df = add_rate_stats(pl.read_csv(FIXTURE))
    league = league_context(df)

    df = df.with_columns(
        ops_plus=pl.Series(saberkit.ops_plus(df["obp"], df["slg"], ctx=league))
    )

    # Savant's threshold is looser than MLB's official 3.1 PA per team game,
    # on purpose: it widens the population the bubbles are drawn against.
    minimum = saberkit.batter_qualifier(team_games=162)

    for metric, direction in DIRECTIONS.items():
        df = df.with_columns(
            pl.Series(
                saberkit.percentile_ranks(
                    df[metric],
                    direction=direction,
                    qualifier=df["pa"],
                    qualifier_min=minimum,
                    scale="savant",
                )
            ).alias(f"{metric}_pct")
        )

    print(
        f"League  OBP {league.lg_obp:.3f}   SLG {league.lg_slg:.3f}   "
        f"wOBA {league.lg_woba:.3f}"
    )
    print(f"Savant qualifier: {minimum:.0f} PA")
    print("Players below it get no bubble and do not shift anyone else's.\n")

    display = (
        df.select("name", "pa", "ops_plus", *[f"{m}_pct" for m in DIRECTIONS])
        .sort("ops_plus", descending=True, nulls_last=True)
    )

    with pl.Config(tbl_rows=-1, float_precision=1):
        print(display)


if __name__ == "__main__":
    main()
