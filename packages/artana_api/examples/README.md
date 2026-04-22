# Examples

These examples are ordered from first-time setup to more advanced workflows.

Run them from the repository root with:

```bash
venv/bin/python packages/artana_api/examples/01_bootstrap_api_key.py --help
```

Or run the whole sequence in one command:

```bash
make sdk-examples \
  ARTANA_API_BASE_URL="https://api.example.com" \
  ARTANA_BOOTSTRAP_KEY="bootstrap-secret"
```

Or after installing the SDK in your own environment:

```bash
python path/to/examples/01_bootstrap_api_key.py --help
```

## Environment Variables

Most examples read these variables:

- `ARTANA_API_BASE_URL`
- `ARTANA_API_KEY`
- `ARTANA_BOOTSTRAP_KEY`

Optional example-specific defaults:

- `ARTANA_EXAMPLE_EMAIL`
- `ARTANA_EXAMPLE_USERNAME`
- `ARTANA_EXAMPLE_FULL_NAME`

## Progression

1. `01_bootstrap_api_key.py`
   Bootstraps a self-hosted user and prints the first issued `art_sk_...` key.
2. `02_health_and_identity.py`
   Confirms connectivity and prints the authenticated user plus default space.
3. `03_graph_search_default_space.py`
   Ensures the personal default space and runs a graph search.
4. `04_project_space_workflow.py`
   Creates an additional project space and runs a scoped search inside it.
5. `05_onboarding_round_trip.py`
   Starts onboarding and sends one follow-up reply.
6. `06_runs_and_artifacts.py`
   Triggers a run, then inspects run records, artifacts, and workspace state.
7. `07_graph_connection_workflow.py`
   Runs graph connection from a seed entity and prints proposed relations.
8. `08_document_ingestion_and_extraction.py`
   Submits one text document, extracts staged facts, and lists the review queue.
9. `09_review_queue_actions.py`
   Reviews the first staged queue item by promoting or rejecting it.
10. `10_chat_with_documents.py`
   Runs the assistant-first workflow with a text document and chat.
11. `11_pubmed_search.py`
   Runs one explicit PubMed search and then fetches the saved job.
12. `12_chat_with_pdf.py`
   Runs the assistant-first workflow with an embedded PDF and chat.

## Start Here If You Only Want 15 Minutes

Run this short path:

1. `01_bootstrap_api_key.py`
   Creates your first API key.
2. `02_health_and_identity.py`
   Confirms auth works and shows your default space.
3. `08_document_ingestion_and_extraction.py`
   Shows the document -> review queue flow.
4. `09_review_queue_actions.py`
   Shows the manual review gate.
5. `10_chat_with_documents.py` or `12_chat_with_pdf.py`
   Shows the grounded assistant flow with tracked evidence.

## Pick By Goal

Run:

- `08_document_ingestion_and_extraction.py` if you want to learn documents plus the review queue first
- `09_review_queue_actions.py` if you want to learn the manual review step
- `10_chat_with_documents.py` if you want assistant-first chat with text input
- `11_pubmed_search.py` if you want explicit literature search only
- `12_chat_with_pdf.py` if you want the full PDF -> extract -> chat flow

What each beginner example proves:

- `08` proves documents create tracked records and extraction feeds the review queue
- `09` proves staged review work stays manual and reviewable
- `10` proves chat can use tracked documents as context
- `11` proves PubMed is available directly, not only through chat
- `12` proves the PDF flow works end to end

## Typical Flow

```bash
export ARTANA_API_BASE_URL="https://api.example.com"
export ARTANA_BOOTSTRAP_KEY="bootstrap-secret"

venv/bin/python packages/artana_api/examples/01_bootstrap_api_key.py \
  --email developer@example.com \
  --username developer
```

Take the returned `api_key`, then:

```bash
export ARTANA_API_KEY="art_sk_..."
venv/bin/python packages/artana_api/examples/02_health_and_identity.py
venv/bin/python packages/artana_api/examples/03_graph_search_default_space.py
venv/bin/python packages/artana_api/examples/07_graph_connection_workflow.py
venv/bin/python packages/artana_api/examples/08_document_ingestion_and_extraction.py
venv/bin/python packages/artana_api/examples/10_chat_with_documents.py
venv/bin/python packages/artana_api/examples/12_chat_with_pdf.py
```

## One-Command Runner

The repo also includes
[`run_all_examples.sh`](./run_all_examples.sh),
which bootstraps a user, extracts the issued `art_sk_...` key, exports
`ARTANA_API_KEY`, and then runs `02` through `12` in order.

It expects:

- `ARTANA_API_BASE_URL`
- `ARTANA_BOOTSTRAP_KEY`

Optional defaults:

- `ARTANA_EXAMPLE_EMAIL`
- `ARTANA_EXAMPLE_USERNAME`
- `ARTANA_EXAMPLE_FULL_NAME`
