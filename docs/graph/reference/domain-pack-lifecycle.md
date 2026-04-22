# Domain-Pack Lifecycle

This reference explains how graph domain packs are defined, registered,
selected, and consumed by the standalone graph service.

## Current Runtime Model

The active runtime flow is:

1. A domain pack is defined under `src/graph/domain_*`.
2. The pack is exposed as a `GraphDomainPack` instance.
3. The process-local registry registers available packs.
4. service startup bootstraps built-in packs.
5. `GRAPH_DOMAIN_PACK` selects the active pack.
6. runtime helpers and service composition consume the active pack.

The current built-in packs are `biomedical` and `sports`.

## Core Contracts

Primary code locations:

- `src/graph/core/domain_pack.py`
  Defines the `GraphDomainPack` contract.
- `src/graph/core/pack_registration.py`
  Defines the registry interface used to register packs.
- `src/graph/pack_registry.py`
  Owns process-local registration and active-pack resolution.
- `src/graph/runtime.py`
  Provides the shared runtime helper layer that composition code calls.

`GraphDomainPack` is the unit of registration. It bundles the pack-owned
extensions and defaults that the runtime is allowed to consume, including:

- runtime identity
- view extension
- search extension
- connector extension
- relation-suggestion extension
- dictionary-loading extension
- feature flags
- domain-context policy
- auto-promotion defaults
- domain-specific bootstrap and fallback config

## Registration Lifecycle

### 1. Define The Pack

A pack is implemented under `src/graph/domain_<name>/`.

Current built-in entrypoints:

- `src/graph/domain_biomedical/pack.py`
- `src/graph/domain_sports/pack.py`

Each module constructs one `GraphDomainPack` object from explicit extension and
config modules.

### 2. Register The Pack

Registration is done through the registry interface in
`src/graph/core/pack_registration.py`.

The process-local implementation lives in `src/graph/pack_registry.py`.
Important functions:

- `register_graph_domain_pack(...)`
- `register_graph_domain_packs(...)`
- `bootstrap_default_graph_domain_packs(...)`

Built-in packs are registered by `bootstrap_default_graph_domain_packs(...)`.

### 3. Bootstrap During Service Startup

The standalone graph service calls
`bootstrap_default_graph_domain_packs()` in:

- `services/artana_evidence_db/app.py`

That makes built-in pack registration part of application startup instead of an
implicit side effect buried in unrelated runtime code.

### 4. Resolve The Active Pack

The active pack is selected in `src/graph/pack_registry.py` by
`resolve_graph_domain_pack()`.

Selection rules:

- `GRAPH_DOMAIN_PACK` chooses the pack name
- names are normalized to lowercase
- the current default is `biomedical`
- unsupported names raise a runtime error with the supported pack list

### 5. Consume The Active Pack

Runtime and composition code should not import domain-pack modules directly.
They should consume the active pack through:

- `src/graph/runtime.py`

Primary helper:

- `create_graph_domain_pack()`

That helper is the intended boundary for runtime consumers such as:

- `services/artana_evidence_db/composition.py`
- `services/artana_evidence_db/dependencies.py`
- `src/infrastructure/dependency_injection/graph_runtime_factories.py`
- `src/infrastructure/dependency_injection/service_factories.py`
- `src/graph/core/service_config.py`

## Adding A New Pack

The current expected process is:

1. Add a new package under `src/graph/domain_<name>/`.
2. Build a `GraphDomainPack` with explicit extension/config objects.
3. Update `bootstrap_default_graph_domain_packs(...)` to register it.
4. Run startup and boundary checks with `GRAPH_DOMAIN_PACK=<name>`.
5. Add focused tests proving the pack works through the same runtime boundary.

At this stage, pack registration is still in-process and static. There is no
dynamic plugin discovery, external pack manifest, or hot reload lifecycle.

## Invariants

Domain packs may provide defaults, prompts, connector dispatch, dictionary
loading, and heuristics. They may not:

- override claim invariants
- replace canonical projection rules
- require graph-core to import pack modules as a compile-time dependency

The architectural boundary is enforced by:

- `scripts/validate_graph_phase2_boundary.py`
- `make graph-phase2-boundary-check`

Pack-level validation currently uses:

- `make graph-phase2-biomedical-pack-check`

## Practical Guidance

When adding runtime behavior:

- put new extension contracts in `src/graph/core/`
- implement pack-owned values in `src/graph/domain_<name>/`
- inject the active pack or one of its extension objects from composition
- avoid direct imports from `src.graph.domain_biomedical` in generic runtime
  code

When documenting new pack-owned behavior, update this file if the behavior
changes how packs are registered, selected, or consumed.
