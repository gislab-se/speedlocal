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

V2 Final published deployment:

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

`main` is the published branch connected to the external V2 Final deployment.
`v2-final-dev` is the daily development and integration branch. Pushing a
validated development checkpoint to `v2-final-dev` does not publish it.

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

The currently published `main` cloud runtime contract is:

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

The locally promoted but unpublished `v2-final-dev` direct-R7 population
checkpoint instead pins
`data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-08-04.1.json`:

- 48 files and 103,563,758 expanded bytes;
- archive name `speedlocal-v2-final-runtime-trondelag-r7-2026-08-04.1.zip`;
- 16,259,464 archive bytes;
- archive SHA-256
  `797eb8fda675718251850deac23cd7e2129ea25be835997d4d37043d7b0b3781`.

It adds three generated direct-R7 population distance tables. Two local builds
were byte-identical, the release-archive validator passed 25/25, and localhost
review was approved on 2026-08-04. The package has not been uploaded or
externally verified. The current public
45-file Release remains authoritative until a publication window.

The eligible-surface candidate additionally pins
`data/runtime/manifests/trondelag/v2-final-runtime-r7-2026-08-06.1.json`:

- 53 files and 118,149,644 expanded bytes;
- archive name `speedlocal-v2-final-runtime-trondelag-r7-2026-08-06.1.zip`;
- 19,145,804 archive bytes;
- archive SHA-256
  `5e0f83b65e74c1a58c40c72d3b7840391a48e9def7207ce1e02f908c43ae74fa`.

It preserves the 48-file direct-R7 package and adds the reviewed land/region
mask, deterministic R7/R6/R5 eligible-surface geometries, and build evidence.
Its full package gate passes 25/25. The package remains local and unpublished
until clean localhost review and a later publication window. The public
45-file Release remains authoritative.

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

## Current runtime publication

The Trøndelag runtime prerelease is published at:

`https://github.com/gislab-se/speedlocal/releases/tag/v2-final-runtime-trondelag-r7-2026-07-30.1`

It contains exactly the ZIP, canonical manifest, and two-line checksum
sidecar declared by the tracked contract. Anonymous redownload verification
passed for all three assets. The ZIP and manifest hashes are respectively:

- `43e6ccc8cae99c7a7e15f85d92a8e3e9c15a077abfb9b28bd4c12a92fc63202c`;
- `079fa695287141026ba5bf6b288986904d3bc75c388cf9c0f2e30e0854cef894`.

Transport checkpoint `d914563f49e95c65d13c79d6a66b08b4bc26392b`
contains the contract and bootstrap. Application checkpoint
`72f1783d03166434ad5e35e1a8a85b27312d5e33` adds the verified Windows
directory-promotion fix. A clean machine-style run with no local V2 source
variable downloaded the public ZIP, verified and materialized it, rendered the
real root app, and passed the 20/20 interactive gate including the
300 -> 1000 m road change.

The Streamlit Cloud app is currently access-controlled: anonymous requests to
both the app and its health endpoint redirect to Streamlit authentication.
On 2026-07-30 the user completed the authenticated visual and interaction smoke
review and confirmed that the deployed Trøndelag app works correctly. The
external publication gate is therefore complete. Colleagues must still be
granted access in Streamlit Cloud if they are expected to review the private
deployment.

## Development checkpoints and publication windows

End each workday by committing and pushing one coherent validated checkpoint
to `v2-final-dev`. Record whether it is only a development checkpoint or has
also passed the localhost gate and is locally promoted.

Friday is the normal publication window. Tuesday is an optional window when a
coherent locally promoted increment is ready. Do not update `main` or trigger
an external publication outside those windows unless the current daily log
records an emergency reason.

For a publication:

1. Select and record the exact locally promoted `v2-final-dev` checkpoint.
2. Run focused slice tests and the full required regression set against it.
3. Visually inspect V2 Final on localhost.
4. Update the daily log and slice report except for post-deployment evidence.
5. Update `main` to the selected checkpoint and push `main` to `origin`.
6. Confirm that exact published checkpoint exists on GitHub.
7. If runtime transport changed, confirm the exact Release tag, all three
   assets, archive checksum, and a clean cold download.
8. Confirm the external V2 Final deployment serves that checkpoint and complete
   its Trøndelag smoke check against frozen V2.
9. If `site/**` changed, confirm the GitHub Pages workflow and landing page.
10. Record the checkpoint hash, URLs, runtime release, and results in the daily
    log.
11. Commit and push that publication record on `main`, bring it back into
    `v2-final-dev`, and then confirm a clean worktree.

GitHub Pages deploys automatically only for pushes to `main` that modify
`site/**` or its workflow. The interactive Streamlit deployment is a separate
service and must be checked independently after every push to `main`.

A **locally promoted** increment has passed its automated and localhost gates
and may be followed by the next planned development work. A **published**
increment is additionally present on `main` and verified in the external app.
Keep both states explicit in the daily log.

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
