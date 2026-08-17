# saberkit

Fast batch sabermetrics in Rust, with Python bindings: the **"plus" family** of
baseball statistics (OPS+, sOPS+, tOPS+, ERA+, wRC+), the FanGraphs **"minus"
family** (ERA-, FIP-, xFIP-), and **Baseball-Savant-style league percentile
rankings** — the 1–100 "bubbles".

```python
import polars as pl
import saberkit

df = pl.read_csv("batters.csv")
obp = saberkit.obp(df["h"], df["bb"], df["hbp"], df["ab"], df["sf"])
```

Arrow arrays cross the Rust/Python boundary through the
[Arrow PyCapsule interface](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html),
so `polars.Series`, `pyarrow.Array`, and pandas `ArrowDtype` columns all pass
with **no copy and no conversion**. `saberkit` has **zero required runtime
dependencies** — not even pyarrow.

Pass plain numbers instead of arrays and you get a plain number back:

```python
>>> round(saberkit.obp(h=150, bb=60, hbp=5, ab=500, sf=5), 4)
0.3772
```

## Install

```bash
pip install saberkit              # core library, no dependencies
pip install "saberkit[data]"      # adds pybaseball helpers for fetching data
```

Requires Python 3.11+.

## Design

**Undefined is not an error.** A player with zero at-bats has no batting
average. Every statistic returns `None` — an Arrow null in batch mode — rather
than raising, returning NaN, or returning infinity. Nulls propagate elementwise.

**Misconfiguration *is* an error.** A null player row is normal; a NaN league
constant silently poisons every result it touches. Bad constants and mismatched
array lengths raise `saberkit.SaberError` (a `ValueError` subclass).

**Park factors are on the 100-scale everywhere** (100 = neutral), matching how
Baseball-Reference and FanGraphs publish them. Some source formulas are written
in terms of a decimal ratio; `saberkit` normalizes at the API boundary so
callers never have to track which convention a given statistic wants.

**You choose the population.** League averages are *inputs*, not something the
library guesses. Whether `lgOBP` includes pitchers hitting is a real
methodological choice, so it belongs to the caller.

## Layout

The statistical core is a separate crate that depends on nothing but
`thiserror` — no Python, no Arrow, no I/O:

| Crate | Role |
| --- | --- |
| `crates/saberkit-core` | The statistics. Pure Rust, testable with `cargo test`, no interpreter needed. Usable standalone from Rust. |
| `crates/saberkit-py` | The only crate that knows Python exists. Arrow conversion and PyO3 bindings; contains no statistics. |

## Development

```bash
cargo test -p saberkit-core                 # statistics, no Python involved
cargo clippy --workspace -- -D warnings
maturin develop -E dev                      # build + install into the active venv
pytest                                      # Arrow interop, nulls, error paths
```

## What's implemented

| Group | Statistics |
| --- | --- |
| Rate stats | `obp` `slg` `avg` `ops` `iso` `babip` `woba` `fip` `xfip` `era` `total_bases` `singles` |
| Plus family | `ops_plus` `sops_plus` `tops_plus` `era_plus` `wraa` `wrc` `wrc_plus` |
| Minus family | `era_minus` `fip_minus` `xfip_minus` |
| Percentiles | `LeagueDistribution` `percentile_ranks` `batter_qualifier` `pitcher_qualifier` |
| Innings | `ip_to_outs` `outs_to_innings` |

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

## Not yet included

- **Season constants.** The FanGraphs "Guts!" table (wOBA weights, `wOBAScale`,
  `cFIP`, league R/PA) is not bundled, so there is no
  `LeagueContext.for_season(2024)`. Supply the constants yourself, or derive
  what you can from counting stats with `LeagueContext.from_totals`. Shipping
  unverified constants that *look* authoritative would be worse than shipping
  none.
- **Published wheels.** Building from source works; there is no PyPI release
  and no cross-platform wheel matrix yet.
- **Park factors.** You supply them. `saberkit` does not compute or bundle any.

## License

MIT OR Apache-2.0
