# Graph Cross-Domain Examples

This reference shows how the same graph-core surfaces are reused by different
domain packs without changing graph-core contracts.

Current built-in packs:

- `biomedical`
- `sports`

## Runtime Identity

The same startup contract in `src/graph/core/service_config.py` reads
pack-owned runtime identity.

Biomedical:

```text
GRAPH_DOMAIN_PACK=biomedical
app_name   = Biomedical Graph Service
jwt_issuer = graph-biomedical
```

Sports:

```text
GRAPH_DOMAIN_PACK=sports
app_name   = Sports Graph Service
jwt_issuer = graph-sports
```

Shared graph-core behavior:

- env loading
- service settings contract
- JWT/runtime metadata wiring

## Dictionary Seeding

The same governance builders consume the pack-owned
`dictionary_loading_extension`.

Biomedical builtin contexts:

- `general`
- `clinical`
- `genomics`

Sports builtin contexts:

- `general`
- `competition`
- `roster`

Shared graph-core/runtime behavior:

- dictionary repository implementations
- governance service/builders
- admin dictionary route shapes

## Connector Default Dispatch

The same graph-connection route and service resolve source type from the active
pack.

Biomedical:

```text
default source_type -> clinvar
```

Sports:

```text
default source_type -> match_report
```

Shared graph-core/runtime behavior:

- connector extension contract
- graph-connection application service
- graph-connection route shape

## Access And Tenancy

The same graph-core access and tenancy abstractions apply across packs.

Shared graph-core types:

- `GraphPrincipal`
- `GraphAccessRole`
- `GraphTenant`
- `GraphTenantMembership`
- `GraphRlsSessionContext`

Cross-pack behavior already proven:

- graph-admin routes still require `graph_admin=true`
- non-members still receive `403`
- viewer membership remains read-only

## One-Hop Neighborhood Read Model

The same graph-core read model powers one-hop neighborhood reads for both
packs.

Shared read model:

- `entity_neighbors`

Shared route:

- `GET /v1/spaces/{space_id}/graph/neighborhood/{entity_id}?depth=1`

What changes by pack:

- entity vocabulary
- dictionary defaults
- connector/source semantics that populate the graph

What stays shared:

- read-model table
- projector
- rebuild/update contract
- repository indexed query path

## Design Rule

When a new pack-owned behavior is added:

1. define the extension contract in `src/graph/core/`
2. implement the values in `src/graph/domain_<name>/`
3. inject the extension from runtime/composition
4. prove the same shared route or service works under at least two packs

If a feature requires graph-core branching on pack name, treat that as a
boundary regression.
