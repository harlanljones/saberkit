# saberkit

Live sabermetrics for [marimo](https://marimo.io) notebooks, computed in Rust:
the **"plus" family** of baseball statistics (OPS+, sOPS+, tOPS+, ERA+, wRC+),
the FanGraphs **"minus" family** (ERA-, FIP-, xFIP-), and
**Baseball-Savant-style league percentile rankings** — the 1–100 "bubbles".

Fetch a season, compute everything, and drive it with sliders:

```python
import marimo as mo
import saberkit

season = mo.ui.dropdown(options=list(saberkit.compute.SEASONS), value=2024)
park_factor = mo.ui.slider(start=85, stop=115, value=100)

table = saberkit.compute.batting_table(
    saberkit.ingest.load_batting(season.value),
    league="season",
    season=season.value,
    park_factor=float(park_factor.value),
)
```

Every rate stat, OPS+, wRC+, and the percentile ranks recompute reactively as
the controls move. Four ready-to-run notebooks ship in
[`notebooks/`](notebooks/):

- **percentile explorer** — Savant-style 1–100 percentile bubbles across wOBA,
  OPS+, and wRC+. ([![Open in molab](https://marimo.io/molab-shield.svg)](https://molab.marimo.io/github/harlanljones/saberkit/blob/main/notebooks/percentile_explorer.py))
- **pitcher scout** — the ERA-/FIP- "minus" family against the strikeout bubble.
  ([![Open in molab](https://marimo.io/molab-shield.svg)](https://molab.marimo.io/github/harlanljones/saberkit/blob/main/notebooks/pitcher_explorer.py))
- **saberkit tour** — the whole stat family (rate, plus, minus, percentiles) on
  one screen, plus a tour of the scalar batch API underneath.
  ([![Open in molab](https://marimo.io/molab-shield.svg)](https://molab.marimo.io/github/harlanljones/saberkit/blob/main/notebooks/saberkit_tour.py))
- **biomech explorer** — Savant-style percentiles for OpenBiomechanics pitching
  and hitting athletes. The data is *not* saberkit's and is *not* MIT: it is
  downloaded at runtime under CC BY-NC-SA 4.0 with a professional-organization
  exclusion. Read [`docs/openbiomechanics.md`](docs/openbiomechanics.md) before
  running it; offline it shows synthetic demo data only.
  ([![Open in molab](https://marimo.io/molab-shield.svg)](https://molab.marimo.io/github/harlanljones/saberkit/blob/main/notebooks/biomech_explorer.py))

```bash
pip install "saberkit[marimo,data]"   # data adds pybaseball for live fetching
marimo edit notebooks/saberkit_tour.py   # runs offline without `data` too
```

## Also a fast batch library

Pass Arrow arrays and you get Arrow back through the
[PyCapsule interface](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html)
— `polars.Series`, `pyarrow.Array`, and pandas `ArrowDtype` columns all pass
with no copy and no conversion. Pass plain numbers and you get a number:

```python
>>> round(saberkit.obp(h=150, bb=60, hbp=5, ab=500, sf=5), 4)
0.3772

league = saberkit.LeagueContext.for_season(2024)
rating = saberkit.wrc_plus(0.390, ctx=league, park_factor=102)
```

`saberkit` has **zero required runtime dependencies** — not even pyarrow.
The notebook layer (`ingest`, `compute`) imports polars lazily; scalar use
needs nothing installed at all.

## Install

```bash
pip install saberkit              # core library, no dependencies
pip install "saberkit[marimo]"    # adds marimo + altair + polars for notebooks
pip install "saberkit[data]"      # adds pybaseball helpers for fetching data
```

Requires Python 3.11+.

## Design

**Undefined is not an error.** A player with zero at-bats has no batting
average. Every statistic returns `None` — an Arrow null in batch mode — rather
than raising, returning NaN, or returning infinity. Nulls propagate
elementwise, and the table layer extends the rule to whole populations: filter
a dashboard until nobody qualifies and the percentile columns come back
all-null instead of crashing your cell.

**Misconfiguration *is* an error.** A null player row is normal; a NaN league
constant silently poisons every result it touches. Bad constants and mismatched
array lengths raise `saberkit.SaberError` (a `ValueError` subclass).

**League baselines are inputs, not guesses.** `compute.batting_table` makes
you say which population defines "league average": bundled season constants
(`league="season"`), the data on screen (`league="sample"`), or your own
`LeagueContext`. Whether pitchers' hitting counts is a methodological choice,
and it stays with you.

**Park factors are on the 100-scale everywhere** (100 = neutral), matching how
Baseball-Reference and FanGraphs publish them.

## Layout

The statistical core is a separate crate that depends on nothing but
`thiserror` — no Python, no Arrow, no I/O:

| Crate / package | Role |
| --- | --- |
| `crates/saberkit-core` | The statistics. Pure Rust, testable with `cargo test`, no interpreter needed. Usable standalone from Rust. |
| `crates/saberkit-py` | The only crate that knows Python exists. Arrow conversion and PyO3 bindings; contains no statistics. |
| `python/saberkit/ingest.py` | Fetch-and-reshape: publisher column names → canonical polars frames. No formulas. |
| `python/saberkit/compute.py` | One-call tables: wires columns into the Rust-backed functions and reattaches results. No formulas. |
| `notebooks/` | Shipped marimo apps built on the above. |

## Development

```bash
cargo test -p saberkit-core                 # statistics, no Python involved
cargo test -p saberkit-py --no-default-features  # binding layer (cast, nulls, chunks)
cargo clippy --workspace -- -D warnings
maturin develop -E dev                      # build + install into the active venv
pytest                                      # incl. headless runs of every notebook
SABERKIT_OFFLINE=1 marimo edit notebooks/pitcher_explorer.py   # notebooks without network
```

Maintainers should follow [`RELEASING.md`](RELEASING.md) for versioning,
artifact verification, trusted-publisher setup, and tagging.

## What's implemented

| Group | Statistics |
| --- | --- |
| Rate stats | `obp` `slg` `avg` `ops` `iso` `babip` `woba` `fip` `xfip` `era` `total_bases` `singles` |
| Plus family | `ops_plus` `sops_plus` `tops_plus` `era_plus` `wraa` `wrc` `wrc_plus` |
| Minus family | `era_minus` `fip_minus` `xfip_minus` |
| Percentiles | `LeagueDistribution` `percentile_ranks` `batter_qualifier` `pitcher_qualifier` |
| Innings | `ip_to_outs` `outs_to_innings` |
| League context | `LeagueContext.from_totals` `LeagueContext.for_season` (2010–2025) |
| Tables | `compute.batting_table` `compute.pitching_table` |

### Accuracy

Statistics that depend only on their inputs — OBP, SLG, wOBA, FIP, sOPS+,
tOPS+ — reproduce published figures exactly. Those involving park factors
(OPS+, ERA+, and the minus family) approximate the publishers' internal
pipelines, which use regressed multi-year park factors; expect agreement to
within a point or two. Each function's docstring says which it is.

### Innings pitched

Baseball records innings in a notation where the digit after the decimal counts
*outs*: `190.1` is 190⅓ and `190.2` is 190⅔. Reading those as decimals
understates the denominator by about 0.7% — enough to shift a FIP in the third
decimal and quietly break comparisons against published figures. `saberkit`
converts through outs internally and rejects impossible values like `190.4`.

### Season constants and provenance

`LeagueContext.for_season(year)` supplies completed-season MLB constants for
2010–2025. They are saberkit constants derived from Retrosheet regular-season
play-by-play—not copies of FanGraphs' Guts! table. The population is all MLB
batters, including pitcher batting where it occurred. The generator measures
each season's RE24 matrix, derives linear event weights relative to outs, scales
wOBA to league OBP, and computes the FIP constant from league totals.

The derivation is reproducible with
[`scripts/generate_season_constants.py`](scripts/generate_season_constants.py).
Every season row records a SHA-256 digest of its source event files and the
generated module records the exact Chadwick Bureau Retrosheet revision. Raw
Retrosheet data is not packaged. See [`NOTICE`](NOTICE) for attribution.

Because the methodology and population are explicit, these constants can
differ slightly from publisher-specific tables. In-progress seasons are never
bundled; requesting an unsupported year raises `SaberError`.

### Data sources

`saberkit.data` wraps pybaseball's FanGraphs scrapers behind the optional
`data` extra; `saberkit.ingest` reshapes their output — and any polars/
pandas/pyarrow frame you already have — into canonical lowercase columns.
Scraped sites change without notice, so treat fetching as convenience, not
contract, and pin snapshots for anything reproducible. The season notebooks
fall back to committed fixtures when a live fetch fails (`SABERKIT_OFFLINE=1`
forces it). `biomech_explorer` does not: its fixtures are synthetic, so a
failed OpenBiomechanics fetch reports the error instead of silently
substituting fabricated numbers.

## Not yet included

- **Published wheels.** CI builds candidate wheels for Linux x86_64/aarch64,
  macOS Intel/Apple Silicon, and Windows x86_64, but no PyPI release has been
  published yet.
- **Park factors.** You supply them. `saberkit` does not compute or bundle any.

## License and data attribution

MIT OR Apache-2.0

Bundled season constants are derived from Retrosheet data under its attribution
terms; see [`NOTICE`](NOTICE).
