# Artana Kernel Integration Notes

Status date: April 23, 2026.

These are repo-local notes for how the Evidence API uses the pinned
`artana-kernel` dependency. They are not a vendored copy of upstream kernel
documentation.

Current integration points:

- `services/artana_evidence_api/composition.py`
- `services/artana_evidence_api/runtime_support.py`
- `services/artana_evidence_api/runtime_skill_registry.py`
- `services/artana_evidence_api/runtime_skill_agent.py`
- `services/artana_evidence_api/tool_catalog.py`
- `services/artana_evidence_api/runtime_skills/`

Read in this order:

1. [Kernel Contracts](./kernel_contracts.md)
2. [Runtime Skills](./runtime_skills.md)
3. [Deep Traceability](./deep_traceability.md)
4. [Strong Model Harnesses](./strong_model_harnesses.md)
5. [Compatibility Matrix](./compatibility_matrix.md)
6. [Runtime Skills Upgrade Notes](./runtime_skills_upgrade.md)
