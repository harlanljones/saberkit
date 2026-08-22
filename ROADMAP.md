# ROADMAP.md

An executable plan for `saberkit`, not a wish list. See `AGENTS.md` for
durable development rules; this file is where scope, priority, and
milestone-level decisions live.

## Current state (recorded verified baseline unless noted)

- Two-crate workspace: `saberkit-core` (pure Rust, only dep `thiserror`) and
  `saberkit-py` (PyO3 + Arrow PyCapsule bindings).
- `cargo test -p saberkit-core`: **63 passed, 0 failed**, plus **1 passing
  doctest** (`ip::ip_to_outs`).
- `cargo clippy --workspace --all-targets -- -D warnings`: **clean, 0
  warnings**.
- `saberkit-py` now has a native Rust test suite: **12 passed, 0 failed**
  via `cargo test -p saberkit-py --no-default-features` (RM-4 complete: tests
  for `cast_f64` dtype/null handling, multi-chunk merging, and
  `operand.rs`'s length-mismatch/scalar logic). This required three changes:
  an `extension-module` default feature (tests build without it), a
  dev-dependency on `pyo3/auto-initialize`, and a `build.rs` that links
  libpython for the test harness only — under `abi3`, pyo3 skips libpython
  linking even when `extension-module` is off. CI's `rust` job runs this
  suite with `setup-python` + `PYO3_PYTHON`.
- pytest baseline now verified: **50 passed** (`pytest -q` after
  `maturin develop -E dev`), up from the 43 counted at planning time.
- RM-5, RM-6, RM-7, and RM-8 are complete:
  `LeagueContext.from_totals` delegates all
  rate derivations to the exposed `_core.LeagueTotals` pyclass with a
  regression test pinning Python vs Rust `c_fip`; both `.expect()` calls in
  `arrow_bridge.rs` carry documented-invariant SAFETY comments;
  `tests/test_data.py` covers the column fallback; `test_plus.py`'s park-factor
  tolerances are ±2.0, matching README's "within a point or two".
- Statistics implemented per `README.md`'s table: rate stats (`obp` `slg`
  `avg` `ops` `iso` `babip` `woba` `fip` `xfip` `era` `total_bases`
  `singles`), plus family (`ops_plus` `sops_plus` `tops_plus` `era_plus`
  `wraa` `wrc` `wrc_plus`), minus family (`era_minus` `fip_minus`
  `xfip_minus`), percentiles (`LeagueDistribution` `percentile_ranks`
  `batter_qualifier` `pitcher_qualifier`), innings conversion (`ip_to_outs`
  `outs_to_innings`). Cross-checked against actual source files present:
  `rates.rs`, `plus.rs`, `minus.rs`, `percentile.rs`, `savant.rs`,
  `league.rs`, `ip.rs` all exist and match.
- CI (`.github/workflows/ci.yml`) defines five jobs: `rust`, `python` (matrix
  3.11/3.12/3.13), `minimal` (dependency-free wheel install/compute check),
  `wheels` (the approved five-target matrix), and `sdist`. The workflow parses
  locally; the new cross-platform jobs have not yet run on GitHub.
- README's own "Not yet included" list (verified still accurate by reading
  README and grepping source for any partial implementation):
  1. No bundled season constants table / no `LeagueContext.for_season(2024)`.
     `LeagueContext::from_totals` exists in `league.rs` as the
     derive-it-yourself path; no per-season constant table exists anywhere
     in the tree (grepped, none found).
  2. No PyPI release. Candidate cross-platform wheel and sdist jobs now exist,
     but their first GitHub matrix run and the publishing step remain open.
  3. No park-factor computation — this is stated as a deliberate design
     choice ("You supply them"), not a gap.
- The binding-layer hardening backlog from the initial planning pass is
  closed: native tests exist, league-total derivation has one Rust source of
  truth, guarded downcasts are documented, the optional-data fallback has a
  network-free test, and the published-reference tolerances match README.
  These are now regression gates rather than active roadmap work.

## Objective

