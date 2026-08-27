# Changelog

All notable user-visible changes to `saberkit` are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases
use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because the project is still pre-1.0, a minor release may contain breaking API
changes. Patch releases remain backward-compatible bug fixes. Every breaking
change must be called out explicitly in this file.

## [0.1.0] — 2026-08-27

### Initial release

## [Unreleased]

### Added

- A marimo-focused interactive layer, while keeping the base install at zero
  required dependencies: `saberkit.ingest` (season loaders and an offline
  `normalize` that maps publisher column names like `AB`/`2B`/`SO` to
  canonical ones), `saberkit.compute.batting_table` and
  `saberkit.compute.pitching_table` (one-call polars tables wiring rate
  stats, plus/minus ratings, and Savant percentile ranks from the existing
  Rust-backed functions), and two shipped reactive notebooks under
  `notebooks/`.
- A `marimo` optional extra (`marimo`, `altair`, `polars`) so the notebooks
  run out of the box; the CI `minimal` job continues to enforce that plain
  installs pull in nothing.
- Headless notebook smoke tests (offline via committed fixtures or
  `SABERKIT_OFFLINE=1`) plus ingestion/compute suites; a regression test pins
  that `import saberkit` never loads polars, pyarrow, pandas, numpy, marimo,
  or pybaseball.
- Native Rust tests for the Python binding layer's Arrow casting, null,
  multi-chunk, scalar, and length-mismatch paths.
- A Python-exposed `LeagueTotals` object so `LeagueContext.from_totals` uses
  the Rust core as the single source of derived league rates and `c_fip`.
- Offline tests for the optional pybaseball column-name fallback.
- CI wheel builds for Linux x86_64/aarch64, macOS Intel/Apple Silicon, and
  Windows x86_64, plus a source-distribution artifact.
- `LeagueContext.for_season(year)` with reproducible Retrosheet-derived MLB
  constants for completed seasons 2010–2025.
- A standard-library-only constants generator, per-season source digests,
  Retrosheet attribution, and a trusted-publishing release workflow.

### Changed

- The package now presents itself as a marimo-first toolkit for live
  sabermetrics; the batch function-level API is unchanged and remains the
  compute engine underneath.
- `examples/savant_bubbles.py` was ported into `notebooks/` and removed; CI's
  Python job runs the notebooks headlessly through pytest instead.
- Tightened published-reference tests for park-factor-dependent statistics to
  match the documented two-point tolerance.
