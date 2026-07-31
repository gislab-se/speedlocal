# Daily V2 Final workflow

Every workday has one dated file under `docs/daily/`.

## Branch and status model

- `v2-final-dev` is the daily development and integration branch.
- `main` is the published branch used by the external V2 Final deployment.
- A **development checkpoint** is one coherent validated commit on
  `v2-final-dev`.
- **Locally promoted** means that the applicable automated gates and localhost
  visual review pass and the replaced path inside that promotion boundary has
  been removed. Work may continue from a locally promoted increment without
  waiting for external publication.
- **Published** means that the exact reviewed checkpoint is present on
  `main`, the external deployment has been verified, and the evidence is
  recorded. A push to `v2-final-dev` is never a publication.

## Start of day

1. Read `GENERAL_PROGRAM_PLAN.md`, `DELIVERY_PLAN.md`, and the latest daily log.
2. Confirm Git branch and worktree state.
3. Select one testable outcome from the active slice.
4. Create or update `daily/YYYY-MM-DD.md`.
5. Record:
   - today's outcome;
   - in-scope behavior;
   - files/data expected to be touched;
   - acceptance checks;
   - known risks.

The daily plan should normally contain three to five tasks. It is a subplan of
the delivery plan, not a replacement for it.

## During work

- Characterize the region's accepted reference before modifying the
  corresponding V2 Final path: frozen V2 for Trøndelag, and the independently
  pinned V1/reference contract for Bornholm.
- Record important discoveries and decisions in the daily file.
- Keep V2 Final functional throughout the slice and leave frozen V2 untouched.
- Run focused validation after each meaningful step.
- If runtime transport changes, run the synthetic bundle security validator,
  rebuild the real untracked package, and validate that exact ZIP through the
  root Streamlit entrypoint.
- Fully restart the local Streamlit server after changing an imported
  function signature or module boundary. Stop the complete previous process
  tree, confirm that the app port has no listener, and then start one instance
  through `scripts/start_app.ps1`. Hot reload is not a sufficient visual gate
  for that class of change.
- Do not expand into another slice because related code happens to be nearby.

## End of day

Update the same daily file with:

- completed work;
- files or behavior changed;
- validation results;
- code classified as keep, extract, configure, rewrite, or remove;
- blockers and unresolved questions;
- exact next starting point;
- development-checkpoint commit hash and push result;
- local-promotion status and evidence;
- publication status, when a publication window was used.

Then update `DELIVERY_PLAN.md` only if milestone status, order, assumptions, or
dates changed.

Create and push one coherent validated checkpoint on `v2-final-dev` at the end
of the workday. A partially completed slice may be a valid development
checkpoint, but it must not be labelled locally promoted.

## Publication windows

Friday is the normal publication window. Tuesday is an optional publication
window when a coherent locally promoted increment is ready. External
publication does not happen on other days unless an emergency reason is
recorded in the current daily log.

During a publication window:

1. select and record the exact locally promoted `v2-final-dev` checkpoint;
2. rerun the applicable validation against that exact checkpoint;
3. update `main` to that checkpoint and push `main` to `origin`;
4. verify that exact published checkpoint on GitHub;
5. if the runtime package changed, verify the immutable Release assets and
   their tracked SHA-256 before testing Streamlit Cloud;
6. verify the externally deployed V2 Final app and compare the affected
   behavior with the active region's accepted reference;
7. if `site/**` changed, verify the GitHub Pages workflow and public page;
8. record the published checkpoint hash, URLs, runtime release, deployment
   result, accepted-reference comparison, and publication window in the daily
   log;
9. create and push one small publication-record commit on `main`;
10. confirm the publication-record commit on GitHub, confirm the external app
    remains available if that documentation commit triggers a rebuild, and
    bring the publication record back into `v2-final-dev` before further
    development.

Do not report a checkpoint as published merely because a Git push succeeded.
If external verification is blocked, record it as locally promoted but not
published.

## Daily file template

```markdown
# Daily plan — YYYY-MM-DD

## Outcome

One testable result for the day.

## Starting state

- Branch and commit:
- Active slice:
- Previous handoff:

## Tasks

- [ ] Task 1
- [ ] Task 2
- [ ] Task 3

## Acceptance checks

- Check 1
- Check 2

## Decisions and discoveries

- None yet.

## Code classification

- Keep:
- Extract:
- Configure:
- Rewrite:
- Remove:

## Completed

- Nothing yet.

## Validation

- Not run yet.

## Blockers

- None.

## Next starting point

Exact file, function, or test to open next.

## Work checkpoint

- Branch: `v2-final-dev`.
- Commit: not created.
- Push:
- GitHub development checkpoint:

## Local promotion

- Status: not promoted.
- Scope:
- Automated evidence:
- Localhost visual evidence:

## Publication

- Window: not used.
- Emergency reason, if outside Tuesday or Friday:
- Published commit on `main`:
- GitHub published checkpoint:
- V2 Final deployment:
- Runtime release, if applicable:
- Accepted-reference comparison:
- GitHub Pages, if applicable:
- Publication-record commit:
- Final worktree:
```
