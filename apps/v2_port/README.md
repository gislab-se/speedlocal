# V2 Quarantine Port

This folder is a guarded copy of the V2 potential app baseline.

Purpose:

- keep real V2 app behavior available while SpeedLocal is slimmed down
- reduce from a working baseline instead of rebuilding from scratch
- prevent old region discovery, inactive regions, and generated data clutter

Rules:

- Do not copy `data/`, `exports/`, `artifacts/`, or `tmp/` into this folder.
- Do not copy `apps/potential_model/manifests/regions/`.
- Do not copy `apps/acceptance_model/registry.json`.
- Keep region discovery tied to the SpeedLocal `regions/index.json`.
- Keep generated acceptance geometry disabled until it is deliberately ported.

Run the guardrail before promoting changes:

```powershell
python -B scripts\validate_v2_port_guardrails.py
```
