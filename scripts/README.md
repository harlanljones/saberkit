# Season-constants generator

`generate_season_constants.py` is a development-only, standard-library Python
program. It invokes Chadwick's `cwevent` parser against a checkout of the
Chadwick Bureau Retrosheet mirror, derives one completed MLB season at a time,
and writes `crates/saberkit-core/src/season_constants_generated.rs`.

The derivation uses regular-season `.EVA`/`.EVN` files only. RE24 observations
come only from half-innings completed with three outs so walk-off fragments do
not bias run expectancy. Linear weights are measured for unintentional walks,
HBP, singles, doubles, triples, and home runs relative to batting outs. A single
scale factor makes league wOBA equal league OBP. League ERA, slugging, runs per
PA, and the FIP constant come from summed event totals. The population is all
MLB batters, including pitcher batting where applicable.

Example, after building `cwevent` and checking out the recorded Retrosheet
revision:

```bash
python scripts/generate_season_constants.py \
  --retrosheet-dir /path/to/chadwick-retrosheet \
  --cwevent /path/to/cwevent \
  --revision REVISION_SHA \
  --first-season 2010 \
  --last-season 2025 \
  --output crates/saberkit-core/src/season_constants_generated.rs
```

Review the diff, confirm every changed season's source digest, and run all
release gates. Raw Retrosheet files are inputs and must not be added to this
repository or wheel. The required data attribution is in the root `NOTICE`.
