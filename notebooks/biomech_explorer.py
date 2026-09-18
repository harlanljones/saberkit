# marimo notebook: biomech explorer — Savant-style percentiles for
# The OpenBiomechanics Project (Driveline Baseball). See
# docs/openbiomechanics.md and docs/superpowers/specs/
# 2026-09-15-openbiomechanics-notebook-design.md before running.
import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


with app.setup:
    from collections.abc import Sequence
    import hashlib
    import http.client
    import os
    from pathlib import Path
    import tempfile
    import urllib.request

    import altair as alt
    import marimo as mo
    import polars as pl
    import saberkit

    OBP_COMMIT = "44b98dae05cceb016f080ab39d105c85b8639084"
    OBP_RAW_BASE = (
        "https://raw.githubusercontent.com/drivelineresearch/"
        f"openbiomechanics/{OBP_COMMIT}"
    )
    OBP_FILES = {
        "pitching_metadata": (
            "baseball_pitching/data/metadata.csv",
            "ec5686fef140e728193d4ce4bb16aa116751e716963bb2aedca11111b03816e3",
        ),
        "pitching_poi": (
            "baseball_pitching/data/poi/poi_metrics.csv",
            "5ba2ac8536fba1d6997ebd81d7b1956c73fbb2e141b9c6156cd76f66265f391e",
        ),
        "hitting_metadata": (
            "baseball_hitting/data/metadata.csv",
            "b87567a7dbed13dd438a16512b80b80af81cf909e1203a89f545e6b31a245372",
        ),
        "hitting_poi": (
            "baseball_hitting/data/poi/poi_metrics.csv",
            "95ab62e2c36e5034435f3edaec2d7d320caf9aa61eac923d907aed6751a2619b",
        ),
    }
    METRICS = {
        "pitching": {
            "ranked": {
                "pitch_speed_mph": ("Pitch speed", "mph"),
                "max_shoulder_internal_rotational_velo": (
                    "Peak shoulder IR velocity",
                    "deg/s",
                ),
                "max_elbow_extension_velo": (
                    "Peak elbow extension velocity",
                    "deg/s",
                ),
                "max_torso_rotational_velo": (
                    "Peak torso rotation velocity",
                    "deg/s",
                ),
                "max_pelvis_rotational_velo": (
                    "Peak pelvis rotation velocity",
                    "deg/s",
                ),
                "lead_knee_extension_angular_velo_max": (
                    "Peak lead-knee extension velocity",
                    "deg/s",
                ),
                "max_cog_velo_x": ("Peak center-of-mass velocity to plate", "m/s"),
            },
            "load": {
                "elbow_varus_moment": ("Peak elbow varus moment", "Nm"),
                "shoulder_internal_rotation_moment": (
                    "Peak shoulder IR moment",
                    "Nm",
                ),
            },
        },
        "hitting": {
            "ranked": {
                "exit_velo_mph_x": ("Exit velocity", "mph"),
                "bat_speed_mph_max_x": ("Peak bat speed", "mph"),
                "pelvis_angular_velocity_seq_max_x": (
                    "Peak pelvis angular velocity",
                    "deg/s",
                ),
                "torso_angular_velocity_seq_max_x": (
                    "Peak torso angular velocity",
                    "deg/s",
                ),
                "upper_arm_speed_mag_seq_max_x": (
                    "Peak upper-arm angular speed",
                    "deg/s",
                ),
                "max_cog_velo_x": ("Peak center-of-mass velocity", "m/s"),
            },
            "load": {},
        },
    }
    DISCIPLINES = {
        "pitching": ("session_pitch", "playing_level", "p_throws", "poi"),
        "hitting": (
            "session_swing",
            "highest_playing_level",
            "hitter_side",
            "metadata",
        ),
    }
    SMALL_POPULATION = 20
    ATTRIBUTION_MD = (
        "Source: **The OpenBiomechanics Project** — Driveline Baseball Research "
        "and Development (Wasserberger KW, Brady AC, Besky DM, Jones BR, Boddy "
        f"KJ, 2022), repository at commit `{OBP_COMMIT[:8]}` · licensed "
        "CC BY-NC-SA 4.0 plus the exclusion in `LICENSE-DATA.md` · provided "
        "as-is, without warranties of any kind (license §5). "
        "**Changes made by saberkit:** a subset of columns; trials reduced per "
        "athlete (best or mean); athletes filtered by playing level; metrics "
        "converted to Savant-style percentile ranks. The numbers shown are "
        "saberkit's aggregates, not upstream values. Anything you export, "
        "download or screenshot here is adapted material and stays under "
        "CC BY-NC-SA 4.0 with the same exclusion."
    )
    # The text below is quoted verbatim from Driveline Baseball's
    # LICENSE-DATA.md (The OpenBiomechanics Project) at commit
    # 44b98dae05cceb016f080ab39d105c85b8639084, for license notice purposes
    # only. It is part of Driveline's CC BY-NC-SA data license, and is NOT
    # covered by saberkit's MIT/Apache-2.0 grant.
    EXCLUSION_TEXT = (
        "While the license is clear that this data cannot be used for "
        "commercial purposes (which includes but is not limited to for-profit "
        "organizations, corporations, and sole proprietorships with the intent "
        "to profit now or in the future), there is also one additional specific "
        "exclusion where this data cannot be used in any form without a "
        "specific written commercial (paid) license:\n\n"
        "> Any employee or contractor employed by, associated with, or a "
        "significant shareholder of a professional sports organization or "
        "financial analysis firm is forbidden to use The OpenBiomechanics "
        "Project data for any use whatsoever."
    )


