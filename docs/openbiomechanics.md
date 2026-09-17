# OpenBiomechanics data — license, provenance, and pin procedure

This document covers the data fetched at runtime by
[`notebooks/biomech_explorer.py`](../notebooks/biomech_explorer.py) from
[The OpenBiomechanics Project](https://openbiomechanics.org) (OBP), published
by Driveline Baseball Research and Development. The data is **not** saberkit's
and is **not** covered by saberkit's MIT/Apache-2.0 license: it is licensed
CC BY-NC-SA 4.0, with one additional professional-organization exclusion.
Read this page before running the notebook's online path.

## License summary

The upstream repository's `LICENSE-DATA.md` applies CC BY-NC-SA 4.0 to the
data and states one additional, specific exclusion. Quoted verbatim at the
current pin (commit `44b98dae05cceb016f080ab39d105c85b8639084`):

> While the license is clear that this data cannot be used for commercial
> purposes (which includes but is not limited to for-profit organizations,
> corporations, and sole proprietorships with the intent to profit now or in
> the future), there is also one additional specific exclusion where this
> data cannot be used in any form without a specific written commercial
> (paid) license:
>
> > Any employee or contractor employed by, associated with, or a significant
> > shareholder of a professional sports organization or financial analysis
> > firm is forbidden to use The OpenBiomechanics Project data for any use
> > whatsoever.

If your use is institutional, on behalf of a company, or otherwise not
clearly individual and non-commercial, obtain a commercial license or written
confirmation from Driveline first. This page describes what the license
documents say; it is not legal advice.

## Citation

The project site asks users of OBP data to cite:

> Wasserberger KW, Brady AC, Besky DM, Jones BR, Boddy KJ (2022). The
> OpenBiomechanics Project: The open source biomechanics dataset.
> https://openbiomechanics.org

Upstream's `CITATION.cff` additionally names Driveline Baseball Research and
Development and Kyle Boddy; the notebook shows both.

## Pin and digest table

The notebook fetches four CSVs from upstream at one immutable commit.
Digests were computed by saberkit at the pin on 2026-09-15; upstream
publishes no checksums for the in-git CSVs.

| Key | Upstream path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `pitching_metadata` | `baseball_pitching/data/metadata.csv` | 45653 | `ec5686fef140e728193d4ce4bb16aa116751e716963bb2aedca11111b03816e3` |
| `pitching_poi` | `baseball_pitching/data/poi/poi_metrics.csv` | 266651 | `5ba2ac8536fba1d6997ebd81d7b1956c73fbb2e141b9c6156cd76f66265f391e` |
| `hitting_metadata` | `baseball_hitting/data/metadata.csv` | 48953 | `b87567a7dbed13dd438a16512b80b80af81cf909e1203a89f545e6b31a245372` |
| `hitting_poi` | `baseball_hitting/data/poi/poi_metrics.csv` | 717888 | `95ab62e2c36e5034435f3edaec2d7d320caf9aa61eac923d907aed6751a2619b` |

Pin commit: `44b98dae05cceb016f080ab39d105c85b8639084`.

## Site terms vs. repo terms (read 2026-09-15; the site is not versioned)

`LICENSE-DATA.md` calls openbiomechanics.org/#terms "the HTML-formatted
version" of the same license, but the site states conditions the repo file
does not: "OBP is 100% free for individual use, forever. Institutional and
educational uses are also permitted with a commercial license"; the FAQ
answers that classroom use is free "through December 31st, 2030 [updated
February 2026]" and that a researcher "affiliated or contracted with a
professional sports team or other private company" may use OBP only with a
commercial license; and the site applies CC BY-NC-SA to "All data, code, and
any derived works", while the repo licenses code under MIT. saberkit does
not treat either document as superseding the other: the notebook quotes
`LICENSE-DATA.md` at the pin because it is versioned and citable, and users
must satisfy **both**. If your use is institutional, on behalf of a company,
or otherwise not clearly individual and non-commercial, obtain a commercial
license or written confirmation first. This records what the documents say;
it is not legal advice.

## Maintainer self-certification record

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

## Attribution parties and notices at the pin

`CITATION.cff` names Driveline Baseball Research and Development and Kyle
Boddy; the project site asks for Wasserberger KW, Brady AC, Besky DM, Jones
BR, Boddy KJ (2022). The notebook shows both. No copyright notice accompanies
the data at the pin — the only copyright line, in `LICENSE-CODE.md`, covers
the software — so there is no data copyright notice to retain. Re-check at
every pin bump.

## Pin-bump procedure

1. Choose a new upstream commit.
2. Re-fetch `LICENSE-DATA.md` at the new commit and compare its SHA-256 with
   the recorded digest for the current pin (`44b98dae`:
   `19b1e9bedd22c36f02cdccd67b7c4dd561e2379f96b540006ad0c6dc9c49cc50`,
   2839 bytes — recorded for this check only; the notebook never fetches
   it). If it differs, read the diff and update the notebook's
   `EXCLUSION_TEXT`, the `NOTICE` gate sentence, and this document.
3. Recompute the four CSV digests and update `OBP_FILES` in the notebook
   (the short SHA in `SOURCE_LABEL` and `ATTRIBUTION_MD` is `OBP_COMMIT[:8]`,
   so it follows the pin without a separate edit).
4. Re-verify required columns against the new data dictionaries; update the
   test's upstream column literals if they changed.
5. Re-check the attribution parties (see above).
6. Re-sign the self-certification record: re-make it, date it, and replace
   the record above.
7. Update this document.
