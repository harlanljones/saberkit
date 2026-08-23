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
        # Pitcher scout: ERA-, FIP-, and the strikeout bubble

        The FanGraphs "minus" family inverts the scale \u2014 **lower is better**
        \u2014 so a 62 ERA- reads like a 138 wRC+. Filter out short-season
        relievers, drag the park factor, and watch percentiles re-rank.
        Percentiles need a `bf` (batters faced) column; without one everyone
        is ranked.
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
    min_ip = mo.ui.slider(
        start=0, stop=200, value=80, step=5, label="Minimum IP",
    )
    mo.hstack([season, park_factor, min_ip], justify="start", gap=3)
    return (min_ip, park_factor, season)


@app.cell
def _():
    import os
    from pathlib import Path

    OFFLINE = os.environ.get("SABERKIT_OFFLINE", "") == "1"
    FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    return FIXTURES, OFFLINE


@app.cell
def _(FIXTURES, OFFLINE, mo, pl, saberkit, season):
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

    raw, source = _load_pitchers(season.value)
    mo.md(f"Data source: *{source}*")
    return (raw,)


@app.cell
def _(min_ip, park_factor, pl, raw, saberkit, season):
    table = saberkit.compute.pitching_table(
        raw,
        league="season",
        season=season.value,
        park_factor=float(park_factor.value),
        # Baseball's .1/.2 notation preserves ordering, so this filter is
        # exact without converting through outs first.
    ).filter(pl.col("ip") >= float(min_ip.value))
    return (table,)


@app.cell
def _(alt, mo, table):
    bubbles = (
        alt.Chart(table)
        .mark_circle(opacity=0.75)
        .encode(
            x=alt.X("k_rate_pct:Q", title="K-rate percentile", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("era_pct:Q", title="ERA percentile", scale=alt.Scale(domain=[0, 100])),
            size=alt.Size("ip:Q", title="IP"),
            color=alt.Color("era_minus:Q", title="ERA- (low = good)",
                            scale=alt.Scale(scheme="turbo", reverse=True)),
            tooltip=["name", "ip", "era", "fip", "era_minus", "fip_minus"],
        )
        .properties(title="Miss bats (x) vs prevent runs (y)")
        .interactive()
    )
    chart = mo.ui.altair_chart(bubbles)
    chart
    return (chart,)


@app.cell
def _(mo, pl, table):
    leaders = mo.ui.table(
        table.sort(pl.col("era_minus"), descending=False, nulls_last=True).select(
            "name", "ip", "era", "fip", "k_rate",
            "era_minus", "fip_minus", "era_pct",
        ),
        selection=None,
        page_size=12,
    )
    leaders
    return (leaders,)


if __name__ == "__main__":
    app.run()