@app.function
def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or ""
    root = Path(base) if base.startswith("/") else Path.home() / ".cache"
    return root / "saberkit" / "openbiomechanics" / OBP_COMMIT


@app.function
def fetch_csv(key: str, *, cache_dir: Path) -> bytes:
    try:
        path, expected = OBP_FILES[key]
    except KeyError:
        raise ValueError(f"unknown OpenBiomechanics file key: {key!r}") from None
    cached = cache_dir / f"{key}.csv"
    if cached.exists():
        try:
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() == expected:
                return data
            cached.unlink()
        except OSError as exc:
            raise RuntimeError(f"reading cache file {cached} failed: {exc}") from exc
    url = f"{OBP_RAW_BASE}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError(
            f"fetching {url} failed (OpenBiomechanics pin {OBP_COMMIT}): {exc}"
        ) from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {path} at OpenBiomechanics pin {OBP_COMMIT}: "
            f"expected {expected}, got {actual}"
        )
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=cache_dir)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, cached)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise RuntimeError(f"writing cache file {cached} failed: {exc}") from exc
    return data


@app.function
def load_discipline(
    discipline: str, *, metadata_csv: bytes, poi_csv: bytes
) -> pl.DataFrame:
    try:
        trial_key, level_column, hand_column, hand_table = DISCIPLINES[discipline]
    except KeyError:
        raise ValueError(f"unknown discipline: {discipline!r}") from None
    meta_all = pl.read_csv(metadata_csv, infer_schema=False)
    poi_all = pl.read_csv(poi_csv, infer_schema=False)
    ranked = METRICS[discipline]["ranked"]
    load = METRICS[discipline]["load"]
    meta_required = [trial_key, level_column]
    if hand_table == "metadata":
        meta_required.append(hand_column)
    poi_required = [trial_key, "session"]
    if hand_table == "poi":
        poi_required.append(hand_column)
    poi_required.extend(ranked)
    poi_required.extend(load)
    missing_meta = [c for c in meta_required if c not in meta_all.columns]
    missing_poi = [c for c in poi_required if c not in poi_all.columns]
    if missing_meta or missing_poi:
        parts = []
        if missing_meta:
            parts.append("metadata: " + ", ".join(missing_meta))
        if missing_poi:
            parts.append("poi: " + ", ".join(missing_poi))
        raise ValueError(f"{discipline}: missing required columns ({'; '.join(parts)})")
    meta = meta_all.select(meta_required)
    orphans = poi_all.join(meta, on=trial_key, how="anti")[trial_key]
    if orphans.len():
        raise ValueError(
            f"{discipline}: POI trials without a metadata row: "
            f"{orphans.head(5).to_list()}"
        )
    metric_cols = list(ranked) + list(load)
    try:
        joined = poi_all.join(meta, on=trial_key, how="inner", validate="1:1")
        joined = joined.with_columns(
            pl.col(c).cast(pl.Float64, strict=True) for c in metric_cols
        )
    except pl.exceptions.PolarsError as exc:
        raise ValueError(f"{discipline}: {exc}") from exc
    return joined.select(
        pl.col("session").alias("athlete"),
        pl.col(trial_key).alias("trial"),
        pl.col(level_column).alias("level"),
        pl.col(hand_column).alias("hand"),
        *metric_cols,
    )


