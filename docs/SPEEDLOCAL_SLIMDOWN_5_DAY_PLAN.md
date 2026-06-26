# Speedlocal Bare-Minimum Delivery Repo: 5-Day Migration Plan

## Summary

Create a slim delivery repo in `gislab-se/speedlocal` using the current V2
landskapsanalys repo only as a source archive. The delivery repo should host the
static landing page at:

`https://gislab-se.github.io/speedlocal/landskapspotential/`

The repo should run the three regional cards/surfaces for Bornholm, Trondelag
and Skaraborg, and should prefer Docker/Postgres runtime data with file-path
fallbacks until database coverage is complete.

Checked facts:

- `gislab-se/speedlocal` exists, uses default branch `main`, and is private.
- GitHub Pages can publish from private repos only on GitHub Pro, Team, or
  Enterprise plans. If that is not available, keep this repo private during
  development and temporarily make it public only when publication is needed.
- GitHub Pages is static hosting only. It does not run Python or Streamlit apps.
- GitHub Pages sites are public even when sourced from a private repo.

References:

- GitHub Pages overview:
  `https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages`
- GitHub Pages site creation and limitations:
  `https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site`
- Streamlit deployment:
  `https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app`

## Migration Instruction

Plan and implement a 5-day bare-minimum migration/slimdown for the
`gislab-se/speedlocal` delivery repo.

Context:

- `gislab-se/speedlocal` is a private repo and is part of the actual delivery.
- Existing contents in this repo do not need to be preserved and may be deleted,
  replaced, or heavily restructured as needed.
- The current V2 repo remains a reference/source archive.
- When something breaks in the slim repo, look back into V2 and copy only the
  smallest required code, manifest, data file, or asset.

Hosting:

- Keep the old GitHub Pages landing page working until the new repo is ready:
  `https://gislab-se.github.io/landskapsanalys/speedlocal-landskapspotential.html`
- When `gislab-se/speedlocal` is ready, move the canonical landing page to:
  `https://gislab-se.github.io/speedlocal/landskapspotential/`
- If GitHub Pages cannot publish from the private repo under the current GitHub
  plan, keep this repo private during development and make it public temporarily
  only when publication is needed, until the project migrates to Flowcore.
- Treat GitHub Pages as static hosting only. Do not attempt to run Python or
  Streamlit apps from Pages.
- Interactive apps should run through Flowcore, Docker/server runtime, or
  another Streamlit-compatible backend.

Runtime data:

- Prefer Docker/Postgres using the `speedlocal` database/runtime schema.
- Keep file paths to required data as fallbacks until equivalent Docker/Postgres
  runtime tables exist and pass validation.
- Do not remove file fallback paths prematurely.
- Import only app-ready runtime data.
- Do not import generated review clutter, QGIS QA packages, old reports, or
  exploratory outputs unless they are required.

Regional design:

- The three regional cards/surfaces are Bornholm, Trondelag and Skaraborg.
- Skaraborg is part of the forward design, even if initially planned/disabled.
- The long-term rule is catalog-driven onboarding: adding Skaraborg, Skane, or
  another region should require a correct region catalog/manifest plus required
  runtime data, not hardcoded app changes.
- Test this assumption explicitly. A new region is not just a name in the
  catalog. It must also provide the required data contracts, validation status,
  CRS, display geometry, landscape/potential/scenario/acceptance manifests, and
  runtime tables or file fallbacks.

## 5-Day Plan

### Day 1 - Repo Reset And Runtime Inventory

- Inspect current `gislab-se/speedlocal` contents and confirm no preservation
  requirement.
- Define clean repo layout:
  `/apps`, `/regions`, `/db`, `/data/runtime`, `/site`, `/scripts`, `/docs`.
- Inventory minimum V2 runtime contract:
  app entrypoints, shared app modules, region manifests, parameter catalogs,
  required static assets, required data paths, validation scripts.
- Produce a copy list and leave-behind list before moving files.
- Do not copy exploratory docs, rendered report folders, QGIS review packages,
  or large generated artifacts.

### Day 2 - Static Landing Page

- Move/copy only the landing page assets needed for
  `site/landskapspotential/index.html`.
- Configure GitHub Pages for:
  `https://gislab-se.github.io/speedlocal/landskapspotential/`
- If private Pages is unavailable, document the public-temporary fallback and
  keep the repo private until publish time.
- Landing page should show three cards: Bornholm, Trondelag, Skaraborg.
- Cards should link to the appropriate app routes or deployment placeholders.

### Day 3 - App Shell And Catalog-Driven Regions

- Copy the minimal Streamlit/app shell and shared modules.
- Copy only active region packages/catalogs for Bornholm and Trondelag, plus
  Skaraborg as planned/disabled.
- Remove or disable legacy region fallback behavior that can expose old regions
  such as Vara unintentionally.
- Make region discovery come from `regions/index.json` and region package
  manifests only.
- Add a minimal new-region readiness validator proving what Skane would need:
  catalog sections, CRS, display geometries, manifests, runtime tables and file
  fallbacks.

### Day 4 - Docker/Postgres Runtime With File Fallbacks

- Add Docker/Postgres schema and import scripts for `speedlocal`.
- Import only reviewed/app-ready runtime data first.
- Keep manifest file paths as fallbacks until database-backed reads match
  file-backed reads.
- Clearly mark placeholder and synthetic data.
- Do not migrate QGIS review outputs, prototype caches, large rendered reports,
  or inactive V3 material into runtime tables.
- Add backend selection behavior:
  default to Postgres when available and validated, fall back to file paths
  otherwise.

### Day 5 - Validation, Polish And Handoff

- Run landing-page smoke test.
- Run app-card smoke tests for Bornholm, Trondelag, and Skaraborg planned state.
- Validate Bornholm independently, including R10-derived R9 PEY labelling.
- Validate Trondelag independently, including EPSG:25832, R7/R6/R5 only, no
  R8/R9 exposure, and 250 m population-grid proxy labelling.
- Validate database-backed and file-backed outputs match where both exist.
- Document local run command, Docker/Postgres startup, GitHub Pages publishing,
  private/public repo fallback, Flowcore assumptions, adding a new region from
  catalog plus runtime data, and known gaps before production migration.

## Acceptance Criteria

- `gislab-se/speedlocal` contains only delivery/runtime-relevant files.
- Landing page works from `/speedlocal/landskapspotential/` when Pages is
  enabled.
- Three regional cards exist.
- Bornholm and Trondelag app behavior validates independently.
- Skaraborg is represented as planned/disabled unless required runtime data is
  complete.
- Postgres path is preferred where validated.
- File fallback remains available and documented.
- No destructive changes are made to the V2 repo.

## Implementation Notes

- Target repo: `gislab-se/speedlocal`.
- Suggested local checkout: `C:\tmp\speedlocal`.
- Before modifying implementation files, confirm branch, status, and the
  intended change scope.
- Do not edit the V2 repo except as a read-only reference during migration.
