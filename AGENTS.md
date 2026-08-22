# AGENTS.md

Instructions for any agent (human or AI) working in this repository.

## Project intent and boundaries

`saberkit` is a Rust statistics engine for baseball sabermetrics ("plus"
stats, "minus" stats, and Baseball-Savant-style percentile rankings) exposed
to Python through PyO3 with zero-copy Arrow interchange (PyCapsule
interface). The headline product guarantee is: **zero required runtime
Python dependencies** — not pyarrow, not numpy. Anything that would make
that guarantee false (a new required dependency on pyarrow/numpy/pandas, or
a transitive one that leaks into the minimal install) is out of bounds
without an explicit decision recorded in ROADMAP.md. Statistical scope is
bounded to what's already listed in README.md's "What's implemented" table
plus explicitly planned roadmap items — this is not a general-purpose
baseball data or scraping library (pybaseball integration is an optional
extra, `saberkit[data]`, not core).

## Instruction precedence

1. Direct instructions from the user in the current session.
2. This file (`AGENTS.md`).
3. `ROADMAP.md` for what to work on and in what order.
4. `README.md` for user-facing behavior and design principles.
5. Inline code comments and doc comments for local rationale (e.g. the
   pyo3/pyo3-arrow/arrow-rs lockstep-versioning comment in `Cargo.toml`, the
   Arrow chunking rationale in `arrow_bridge.rs`).

If any of these conflict, resolve upward (user > AGENTS.md > ROADMAP.md >
README.md) and flag the conflict rather than silently picking one.

## Architectural ownership

Two crates, one hard boundary:

| Crate | Owns | Must never contain |
| --- | --- | --- |
| `crates/saberkit-core` | All statistics logic (rate stats, plus/minus families, percentiles, innings-pitched conversion, `LeagueContext`). Depends on nothing but `thiserror`. Pure, deterministic, no I/O. | Any `pyo3`, `arrow-*`, or Python-aware code. Verified: `cargo test -p saberkit-core` builds and runs with zero Python/Arrow in its dependency tree. |
| `crates/saberkit-py` | PyO3 bindings, Arrow PyCapsule conversion (`arrow_bridge.rs`), Python-facing error mapping (`error.rs`), the `operand.rs` scalar-vs-array dispatch. | Any statistical formula, threshold, or business rule. If you find yourself computing a stat inside `saberkit-py`, it belongs in `saberkit-core` instead. |
| `python/saberkit` | Thin Python package surface (`__init__.py`, `data.py` for the optional pybaseball helpers, `py.typed`). | Statistical logic. `data.py` fetches/reshapes data; it does not compute stats. |

This split is verified, not aspirational: `saberkit-core`'s own `Cargo.toml`
pulls in only `thiserror`, and `cargo test -p saberkit-core` currently runs
with no interpreter or Arrow linkage.

Within `saberkit-core`, file-level ownership by statistic family:
`rates.rs` (OBP/SLG/AVG/OPS/ISO/BABIP/wOBA/FIP/xFIP/ERA), `plus.rs` (OPS+,
sOPS+, tOPS+, ERA+, wRAA/wRC/wRC+), `minus.rs` (ERA-, FIP-, xFIP-),
`percentile.rs` (`LeagueDistribution`, percentile ranks, qualifiers),
`savant.rs` (Savant-style qualifier thresholds), `league.rs`
(`LeagueContext`), `ip.rs` (innings-pitched notation), `util.rs` (shared
numeric helpers like `safe_div`), `error.rs` (`SaberError`).
`season_constants.rs` owns lookup/provenance for bundled completed seasons;
`season_constants_generated.rs` is generator-owned and must not be hand-edited.

## Verified build/test/lint commands

Commands below marked **verified baseline** were run in this repo during the
planning/implementation pass that established this file. Commands marked
**from CI/README, not executed as a full lane here** are cited from
`.github/workflows/ci.yml` or `README.md`. Re-run every relevant command
before relying on a recorded result.

- **verified baseline** — `cargo test -p saberkit-core` → 67 passed, 0
  failed, plus 1 passing doctest (`ip::ip_to_outs`).
- **verified baseline** — `cargo clippy --workspace --all-targets -- -D
  warnings` → clean, zero warnings, across both crates.
- **verified baseline** — `cargo test -p saberkit-py
  --no-default-features` → 13 passed, 0 failed. This is the native
  binding-layer suite; keep
  `extension-module` disabled for this command so the test harness can link
  libpython.