Keep `saberkit-core`'s statistical correctness and `saberkit-py`'s
zero-copy, zero-required-dependency binding guarantee intact while closing
the two addressable backlog items README names: sourced season constants and
published wheels. The next development phase is decision-led: define the
release policy, wheel platform matrix, and acceptable constants source
before implementing or publishing artifacts.

## Scope

- Closing README's "Not yet included" items #1 and #2.
- Preserving the completed RM-4 through RM-8 work as regression coverage.
- Ongoing maintenance of the pyo3/pyo3-arrow/arrow-rs lockstep-versioning
  constraint as a standing risk (see Risks).

## Non-goals (permanent, not deferred work)

- **Computing or bundling park factors.** README states callers supply
  them; this is a permanent design boundary, not a TODO. Do not add a work
  item for "implement park factor calculation."
- **Becoming a data-fetching/scraping library.** `pybaseball` integration
  via the `saberkit[data]` extra is a convenience, not core scope. Do not
  expand `data.py` into a general MLB data client.
- **Guessing league population definitions.** Whether pitcher batting lines
  count toward a league average is a caller decision (`LeagueContext`
  input), not something to infer or default.
- **Adding numpy or pyarrow as a required runtime dependency.** The
  zero-copy PyCapsule design exists specifically to avoid this; it is not a
  simplification to revisit.

## Release and versioning policy

- Releases follow Semantic Versioning. While the project is pre-1.0, minor
  releases may contain documented breaking API changes; patch releases remain
  backward-compatible fixes.
- Root `Cargo.toml`'s `workspace.package.version` is the single version source.
  Both crates inherit it and maturin supplies the Python package version from
  the extension metadata; do not add a second literal version to
  `pyproject.toml`.
- User-visible changes accumulate under `CHANGELOG.md`'s `[Unreleased]`
  section. A release moves those entries under a dated version heading and
  adds a fresh empty `[Unreleased]` section.
- Release tags use `vMAJOR.MINOR.PATCH` and must match the workspace version.
  The release commit must pass the Rust, Python, and minimal-install CI jobs.
- The first package-index release includes cross-platform wheels if RM-2/RM-2b
  are approved and complete. Season constants are not required for the first
  release; RM-3/RM-3b remain the next product milestone if they are not ready.
- Publishing must use a repository-scoped trusted publisher or an equivalently
  short-lived credential, gated by maintainer approval. The package-index
  project owner and approving maintainer are still TBD, so RM-1b cannot start.

## Remaining unresolved decisions (TBD)
- **PyPI ownership/publishing credentials: TBD.** Nothing in the repo
  indicates who would own a PyPI account/trusted-publisher setup for
  `saberkit`. Cannot assign an owner for wheel-publish work until this is
  resolved by the user.
- **Wheel platform matrix scope: resolved.** The first release targets the five
  entries recorded under M3. The maintainer approved the proposal by directing
  development to begin; RM-2b is now in progress.
- **Season-constants sourcing: TBD.** README explains *why* no table is
  bundled (avoiding unverified data that looks authoritative) but not what
  would make a source acceptable (a specific dataset license, a citation
  requirement, a validation process against known published wOBA weights).
  `RM-3` starts by proposing a sourcing/validation standard, not by
  fabricating a table.

## Metrics

| Metric | Baseline (verified) | Target | Measurement method | Owner | Cadence |
| --- | --- | --- | --- | --- | --- |
| `saberkit-core` unit test pass count | 63 passed / 0 failed (recorded baseline) | No regression; grows with new statistics | `cargo test -p saberkit-core`, read summary line | TBD | Every PR touching `saberkit-core` |
| `saberkit-core` doctest pass count | 1 passed | No regression | `cargo test -p saberkit-core` (doctest section) | TBD | Every PR touching doc comments with examples |
| Clippy warnings (workspace) | 0 (recorded baseline) | 0, always | `cargo clippy --workspace --all-targets -- -D warnings` | TBD | Every PR |
| `saberkit-py` native Rust test count | 12 passed (RM-4 landed) | Grows with binding-layer changes | `cargo test -p saberkit-py --no-default-features` | TBD | Every PR touching `crates/saberkit-py` |
| pytest pass count | 50 passed (recorded baseline) | 50/50 passing at minimum, grows with new coverage | `pytest -q` from repo root | TBD | Every PR touching `python/` or `crates/saberkit-py` |
| README "Not yet included" items closed | 0 of 2 addressable items (park factors is a non-goal, excluded from this count) | 2 of 2 | Manual: re-read README, confirm section rewritten/removed with matching capability shipped | TBD | Per milestone |
| CI job pass/fail (`rust`, `python`, `minimal`, `wheels`, `sdist`) | Existing local gates pass; new artifact jobs await GitHub | All configured jobs green on `main` | GitHub Actions status on the branch | TBD | Every push/PR |
| Wheel platforms configured | 5 candidate wheel targets; GitHub run pending | 5 wheel targets passing in CI | Count of successful agreed OS/architecture matrix entries | TBD | Per RM-2/RM-2b |