@app.function
def per_athlete(trials: pl.DataFrame, metrics: Sequence[str], how: str) -> pl.DataFrame:
    if how not in ("max", "mean"):
        raise ValueError(f"how must be 'max' or 'mean', got {how!r}")
    aggs = [
        pl.col("level").first(),
        pl.col("hand").first(),
        pl.len().alias("n_trials"),
    ]
    for metric in metrics:
        column = pl.col(metric)
        aggs.append(column.max() if how == "max" else column.mean())
    return trials.group_by("athlete", maintain_order=True).agg(aggs)


@app.function
def rank_population(
    athletes: pl.DataFrame, ranked_metrics: Sequence[str]
) -> pl.DataFrame:
    new_columns = []
    for metric in ranked_metrics:
        column = athletes[metric]
        if (
            column.dtype == pl.Null
            or not (column.is_not_null() & column.is_not_nan()).any()
        ):
            new_columns.append(pl.lit(None, dtype=pl.Float64).alias(f"{metric}_pct"))
        else:
            ranks = saberkit.percentile_ranks(
                column, direction="higher_is_better", scale="savant"
            )
            new_columns.append(pl.Series(ranks).alias(f"{metric}_pct"))
    return athletes.with_columns(new_columns)


@app.function
def small_population_note(n: int):
    if 0 < n < SMALL_POPULATION:
        return mo.callout(
            mo.md(
                f"Only {n} athletes match this filter. Percentiles computed "
                "on a population this small are unstable."
            ),
            kind="warn",
        )
    return None


@app.cell
def _(SOURCE_LABEL):
    mo.md(
        f"""# biomech explorer

Savant-style percentile ranks for athletes in [The OpenBiomechanics
Project](https://github.com/drivelineresearch/openbiomechanics) (OBP), the
public biomechanics dataset produced by **Driveline Baseball Research and
Development** (project site: [openbiomechanics.org](https://openbiomechanics.org)).

The notebook fetches point-of-interest metrics at runtime, pinned to one
upstream commit, ranks athletes with saberkit's percentile engine, and shows
per-athlete percentile bubbles and a leaderboard for pitching and hitting.
Read the license notice below before accepting the gate.

**Data source:** {SOURCE_LABEL}
"""
    )
    return


@app.cell
def _():
    OFFLINE = os.environ.get("SABERKIT_OFFLINE", "") == "1"
    FIXTURES = (
        Path(__file__).resolve().parent.parent
        / "tests"
        / "fixtures"
        / "openbiomechanics"
    )
    SOURCE_LABEL = (
        f"OpenBiomechanics Project @ {OBP_COMMIT[:8]}"
        if not OFFLINE
        else "SYNTHETIC DEMO DATA — not OpenBiomechanics data"
    )
    return FIXTURES, OFFLINE, SOURCE_LABEL


