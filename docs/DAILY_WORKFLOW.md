# Daily V2 Final workflow

Every workday has one dated file under `docs/daily/`.

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
- commit hash, if committed.

Then update `DELIVERY_PLAN.md` only if milestone status, order, assumptions, or
dates changed.

## Publish the work session

After local validation and visual localhost approval:

1. complete the daily log except for post-push results;
2. create one coherent work-checkpoint commit and push `main` to `origin`;
3. verify that exact work-checkpoint commit on GitHub;
4. verify the externally deployed V2 Final app and compare the affected
   behavior with the active region's accepted reference;
5. if `site/**` changed, verify the GitHub Pages workflow and public page;
6. record the work-checkpoint hash, URLs, deployment result, and comparison
   result in the daily log;
7. create and push one small publication-record commit;
8. confirm the publication-record commit on GitHub and a clean local worktree.

Pushing is not the same as publishing. A session is published only after the
external app has been checked and the result has been recorded. The second
commit contains documentation only; if it triggers a new Streamlit build,
confirm that the app remains available.

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

- Commit: not created.

## Publication

- Push:
- GitHub checkpoint:
- V2 Final deployment:
- Accepted-reference comparison:
- GitHub Pages, if applicable:
- Publication-record commit:
- Final worktree:
```
