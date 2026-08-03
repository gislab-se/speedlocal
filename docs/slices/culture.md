# Culture slice characterization

Status: automated promotion gates pass; localhost visual review pending
Behavior reference: frozen V2 for Trøndelag only
Integration target: V2 Final wind restriction flow

## Scope

The public and canonical group id is `culture`. The complete current
Trøndelag group contains two independently selectable polygon sources:

- `cultural_preservation`, labelled `Kulturmiljöer och kulturminnen`;
- `valuable_cultural_environment`, labelled `Värdefulla kulturlandskap`.

The registry's third generic culture id, `cultural_conservation_values`, has
no declared Trøndelag asset and remains outside the product contract. The two
declared sources replace the wind flow's registry-backed culture behavior;
solar keeps its separate culture behavior until the solar slice.

## Accepted behavior

- Operation: `hard_exclusion`.
- Shared slider: optional buffer from 0 to 1,500 m in 50 m steps; default 0 m.
- A display cell is blocked when any selected source intersects it. At a
  positive buffer it is also blocked when minimum distance to any selected
  source is at or below the selected distance.
- Acceptance is strictly binary: blocked cells receive 0 and all other cells
  receive 1.
- Raw R7 observations roll up by minimum distance and any intersection before
  filtering to the manifest-declared R7, R6, or R5 analysis domain.

The public control exposes both source checkboxes directly. There is no
redundant group-enable checkbox or advanced-source panel. Source and buffer
preview are map-only controls and do not change the selected analysis layers,
parameters, or result.

## Source geometry contract

Both assets are declared as polygon sources. Their preview GeoJSON files are
dissolved FeatureCollections containing one MultiPolygon each, while the asset
manifest retains the original source feature counts: 64 for
`cultural_preservation` and 146 for `valuable_cultural_environment`.

The dissolved `cultural_preservation` geometry contains one self-intersection.
Its source contract therefore explicitly declares
`geometry_validity_policy=make_valid`. Invalid geometry still fails closed by
default; only a source with this manifest policy may use Shapely's deterministic
topology repair, and the repaired result must be non-empty, valid, and remain
in the declared polygon family.

Each distance table contains exactly the complete 13,735-cell Trøndelag R7
domain. Both have the same signed id-set digest,
`fdea5973b898319643b7c94ad43b3480c98e639a8f378cbc23e8bc56751fcbba`,
and roll up without missing or outside cells at R7, R6, and R5.

## Frozen numeric anchors

The complete-group anchors below select both sources.

| Resolution | Buffer | Mean potential | Blocked cells |
|---|---:|---:|---:|
| R7 | 0 m | 88.867855842738% | 1,529 |
| R7 | 250 m | 88.867855842738% | 1,529 |
| R7 | 1,000 m | 88.816891153986% | 1,536 |
| R7 | 1,500 m | 87.222424463051% | 1,755 |
| R6 | 0 m | 80.952380952381% | 412 |
| R6 | 250 m | 80.952380952381% | 412 |
| R6 | 1,000 m | 80.906148867314% | 413 |
| R6 | 1,500 m | 79.010633379565% | 454 |
| R5 | 0 m | 58.082191780822% | 153 |
| R5 | 250 m | 58.082191780822% | 153 |
| R5 | 1,000 m | 58.082191780822% | 153 |
| R5 | 1,500 m | 56.164383561644% | 160 |

Individual-source anchors at 0 m are also secured so a broken combination
cannot hide layer drift: R7 blocks 1,070/523 cells, R6 blocks 197/254 cells,
and R5 blocks 48/130 cells for `cultural_preservation` and
`valuable_cultural_environment`, respectively.

## Code classification

- **Keep:** frozen binary culture semantics, the common analysis domain, form
  batching, map-review behavior, and downstream result consumers.
- **Extract:** reuse the generic `hard_exclusion` engine and canonical group
  bridge, and add a fail-closed-by-default geometry-validity policy for vector
  preview.
- **Configure:** canonical group/layer ids, source paths, labels, colors,
  buffer bounds, ordering, and default.
- **Rewrite:** Trøndelag wind controls, selection normalization, calculation,
  source/buffer previews, and allocation-ranking source consume the canonical
  culture contract.
- **Remove:** the Trøndelag wind culture group-enable toggle, advanced-source
  adapter, registry availability path, and legacy distance-loader fallthrough
  for both migrated culture layers.

Solar's culture identifiers and helpers are intentionally retained because
they belong to a different, not-yet-migrated product behavior.

## Promotion gates

- Generic engine validates both polygon sources, binary output, fixed anchors,
  and complete R7/R6/R5 domains.
- Frozen parity compares every cell for each source and their combination at
  0, 250, 1,000, and 1,500 m with an independent raw-CSV oracle.
- Invalid blank, duplicate, undeclared, and undeclared third-layer selections
  fail before legacy normalization.
- The actual V2 Final runtime and wind allocation-ranking contract never load
  either migrated culture layer through the legacy registry.
- Vector preview validates each dissolved footprint and monotonically growing
  combined 250/1,000 m metric buffers.
- Real Streamlit checks validate the direct controls, 0/1,500 m interaction,
  source/buffer map review, and R7/R6/R5 values.
- Roads, population, and nature regression gates remain unchanged.

The shared literal establishment-area percentage and reliable result hover
remain scheduled for the combined-result and wind/solar phases. This slice
preserves the accepted binary per-cell culture restriction.
