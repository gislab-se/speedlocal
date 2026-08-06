# Eligible establishment surface

Status: active candidate, not locally promoted or published  
Date: 2026-08-06

## Decision

Onshore wind and large-scale land solar calculate literal establishment area
against a manifest-declared eligible surface, not the full geometry of every
H3 cell in the analysis domain.

For Trøndelag, `onshore_land` is the intersection of each canonical R7 cell and
the checksum-pinned regional land mask. The current mask excludes sea and area
outside the region but retains inland water. This is deliberate and visible in
the contract. Excluding lakes and rivers requires a separately reviewed
hydrographic source; enabling offshore wind or floating solar requires a
separate technology-specific surface.

## Contract boundary

The canonical analysis domain and eligible surface have different jobs:

- the analysis domain keeps the reviewed R7/R6/R5 cells used by roads,
  population, nature, culture, and grid-infrastructure group calculations;
- the eligible surface supplies geometry and area for wind/solar potential,
  combined map classes, hover values, result tables, acceptance capacity, and
  continuous allocation;
- active restrictions remove area only inside the eligible surface;
- map class and percentage are derived from the same remaining and model-area
  values;
- region ids never choose the clipping algorithm.

The formula is:

```text
technology potential % =
    remaining eligible establishment area
    / eligible establishment-surface area
    * 100
```

## Trøndelag evidence

| Resolution | Cells | Eligible area |
|---|---:|---:|
| R7 | 13,735 | 41,826.930636 km² |
| R6 | 2,163 | 41,826.930636 km² |
| R5 | 365 | 41,826.930636 km² |

The former full-cell domain is 45,213.188644 km². The eligible surface removes
3,386.258008 km², or 7.49%, from sea and area outside the reviewed mask. R6 and
R5 declared areas are exact sums of their R7 children.

The generated geometry is static runtime data outside Git. Its source mask,
R7/R6/R5 artifacts, byte sizes, and SHA-256 values are pinned by the region
analysis manifest and the 53-file runtime contract. Missing files, unsupported
policies, path drift, or checksum drift fail closed.

## Performance

Clipping is a build step, not a Streamlit rerun step. The app reads cached,
precomputed display geometries and cell areas. Hover remains client-side and
does not trigger new geospatial work.

## Promotion gate

Before this candidate is locally promoted:

- `validate_eligible_surface.py` must pass;
- generic-engine and accepted-reference/drift gates must pass while preserving
  all five group metrics;
- vector-preview, real-app, runtime-bundle, guardrail, and delivery gates must
  pass;
- clean localhost review must confirm that coastal hexagons are visibly clipped
  and that map, hover, table, and allocation agree.

Publication remains a separate Tuesday/Friday action after local promotion.