@app.cell
def _(EXCLUSION_TEXT, FIXTURES, OFFLINE, SOURCE_LABEL):
    accepted = mo.ui.checkbox(
        label=(
            "I have read Driveline's license terms and the exclusion above, "
            "and I am eligible to use OpenBiomechanics data under them."
        )
    )
    if OFFLINE:
        notice = mo.callout(
            mo.md(
                "This session runs offline with synthetic demo data. Nothing "
                "here is OpenBiomechanics data, and no fetch is performed."
            ),
            kind="info",
        )
    else:
        notice = mo.vstack(
            [
                mo.md(
                    f"**Data source:** {SOURCE_LABEL}. The OpenBiomechanics "
                    "Project data is licensed "
                    "[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/): "
                    "**NonCommercial** (no commercial use) and **ShareAlike** "
                    "(adapted material must carry the same license) both apply."
                ),
                mo.md(EXCLUSION_TEXT),
                mo.md(
                    "Cite the data in both forms the licensor asks for:\n"
                    "- `CITATION.cff`: Driveline Baseball Research and "
                    "Development; Boddy, Kyle. *The OpenBiomechanics Project "
                    "(OBP)*, openbiomechanics.org.\n"
                    '- The site\'s "Citing OBP" form: Wasserberger KW, '
                    "Brady AC, Besky DM, Jones BR, Boddy KJ, 2022."
                ),
                mo.md(
                    f"Upstream pin: `{OBP_COMMIT}` — [repository tree at the "
                    f"pin](https://github.com/drivelineresearch/openbiomechanics/tree/{OBP_COMMIT})"
                    " · "
                    f"[LICENSE-DATA.md]({OBP_RAW_BASE}/LICENSE-DATA.md) · "
                    f"[pitching metadata]({OBP_RAW_BASE}/baseball_pitching/data/metadata.csv)"
                    " · "
                    f"[pitching POI]({OBP_RAW_BASE}/baseball_pitching/data/poi/poi_metrics.csv)"
                    " · "
                    f"[hitting metadata]({OBP_RAW_BASE}/baseball_hitting/data/metadata.csv)"
                    " · "
                    f"[hitting POI]({OBP_RAW_BASE}/baseball_hitting/data/poi/poi_metrics.csv)"
                ),
                mo.md(
                    "The data is provided as-is, without warranties of any "
                    "kind (license §5), by the licensor. saberkit adds none."
                ),
                mo.md(
                    "Anything derived here — tables, charts, exports, "
                    "downloads, screenshots — is adapted material that stays "
                    "under CC BY-NC-SA 4.0 with the same exclusion, and must "
                    "carry the same attribution if shared."
                ),
                mo.md(
                    "saberkit's MIT/Apache license does not cover the data. "
                    "saberkit cannot verify anyone's eligibility: the "
                    "exclusion is a condition between you and Driveline, and "
                    "ticking the box is your own assessment."
                ),
                mo.md(
                    "Fetched files are cached under "
                    "`$XDG_CACHE_HOME/saberkit/openbiomechanics/<commit>` "
                    "(falling back to `~/.cache`). Deleting that directory "
                    "removes every local copy."
                ),
            ]
        )
    mo.vstack([notice, accepted])
    return (accepted, notice)


@app.cell
def _(OFFLINE, accepted):
    mo.stop(
        not OFFLINE and not accepted.value,
        mo.md("Accept the licence above to load OpenBiomechanics data."),
    )
    license_ok = True
    return (license_ok,)


