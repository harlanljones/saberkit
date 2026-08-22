# Changelog

All notable user-visible changes to `saberkit` are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases
use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Because the project is still pre-1.0, a minor release may contain breaking API
changes. Patch releases remain backward-compatible bug fixes. Every breaking
change must be called out explicitly in this file.

## [Unreleased]

### Added

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

- Tightened published-reference tests for park-factor-dependent statistics to
  match the documented two-point tolerance.
