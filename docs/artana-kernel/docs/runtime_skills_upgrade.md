# Runtime Skills Upgrade Notes

Status date: April 23, 2026.

The current repo uses service-local runtime skills under:

```text
services/artana_evidence_api/runtime_skills/
```

There is no separate hidden-tool skill tree in this checkout.

## When Adding Or Changing A Skill

1. Add or edit a `SKILL.md` file under the runtime skill tree.
2. Declare only tool names that exist in `services/artana_evidence_api/tool_catalog.py`.
3. Add required capabilities only when the skill should be tenant-gated.
4. Run Evidence API startup or tests that call
   `validate_graph_harness_skill_configuration`.
5. Run:

```bash
make artana-evidence-api-service-checks
```

## Compatibility Rule

Do not change the skill frontmatter shape without updating
`services/artana_evidence_api/runtime_skill_registry.py` and tests.
