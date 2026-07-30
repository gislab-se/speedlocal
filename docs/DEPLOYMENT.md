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

The following external Streamlit Cloud settings are required and must be
verified in the Streamlit Cloud owner interface:

- repository: `gislab-se/speedlocal`;
- branch: `main`;
- entrypoint: `app.py`;
- auto-deploy behavior and the deployed Git commit;
- Python runtime and system dependencies;
- secrets and environment variables;
- a cloud-accessible runtime-data provider.

Only the entrypoint and Python dependencies are visible in this repository.
The source connection, deployed commit, secrets, and runtime provider are not
yet verified.

`SPEEDLOCAL_V2_SOURCE_ROOT` is a localhost-only fallback when it points to a
Windows `C:\...` archive. That path cannot supply a cloud deployment. Until a
cloud-accessible archive or validated database is configured, a successful
GitHub push does not guarantee that external maps and data work.

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
7. Confirm the external V2 Final deployment serves that checkpoint and complete
   its Trøndelag smoke check against frozen V2.
8. If `site/**` changed, confirm the GitHub Pages workflow and landing page.
9. Record the checkpoint hash, URLs, and results in the daily log.
10. Commit and push that publication record, then confirm a clean worktree.

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

Do not remove file fallbacks until the database-backed path has matching
validation.
