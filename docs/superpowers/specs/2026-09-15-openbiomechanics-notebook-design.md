# OpenBiomechanics biomechanics explorer — design

**Status:** approved in brainstorming, 2026-09-15 · **Target release:** 0.2.0 ·
**Branch:** `feat/openbiomechanics-notebook`, rebased after the v0.1.0 docs
reconciliation PR merges.

## Summary

Ship one marimo notebook, `notebooks/biomech_explorer.py`. It fetches Driveline's
[OpenBiomechanics Project](https://github.com/drivelineresearch/openbiomechanics)
(OBP) pitching and hitting point-of-interest (POI) metrics at runtime, pinned to
one upstream commit, and ranks athletes Savant-style with the existing
`saberkit.percentile_ranks`. No Rust changes, no new public API, no change to the
wheel's contents. OBP data never enters the repository or any artifact.

## Goals

- Savant-style percentile bubbles and a leaderboard for OBP athletes, with a
  pitching/hitting toggle.
- A reproducible fetch: an immutable commit pin plus SHA-256 digests owned by
  saberkit, with errors that name the pin.
- License compliance by construction: runtime fetch, a license gate on every
  session, and synthetic fixtures for every test and offline run.
- Helpers that tests can call directly, and the same headless notebook smoke
  test every shipped notebook gets.

## Non-goals

- HitTrax (`poi/hittrax.csv`), High Performance (`hp_obp.csv`), C3D and
  full-signal release archives.
- A package-level loader (`saberkit.openbiomechanics`) or a
  `compute.biomech_table`. The library itself still performs no fetching.
- marimo WASM/Pyodide support, a persisted license acceptance, or contacting
  Driveline.
- Normalizing load metrics (per kg or per mph) or ranking them.
- Fixing the unrelated `pitching_table` `k_rate` direction issue. It is tracked
  separately.

## Decisions and rationale

| Decision | Choice | Why |
| --- | --- | --- |
| Deliverable | Notebook with percentile bubbles | Fits saberkit's marimo-first product face; the percentile engine already ranks arbitrary numeric columns in either direction (verified on real OBP aggregates). |
| Structure | Self-contained notebook, helpers as `@app.function` | Verified on marimo 0.24: `@app.function` helpers are importable attributes after an `importlib` load, and `app.run()` still works, so they are unit-testable without a sibling module or `sys.path` changes. Keeps the library's "not a data-fetching library" non-goal true. |
| Modules | Pitching + hitting, POI + metadata | Both join 1:1 on a trial key, and each athlete has exactly one session. HitTrax needs sentinel cleaning, and HP has no column definitions. |
| Trial reduction | Visible dropdown: best trial (max, default) / mean of trials | Rows are trials (2–5 pitches, 4–9 swings per athlete). Ranking raw trials would over-weight athletes with more trials. |
| Metrics | Outcomes + curated peak velocities ranked higher-is-better; load moments shown raw, never ranked | Upstream never states a direction. Absolute joint moments (Nm) mostly track body size and measure load, not performance. |
| Pin | Commit `44b98dae05cceb016f080ab39d105c85b8639084` | `dataset-v1` is a lightweight, unprotected tag. It points at a commit that lacks the data dictionaries and the MIT/CC license split, although its CSV bytes are identical. Upstream publishes no checksums for the in-git CSVs, so saberkit owns the digests. |
| Fixtures | Synthetic, schema-shaped | Real rows would put CC BY-NC-SA data in an MIT/Apache repo, and the person-based exclusion would then apply to anyone running pytest. |
| Naming | `openbiomechanics` / `biomech` | `saberkit.obp` is on-base percentage, and `obp` on PyPI is Open Bandit Pipeline. Convention: `openbiomechanics` names the data source (cache path, `tests/fixtures/openbiomechanics/`, `docs/openbiomechanics.md`, NOTICE); `biomech` names saberkit's own artefacts (`notebooks/biomech_explorer.py`, `tests/test_biomech_explorer.py`); the notebook's display name is **biomech explorer**. |

## Data source

Raw base URL:
`https://raw.githubusercontent.com/drivelineresearch/openbiomechanics/<OBP_COMMIT>/<path>`.
The files are served unauthenticated. Digests were computed by saberkit at the
pin on 2026-09-15.

| Key | Upstream path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `pitching_metadata` | `baseball_pitching/data/metadata.csv` | 45653 | `ec5686fef140e728193d4ce4bb16aa116751e716963bb2aedca11111b03816e3` |
| `pitching_poi` | `baseball_pitching/data/poi/poi_metrics.csv` | 266651 | `5ba2ac8536fba1d6997ebd81d7b1956c73fbb2e141b9c6156cd76f66265f391e` |
| `hitting_metadata` | `baseball_hitting/data/metadata.csv` | 48953 | `b87567a7dbed13dd438a16512b80b80af81cf909e1203a89f545e6b31a245372` |
| `hitting_poi` | `baseball_hitting/data/poi/poi_metrics.csv` | 717888 | `95ab62e2c36e5034435f3edaec2d7d320caf9aa61eac923d907aed6751a2619b` |

Facts the design relies on (verified at the pin):

- **Pitching.** 411 trials, 100 athletes. POI and metadata join 1:1 on
  `session_pitch`, formatted `<session>_<pitch>`. POI `session` identifies the
  athlete. Level comes from metadata `playing_level`, which records the level *at
  collection*: `college`, `high_school`, `independent` or `milb`. Handedness
  comes from POI `p_throws` (`R`/`L`). `pitch_type` is always `FF`.
- **Hitting.** 677 trials, 98 athletes. The tables join 1:1 on `session_swing`,
  formatted `<session>_<swing>`. POI `session` is unpadded, while metadata `user`
  and `session` are the same value zero-padded to six characters, which type
  inference would silently turn into integers. Level comes from metadata
  `highest_playing_level` (the *highest level reached*, same four values), and
  handedness from metadata `hitter_side`.
- **Nulls.** `exit_velo_mph_x` is null for every trial of at least one hitting
  session. `exit_velo_mph_x` and `bat_speed_mph_max_x` agree between metadata
  and POI wherever the POI value is present, so metrics always come from POI.

## Architecture

`notebooks/biomech_explorer.py` contains the following.

**`with app.setup:`** stdlib (`collections.abc.Sequence`, `hashlib`,
`http.client`, `os`, `pathlib`, `tempfile`, `urllib.request`), `marimo as mo`,
`polars as pl`, `altair as alt`, `saberkit`, and module-level constants
(`urllib.error` is deliberately absent: `HTTPError` and `URLError` are already
`OSError` subclasses, so the error taxonomy below never names them and an
unused import would fail `marimo check --strict`):

- `OBP_COMMIT`, `OBP_RAW_BASE`, and `OBP_FILES`, which maps key to
  `(path, sha256)` as in the table above.
- `METRICS`: per discipline, a `ranked` mapping and a `load` mapping of
  column → `(label, unit)`, as in the metric table below.
- `DISCIPLINES`: per discipline, `(trial_key, level_column, hand_column,
  hand_table)` — `("session_pitch", "playing_level", "p_throws", "poi")` for
  pitching and `("session_swing", "highest_playing_level", "hitter_side",
  "metadata")` for hitting. `load_discipline` reads the join key, the level
  source and the handedness source from here.
- `SMALL_POPULATION = 20`.
- `ATTRIBUTION_MD`: the source-and-changes notice rendered beneath every output
  built from OBP data (cells 6, 8, 9, 10):
  > Source: **The OpenBiomechanics Project** — Driveline Baseball Research and
  > Development (Wasserberger KW, Brady AC, Besky DM, Jones BR, Boddy KJ, 2022),
  > repository at commit `44b98dae` · licensed CC BY-NC-SA 4.0 plus the exclusion
  > in `LICENSE-DATA.md` · provided as-is, without warranties of any kind
  > (license §5). **Changes made by saberkit:** a subset of columns; trials
  > reduced per athlete (best or mean); athletes filtered by playing level;
  > metrics converted to Savant-style percentile ranks. The numbers shown are
  > saberkit's aggregates, not upstream values. Anything you export, download or
  > screenshot here is adapted material and stays under CC BY-NC-SA 4.0 with the
  > same exclusion.
- `EXCLUSION_TEXT`: the **complete** professional-organization exclusion clause
  from `LICENSE-DATA.md` at the pin — both the "While the license is clear that
  this data cannot be used for commercial purposes (which includes but is not
  limited to for-profit organizations, corporations, and sole proprietorships
  with the intent to profit now or in the future), there is also one additional
  specific exclusion where this data cannot be used in any form without a
  specific written commercial (paid) license:" lead-in and the blockquoted
  sentence that follows it. Quoting only the blockquote drops the broader
  commercial-purposes definition and the paid-licence route, which is the half
  most of saberkit's audience needs. Verbatim means word-for-word; Markdown
  emphasis markers and line wrapping may be normalized, nothing else. A comment
  above the constant records the file, the pin, and that the text is quoted from
  Driveline's license for notice purposes and is not covered by saberkit's
  MIT/Apache grant.

**`@app.function` helpers**, all pure apart from `default_cache_dir`'s
environment read and `fetch_csv`'s cache and network I/O:

1. `default_cache_dir() -> Path` returns
   `$XDG_CACHE_HOME/saberkit/openbiomechanics/<OBP_COMMIT>`, falling back to
   `~/.cache` when `XDG_CACHE_HOME` is unset, empty or not absolute
   (`base = os.environ.get("XDG_CACHE_HOME") or ""; root = Path(base) if base.startswith("/") else Path.home() / ".cache"`)
   — a naive `os.environ.get(key, default)` turns an empty value into a path
   relative to the process CWD, which could land inside the repository. The
   environment is read at call time, so tests can set `XDG_CACHE_HOME` to
   `tmp_path`.
2. `fetch_csv(key, *, cache_dir) -> bytes` looks up `(path, sha256)` in
   `OBP_FILES` at call time.
   - An unknown key raises `ValueError`.
   - If the cached file exists and its digest matches, it returns the cached
     bytes and makes no network call.
   - If the cached file exists but its digest does not match, it deletes the
     file and fetches again.
   - It fetches through `urllib.request.urlopen` (looked up at call time so tests
     can monkeypatch it) with a 30 s timeout.
   - Transport failures are caught as `except (OSError, http.client.HTTPException) as exc`
     — covering `HTTPError`, `URLError`, the `TimeoutError` a 30 s read timeout
     raises (which is *not* a `URLError`) and the `IncompleteRead` a truncated
     body raises (which is not an `OSError`) — and re-raised as `RuntimeError`
     with a message naming the URL and `OBP_COMMIT`.
   - A digest mismatch after fetching raises `RuntimeError` naming `OBP_COMMIT`,
     the path, and the expected and actual digests. Nothing is written.
   - The cached path is `cache_dir / f"{key}.csv"`, keyed by the `OBP_FILES`
     key, not by the upstream basename, which is not unique across disciplines
     (both metadata files are `metadata.csv` and both POI files are
     `poi_metrics.csv`).
   - On success it creates the directory
     (`cache_dir.mkdir(parents=True, exist_ok=True)`) **after** the digest check,
     then writes atomically: `tempfile.mkstemp(dir=cache_dir)`, write,
     `os.replace`, removing the temp file if the write fails. A digest mismatch
     therefore leaves no directory and no file. A cache write failure (`OSError`)
     is re-raised as `RuntimeError` naming the cache path, so cell 4 can render
     it — an uncaught `FileNotFoundError` from writing into a directory that does
     not yet exist is neither `RuntimeError` nor `ValueError`.
3. `load_discipline(discipline, *, metadata_csv: bytes, poi_csv: bytes) -> pl.DataFrame`
   - Reads both CSVs with `infer_schema=False`, so every column is a string and
     IDs keep their zero-padding.
   - Checks the required columns **per table** — metadata: the trial key, the
     level column, and (hitting) `hitter_side`; POI: the trial key, `session`,
     (pitching) `p_throws`, and every `ranked` and `load` metric for that
     discipline. Metrics are required in POI only. If any are absent it raises
     `ValueError` listing them per table. The metadata select is restricted to
     its required columns so the metadata copies of `pitch_speed_mph`,
     `exit_velo_mph_x` and `bat_speed_mph_max_x` cannot collide with the POI
     columns on the join.
   - Selects only the required metadata columns, then **checks for orphans
     explicitly** before joining: `poi.join(meta, on=key, how="anti")[key]` must
     be empty, otherwise it raises `ValueError` naming the discipline and up to
     five unmatched trial keys. `validate="1:1"` alone cannot do this — it checks
     only key uniqueness, and an inner join drops an unmatched POI trial
     silently. The reverse direction (a metadata row with no POI trial) is
     dropped without error, which is the documented direction of the check.
   - Inner-joins on the trial key with `validate="1:1"`, then casts metric
     columns to `Float64` with `strict=True`; empty fields are null. The join and
     the casts run inside
     `try: ... except pl.exceptions.PolarsError as exc: raise ValueError(f"{discipline}: {exc}") from exc`,
     because a duplicate key raises polars `ComputeError` and a non-numeric
     metric field raises `InvalidOperationError` — neither is a `ValueError`, and
     cell 4 would otherwise fail open with a raw traceback.
   - Returns one row per trial with columns `athlete` (POI `session`), `trial`,
     `level`, `hand`, plus the metric columns.
   - An unknown discipline raises `ValueError`.
4. `per_athlete(trials: pl.DataFrame, metrics: Sequence[str], how: str) -> pl.DataFrame`
   - `how` is `"max"` or `"mean"`; anything else raises `ValueError`.
   - Runs `group_by("athlete", maintain_order=True)` and aggregates `level` and
     `hand` with `pl.col(...).first()` (safe: both are constant within an
     athlete), `n_trials` as `pl.len()` — named to avoid colliding with cell 4's `trials`
     dict; the number of trial rows, UInt32, *not*
     `count()`, which varies per metric, so an athlete with a null in one trial
     still reports every trial — and each metric with max or mean.
   - Nulls are skipped, and an athlete whose trials are all null stays null.
   - Load metrics are aggregated with the same reducer so the load panel matches
     the dropdown.
5. `rank_population(athletes: pl.DataFrame, ranked_metrics: Sequence[str]) -> pl.DataFrame`
   - For each ranked metric it takes `column = athletes[metric]` and **skips the
     core when no finite value exists** —
     `column.dtype == pl.Null or not (column.is_not_null() & column.is_not_nan()).any()`
     — attaching `pl.lit(None, dtype=pl.Float64).alias(f"{metric}_pct")` instead.
     This guard is required, not cosmetic: `saberkit.percentile_ranks` raises
     `SaberError` ("empty distribution: no finite values remained after
     filtering") on an empty, all-null or all-NaN series, and `SaberError`
     subclasses `ValueError`, so an unguarded call would surface as an
     unhandled traceback in cell 6, which has no error handling of its own —
     cell 4's handler wraps only its own fetch-and-load body. `compute._any_qualified`
     is not an equivalent precedent: it tests only `v is not None`, so an all-NaN
     column passes it and still raises.
   - Otherwise it calls
     `saberkit.percentile_ranks(column, direction="higher_is_better", scale="savant")`
     and reattaches through the public API,
     `pl.Series(ranks).alias(f"{metric}_pct")` — the returned Arrow array is
     already Float64 and preserves nulls. The notebook never imports
     `saberkit.compute`'s private `_series`/`_attach_percentiles`.
   - Load metrics never get a `_pct` column.
6. `small_population_note(n)` returns a `mo.callout(kind="warn")` when
   `0 < n < SMALL_POPULATION` and `None` otherwise, so cell 6 has no branch of
   its own and the threshold is directly testable. `n == 0` returns `None` as
   well: an empty population is not a small population, and cell 6 already
   replaces its caption with a "select at least one playing level" callout
   there, which a second warning would only crowd.

**Cells, in file order** (marimo derives execution order from references, not
from position, so a cell may reference a name defined lower in the file):

1. **Title and attribution.** What OBP is, who produced it (Driveline Baseball
   Research & Development), a link to the repository and openbiomechanics.org,
   and a banner rendering `SOURCE_LABEL` from cell 2.
2. **Environment.** Written exactly as the three shipped notebooks write it:
   `OFFLINE = os.environ.get("SABERKIT_OFFLINE", "") == "1"` and
   `FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "openbiomechanics"`
   — the same `Path(__file__)` walk from `notebooks/` to the repository root
   that `saberkit_tour.py`, `pitcher_explorer.py` and `percentile_explorer.py`
   already use, with the extra `openbiomechanics` segment. Plus
   `SOURCE_LABEL = f"OpenBiomechanics Project @ {OBP_COMMIT[:8]}"` when online or
   `"SYNTHETIC DEMO DATA — not OpenBiomechanics data"` when `OFFLINE`, following
   the existing notebooks' "Data source: …" pattern. Cell 1 renders a banner from
   `SOURCE_LABEL`, and cells 6, 8, 9 and 10 each render it as a subtitle above
   their own output (see those cells), so an offline session is visibly
   labelled synthetic wherever it could be screenshotted.
3. **License gate**, split across two cells because marimo forbids reading a UI
   element's value in the cell that created it.
   - **3a. License notice.** Creates the checkbox *unconditionally*, so the
     definition exists in both modes:
     `accepted = mo.ui.checkbox(label="I have read Driveline's license terms and
     the exclusion above, and I am eligible to use OpenBiomechanics data under
     them.")` — the label restates only the licensor's conditions and adds no
     saberkit term of its own. The cell then ends in exactly one top-level
     expression, `notice = <info callout> if OFFLINE else mo.vstack([...])`
     followed by `notice`; a display expression inside an `if`/`else` branch is
     never shown and `marimo check` reports it as `error[branch-expression]`
     (MR002). When `OFFLINE` the callout says the data is synthetic demo data,
     not OpenBiomechanics data. Otherwise the notice gives:
     - the CC BY-NC-SA 4.0 name and link, and that NonCommercial and ShareAlike
       apply;
     - `EXCLUSION_TEXT` verbatim, as a block quote;
     - the citation in both forms the licensor asks for: `CITATION.cff` at the
       pin (Driveline Baseball Research and Development; Boddy, Kyle. *The
       OpenBiomechanics Project (OBP)*, openbiomechanics.org) and the site's
       "Citing OBP" form (Wasserberger KW, Brady AC, Besky DM, Jones BR,
       Boddy KJ, 2022);
     - `OBP_COMMIT`, a link to the repository tree at the pin, and links to
       `LICENSE-DATA.md` and the four CSVs at the pin;
     - that the data is provided as-is, without warranties of any kind
       (license §5), by the licensor, and that saberkit adds none;
     - that anything derived here — tables, charts, exports, downloads,
       screenshots — is adapted material that stays under CC BY-NC-SA 4.0 with
       the same exclusion, and must carry the same attribution if shared;
     - that saberkit's MIT/Apache license does not cover the data;
     - that saberkit cannot verify anyone's eligibility: the exclusion is a
       condition between the user and Driveline, and ticking the box is the
       user's own assessment;
     - where the data is cached
       (`$XDG_CACHE_HOME/saberkit/openbiomechanics/<commit>`, falling back to
       `~/.cache`) and that deleting that directory removes every local copy.
   - **3b. Gate.** A separate cell:
     `mo.stop(not OFFLINE and not accepted.value, mo.md("Accept the licence
     above to load OpenBiomechanics data."))` followed by `license_ok = True`.
     **Every downstream cell that touches data must take `license_ok` as a
     reference** — `mo.stop` only skips cells that reference a variable the
     stopping cell defines, so a data cell that merely sits later "in dependency
     order" runs anyway and performs the fetch. Acceptance is never stored.
4. **Data.** Signature `def _(FIXTURES, OFFLINE, license_ok)`; the body starts
   with `assert license_ok`, which is what makes the gate's `mo.stop` reach this
   cell. Builds `trials = {"pitching": ..., "hitting": ...}` via
   `load_discipline`, fed either by `fetch_csv(key, cache_dir=default_cache_dir())`
   or by reading the fixture files when `OFFLINE`. A `RuntimeError` or
   `ValueError` is surfaced as
   `mo.stop(True, mo.callout(mo.md(str(exc)), kind="danger"))` — the callout must
   be `mo.stop`'s `output` argument, because `mo.stop` replaces the cell's output
   and a callout merely evaluated beforehand is discarded. There is **no fixture
   fallback when online**, unlike the season notebooks: a fetch or parse failure
   stops the notebook with the danger callout, so synthetic values are never
   displayed as OpenBiomechanics data.
5. **Controls**, split across two cells for the same reason as the gate: a cell
   may not read the value of a UI element it created.
   - **5a. Discipline and reducer.**
     `discipline = mo.ui.radio(options=["pitching", "hitting"], value="pitching",
     label="Discipline")` and
     `reducer = mo.ui.dropdown(options={"Best trial": "max", "Mean of trials":
     "mean"}, value="Best trial", label="Trials")` — with dict options the
     `value=` argument is the *label*, not the mapped value; `reducer.value` is
     then `"max"`/`"mean"` and goes straight to `per_athlete`. The cell displays
     `mo.hstack([discipline, reducer], justify="start")`.
   - **5b. Levels.** A separate cell taking `discipline` and `trials` as
     references: `levels`, a multiselect over the levels present in
     `trials[discipline.value]`, defaulting to all, labelled "Playing level at
     collection" for pitching and "Highest level reached" for hitting. Because
     5b re-runs when the discipline changes, the multiselect is re-created with
     all levels of the new discipline selected; level selections are not carried
     across disciplines.
6. **Table.** Filters the trials by `levels`, then `per_athlete`, then
   `rank_population`, and defines `table`.
   - The cell renders exactly one object, `mo.vstack([...])`, because marimo
     displays only a cell's last expression — a caption and a callout written as
     two bare expressions would show only the callout.
   - The stack holds a caption reading "Ranked among N athletes (<levels>) —
     <SOURCE_LABEL>", where N is `table.height` and `<levels>` is the selected
     levels in a fixed order (high school, college, independent, MiLB) with
     display labels, comma-separated, or "all levels" when everything is
     selected. A ranked metric with nulls is ranked among its non-null subset
     only, so the caption adds ", M without a recorded <label>" for any such
     metric.
   - When `small_population_note(N)` returns a callout — that is, when N is below
     `SMALL_POPULATION` — the stack also holds it; it says that percentiles on a
     population this small are unstable.
   - When N is 0 (every level deselected) the caption is replaced by
     `mo.callout(mo.md("Select at least one playing level."), kind="warn")`;
     `small_population_note(0)` returns `None`, so no second warning appears,
     and `table` is an empty frame with the full schema, not an error.
   - The cell also defines `first_ranked`, the first key of the discipline's
     `ranked` mapping, so cells 7 and 10 both order by it without cell 10
     depending on cell 7.
   - The stack ends with `mo.md(ATTRIBUTION_MD)`.
7. **Athlete picker.** First line:
   `mo.stop(table.height == 0, mo.callout(mo.md("Select at least one playing level to rank athletes."), kind="warn"))`
   — this also stops cells 8 and 9, which index the selected athlete's row.
   Cell 10 references nothing this cell defines, so it still runs and renders
   the empty display copy, which is harmless because `table` keeps its full
   schema at N = 0. Then a dropdown over
   `table.sort([first_ranked, "athlete"], descending=[True, False], nulls_last=True)["athlete"]`,
   using `first_ranked` from cell 6.
   `nulls_last=True` is required: polars sorts nulls **first** under
   `descending=True`, which would make the all-null-`exit_velo_mph_x` hitter the
   default selection. The secondary `athlete` key makes ties deterministic. The
   default is the first entry of that order; changing discipline, reducer or
   levels re-creates the picker and resets it to the top athlete.
8. **Bubbles.** One row per ranked metric for the selected athlete, built from a
   long frame of (label, pct, raw value, unit):
   `alt.Chart(...).mark_circle(opacity=0.75)` with
   `y=alt.Y("label:N", sort=<the METRICS order>, title=None)`,
   `x=alt.X("pct:Q", scale=alt.Scale(domain=[0, 100]), title="Percentile")`,
   fixed `size`, `color=alt.Color("pct:Q", scale=alt.Scale(scheme="turbo"), legend=None)`,
   and tooltip label / raw value / unit / pct — matching `percentile_explorer`'s
   circle-and-turbo treatment rather than its two-axis cross-player scatter,
   which is a different chart. Rows whose `_pct` is null are dropped (Altair
   would drop them silently) and listed underneath as "No data at this pin:
   <labels>". A `<SOURCE_LABEL>` subtitle sits above the chart, and
   `mo.md(ATTRIBUTION_MD)` beneath it.
9. **Load panel.** For hitting, `METRICS["hitting"]["load"]` is empty and the
   cell renders nothing (`mo.stop(not load_metrics)`). For pitching it shows the
   selected athlete's elbow varus and shoulder internal rotation moments as raw
   Nm under the current reducer, headed by the reducer's mechanical meaning —
   "highest of the athlete's trials" or "mean of the athlete's trials" — never
   "Best trial", since the highest joint moment is the athlete's worst trial for
   load. With the note: "Joint load, not performance. Absolute moments scale with
   body mass, so they are shown unranked." A `<SOURCE_LABEL>` subtitle heads the
   panel and `mo.md(ATTRIBUTION_MD)` sits beneath it.
10. **Leaderboard.** `mo.ui.table` over a *display copy* of `table` — `table`
    itself keeps its raw column names so the smoke tests still see
    `<metric>_pct`. The copy selects `athlete`, `level`, `hand`, `n_trials`, then
    each ranked metric and its `_pct` column, and **excludes the load metrics**,
    so the leaderboard cannot be sorted into a de-facto load ranking. The
    pipeline order is select, then sort, then rename: the sort key is the raw
    column name, and the header labels are applied to the already-ordered frame.
    Headers use the label and unit, with percentile columns as "<label> pct".
    Following the other notebooks:
    `.sort(first_ranked, descending=True, nulls_last=True)`,
    `selection=None`, `page_size=12`, and `show_download=False` (the default is
    `True`, and a downloaded CSV of adapted material would carry no attribution).
    A `<SOURCE_LABEL>` subtitle heads the table and `mo.md(ATTRIBUTION_MD)` sits
    beneath it.

In a headless `app.run()` under `SABERKIT_OFFLINE=1`, the defaults apply
(pitching, best trial, all levels), so `table` holds the pitching population with
`_pct` columns.

## Metrics

Labels are saberkit's own short names: a generic biomechanics term plus a unit.
A few coincide word-for-word with upstream's data dictionary (for example "pitch
speed", "exit velocity", "peak elbow varus moment") because those are the
standard names for the quantity; nothing sentence-level is copied. No dictionary
description, event-window definition, sign convention, marker-set text or example
value is reproduced anywhere in the repository, since OBP's documentation is
CC BY-NC-SA.

| Discipline | Column | Label | Unit | Role |
| --- | --- | --- | --- | --- |
| pitching | `pitch_speed_mph` | Pitch speed | mph | ranked (outcome) |
| pitching | `max_shoulder_internal_rotational_velo` | Peak shoulder IR velocity | deg/s | ranked |
| pitching | `max_elbow_extension_velo` | Peak elbow extension velocity | deg/s | ranked |
| pitching | `max_torso_rotational_velo` | Peak torso rotation velocity | deg/s | ranked |
| pitching | `max_pelvis_rotational_velo` | Peak pelvis rotation velocity | deg/s | ranked |
| pitching | `lead_knee_extension_angular_velo_max` | Peak lead-knee extension velocity | deg/s | ranked |
| pitching | `max_cog_velo_x` | Peak center-of-mass velocity to plate | m/s | ranked |
| pitching | `elbow_varus_moment` | Peak elbow varus moment | Nm | load (unranked) |
| pitching | `shoulder_internal_rotation_moment` | Peak shoulder IR moment | Nm | load (unranked) |
| hitting | `exit_velo_mph_x` | Exit velocity | mph | ranked (outcome) |
| hitting | `bat_speed_mph_max_x` | Peak bat speed | mph | ranked (outcome) |
| hitting | `pelvis_angular_velocity_seq_max_x` | Peak pelvis angular velocity | deg/s | ranked |
| hitting | `torso_angular_velocity_seq_max_x` | Peak torso angular velocity | deg/s | ranked |
| hitting | `upper_arm_speed_mag_seq_max_x` | Peak upper-arm angular speed | deg/s | ranked |
| hitting | `max_cog_velo_x` | Peak center-of-mass velocity | m/s | ranked |

`(outcome)` and `(unranked)` are annotations for the reader, not a third role
to encode: `METRICS` has exactly two keys per discipline, `ranked` and `load`,
and nothing in the cells, helpers or tests distinguishes an outcome metric from
any other ranked one. The `ranked` mapping's insertion order is the display
order everywhere and supplies `first_ranked`.

Every ranked metric is `higher_is_better`. Deliberately excluded: hand-speed
columns (upstream's units are inconsistent), `blast_bat_speed_mph_x` (a sensor
reading with missing values), and angles such as hip–shoulder separation (they
have no performance direction).

## Testing

**Synthetic fixtures**, in `tests/fixtures/openbiomechanics/`:

- `pitching_metadata.csv`, `pitching_poi.csv`, `hitting_metadata.csv` and
  `hitting_poi.csv`, holding the required columns plus hitting metadata's
  zero-padded `user`/`session`, so the string-typing behaviour of
  `infer_schema=False` is exercised even though `load_discipline` does not select
  them.
- About 12 athletes per discipline, each with 2–5 trials.
- At least one athlete per discipline with a null in one trial, and one hitter
  whose `exit_velo_mph_x` is null in every trial.
- At least two levels per discipline. The whole fixture population is below
  `SMALL_POPULATION`, so the offline run always exercises the small-population
  warning. Requiring a *level* below the threshold would be vacuous at about 12
  athletes per discipline, so the fixtures do not claim it; the other branch is
  covered by unit-testing `small_population_note` instead.
- Fixture values are **generated, never observed**. A committed, seeded
  generator `tests/fixtures/openbiomechanics/generate.py` writes the four CSVs;
  it runs without network access, never opens an OBP file, and draws every value
  from ranges written as literals in the script and justified in a comment from
  general baseball knowledge (e.g. pitch speed 70–95 mph), not from OBP
  statistics. Athlete and trial identifiers come from reserved synthetic
  ranges chosen to sit above the id space in use at the pin: pitching sessions
  from `900001`+, and hitting sessions from `99001`+, five digits so that the
  hitting metadata copy still pads to six characters (`099001`) while POI stays
  unpadded, keeping the padding behaviour exercised. The ranges are a
  readability convention, not a correctness guarantee — fixture rows are only
  ever loaded in place of upstream data, never alongside it, so a collision
  could not arise. The join key `session_swing` is unpadded in both tables
  (`99001_1`); only metadata's `user` and `session` columns carry the
  six-character padding, so the anti-join in `load_discipline` finds no
  orphans. Regenerating with the same seed reproduces the committed files
  byte-for-byte, and the PR review checks that the generator — not a
  transformation of real rows — produced them.
- A `README.md` stating that every value is generated by `generate.py`, that no
  value is taken from or derived from OpenBiomechanics data, and that only the
  column names and file shapes follow upstream. It quotes no upstream
  documentation.

**`tests/test_biomech_explorer.py`** begins with
`marimo = pytest.importorskip("marimo")` and `pytest.importorskip("altair")`
before defining its own copy of the `_load` helper — the notebook's setup cell
imports both at module-import time and `[dev]` alone installs neither, matching
`tests/test_notebooks.py`. polars needs no guard: it is a `[dev]` dependency.
It then loads the notebook module the same way `tests/test_notebooks.py` does,
and tests:

- **`per_athlete`.** Max and mean on hand-built frames, with nulls skipped. An
  athlete whose trials are all null gets null; `n_trials` counts every trial
  row, including ones holding nulls;
  `how="median"` raises.
- **`load_discipline`.** On the fixture bytes:
  - one row per trial and `athlete` taken from POI `session`;
  - `infer_schema=False` is honoured: `pl.read_csv(hitting_metadata_bytes, infer_schema=False)`
    keeps the fixture's zero-padded `user`/`session` as strings and never coerces
    them to integers, and `load_discipline`'s `athlete`/`trial` columns come back
    as `pl.String` carrying the unpadded POI ids from the synthetic range: every
    `athlete` equals the POI `session` string and matches `^9\d{4,5}$` with no
    leading zero, and every `trial` equals `f"{athlete}_{n}"` for that row's
    trial number;
  - metrics are Float64;
  - a missing required column raises and names it;
  - a POI trial without metadata raises;
  - an unknown discipline raises.
- **`fetch_csv`.** Against `tmp_path`, with `OBP_FILES` and
  `urllib.request.urlopen` monkeypatched. These tests call
  `module.fetch_csv(...)` **directly**: *rebinding* a module-level constant
  such as `OBP_FILES` — which is what `monkeypatch.setattr` does — does not
  reach cells run through `app.run()`, because those globals are seeded from a
  copy of the setup cell's captured values. Mutating the same dict in place
  would reach them, since the copy holds the same object, but the tests must
  not rely on that: it leaks across tests and only works for mutable
  constants. The gate test
  patches `urllib.request.urlopen` instead, a shared stdlib attribute visible to
  `app.run()` as well. Cases:
  - A first fetch writes the cache, and a second call makes no network call.
  - A fetched digest mismatch raises, names the commit, and writes nothing.
  - A corrupted cache file is fetched again once.
  - An `HTTPError` raises a `RuntimeError` naming the URL.
  - An unknown key raises.
- **`rank_population`.**
  - The pct columns are exactly `<ranked>_pct`, and no load metric gets one.
  - The fastest athlete ranks highest.
  - An empty frame does not raise: the `_pct` columns exist with dtype
    `pl.Float64` and height 0. ("All-null" would be vacuous on a zero-row
    frame, so it is asserted only for the all-null-metric case below.)
  - An all-null metric gives an all-null `_pct` column without raising.
- **`small_population_note`.** `n = 0` returns `None` (an empty population is
  not a small one, and cell 6 shows its own callout there), `n = 19` returns a
  callout, `n = 20` returns `None`.
- **`METRICS` integrity.**
  - Ranked and load sets are disjoint.
  - Every column named in `METRICS` exists in the fixture headers.
  - Every column named in `METRICS`, plus the join keys and the level and
    handedness sources, appears in a per-table literal
    `UPSTREAM_REQUIRED_COLUMNS` recorded in the test — only the columns the
    notebook actually reads, transcribed from the pinned headers, never a full
    upstream header row. The pin-bump procedure re-verifies that literal against
    the live headers.
- **License gate.**
  - Setup: `SABERKIT_OFFLINE` unset, `XDG_CACHE_HOME` set to `tmp_path`, and
    `urllib.request.urlopen` patched to record calls.
  - Assert: `app.run()` finishes, neither `trials` nor `table` is in the
    definitions, and the patched opener was never called. Both names matter:
    `mo.stop` skips only cells that reference a variable the gate defines, so a
    data cell that dropped its `license_ok` reference would still define `trials`
    and fetch.
- **Offline run.** Under `SABERKIT_OFFLINE=1`, `table` has `_pct` columns for all
  ranked pitching metrics.

**`tests/test_notebooks.py`:** add `biomech_explorer` to `NOTEBOOKS`.

**Existing guards stay green.** `tests/test_compute.py`'s fresh-import hygiene
check must still pass (the package is untouched), and so must CI's `minimal` job.

**Acceptance commands** (run locally before the PR):

- `.venv/bin/python -m pytest -q`: all pass, and the count is recorded.
- `marimo check --strict notebooks/biomech_explorer.py`: exits 0 with no
  diagnostics. `--strict` is the actual gate, because plain `marimo check` exits
  0 even on error-severity findings such as `branch-expression` (MR002). Reach it
  with `marimo check --fix`, which rewrites `mo.md(\n    """…""")` into the
  canonical `mo.md("""…""")` form; hand-dedenting the markdown body does not
  clear `markdown-indentation` (MF007), which is why the three existing notebooks
  still emit it.
- A one-time online verification by the self-certified maintainer, run **outside
  the repository working tree**: copy `notebooks/biomech_explorer.py` to a scratch
  directory and run it there (`marimo edit /tmp/obp-check/biomech_explorer.py`, or
  headlessly via `app.run()` after ticking the gate), so no `__marimo__/`
  directory, thumbnail or export can land in the repo. Confirm both disciplines
  load at the pin and all four digests match. Never run `marimo export html` or
  `marimo export session` against this notebook. Afterwards assert the *delta*,
  not an empty tree — the branch legitimately carries the new notebook, docs
  page, fixtures and governance edits, so `git status --porcelain` is never
  empty at this point: capture its output before the online run and require it
  byte-identical afterwards, together with `test ! -e notebooks/__marimo__` and
  no new `notebooks/*.html`.

## Governance and documentation

- **ROADMAP.md.**
  - Add an adopted-decision section for the OpenBiomechanics notebook, dated
    2026-09-15 and user-directed, in the style of the 2026-08 marimo decision. It
    records the decisions table above.
  - Amend the permanent non-goal "Becoming a data-fetching/scraping library"
    (ROADMAP.md:100) with: "Carve-out (2026-09-15): the library package still
    performs no fetching beyond the optional pybaseball extra. One shipped
    notebook, `notebooks/biomech_explorer.py`, downloads four commit-pinned,
    digest-verified OpenBiomechanics CSVs at runtime using only the standard
    library. No loader enters `python/saberkit`, and this does not license a
    general fetching layer."
  - Amend the 2026-08 decision's closing line (ROADMAP.md:203) in the same
    change to "…no expansion of fetching beyond the thin `data.py`/`ingest.py`
    convenience and the pinned OBP fetch carved out by the 2026-09-15
    decision…", so the two sections do not contradict each other.
  - Add the next free RM item and milestone for this work (RM-10/M8 as of this
    writing), with status kept current.
  - Update the "Headless notebook execution" metric row to "Four shipped
    notebooks … All four always executable offline", and the pytest-pass-count
    row to the number `.venv/bin/python -m pytest -q` actually prints after this
    change.
  - Amend adopted-decision item 5 ("Offline determinism for tests") with the
    `biomech_explorer` exception, and record it in the new 2026-09-15 decision
    section as a deliberate departure from the 2026-08 fallback rule.
  - Amend the sanctioned-exceptions sentence at ROADMAP.md:191 exactly as
    described under **AGENTS.md** below, in the same change, so the two files
    state the same list.
- **AGENTS.md.**
  - Append a **new sentence** to the `python/saberkit` row's "Must never
    contain" cell rather than editing the existing parenthetical, which is
    scoped to `compute.py` and ends on a zero-denominator clause that does not
    apply here: "In `notebooks/`, one further exception is sanctioned:
    `biomech_explorer.py`'s per-athlete trial reduction (a `group_by("athlete")`
    max/mean over trial rows). It is a reducer over rows, not a statistic; every
    percentile it feeds still comes from `saberkit.percentile_ranks`."
  - In the same change, amend the sentence at ROADMAP.md:191 ("…the `pa` sum
    and the `k_rate` ratio as polars expressions…") to read "…the `pa` sum, the
    `k_rate` ratio, and — per the 2026-09-15 decision — `biomech_explorer.py`'s
    per-athlete max/mean trial reduction", so AGENTS.md and ROADMAP.md state the
    same list.
  - Add a quality gate: **OpenBiomechanics values never enter the repository or
    artifacts**, stated as two explicit columns so it can be applied:
    - Allowed, as provenance and schema facts: upstream file paths, upstream
      column names, the commit SHA, file byte sizes, SHA-256 digests, the level
      vocabulary, dataset-shape counts stated in prose, and the verbatim
      licence/exclusion/citation text from `LICENSE-DATA.md` and `CITATION.cff`.
    - Forbidden: data rows or field values; athlete, session or trial
      identifiers copied from the data or its dictionaries; any computed value
      (aggregate, percentile, min/max, null count, distribution) committed as a
      literal, fixture value or golden number; sentences from upstream's data
      dictionaries or module READMEs; screenshots, HTML/WASM exports, marimo
      session snapshots (`__marimo__/session/*.json`) or thumbnails
      (`__marimo__/assets/**`) produced from real data.
  - Update the headless-notebook baseline bullet to name all four notebooks, and
    the `pytest -q` baseline bullet to the exact count produced by
    `.venv/bin/python -m pytest -q` after this change.
- **This design doc.** It already satisfies that gate: "Facts the design relies
  on" states identifier *formats* (`<session>_<pitch>`, `<session>_<swing>`,
  "zero-padded to six characters") instead of copied example ids, and the null
  statements in that section and in the metrics section are shape statements
  ("null for every trial of at least one hitting session"), not measured null
  counts. Every later edit to this doc keeps that property.
- **NOTICE.** Append a paragraph, written so it reads correctly in the wheel
  too (the notebooks are sdist-only, so the wheel's reader does not have the
  file): saberkit's source repository and source distribution include the marimo
  notebook `notebooks/biomech_explorer.py`, which can download data from The
  OpenBiomechanics Project (Driveline Baseball Research and Development;
  Wasserberger KW, Brady AC, Besky DM, Jones BR, Boddy KJ, 2022,
  https://openbiomechanics.org) at runtime from the upstream repository at a
  pinned commit; that data is licensed CC BY-NC-SA 4.0 with an additional
  professional-organization exclusion stated in upstream's `LICENSE-DATA.md`, and
  saberkit's MIT/Apache-2.0 license does not cover it. No OpenBiomechanics data
  rows, and no statistics computed from them, are distributed with saberkit; the
  notebook carries only upstream paths, column names, byte sizes and SHA-256
  digests used to verify a runtime download. See `docs/openbiomechanics.md`.
- **`docs/openbiomechanics.md`** (new) covers:
  - the license summary, with the exclusion verbatim;
  - the citation;
  - the pin and digest table;
  - **Site terms vs. repo terms (read 2026-09-15; the site is not versioned).**
    `LICENSE-DATA.md` calls openbiomechanics.org/#terms "the HTML-formatted
    version" of the same license, but the site states conditions the repo file
    does not: "OBP is 100% free for individual use, forever. Institutional and
    educational uses are also permitted with a commercial license"; the FAQ
    answers that classroom use is free "through December 31st, 2030 [updated
    February 2026]" and that a researcher "affiliated or contracted with a
    professional sports team or other private company" may use OBP only with a
    commercial license; and the site applies CC BY-NC-SA to "All data, code, and
    any derived works", while the repo licenses code under MIT. saberkit does not
    treat either document as superseding the other: the notebook quotes
    `LICENSE-DATA.md` at the pin because it is versioned and citable, and users
    must satisfy **both**. If your use is institutional, on behalf of a company,
    or otherwise not clearly individual and non-commercial, obtain a commercial
    license or written confirmation first. This records what the documents say;
    it is not legal advice.
  - the **maintainer self-certification record**, in this form:
    > **Self-certification — 2026-09-15.** Harlan Jones (GitHub: harlanljones),
    > sole maintainer, certifies against `LICENSE-DATA.md` at commit
    > `44b98dae05cceb016f080ab39d105c85b8639084` (SHA-256 `19b1e9be…`) and
    > openbiomechanics.org/#terms as read on 2026-09-15: I am not an employee or
    > contractor employed by, associated with, or a significant shareholder of, a
    > professional sports organization or financial analysis firm; my use of OBP
    > is individual, personal and non-commercial, not on behalf of an
    > institution, a for-profit organization, a corporation or a sole
    > proprietorship with intent to profit now or in the future; I hold no
    > commercial OBP license and need none for this use.
    >
    > **Scope.** This record covers only the named person. It is not a
    > certification for contributors, reviewers, CI systems or users of saberkit;
    > anyone who runs the online path must assess their own eligibility. No
    > automated job ever performs the OBP fetch. The record is re-made, dated and
    > re-signed at every pin bump.
  - **Attribution parties and notices at the pin.** `CITATION.cff` names
    Driveline Baseball Research and Development and Kyle Boddy; the project site
    asks for Wasserberger KW, Brady AC, Besky DM, Jones BR, Boddy KJ (2022). The
    notebook shows both. No copyright notice accompanies the data at the pin —
    the only copyright line, in `LICENSE-CODE.md`, covers the software — so there
    is no data copyright notice to retain. Re-check at every pin bump.
  - the **pin-bump procedure**: choose a new commit; re-fetch `LICENSE-DATA.md`
    at the new commit and compare its SHA-256 with the recorded digest for the
    current pin (`44b98dae`: `19b1e9bedd22c36f02cdccd67b7c4dd561e2379f96b540006ad0c6dc9c49cc50`,
    2839 bytes — recorded for this check only; the notebook never fetches it). If
    it differs, read the diff and update `EXCLUSION_TEXT`, the gate notice and
    this doc. The short SHA in `SOURCE_LABEL` and `ATTRIBUTION_MD` is
    `OBP_COMMIT[:8]`, so it follows the pin without a separate edit. Then recompute the four CSV digests, re-verify required columns,
    re-check the attribution parties, re-sign the self-certification record, and
    update this doc and the test's upstream column literals.
- **README.md.**
  - Change "Three ready-to-run notebooks ship in" (README.md:26) to "Four".
  - Add the list entry: "**biomech explorer** — Savant-style percentiles for
    OpenBiomechanics pitching and hitting athletes. The data is *not* saberkit's
    and is *not* MIT: it is downloaded at runtime under CC BY-NC-SA 4.0 with a
    professional-organization exclusion. Read
    [`docs/openbiomechanics.md`](docs/openbiomechanics.md) before running it;
    offline it shows synthetic demo data only."
  - Amend the data-sources paragraph (README.md:173-174) to "The season
    notebooks fall back to committed fixtures when a live fetch fails
    (`SABERKIT_OFFLINE=1` forces it). `biomech_explorer` does not: its fixtures
    are synthetic, so a failed OpenBiomechanics fetch reports the error instead
    of silently substituting fabricated numbers."
  - No screenshot of OBP data; a screenshot is permitted only from an offline
    run with the synthetic banner visible.
- **`.gitignore`.** Add, with a comment saying these embed cell outputs:
  ```
  # marimo session snapshots, thumbnails and HTML exports embed cell outputs
  __marimo__/
  /notebooks/*.html
  ```
  marimo writes `<notebook_parent>/__marimo__/session/<name>.json` — which
  contains the serialized cell values — from `marimo export session` and from
  edit mode whenever lazy execution is on, and
  `__marimo__/assets/<stem>/opengraph.png` for thumbnails. None of these are
  ignored today.
- **CHANGELOG.md.** An `[Unreleased]` → Added entry for the notebook and
  `docs/openbiomechanics.md`, plus a `Fixed` entry: "The sdist now includes
  `notebooks/saberkit_tour.py`, which was omitted from the packaging list."
- **pyproject.toml.** Add `notebooks/biomech_explorer.py` to the sdist `include`
  list, plus `notebooks/saberkit_tour.py`, which is currently missing from it.

## Risks

| Risk | Mitigation |
| --- | --- |
| Upstream rewrites history again and the pinned URL 404s | The error names the pin; the pin-bump procedure in `docs/openbiomechanics.md`; the cache keeps prior fetches usable locally |
| License terms change upstream | The pin freezes the reference text; the pin-bump procedure re-reads `LICENSE-DATA.md` |
| saberkit's audience overlaps the exclusion (team or betting analysts) | Per-session gate with the verbatim exclusion; README warning; saberkit cannot enforce a person-based condition and says so |
| Tiny filtered populations give meaningless percentiles | Constant "ranked among N" caption; warning below 20 athletes |
| Load metrics misread as performance | Never ranked; explicit load note |
| OBP-derived material leaks into MIT artifacts | AGENTS quality gate; synthetic fixtures; no screenshots or exports; review checklist item in the PR |
