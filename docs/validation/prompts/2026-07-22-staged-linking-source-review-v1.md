# Staged Linking Source-Only Review V1

Review the supplied candidate event graph against only the supplied source
passage. You have no benchmark answer and must not infer missing evidence.

Judge whether the complete typed graph, including participants, entity types,
roles, event-to-event nesting, root event, and structure assessment, is directly
supported by the source.

Return exactly one categorical verdict:

- `SUPPORTED`
- `CONTRADICTED`
- `INCOMPLETE`
- `ABSTAIN`

Also return exact source evidence and a short explanation. Do not return a
numeric confidence or quality score. This review cannot modify the graph.