@app.cell
def _(FIXTURES, OFFLINE, license_ok):
    assert license_ok

    trials = None

    def _read_fixture(key):
        return (FIXTURES / f"{key}.csv").read_bytes()

    try:
        if OFFLINE:
            trials = {
                "pitching": load_discipline(
                    "pitching",
                    metadata_csv=_read_fixture("pitching_metadata"),
                    poi_csv=_read_fixture("pitching_poi"),
                ),
                "hitting": load_discipline(
                    "hitting",
                    metadata_csv=_read_fixture("hitting_metadata"),
                    poi_csv=_read_fixture("hitting_poi"),
                ),
            }
        else:
            cache_dir = default_cache_dir()
            trials = {
                "pitching": load_discipline(
                    "pitching",
                    metadata_csv=fetch_csv("pitching_metadata", cache_dir=cache_dir),
                    poi_csv=fetch_csv("pitching_poi", cache_dir=cache_dir),
                ),
                "hitting": load_discipline(
                    "hitting",
                    metadata_csv=fetch_csv("hitting_metadata", cache_dir=cache_dir),
                    poi_csv=fetch_csv("hitting_poi", cache_dir=cache_dir),
                ),
            }
    except (RuntimeError, ValueError) as exc:
        mo.stop(True, mo.callout(mo.md(str(exc)), kind="danger"))
    return (trials,)


@app.cell
def _():
    discipline = mo.ui.radio(
        options=["pitching", "hitting"], value="pitching", label="Discipline"
    )
    reducer = mo.ui.dropdown(
        options={"Best trial": "max", "Mean of trials": "mean"},
        value="Best trial",
        label="Trials",
    )
    mo.hstack([discipline, reducer], justify="start")
    return (discipline, reducer)


@app.cell
def _(discipline, trials):
    frame = trials[discipline.value]
    level_options = frame["level"].unique().to_list()
    levels = mo.ui.multiselect(
        options=level_options,
        value=level_options,
        label=(
            "Playing level at collection"
            if discipline.value == "pitching"
            else "Highest level reached"
        ),
    )
    levels
    return (levels,)


@app.cell
def _(
    ATTRIBUTION_MD,
    METRICS,
    SOURCE_LABEL,
    discipline,
    levels,
    per_athlete,
    rank_population,
    reducer,
    small_population_note,
    trials,
):
    selected_levels = list(levels.value)
    filtered = trials[discipline.value].filter(pl.col("level").is_in(selected_levels))
    ranked_metrics = list(METRICS[discipline.value]["ranked"])
    moment_metrics = list(METRICS[discipline.value]["load"])
    athletes = per_athlete(filtered, ranked_metrics + moment_metrics, reducer.value)
    table = rank_population(athletes, ranked_metrics)
    first_ranked = ranked_metrics[0]
    n_athletes = table.height
    if n_athletes == 0:
        caption = mo.callout(mo.md("Select at least one playing level."), kind="warn")
    else:
        level_labels = {
            "high_school": "high school",
            "college": "college",
            "independent": "independent",
            "milb": "MiLB",
        }
        ordered = [
            level
            for level in ("high_school", "college", "independent", "milb")
            if level in selected_levels
        ]
        if set(selected_levels) == set(levels.options):
            levels_text = "all levels"
        else:
            levels_text = ", ".join(level_labels.get(v, v) for v in ordered)
        null_clauses = ""
        for _metric, (_label, _unit) in METRICS[discipline.value]["ranked"].items():
            nulls = table[_metric].is_null().sum()
            if nulls:
                null_clauses += f", {nulls} without a recorded {_label}"
        caption = mo.md(
            f"Ranked among {n_athletes} athletes ({levels_text}) — "
            f"{SOURCE_LABEL}{null_clauses}"
        )
    stack = [caption]
    population_note = small_population_note(n_athletes)
    if population_note is not None:
        stack.append(population_note)
    stack.append(mo.md(ATTRIBUTION_MD))
    mo.vstack(stack)
    return (first_ranked, table)


@app.cell
def _(first_ranked, table):
    mo.stop(
        table.height == 0,
        mo.callout(
            mo.md("Select at least one playing level to rank athletes."),
            kind="warn",
        ),
    )
    ordered_athletes = table.sort(
        [first_ranked, "athlete"], descending=[True, False], nulls_last=True
    )["athlete"].to_list()
    athlete = mo.ui.dropdown(
        options=ordered_athletes,
        value=ordered_athletes[0],
        label="Athlete",
    )
    athlete
    return (athlete,)


