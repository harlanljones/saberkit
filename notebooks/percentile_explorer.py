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
        # Savant-style percentile explorer

        Pick a season and drag the park factor: every rate stat, OPS+, wRC+,
        and the 1\u2013100 percentile "bubbles" recompute reactively. Percentiles
        use Savant thresholds \u2014 players under them get no bubble and never
        shift anyone else's.
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

    raw, source = _load_batters(season.value)
    mo.md(f"Data source: *{source}*")
    return (raw,)


@app.cell
def _(park_factor, pl, raw, saberkit, season):
    table = saberkit.compute.batting_table(
        raw,
        league="season",
        season=season.value,
        park_factor=float(park_factor.value),
    ).filter(pl.col("ops_plus_pct").is_not_null())
    return (table,)


@app.cell
def _(alt, mo, pl, table):
    bubbles = (
        alt.Chart(table)
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X("woba_pct:Q", title="wOBA percentile", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("ops_plus_pct:Q", title="OPS+ percentile", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("pa:Q", title="PA"),
            color=alt.Color("ops_plus:Q", title="OPS+", scale=alt.Scale(scheme="turbo")),
            tooltip=["name", "pa", "obp", "slg", "woba", "ops_plus", "wrc_plus"],
        )
        .properties(title="The bubbles: percentile vs percentile")
        .interactive()
    )
    chart = mo.ui.altair_chart(bubbles)
    chart
    return (chart,)


@app.cell
def _(mo, pl, table):
    leaders = mo.ui.table(
        table.sort(pl.col("wrc_plus"), descending=True, nulls_last=True).select(
            "name", "pa", "obp", "slg", "woba", "ops_plus", "wrc_plus",
            "wrc_plus_pct", "k_rate_pct",
        ),
        selection=None,
        page_size=12,
    )
    leaders
    return (leaders,)


if __name__ == "__main__":
    app.run()
