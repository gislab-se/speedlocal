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

- Characterize existing V2 behavior before modifying that path.
- Record important discoveries and decisions in the daily file.
- Keep V2 functional until parity exists.
- Run focused validation after each meaningful step.
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

## Commit

- Not committed.
```