@app.cell
def _(
    ATTRIBUTION_MD,
    METRICS,
    SOURCE_LABEL,
    athlete,
    discipline,
    table,
):
    ranked = METRICS[discipline.value]["ranked"]
    bubble_row = table.filter(pl.col("athlete") == athlete.value)
    bubble_records = []
    missing = []
    for _column, (_label, _unit) in ranked.items():
        pct = bubble_row[f"{_column}_pct"][0]
        raw = bubble_row[_column][0]
        if pct is None:
            missing.append(_label)
        else:
            bubble_records.append(
                {"label": _label, "pct": pct, "raw": raw, "unit": _unit}
            )
    chart = (
        alt.Chart(alt.Data(values=bubble_records))
        .mark_circle(size=140, opacity=0.75)
        .encode(
            y=alt.Y(
                "label:N",
                sort=[label for label, _unit in ranked.values()],
                title=None,
            ),
            x=alt.X(
                "pct:Q",
                scale=alt.Scale(domain=[0, 100]),
                title="Percentile",
            ),
            color=alt.Color("pct:Q", scale=alt.Scale(scheme="turbo"), legend=None),
            tooltip=[
                alt.Tooltip("label:N", title="Metric"),
                alt.Tooltip("raw:Q", title="Value", format=".2f"),
                alt.Tooltip("unit:N", title="Unit"),
                alt.Tooltip("pct:Q", title="Percentile", format=".0f"),
            ],
        )
    )
    bubble_stack = [
        mo.md(f"**{athlete.value}** · *{SOURCE_LABEL}*"),
        chart,
    ]
    if missing:
        bubble_stack.append(mo.md("No data at this pin: " + ", ".join(missing)))
    bubble_stack.append(mo.md(ATTRIBUTION_MD))
    mo.vstack(bubble_stack)
    return


@app.cell
def _(
    ATTRIBUTION_MD,
    METRICS,
    SOURCE_LABEL,
    athlete,
    discipline,
    reducer,
    table,
):
    load_metrics = METRICS[discipline.value]["load"]
    mo.stop(not load_metrics)
    load_row = table.filter(pl.col("athlete") == athlete.value)
    load_records = [
        {"Metric": _label, "Moment (Nm)": load_row[_column][0]}
        for _column, (_label, _unit) in load_metrics.items()
    ]
    meaning = (
        "highest of the athlete's trials"
        if reducer.value == "max"
        else "mean of the athlete's trials"
    )
    mo.vstack(
        [
            mo.md(f"**{athlete.value}** · *{SOURCE_LABEL}*"),
            mo.md(
                f"Joint load ({meaning}). Joint load, not performance: "
                "absolute moments scale with body mass, so they are shown "
                "unranked."
            ),
            mo.ui.table(
                pl.DataFrame(load_records),
                selection=None,
                show_download=False,
            ),
            mo.md(ATTRIBUTION_MD),
        ]
    )
    return


@app.cell
def _(
    ATTRIBUTION_MD,
    METRICS,
    SOURCE_LABEL,
    discipline,
    first_ranked,
    table,
):
    lb_ranked = METRICS[discipline.value]["ranked"]
    lb_columns = ["athlete", "level", "hand", "n_trials"]
    for _column in lb_ranked:
        lb_columns.append(_column)
        lb_columns.append(f"{_column}_pct")
    display = table.select(lb_columns).sort(
        first_ranked, descending=True, nulls_last=True
    )
    headers = {
        "athlete": "Athlete",
        "level": "Level",
        "hand": "Hand",
        "n_trials": "Trials",
    }
    for _column, (_label, _unit) in lb_ranked.items():
        headers[_column] = f"{_label} ({_unit})"
        headers[f"{_column}_pct"] = f"{_label} pct"
    leaderboard = mo.ui.table(
        display.rename(headers),
        selection=None,
        page_size=12,
        show_download=False,
    )
    mo.vstack(
        [
            mo.md(f"*{SOURCE_LABEL}*"),
            leaderboard,
            mo.md(ATTRIBUTION_MD),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