- **verified baseline** — `pytest -q` against a locally built wheel → 53
  passed, 0 failed.
- **verified baseline** — `cargo fmt --all --check` → clean.
- **verified baseline** — duplicate-arrow-crate guard:
  `cargo tree --workspace --duplicates | grep '^arrow-'` found nothing.
- from CI, not executed as a full matrix here — `pip install -e '.[dev]'` then
  `pytest -q` then `python examples/savant_bubbles.py` (CI job `python`,
  matrix 3.11/3.12/3.13).
- from README, not executed here — `maturin develop -E dev` (build +
  install into active venv), then `pytest` from repo root.
- from CI, not executed as a full lane here — the `minimal` job: `maturin
  build --out dist`, install the wheel with `--no-deps` into a polars-only venv, assert
  neither `numpy` nor `pyarrow` importable, then run a real computation
  (`saberkit.obp`, `saberkit.ops_plus`) against polars Series alone. This is
  the enforcement mechanism for the zero-dependency guarantee — treat a
  failure here as a release blocker, not a flaky test.

Do not assume any recorded baseline still succeeds after a change. Re-run
the commands relevant to the files touched, and distinguish a local
single-interpreter result from the full CI matrix.

## Quality gates and prohibited shortcuts

- **No unwrap/panic/expect on user-controlled input.** Verified as of this
  writing: the only `unwrap()` calls in `crates/saberkit-core/src` are
  inside `#[cfg(test)]` modules or doctests. The only `.expect()` calls in
  `crates/saberkit-py/src` are the two in `arrow_bridge.rs` (`cast_f64`),
  each guarded by a preceding `dtype` check that makes the downcast
  infallible by construction — that pattern (a documented, guarded
  invariant `.expect()`) is acceptable; an unguarded `.expect()`/`.unwrap()`
  on data arriving from Python is not. New code must preserve this: fallible
  paths on user input return `Result`/`PyResult`, not panic.
- **Preserve "undefined is not an error."** A statistic with a zero
  denominator or otherwise undefined input returns `None` (an Arrow null in
  batch mode), never `NaN`, `Infinity`, or a panic. `util::safe_div` is the
  existing enforcement point in `saberkit-core` — reuse it rather than
  reimplementing zero-guard logic ad hoc.
- **Preserve "misconfiguration is an error."** Bad league constants
  (missing, NaN, out of range) and mismatched array lengths must raise
  `SaberError` (`crates/saberkit-core/src/error.rs`), surfaced to Python as
  `saberkit.SaberError`, a `ValueError` subclass
  (`crates/saberkit-py/src/error.rs`). Do not silently coerce or clamp bad
  constants.
- **Park factors stay on the 100-scale at the API boundary**, even where an
  internal formula wants a decimal ratio (`util::pf_ratio` exists for that
  conversion — use it rather than duplicating the `/100.0`).
- **Caller supplies league population definitions.** Do not add code that
  guesses or hardcodes which players count toward a league average (e.g.
  whether pitchers' batting lines are included) — that decision is a
  `LeagueContext` input, not library logic.
- **No new required runtime dependency in `pyproject.toml`'s
  `[project].dependencies`.** It is deliberately empty (see the comment in
  `pyproject.toml`). Anything needed only for `saberkit[data]` goes in the
  `data` extra; anything needed only for testing goes in `dev`. If a change
  requires numpy or pyarrow at runtime for the base install, stop and raise
  it — this breaks the CI `minimal` job by design.
- **No statistics logic in `saberkit-py`.** Bindings call into
  `saberkit-core` and translate types/errors; they do not compute.
- **Keep pyo3 / pyo3-arrow / arrow-rs versions in lockstep.** Per the
  comment in root `Cargo.toml`: `pyo3-arrow` pins a specific `arrow-*` major
  version, and bumping one without the others produces two incompatible
  copies of `arrow-array` in the dependency graph (manifests as a confusing
  "expected ArrayRef, found ArrayRef" type error, not an obvious version
  conflict). Bump the trio together or not at all, and let the CI
  duplicate-arrow guard (`cargo tree --workspace --duplicates`) catch
  regressions.
- **Keep league-total derivation in Rust.** `LeagueContext.from_totals`
  delegates rate and `c_fip` derivation to the Python-exposed
  `saberkit._core.LeagueTotals`. Do not reintroduce a parallel Python
  formula. Changes to `LeagueTotals` or `from_totals` must preserve the
  cross-language regression test in `tests/test_plus.py`.
- **Season constants are generated, never hand-edited.** Bundled 2010–2025
  values come from Retrosheet regular-season play-by-play through
  `scripts/generate_season_constants.py`, with attribution in `NOTICE`, an
  exact Chadwick Bureau mirror revision, and per-season source digests.
  Preserve the all-MLB-batters population, completed-half-inning RE24 rule,
  source-integrity tests, and published-reference tolerance test. A new season
  is a reviewed regeneration from completed data, not a plausible row typed
  into `season_constants_generated.rs`.

## Coordination protocol for concurrent agent work

- **Decompose by crate/file ownership**, not by feature-across-files.
  `saberkit-core` changes and `saberkit-py` changes are independent lanes
  whenever a task doesn't require both (e.g. adding a new rate stat that has
  no new binding yet). Within `saberkit-core`, different statistic families
  (`rates.rs`, `plus.rs`, `minus.rs`, `percentile.rs`, `league.rs`) can
  usually be edited concurrently by different agents since they don't share
  mutable state — but check for cross-file dependencies first (e.g.
  `minus.rs` and `plus.rs` both call into `util.rs` and share test fixtures
  like `NEUTRAL`).
