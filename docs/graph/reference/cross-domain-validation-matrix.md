# Graph Cross-Domain Validation Matrix

Recorded on `2026-03-13`.

This matrix records the first explicit cross-domain proof slice for the graph
platform. It focuses on the two built-in packs currently shipped by the repo:
`biomedical` and `sports`.

## Commands

- `make graph-phase7-cross-domain-check`
- `make graph-phase2-boundary-check`
- `make graph-phase6-release-check`

## Matrix

| Check | biomedical | sports | Notes |
| --- | --- | --- | --- |
| Built-in pack registration | pass | pass | Both packs are bootstrapped by `src/graph/pack_registry.py`. |
| Runtime identity via `GRAPH_DOMAIN_PACK` | pass | pass | `Biomedical Graph Service` / `graph-biomedical`; `Sports Graph Service` / `graph-sports`. |
| Dictionary domain-context seeding through HTTP boundary | pass | pass | Biomedical proof uses `clinical`; sports proof uses `competition`. |
| Connector default source dispatch | pass | pass | Biomedical default remains `clinvar`; sports default is `match_report`. |
| Admin claim enforcement | pass | pass | Graph admin routes still require `graph_admin=true` for both packs. |
| Tenant membership and role hierarchy | pass | pass | Non-members remain blocked; viewer remains read-only under both packs. |
| One-hop neighborhood read model | pass | pass | `entity_neighbors` rebuilds and the same depth-1 neighborhood route works unchanged under both packs. |
| Release contract / OpenAPI workflow | pass | pass | `make graph-phase6-release-check` passes with shared product-boundary metadata. |
| Graph-core import boundary | pass | pass | `make graph-phase2-boundary-check` protects graph-core from pack reverse imports. |

## Current Limits

- This matrix proves the core admin-claim and tenant-membership flows across
  both packs, but it does not yet cover the full route surface.
- This matrix now proves the shared read-model framework through the
  `entity_neighbors` path across both packs, but it does not yet cover every
  query surface.
- This matrix does not yet add a third non-biomedical pack.

## Next Expansion

1. Add a second non-biomedical pack to expand the validation matrix beyond one
   alternate domain.
2. Extend cross-pack proof from `entity_neighbors` to at least one additional
   read-model surface.
3. Expand auth/tenancy validation from the core admin and membership path to
   more route families.
