import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        """
        # saberkit in one screen

        Every stat family in a single reactive dashboard. Pick a season, drag the
        park factor, and watch the **rate stats** (OBP, SLG, AVG, ISO, BABIP,
        wOBA, FIP), the **plus family** (OPS+, wRC+), the **minus family**
        (ERA-, FIP-), and the **Savant percentiles** recompute together. Below
        the tables there is a tour of the scalar API that sits underneath them.
        """
    )
    return


@app.cell
def _():
    import altair as alt
    import polars as pl
    import saberkit
    return alt, pl, saberkit


@app.cell
def _(mo, saberkit):
    season = mo.ui.dropdown(
        options=list(saberkit.compute.SEASONS),
        value=max(saberkit.compute.SEASONS),
        label="Season",
    )
    park_factor = mo.ui.slider(
        start=85, stop=115, value=100, step=1, label="Park factor",
    )
    mo.hstack([season, park_factor], justify="start", gap=3)
    return (park_factor, season)


@app.cell
def _():
    import os
    from pathlib import Path

    OFFLINE = os.environ.get("SABERKIT_OFFLINE", "") == "1"
    FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    return FIXTURES, OFFLINE


@app.cell
def _(FIXTURES, OFFLINE, mo, pl, saberkit, season):
    def _load_batters(year):
        """Live FanGraphs fetch when available, committed fixture otherwise."""
        if not OFFLINE:
            try:
                return (
                    saberkit.ingest.load_batting(year),
                    f"FanGraphs {year} via pybaseball",
                )
            except Exception:
                pass
        frame = pl.read_csv(FIXTURES / "batters.csv")
        return frame, f"sample fixture ({frame.height} batters, offline)"

    def _load_pitchers(year):
        """Live FanGraphs fetch when available, committed fixture otherwise."""
        if not OFFLINE:
            try:
                return (
                    saberkit.ingest.load_pitching(year),
                    f"FanGraphs {year} via pybaseball",
                )
            except Exception:
                pass
        frame = pl.read_csv(FIXTURES / "pitchers.csv")
        return frame, f"sample fixture ({frame.height} pitchers, offline)"

    batting_raw, batting_source = _load_batters(season.value)
    pitching_raw, pitching_source = _load_pitchers(season.value)
    mo.md(f"Data sources: *{batting_source}* &nbsp;|&nbsp; *{pitching_source}*")
    return batting_raw, pitching_raw


@app.cell
def _(batting_raw, park_factor, saberkit, season):
    table = saberkit.compute.batting_table(
        batting_raw,
        league="season",
        season=season.value,
        park_factor=float(park_factor.value),
    )
    return (table,)


@app.cell
def _(park_factor, pitching_raw, saberkit, season):
    pitching = saberkit.compute.pitching_table(
        pitching_raw,
        league="season",
        season=season.value,
        park_factor=float(park_factor.value),
    )
    return (pitching,)


@app.cell
def _(mo, saberkit, season):
    league = saberkit.LeagueContext.for_season(season.value)
    mo.md(
        f"""
        ## The scalar API underneath

        `saberkit` is also a fast batch library: pass plain numbers, get a plain
        number -- no Arrow, no polars, no dependencies.

        - `saberkit.obp(h=150, bb=60, hbp=5, ab=500, sf=5)` → `{saberkit.obp(h=150, bb=60, hbp=5, ab=500, sf=5):.4f}`
        - `saberkit.total_bases(h=178, doubles=38, triples=2, hr=41)` → `{saberkit.total_bases(h=178, doubles=38, triples=2, hr=41):g}`
        - `saberkit.ip_to_outs(190.2)` → `{saberkit.ip_to_outs(190.2)}` outs;  \
          `saberkit.outs_to_innings(572)` → `{saberkit.outs_to_innings(572):.3f}`
        - `saberkit.wrc_plus(0.390, ctx=league, park_factor=102)` → `{saberkit.wrc_plus(0.390, ctx=league, park_factor=102):.1f}`

        `LeagueContext.for_season({season.value})` supplies the league baselines
        the tables use -- OBP `{league.lg_obp:.3f}`, SLG `{league.lg_slg:.3f}`,
        FIP constant `{league.c_fip:.2f}`.
        """
    )
    return (league,)


@app.cell
def _(league, mo, saberkit, season):
    mo.md(
        f"""
        ## Reading the scales

        | Family | Meaning | Direction |
        | --- | --- | --- |
        | **Plus** (OPS+, wRC+) | 100 = league average | **higher is better** |
        | **Minus** (ERA-, FIP-) | 100 = league average | **lower is better** |
        | **Percentiles** | 1–100 bubble, Savant scale | under the playing-time threshold = none |

        A league-average batting line scores OPS+ = **{saberkit.ops_plus(league.lg_obp, league.lg_slg, ctx=league):.1f}**
        by construction. The minus family runs the other way: a 2.50 ERA against
        the {season.value} league (league ERA `{league.lg_era:.2f}`) scores
        ERA- = **{saberkit.era_minus(2.50, ctx=league):.0f}** — a *good* ERA,
        so an ERA- well under 100.

        Drag the park factor slider: OPS+/wRC+/ERA-/FIP- shift with it while the
        percentiles re-rank.
        """
    )
    return


@app.cell
def _(alt, mo, pl, table):
    batting_view = table.filter(pl.col("wrc_plus_pct").is_not_null())
    _bubbles = (
        alt.Chart(batting_view)
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X("woba_pct:Q", title="wOBA percentile", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("wrc_plus_pct:Q", title="wRC+ percentile", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("pa:Q", title="PA"),
            color=alt.Color("wrc_plus:Q", title="wRC+", scale=alt.Scale(scheme="turbo")),
            tooltip=["name", "pa", "obp", "slg", "woba", "ops_plus", "wrc_plus"],
        )
        .properties(title="Batting bubbles: wOBA percentile vs wRC+ percentile")
        .interactive()
    )
    batting_chart = mo.ui.altair_chart(_bubbles)
    batting_chart
    return (batting_chart,)


@app.cell
def _(mo, pl, table):
    batters = mo.ui.table(
        table.sort(pl.col("wrc_plus"), descending=True, nulls_last=True).select(
            "name", "pa", "obp", "slg", "avg", "woba", "ops_plus",
            "wrc_plus", "wrc_plus_pct", "k_rate_pct",
        ),
        selection=None,
        page_size=12,
    )
    batters
    return (batters,)


@app.cell
def _(alt, mo, pitching):
    _bubbles = (
        alt.Chart(pitching)
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X("k_rate_pct:Q", title="K-rate percentile", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("era_pct:Q", title="ERA percentile", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("ip:Q", title="IP"),
            color=alt.Color("era_minus:Q", title="ERA- (lower = better)",
                            scale=alt.Scale(scheme="turbo", reverse=True)),
            tooltip=["name", "ip", "era", "fip", "era_minus", "fip_minus"],
        )
        .properties(title="Pitching bubbles: miss bats (x) vs prevent runs (y)")
        .interactive()
    )
    pitching_chart = mo.ui.altair_chart(_bubbles)
    pitching_chart
    return (pitching_chart,)


@app.cell
def _(mo, pl, pitching):
    pitchers = mo.ui.table(
        pitching.sort(pl.col("era_minus"), descending=False, nulls_last=True).select(
            "name", "ip", "era", "fip", "k_rate",
            "era_minus", "fip_minus", "era_pct",
        ),
        selection=None,
        page_size=12,
    )
    pitchers
    return (pitchers,)


if __name__ == "__main__":
    app.run()
