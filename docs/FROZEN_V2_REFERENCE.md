# Frozen V2 reference

The immutable V2 snapshot is:

- repository: `gislab-se/landskapsanalys`;
- frozen branch: `frozen-v2-reference-2026-07-30`;
- frozen tag: `v2-frozen-reference-2026-07-30`;
- commit: `75ba14871100c208cbf8eedb794d56c165340811`;
- entrypoint: `streamlit_app.py`;
- launcher target: `potential_app.py`;
- deployment:
  `https://landskapsanalys-potential-v2-test.streamlit.app/`;
- Streamlit app id: `63561ff3-f8c2-4c09-a9e7-ea110c51dc4a`.

## Acceptance scope

Snapshot integrity and behavioral authority are different contracts.

- Trøndelag is the only region for which this deployment is the authoritative
  visual and numerical V2 parity reference.
- Bornholm files remain in the checksum contract because their provenance and
  integrity matter. They were imported from V1 and are diagnostic onboarding
  material, not proof of working Bornholm V2 behavior.
- Bornholm's intended public reference is V1. It remains a visual reference
  until its repository, commit, entrypoint, deployment, and protected ref are
  recovered and recorded.
- Skaraborg has no historical V2 behavior reference.

The deliberate Trøndelag-only decision is recorded by commit
`9095d996797a3173e7bbc5315a0beae5f712011e` (`Make v2 Trondelag only`).
The older tag `stable-v2-trondelag-2026-05-19-zoom` is a useful
Trøndelag-only history checkpoint. It is secondary context only. The immutable
snapshot at `75ba148` is the current full-flow Trøndelag V2 parity authority.

The branch and tag were both created at the exact verified commit on
2026-07-30. GitHub branch protection was then enabled with administrator
enforcement, force pushes and deletion disabled, and `lock_branch` enabled on
both `frozen-v2-reference-2026-07-30` and the deployment's existing
`potential-v2-multiregion` branch. Both branches resolve to the recorded commit.
They must never be unlocked, moved, or deleted.

GitHub ruleset `20038506`, `Protect frozen V2 reference tag`, is active for
`refs/tags/v2-frozen-reference-2026-07-30` and blocks tag updates and deletion.

The publicly readable Streamlit metadata confirmed that the reference deployment used
`gislab-se/landskapsanalys`, branch `potential-v2-multiregion`, entrypoint
`streamlit_app.py`, and Python 3.11 at the time of verification. The app may
later be repointed to `frozen-v2-reference-2026-07-30` to make its
purpose clearer, but this is no longer required for immutability: its current
source branch is locked at the same commit. Any later service-interface change
must preserve that exact commit and be recorded here.

The application itself is private and requires Streamlit authentication. Its
metadata being publicly readable does not mean colleagues can open the app
without access.

## Runtime archive

`SPEEDLOCAL_V2_SOURCE_ROOT` points to the read-only runtime archive. On this
computer it is currently:

`C:\gislab\data\landskapsanalys-v2-multiregion`

All 2,443 files in the folder were marked read-only on 2026-07-30. That folder
is not a functioning Git checkout. Its `.git` file points to a
worktree location that no longer exists. It also contains two known local
additions compared with the frozen commit: the environment/machine block in
`.gitignore`, plus `runtime_mode` and `rollup_note` in
`regions/bornholm/region.json`. Treat it as a data/runtime archive, never as
Git provenance and never as the editable V2 Final codebase.

The machine-readable identity and archive checksums are stored in
`frozen_v2_reference.json`. They cover ten core code/manifest files plus an
aggregate checksum for all 120 GeoJSON, distance-table, and RDS assets declared
by the two acceptance asset manifests. Validate them with:

```powershell
$env:SPEEDLOCAL_V2_SOURCE_ROOT = "C:\gislab\data\landskapsanalys-v2-multiregion"
& ".\.venv\Scripts\python.exe" -B scripts\validate_frozen_v2_reference.py
```

Add `--remote` during publication to verify that the deployment branch, frozen
branch, and tag still resolve to the recorded commit.
