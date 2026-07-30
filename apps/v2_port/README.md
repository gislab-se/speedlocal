# V2 Final monolith

This folder is the active V2 Final monolith. It began as the guarded V2 copy
and is now reduced and generalized one validated behavior slice at a time.

Purpose:

- preserve the working user flow while SpeedLocal is slimmed down;
- replace hardcoded regional behavior with shared contracts and providers;
- prevent old region discovery, inactive regions, and generated data clutter.

Rules:

- Do not copy `data/`, `exports/`, `artifacts/`, or `tmp/` into this folder.
- Do not copy `apps/potential_model/manifests/regions/`.
- Do not copy acceptance registries into this folder. Active regions declare
  their registry provider and path in `regions/<region>/region.json`.
- Keep region discovery tied to the SpeedLocal `regions/index.json`.
- Resolve external registries and assets through `speedlocal.paths`.
- Keep generated acceptance geometry disabled until it is deliberately ported.
  Bornholm's checksum-declared, precomputed polygon fixtures are retained for
  onboarding diagnostics only; unknown combinations fail closed and the public
  Bornholm V2 Final route remains disabled.
- Remove old monolith code only after its replacement has parity evidence and
  is connected to this user flow.

Run the guardrail before promoting changes:

```powershell
python -B scripts\validate_v2_port_guardrails.py
```