- **One writer per file.** Do not have two agents editing the same file
  concurrently; if a task needs changes to a shared file (e.g. `lib.rs`
  re-exports, `error.rs` new variants), serialize that file through one
  agent and let others build on top once it lands.
- **Run the three CI lanes independently, then integrate.** The `rust` job
  (fmt, clippy, `cargo test -p saberkit-core`, duplicate-arrow guard), the
  `python` job (pytest matrix + example script), and the `minimal` job
  (wheel build + dependency-free import check) exercise different
  boundaries and can be validated in parallel by different agents. A change
  is not done until all three would pass, even if only one lane's files
  were touched — a `saberkit-core` change can still break `minimal` if it
  changes public signatures the Python layer depends on.
- **Revalidate after every merge**, not just before: run `cargo test -p
  saberkit-core` and `cargo clippy --workspace --all-targets -- -D
  warnings` after integrating concurrent branches, since two independently
  passing changes can still conflict (e.g. two agents adding the same
  export name, or a core-side signature change landing after a Python
  binding was already written against the old signature).
- **Cross-crate changes are a single lane, not two.** If a task requires
  both a new `saberkit-core` function and a new `saberkit-py` binding for
  it, treat that as one unit of work assigned to one agent (or a strictly
  sequential handoff: core lands and is tested first, then bindings), not
  two agents working the two halves in parallel — the binding can't be
  written correctly against an unstable core signature.

## Required progress reporting

Report progress against measures that are actually checkable in this repo,
not activity counts:

- **Rust test pass count and delta.** State the `cargo test -p
  saberkit-core` summary line verbatim (e.g. "67 passed; 0 failed") before
  and after a change, plus doctest count. A regression in passed-test count
  is a stop-and-fix condition, not something to report and move past.
- **Clippy warning count.** `cargo clippy --workspace --all-targets -- -D
  warnings` must remain at zero warnings (it currently is, verified). Report
  the exact command output, not "clippy passes."
- **Binding-layer Rust test pass count and delta.** State the
  `cargo test -p saberkit-py --no-default-features` summary before and after
  changes to `crates/saberkit-py`; the recorded baseline is 13 passed, 0
  failed.
- **Which README backlog items are closed.** Season constants /
  `LeagueContext.for_season` is closed; published PyPI wheels remain open;
  park-factor computation is a permanent non-goal. Report status against these
  three by name, not vague "progress made."
- **New unwrap/panic/expect introduced on user-controlled paths.** Zero is
  the bar; grep for it (`grep -rn "unwrap()\|panic!\|expect(" crates/*/src`)
  before claiming a change is done, and manually confirm any hit is either
  test code or a guarded invariant.
- **New required runtime dependencies.** Zero is the bar for
  `[project].dependencies` in `pyproject.toml`; any addition must be called
  out explicitly, not left to be discovered by the `minimal` CI job.
- When a claim can't be backed by a command you actually ran, say so
  explicitly ("not verified in this session") rather than asserting it.
