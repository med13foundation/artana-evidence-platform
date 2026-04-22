# Artana Evidence DB HTTP Examples

These examples are intentionally HTTP-only. They do not import
`artana_evidence_db`, platform models, or service internals, so they can be used
as templates for other projects.

Run the end-to-end flow against a running graph service:

```bash
export GRAPH_URL="http://localhost:8090"
export GRAPH_TOKEN="your-graph-admin-token"
python services/artana_evidence_db/examples/http_only_client_flow.py
```

The example creates or reuses one graph space, seeds a domain pack, validates
entity and claim payloads, writes entities and a claim, and exports the graph.
