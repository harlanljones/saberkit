# Releasing saberkit

Releases are built from tags and published to PyPI through OpenID Connect. No
long-lived PyPI token belongs in GitHub secrets.

## One-time setup

1. Create or claim the `saberkit` project on PyPI.
2. In the PyPI project, add a trusted publisher for repository
   `harlanljones/saberkit`, workflow `release.yml`, environment `pypi`.
3. Create the protected GitHub environment `pypi` and require the desired
   maintainer approval. The workflow's publish job targets this environment.

These are external administrative actions and cannot be completed by repository
changes alone.

## Release checklist

1. Set `workspace.package.version` in `Cargo.toml`. Both Rust crates and the
   Python package inherit this single version.
2. Move `CHANGELOG.md` entries from `[Unreleased]` under a dated version
   heading, then add a fresh empty `[Unreleased]` section.
3. If adding a completed season, regenerate the constants from the recorded
   Retrosheet/Chadwick source, review the source digests, and retain `NOTICE`.
4. Run:

   ```bash
   cargo fmt --all --check
   cargo clippy --workspace --all-targets -- -D warnings
   cargo test -p saberkit-core
   cargo test -p saberkit-py --no-default-features
   pytest -q
   maturin build --release --locked --out dist
   maturin sdist --out dist
   ```

5. Confirm the base wheel installs with `--no-deps`, neither numpy nor pyarrow
   is present, and a Polars Arrow round trip succeeds.
6. Merge the release commit and wait for every CI job, including all five wheel
   targets and the sdist, to pass on that exact commit.
7. Create and push `vMAJOR.MINOR.PATCH`. The workflow rejects a tag that does
   not exactly match `workspace.package.version`.
8. Approve the protected `pypi` environment. Verify the five abi3 wheels and
   source distribution on PyPI, then smoke-test installation from PyPI in a new
   environment.

Never move or overwrite a release tag. If publication fails after artifacts are
uploaded, fix the cause and release a new patch version.