Owners are marked TBD because no team roster or release owner is recorded in
the repo. Cadence is event-based where repository evidence supports one.

## Milestones and exit gates

### M1 — Baseline confirmed

- Exit gate: `AGENTS.md` and `ROADMAP.md` exist and are traceable to
  verified repo state. **Done.**

### M2 — Season constants path decided (maps to README item #1)

- Exit gate: the source, license, supported season range, schema, and
  reference-validation rule are approved and recorded, or a deliberate
  deferral is recorded with a reason. Shipping remains RM-3b's separate
  exit gate.

### M3 — Wheel publishing path decided (maps to README item #2)

- Exit gate: the exact OS/architecture matrix and publishing mechanism are
  approved and recorded, or a deliberate source-only deferral is recorded
  with a reason. Building the matrix remains RM-2b's separate exit gate.

#### RM-2 approved first-release matrix

| Platform tag family | Rust target | GitHub runner | Rationale |
| --- | --- | --- | --- |
| manylinux | `x86_64-unknown-linux-gnu` | `ubuntu-22.04` via maturin's manylinux container | Baseline Linux server and desktop target |
| manylinux | `aarch64-unknown-linux-gnu` | `ubuntu-22.04` via cross-compiling container | Linux ARM servers and developer machines |
| macOS | `x86_64-apple-darwin` | `macos-15-intel` | Intel Macs still within the supported Python range |
| macOS | `aarch64-apple-darwin` | `macos-latest` | Native Apple Silicon support |
| Windows | `x86_64-pc-windows-msvc` | `windows-latest` | Mainstream 64-bit Windows support |

