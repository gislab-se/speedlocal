# Nature slice characterization

Status: automated promotion gates pass; localhost visual review pending
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind restriction flow

## Scope

The public and canonical group id is `nature`. The first and complete current
Trøndelag source is `protected_areas`, labelled `Naturvernområden`. It replaces
the wind flow's transitional registry group id `protected`; solar keeps its
separate registry-backed protected-nature behavior until the solar slice.

The source represents NEA Naturvern clipped and dissolved for Trøndelag. Water
protection is a possible future source, while land-use classes remain outside
this group and this slice.

## Accepted behavior

- Operation: `hard_exclusion`.
- Slider: optional buffer from 0 to 2,000 m in 50 m steps; default 0 m.
- A display cell is blocked when the source intersects it. At a positive
  buffer it is also blocked when minimum source distance is at or below the
  selected distance.
- Acceptance is strictly binary: blocked cells receive 0 and all other cells
  receive 1.
- Raw R7 observations roll up by minimum distance and any intersection before
  filtering to the manifest-declared R7, R6, or R5 analysis domain.

The public control shows the single source checkbox directly and has no
redundant group checkbox or empty advanced-source panel. Source and buffer
preview are map-only controls and do not change the selected analysis layers,
parameters, or result.

## Source geometry contract

The asset manifest declares 420 polygon features. Its dissolved GeoJSON is one
`GeometryCollection` containing 412 polygon members plus one point and one
line created by dimensional collapse. The source therefore declares
`geometry_collection_policy=highest_dimension`.

That policy is generic and fail closed by default: mixed geometry is rejected
unless a source explicitly declares the policy. For a declared polygon source,
only lower-dimensional collection members may be discarded. Vector preview
records both the 412 usable source geometries and the manifest's declared
feature count of 420.

## Frozen numeric anchors

| Resolution | Buffer | Mean potential | Blocked cells |
|---|---:|---:|---:|
| R7 | 0 m | 71.161266836549% | 3,961 |
| R7 | 250 m | 71.161266836549% | 3,961 |
| R7 | 1,000 m | 70.964688751365% | 3,988 |
| R7 | 2,000 m | 60.189297415362% | 5,468 |
| R6 | 0 m | 51.410078594545% | 1,051 |
| R6 | 1,000 m | 51.086453999075% | 1,058 |
| R6 | 2,000 m | 40.776699029126% | 1,281 |
| R5 | 0 m | 17.260273972603% | 302 |
| R5 | 1,000 m | 17.260273972603% | 302 |
| R5 | 2,000 m | 12.876712328767% | 318 |

The unchanged 0/250 m R7 and 0/250/1,000 m R5 values follow from the accepted
distance data, not a special-case rule.

## Code classification

- **Keep:** frozen binary protected-nature semantics, the common analysis
  domain, form batching, map-review behavior, and downstream result consumers.
- **Extract:** generic `hard_exclusion` execution and the explicit
  highest-dimension geometry-collection policy.
- **Configure:** canonical group/layer ids, source path, geometry policy,
  labels, colors, buffer bounds, and default.
- **Rewrite:** Trøndelag wind controls, selection normalization, calculation,
  source/buffer previews, and allocation-ranking source now consume the
  canonical nature contract.
- **Remove:** Trøndelag's public wind `protected` alias and every legacy
  distance-loader fallthrough for `protected_areas`.

Solar's `protected` identifier and helpers are intentionally retained because
they belong to a different, not-yet-migrated product behavior.

## Promotion gates

- Generic engine validates detected polygon geometry, the manifest-only mixed
  geometry policy, binary output, fixed anchors, and R7/R6/R5 domains.
- Frozen parity compares every cell at 0, 250, 1,000, and 2,000 m with an
  independent raw-CSV hard-exclusion oracle.
- Invalid blank, duplicate, undeclared, and legacy `protected` selections fail
  before legacy normalization.
- The actual V2 Final runtime and wind allocation-ranking contract never load
  `protected_areas` through the legacy registry.
- Vector preview validates the 0 m footprint and monotonically growing
  250/1,000 m metric buffers.
- Real Streamlit checks validate the direct control, 0/2,000 m interaction,
  source/buffer map review, and R7/R6/R5 values.
- Roads and population regression gates remain unchanged.

The shared literal establishment-area percentage remains scheduled for the
combined-result and wind/solar phases. This slice preserves the accepted
binary per-cell nature restriction and does not reinterpret that later result.
