# Runtime Skills

Status date: April 23, 2026.

Runtime skills are filesystem-backed instruction bundles used by graph-harness
agents inside the Evidence API.

Skill files live under:

```text
services/artana_evidence_api/runtime_skills/
```

The registry is implemented in:

- `services/artana_evidence_api/runtime_skill_registry.py`

The runtime agent bridge is implemented in:

- `services/artana_evidence_api/runtime_skill_agent.py`

## Current Skill Shape

Each skill is a `SKILL.md` file with YAML frontmatter and markdown
instructions. The required frontmatter fields are:

- `name`
- `version`
- `summary`
- `tools`
- `requires_capabilities`

The registry validates that declared tool names exist in
`services/artana_evidence_api/tool_catalog.py`.

## Current Skill Families

The current tree includes skills for:

- curation;
- orchestration;
- reasoning;
- shared graph/literature helpers.

Harness templates decide which skills are allowed or preloaded. The app fails
fast at startup if a harness references an unknown skill.