Build one `abi3-py311` wheel per target, plus one source distribution. This
matches the package's Python 3.11 floor without rebuilding equivalent wheels
for every CPython minor. Use `PyO3/maturin-action@v1`; for Linux, require a
manylinux policy rather than emitting a host-specific `linux` wheel. The
proposal is based on maturin 1.14.1's local `maturin generate-ci github`
output and the official
[maturin-action guidance](https://github.com/PyO3/maturin-action/blob/main/README.md).

The first matrix deliberately excludes 32-bit targets, musllinux, Windows
ARM64, Linux architectures beyond aarch64, and free-threaded Python. Those may
be added from demonstrated demand; including them now would more than double
build jobs without repository evidence of users who need them. The five targets
and these exclusions are approved for RM-2b.

### M4 — `saberkit-py` test posture decided

- Exit gate: **Done.** Native Rust tests adopted and landed for the
  null-handling, dtype-cast, and multi-chunk paths in `arrow_bridge`
  (plus `operand.rs` length/scalar logic), runnable via
  `cargo test -p saberkit-py --no-default-features`; wired into CI's `rust`
  job.

### M5 — `LeagueContext`/`c_fip` duplication resolved

- Exit gate: **Done.** `LeagueTotals` is exposed from `saberkit-py`,
  `LeagueContext.from_totals` delegates derivation to it, and
  `tests/test_plus.py` checks the Python result against the Rust object.

### M6 — First release published

- Exit gate: RM-1's release policy is recorded; RM-2b is complete; RM-3b is
  either complete or explicitly deferred from the first release; all configured
  CI jobs are green on the release commit; and the tag and configured package
  index artifact exist.

## Dependency graph, critical path, and concurrency waves

Wheel CI is the first-release critical path; season constants remain an
independent product branch:

```text
RM-1 (release policy, complete) ──────────────┐
RM-2 (matrix approval) ──> RM-2b (wheel CI) ──┴─> RM-1b (first release)

RM-3 (source standard) ──> RM-3b (constants)     (independent product branch)
```

The release policy excludes season constants from the first release's critical
path, so RM-3/RM-3b remain the next product milestone and may still land first.
RM-2b stays release-critical because publishing a source-only package would not
close README's wheel backlog item.

- **Wave A — decision preparation:** RM-1 and RM-2 are complete. RM-3 can
  proceed independently; record its decision before RM-3b begins.
- **Decision gate A:** wheel-matrix approval is complete. The constants branch
  separately requires approval of its source/license and validation rule.
- **Wave B — implementation, parallel after each predecessor:** RM-2b owns
  wheel/release workflow files; RM-3b owns the constants data/module plus
  the cross-crate `for_season` path. Keep one writer per branch and integrate
  only after each branch passes its own validation.
- **Integration gate B:** run the Rust, Python, and minimal-install lanes
  against the combined tree. Update README capability claims in the same
  integration change.
- **Wave C — serial release:** RM-1b runs only after the release-scoped Wave
  B branches and integration gate are complete.

## Work items

| ID | Status | Deps | Suggested role | File/component ownership | Deliverable | Validation | Exit criterion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RM-1 | Complete | none | Maintainer (TBD who) | `ROADMAP.md`, `CHANGELOG.md` | Recorded versioning, changelog, tag, and release-approval policy | Read-back review | Policy text exists and replaces the release-policy TBD |
| RM-2 | Complete | none | CI/release agent | `ROADMAP.md` (decision only) | Approved five-target wheel matrix with compatibility and cost rationale | Maintainer sign-off | Exact matrix and explicit exclusions are approved; wheel-platform target is no longer provisional |
| RM-2b | In progress | RM-2 | CI/release agent | `.github/workflows/ci.yml` | Working multi-platform wheel and sdist build jobs | `gh` workflow run, plus local native `maturin build` | CI produces a wheel per agreed-matrix entry and an sdist on a test run |
| RM-3 | Ready | none | Stats/data reviewer | `ROADMAP.md` (decision only) | Source-acceptance standard covering citation, license, schema, historical coverage, and validation tolerance | Maintainer sign-off plus source/license review | Source and validation rule are recorded; no constants are copied before this gate |
| RM-3b | Blocked by RM-3 | RM-3 | Cross-crate Rust/Python agent | constants module/data, `league.rs`, binding surface, Python facade, tests, README | `LeagueContext.for_season(year)` backed by the approved cited dataset | Core tests, binding tests, pytest, source-integrity check, clippy, minimal-install test | Supported seasons are documented; known-season reference test passes at the approved tolerance; README item #1 is closed |
| RM-1b | Blocked by RM-2b and external ownership | RM-1, RM-2b, and every other milestone included by policy | Maintainer (TBD who) | version metadata, release workflow, tag | First tagged package-index release | All CI jobs green on release commit; tag and package artifact exist; minimal wheel smoke test passes | Release policy is exercised end-to-end once |
| RM-4 | Complete | complete | Rust agent | binding test harness and CI Rust job | **Done.** Native binding tests and CI execution | `cargo test -p saberkit-py --no-default-features`: 12 passed, 0 failed | Preserve the suite and zero failures |
| RM-5 | Complete | complete | Rust/Python binding agent | `league_py.rs`, binding registration, Python facade, regression test | **Done.** Rust is the single source for league-total derivation | `pytest -q tests/test_plus.py` | Cross-language regression remains passing |
| RM-6 | Complete | complete | Rust agent | `arrow_bridge.rs` | **Done.** Guarded downcast invariants documented | Clippy plus native binding tests | No undocumented user-controlled panic path |
| RM-7 | Complete | complete | Python agent | `tests/test_data.py`, pytest configuration | **Done.** Offline fallback test added and dead marker removed | `pytest -q tests/test_data.py` | Test passes without network access |
| RM-8 | Complete | complete | Python agent | `tests/test_plus.py` | **Done.** Published-reference tolerances tightened to ±2.0 | `pytest -q tests/test_plus.py` | Tests and README claim remain aligned |

## Requirement-to-work traceability

| Requirement or finding | Disposition | Evidence / work |
| --- | --- | --- |
| Zero required runtime Python dependencies | Standing release gate | Empty `[project].dependencies`; CI `minimal` job; validate again in RM-2b and RM-1b |
| No bundled season constants | Active backlog | RM-3 decides provenance; RM-3b implements and closes README item #1 |
| No published cross-platform wheels | Active backlog | RM-2 decides the matrix; RM-2b builds it; RM-1b publishes and closes README item #2 |
| Park-factor calculation absent | Accepted permanent non-goal | Callers continue supplying 100-scale factors |
| Binding tests, duplicated `c_fip`, Arrow invariant docs, data fallback test, tolerance mismatch | Closed findings | RM-4 through RM-8; preserve through regression gates |

## Integration checkpoints

- Decision-only changes in Wave A require documentation review and
  `git diff --check`; they do not justify claiming source validation.
- Each Wave B branch runs its component checks before integration. RM-2b
  must demonstrate every agreed wheel target in CI. RM-3b must run
  `cargo fmt --all --check`, both Rust test suites, clippy, pytest, and the
  minimal-install computation because it crosses core, binding, and Python
  boundaries.
- After combining Wave B branches, re-run all three CI lanes on the merged
  tree. Two independently passing branches are not release evidence until
  the integration result is green.
- Before `RM-1b` (first release), all three CI jobs (`rust`, `python`,
  `minimal`) must be green on the branch that will be tagged — this is the
  existing enforcement mechanism for both correctness and the
  zero-dependency guarantee, not a new gate.
- After `RM-3b` lands, re-verify README's "Accuracy" section claims
  (statistics computed only from inputs reproduce published figures
  exactly; park-factor-dependent stats agree within a point or two) still
  hold for the newly-enabled `for_season` path specifically, since a wrong
  season constant would silently violate that claim for every stat that
  consumes it.

## Risks

| Risk | Trigger | Mitigation |
| --- | --- | --- |
| pyo3/pyo3-arrow/arrow-rs version drift | Any dependency bump touching one of `pyo3`, `pyo3-arrow`, `arrow-array`/`arrow-buffer`/`arrow-cast`/`arrow-schema` in isolation | Documented already in root `Cargo.toml`'s comment and enforced by CI's duplicate-arrow-crate guard (`cargo tree --workspace --duplicates`); keep that guard in every future CI change, never remove it to "fix" a build |
| Fabricated season constants ship despite the design principle against it | `RM-3b` implemented without `RM-3`'s sourcing standard being resolved first | Do not start `RM-3b` before `RM-3` is signed off; the exit gate for M2 explicitly requires a cited source and a reference-comparison test |
| Zero-dependency guarantee silently broken | A new transitive dependency (e.g. a future pyo3-arrow bump) starts pulling in numpy/pyarrow at runtime | CI's `minimal` job is the existing detector — keep it in the required-checks set for any PR, especially dependency bumps; do not weaken it to unblock a merge |
| Binding-layer regressions escape one test boundary | A binding change is exercised only by native Rust tests or only by pytest | Preserve RM-4's native suite and run it together with pytest for changes to `arrow_bridge.rs`, `operand.rs`, or exposed pyclasses |
| Wheel matrix scope creep or under-scope | `RM-2` proceeds without sign-off, agent guesses a platform list | `RM-2` is explicitly a proposal-first item; do not merge `RM-2b`'s CI changes until the matrix is confirmed |
| Stale roadmap state | Work items above are completed but this file is not updated | Whoever executes an `RM-*` item updates its row and current-state section in the same change, not as a follow-up |
| Python league-total formulas are reintroduced | `LeagueContext.from_totals` starts deriving rates or `c_fip` instead of delegating to `_core.LeagueTotals` | Preserve RM-5's single Rust path and its cross-language regression test |
| Release cannot publish despite green builds | PyPI project ownership or trusted-publisher credentials remain unresolved when RM-1b starts | Resolve the named package index, owner, and credential mechanism in RM-1 before scheduling RM-1b |
