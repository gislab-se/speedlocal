# Deployment Notes

## Static Page

Target path:

`https://gislab-se.github.io/speedlocal/landskapspotential/`

The Pages workflow publishes the `site/` directory.

The repo is public as of 2026-06-26, so GitHub Pages can publish from this repo.
The `Publish GitHub Pages` workflow runs on pushes to `main` that touch the
static site or the workflow, and it can also be run manually.

GitHub Pages is static hosting only. If this repo is made private again before
Flowcore migration, Pages may stop publishing unless the GitHub plan supports
private Pages.

## Interactive apps

V2 Final development deployment:

`https://speedlocal-landskapspotential.streamlit.app/`

Active region deep link:

- `https://speedlocal-landskapspotential.streamlit.app/?region=trondelag`

Bornholm remains visible with its V1 visual reference:

`https://landskapsanalys-potential-v1.streamlit.app/`

Bornholm is under onboarding and Skaraborg remains planned. Neither may have an
active V2 Final button or deep link until its own manifest, runtime data,
accepted behavior reference, and readiness checks pass.

Frozen V2 reference deployment:

`https://landskapsanalys-potential-v2-test.streamlit.app/`

This deployment is the authoritative behavioral and numerical reference for
Trøndelag only. Its Bornholm files remain protected for archive integrity and
diagnostics, not as evidence of working Bornholm V2 parity.

The verified frozen source is:

- repository: `gislab-se/landskapsanalys`;
- source branch at freeze: `potential-v2-multiregion`;
- immutable branch: `frozen-v2-reference-2026-07-30`;
- immutable tag: `v2-frozen-reference-2026-07-30`;
- commit: `75ba14871100c208cbf8eedb794d56c165340811`;
- entrypoint: `streamlit_app.py`;
- Streamlit app id: `63561ff3-f8c2-4c09-a9e7-ea110c51dc4a`.

The branch and tag exist at the verified commit. Both the dedicated frozen
branch and the deployment's current `potential-v2-multiregion` branch are
GitHub-protected and locked with administrator enforcement, force pushes and
deletion disabled. The current Streamlit deployment is therefore fixed at the
verified commit. It may later be repointed to the dedicated frozen branch for
clarity, but that is not a freeze blocker. See `FROZEN_V2_REFERENCE.md` for the
machine-verifiable freeze contract.

The frozen tag is separately protected by active GitHub ruleset `20038506`
against updates and deletion. The Streamlit app itself is private and requires
authentication even though its source metadata can be read publicly.

The active `main` branch in this repository is V2 Final and continues from the
same working monolith, which is reduced and generalized slice by slice.

The current product and migration sequence is defined in
`GENERAL_PROGRAM_PLAN.md`. PostGIS is deferred until the file-backed V2 Final
behavior is stable for the five standard public groups.

Run locally:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\path\to\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\scripts\start_app.ps1"
```

The start script stops with an error if port `8502` already has an active
listener, preventing multiple V2 Final workers from retaining different code
versions on the same localhost port.

The technical runtime status view remains available through `status_app.py`.

## Streamlit Cloud deployment contract

GitHub Actions in this repository publishes only the static Pages site. No
tracked workflow publishes the interactive Streamlit app.

The external app has served the current root entrypoint from:

- repository: `gislab-se/speedlocal`;
- branch: `main`;
- entrypoint: `app.py`;
- URL:
  `https://speedlocal-landskapspotential.streamlit.app/?region=trondelag`.

The previous cloud error proved that this source connection and auto-deploy
path were active, but also proved that a Windows archive path was not a cloud
provider. V2 Final now resolves that gap before importing the monolith.

The cloud runtime contract is:

- tracked manifest:
  `data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-07-30.1.json`;
- release tag: `v2-final-runtime-trondelag-r7-2026-07-30.1`;
- archive:
  `speedlocal-v2-final-runtime-trondelag-r7-2026-07-30.1.zip`;
- archive bytes: `15,730,706`;
- expanded bytes: `101,938,537` across exactly 45 files;
- archive SHA-256:
  `43e6ccc8cae99c7a7e15f85d92a8e3e9c15a077abfb9b28bd4c12a92fc63202c`;
- content-inventory SHA-256:
  `f05045ac0a91fd0f83629d7507157ed62c504f1a95034339200c4e784d4212c2`.

With `SPEEDLOCAL_V2_SOURCE_ROOT` unset, `app.py` downloads that public Release
asset over HTTPS, verifies its exact byte count and outer checksum, safely
extracts only the declared files, verifies every inner checksum, caches the
verified root under the operating-system temporary directory, and only then
sets the existing provider environment variable. Invalid explicit local roots,
unsafe ZIP members, inventory drift, and checksum failures stop before the V2
monolith is imported. No Streamlit secret is needed for this public package.

`SPEEDLOCAL_V2_SOURCE_ROOT` remains the explicit local/full-archive override.
It must never be configured to a Windows path in Streamlit Cloud. The cloud
package is Trøndelag-only runtime transport and deliberately omits Bornholm
diagnostic assets. Full-archive and Bornholm validators continue to use the
read-only local archive.

The current local archive can replay two checksum-declared Bornholm polygon
fixtures for diagnostics. These are not part of the active deployment gate.
Before Bornholm activation, its V1 reference must be technically pinned and a
cloud provider must satisfy the separately accepted regional runtime contract.

## End-of-session publication

1. Run focused slice tests and the full required regression set.
2. Visually inspect V2 Final on localhost.
3. Update the daily log and slice report.
4. Commit one coherent, validated work checkpoint.
5. Push `main` to `origin`.
6. Confirm that exact checkpoint exists on GitHub.
7. If runtime transport changed, confirm the exact Release tag, all three
   assets, archive checksum, and a clean cold download.
8. Confirm the external V2 Final deployment serves that checkpoint and complete
   its Trøndelag smoke check against frozen V2.
9. If `site/**` changed, confirm the GitHub Pages workflow and landing page.
10. Record the checkpoint hash, URLs, runtime release, and results in the daily
    log.
11. Commit and push that publication record, then confirm a clean worktree.

GitHub Pages deploys automatically only for pushes to `main` that modify
`site/**` or its workflow. The interactive Streamlit deployment is a separate
service and must be checked independently after every push.

Do not report a work session as published merely because `git push` succeeded.
If the external Streamlit settings or runtime provider are unavailable, mark
the publication blocked rather than claiming success.

## Runtime Data

Preferred order:

1. Validated Postgres runtime tables.
2. Documented file fallback paths.
3. Planned/disabled region state.

The current active file fallback is the reviewed, checksum-pinned Trøndelag
Release package above. It is not described as an exact export of frozen commit
`75ba148`: nine reviewed runtime inputs differ, and the raw frozen subset failed
the accepted 6.7%/6.2% V2 Final checkpoints. Those deviations are explicit in
the tracked package manifest.

Do not remove file fallbacks until the database-backed path has matching
validation.
