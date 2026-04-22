# `artana-api`

Python SDK for the Artana Evidence API.

It gives developers one installable package, one typed client, and one clean
way to work with Artana research spaces, documents, the unified review queue,
staged proposals, chat sessions, PubMed search, graph-search runs,
graph-connection runs, onboarding flows, runs, and artifacts.

## Install

From PyPI:

```bash
pip install artana-api
```

From this repository during local development:

```bash
pip install -e packages/artana_api
```

## Public Auth Model

The public SDK auth story is `api_key`, not bearer tokens.

The intended flow is:

1. A self-hosted Artana operator enables bootstrap on the service with
   `ARTANA_EVIDENCE_API_BOOTSTRAP_KEY`.
2. A developer uses that bootstrap secret once to create or resolve their user,
   receive an Artana API key, and get a personal default research space.
3. After that, the developer uses only `api_key` for normal SDK calls.

Bearer `access_token` support still exists for internal or advanced scenarios,
but it is not the primary developer experience.

## Quick Start

### First-Time Bootstrap

Use this once on a self-hosted deployment to get an Artana API key:

```python
from artana_api import ArtanaClient

bootstrap_client = ArtanaClient(base_url="https://api.example.com")

bootstrap = bootstrap_client.auth.bootstrap_api_key(
    bootstrap_key="bootstrap-secret-from-your-operator",
    email="developer@example.com",
    username="developer",
    full_name="Developer Example",
    api_key_name="Default SDK Key",
)

print(bootstrap.user.email)
print(bootstrap.api_key.api_key)
print(bootstrap.default_space.id)
```

### Normal Usage

After you have an Artana API key, use that for all normal requests:

```python
from artana_api import ArtanaClient

with ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
) as client:
    health = client.health()
    print(health.status, health.version)

    auth_context = client.auth.me()
    print(auth_context.user.email)
    print(auth_context.default_space.id)

    result = client.graph.search(
        question="What is known about MED13 and cardiomyopathy?",
    )
    print(result.run.space_id)
    print(result.result.decision)
    print(result.result.total_results)
```

If you do not pass `space_id` or configure `default_space_id`, the SDK uses your
personal default research space. The service creates that space automatically on
bootstrap, and `client.spaces.ensure_default()` can also create it on demand.

## Full Research Workflow

The SDK also supports the governed research flow: attach text or PDFs, extract
staged facts, review the queue, chat with document context, and run explicit
PubMed searches.

```python
from artana_api import ArtanaClient

with ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
) as client:
    workflow = client.chat.ask_with_text(
        question="Refresh the latest PubMed evidence for MED13 and cardiomyopathy.",
        title="MED13 evidence note",
        text="MED13 associates with cardiomyopathy.",
    )

    print(workflow.extraction.proposal_count)
    print(workflow.extraction.review_item_count)
    print(workflow.chat.result.verification.status)

    queue = client.review_queue.list(document_id=workflow.extraction.document.id)
    if queue.items:
        reviewed = client.review_queue.act(
            item_id=queue.items[0].id,
            action="promote",
            reason="Looks good to promote",
        )
        print(reviewed.status)

    pdf_workflow = client.chat.ask_with_pdf(
        question="Refresh the latest PubMed evidence for MED13 and cardiomyopathy.",
        title="MED13 PDF evidence note",
        filename="med13.pdf",
        file_path=b"%PDF-1.4 ... real extractable PDF bytes ... %%EOF\n",
    )
    print(pdf_workflow.extraction.document.last_enrichment_run_id)
```

## Start Here By Goal

Use:

- `client.chat.ask_with_text(...)` if you want the shortest possible demo
- `client.chat.ask_with_pdf(...)` if you already have a paper PDF
- `client.documents.*` plus `client.review_queue.*` if you want explicit manual
  review steps
- `client.pubmed.search(...)` if you only need literature search

The beginner mental model is:

1. add evidence
2. extract staged work
3. review the queue
4. ask grounded questions

## Most Common Use Cases

Start with:

- documents plus the review queue if you want to review one paper or note safely
- `chat.ask_with_text(...)` if you want the shortest assistant-first flow
- `chat.ask_with_pdf(...)` if you want the same flow with a PDF
- `pubmed.search(...)` if you only need literature discovery

The mental model is simple:

1. add evidence
2. extract staged work
3. review the queue
4. ask grounded questions

## Use-Case Recipes

### Review One Paper Safely

```python
from artana_api import ArtanaClient

with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    ingestion = client.documents.upload_pdf(
        file_path="/path/to/med13.pdf",
        title="MED13 paper",
    )
    extraction = client.documents.extract(document_id=ingestion.document.id)
    queue = client.review_queue.list(document_id=ingestion.document.id)

    print(extraction.proposal_count)
    print(extraction.review_item_count)
    if queue.items:
        reviewed = client.review_queue.act(
            item_id=queue.items[0].id,
            action="promote",
            reason="Approved after review",
        )
        print(reviewed.status)
```

### Ask A Question With One Note

```python
from artana_api import ArtanaClient

with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    workflow = client.chat.ask_with_text(
        question="What does this note suggest about MED13?",
        title="MED13 note",
        text="MED13 associates with cardiomyopathy.",
    )
    print(workflow.chat.result.answer_text)
    print(workflow.chat.result.verification.status)
```

### Search PubMed Directly

```python
from artana_api import ArtanaClient

with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    job = client.pubmed.search(
        gene_symbol="MED13",
        search_term="MED13 cardiomyopathy",
        max_results=25,
    )
    print(job.total_results)
    print(len(job.preview_results))
```

## Core Capabilities

### Documents

```python
with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    pdf_ingestion = client.documents.upload_pdf(
        file_path="/path/to/med13.pdf",
        title="MED13 PDF evidence note",
    )
    print(pdf_ingestion.document.enrichment_status)  # not_started

    extraction = client.documents.extract(document_id=pdf_ingestion.document.id)
    document = client.documents.get(document_id=pdf_ingestion.document.id)
    print(document.last_enrichment_run_id)
    print(extraction.proposal_count)
```

### Review Queue

```python
with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    queue = client.review_queue.list(status="pending_review")
    reviewed = client.review_queue.act(
        item_id=queue.items[0].id,
        action="promote",
        reason="Reviewed and approved",
    )
    print(reviewed.status)
```

### Proposals (Advanced)

```python
with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    proposals = client.proposals.list(status="pending_review")
    print(proposals.total)
```

### Chat

```python
with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    session = client.chat.create_session(title="MED13 chat")
    chat = client.chat.send_message(
        session_id=session.id,
        content="What grounded evidence is there for MED13?",
    )
    print(chat.result.answer_text)
```

### PubMed

```python
with ArtanaClient(base_url="https://api.example.com", api_key="art_sk_...") as client:
    job = client.pubmed.search(
        gene_symbol="MED13",
        search_term="MED13 cardiomyopathy",
    )
    print(job.id, job.total_results)
```

## Examples

Runnable examples live in
[examples/](./examples).

They are ordered from simple to more complex:

- bootstrap a first API key
- inspect health and identity
- search in the personal default space
- create and use a project space
- run an onboarding round trip
- inspect runs and artifacts
- run graph connection from a seed entity
- ingest a document and extract staged facts
- review the queue
- run chat with document context
- run explicit PubMed search
- run chat with a PDF document

From the repository root:

```bash
venv/bin/python packages/artana_api/examples/01_bootstrap_api_key.py --help
```

Or run the full progression in one command:

```bash
make sdk-examples \
  ARTANA_API_BASE_URL="https://api.example.com" \
  ARTANA_BOOTSTRAP_KEY="bootstrap-secret"
```

## Research Space Model

The SDK is designed for many users against the same `base_url`.

Each authenticated user:

- has one personal default research space
- can create additional research spaces
- can use their owned spaces by passing `space_id`
- cannot access another user's spaces just by knowing the `space_id`

Typical flow:

```python
from artana_api import ArtanaClient

with ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
) as client:
    personal_space = client.spaces.ensure_default()
    print(personal_space.id, personal_space.is_default)

    project_space = client.spaces.create(
        name="MED13 Literature Review",
        description="Private project workspace linked to this user",
    )

    result = client.graph.search(
        space_id=project_space.id,
        question="Summarize evidence for MED13-related cardiomyopathy findings.",
    )
    print(result.run.space_id)
```

## Authentication

### Recommended

Use `api_key`:

```python
from artana_api import ArtanaClient

client = ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
)
```

### Bootstrap for Self-Hosted Deployments

The bootstrap route is the self-contained way to get started without depending
on `research_inbox` or any other first-party UI.

The server operator sets:

```bash
export ARTANA_EVIDENCE_API_BOOTSTRAP_KEY="your-bootstrap-secret"
```

Then the SDK developer calls:

```python
from artana_api import ArtanaClient

bootstrap_client = ArtanaClient(base_url="https://api.example.com")

bootstrap = bootstrap_client.auth.bootstrap_api_key(
    bootstrap_key="your-bootstrap-secret",
    email="developer@example.com",
    username="developer",
    full_name="Developer Example",
)

issued_api_key = bootstrap.api_key.api_key
print(issued_api_key)
```

After that, use the returned `issued_api_key` as your normal `api_key`.

### Create Additional API Keys

Once authenticated with an Artana API key, you can create more keys for the
same user identity:

```python
from artana_api import ArtanaClient

with ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
) as client:
    issued = client.auth.create_api_key(
        name="CI Key",
        description="Used by automation",
    )
    print(issued.api_key.api_key)
```

### Advanced Compatibility

The SDK still supports bearer tokens:

```python
from artana_api import ArtanaClient

client = ArtanaClient(
    base_url="https://api.example.com",
    access_token="your-bearer-token",
)
```

That path is best treated as advanced or internal compatibility. For public SDK
use, prefer `api_key`.

## Configuration

### Direct Configuration

```python
from artana_api import ArtanaClient

client = ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
    timeout_seconds=60,
)
```

### Environment Variables

Supported environment variables:

- `ARTANA_API_BASE_URL`
- `ARTANA_BASE_URL`
- `ARTANA_API_KEY`
- `ARTANA_ACCESS_TOKEN`
- `ARTANA_BEARER_TOKEN`
- `ARTANA_OPENAI_API_KEY`
- `OPENAI_API_KEY`
- `ARTANA_DEFAULT_SPACE_ID`
- `ARTANA_TIMEOUT_SECONDS`

Recommended environment setup:

```bash
export ARTANA_API_BASE_URL="https://api.example.com"
export ARTANA_API_KEY="art_sk_..."
```

Then:

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    print(client.health().status)
```

`ARTANA_ACCESS_TOKEN` and `ARTANA_BEARER_TOKEN` are optional compatibility
inputs. For most SDK users, `ARTANA_API_KEY` is the important value.

## Common Workflows

### Inspect the Current Identity

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    auth_context = client.auth.me()
    print(auth_context.user.email)
    print(auth_context.default_space.id if auth_context.default_space else None)
```

### Ensure the Personal Default Space

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    personal = client.spaces.ensure_default()
    print(personal.id)
    print(personal.is_default)
```

### List and Create Spaces

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    spaces = client.spaces.list()
    print("existing spaces:", spaces.total)

    created = client.spaces.create(
        name="Cardiomyopathy Research",
        description="Workspace for MED13 investigation",
    )
    print(created.id)
    print(created.slug)
```

### Graph Search

If `default_space_id` is configured, or if the service can resolve your
personal default space, you can omit `space_id`:

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    response = client.graph.search(
        question="What is known about MED13?",
        top_k=10,
        max_depth=2,
    )

    print(response.run.id)
    print(response.run.space_id)
    print(response.result.decision)
    print(response.result.total_results)
```

### Graph Connection

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    response = client.graph.connect(
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=2,
    )

    print(response.run.id)
    print(response.outcomes[0].seed_entity_id)
    print(response.outcomes[0].proposed_relations[0].relation_type)
```

### Research Onboarding

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    started = client.onboarding.start(
        research_title="MED13",
        primary_objective="Understand cardiomyopathy mechanisms",
    )

    print(started.run.id)
    print(started.assistant_message.message_type)

    continued = client.onboarding.reply(
        thread_id="thread-1",
        message_id="message-1",
        intent="answer",
        mode="reply",
        reply_text="Focus on cardiomyopathy outcomes first.",
    )

    print(continued.run.id)
    print(continued.assistant_message.message_type)
```

### Runs and Artifacts

```python
from artana_api import ArtanaClient

with ArtanaClient.from_env() as client:
    search = client.graph.search(question="What is known about MED13?")

    runs = client.runs.list()
    print(runs.total)

    run = client.runs.get(run_id=search.run.id)
    print(run.harness_id)

    artifacts = client.artifacts.list(run_id=search.run.id)
    print([artifact.key for artifact in artifacts.artifacts])

    workspace = client.artifacts.workspace(run_id=search.run.id)
    print(workspace.snapshot)
```

## Error Handling

The SDK raises typed exceptions:

- `ArtanaConfigurationError`
- `ArtanaRequestError`
- `ArtanaResponseValidationError`

Example:

```python
from artana_api import ArtanaClient
from artana_api.exceptions import ArtanaRequestError

try:
    with ArtanaClient(
        base_url="https://api.example.com",
        api_key="art_sk_invalid",
    ) as client:
        client.spaces.list()
except ArtanaRequestError as exc:
    print(exc.status_code)
    print(exc.detail)
```

## OpenAI Key Behavior

The SDK can send `openai_api_key` as a header, but the standalone
`services/artana_evidence_api` service in this repository currently keeps model
credentials server-side for graph-search, graph-connection, and onboarding.

So for the service in this repo:

- `api_key` is the main SDK credential
- `openai_api_key` is not required for normal SDK usage
- client-supplied OpenAI keys should be treated as forward-looking or
  deployment-specific behavior

## Custom Headers and Custom HTTP Clients

You can provide default headers:

```python
from artana_api import ArtanaClient

client = ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
    default_headers={
        "X-Trace-Id": "demo-request",
    },
)
```

Or supply your own `httpx.Client`:

```python
import httpx

from artana_api import ArtanaClient

http_client = httpx.Client(
    base_url="https://api.example.com",
    timeout=45.0,
)

client = ArtanaClient(
    base_url="https://api.example.com",
    api_key="art_sk_...",
    client=http_client,
)
```

When you pass a custom `httpx.Client`, the SDK does not own that client and
will not close it for you.

## API Surface

The public client exposes:

- `client.health()`
- `client.auth.bootstrap_api_key(...)`
- `client.auth.me()`
- `client.auth.create_api_key(...)`
- `client.spaces.list()`
- `client.spaces.create(...)`
- `client.spaces.ensure_default()`
- `client.spaces.delete(...)`
- `client.graph.search(...)`
- `client.graph.connect(...)`
- `client.onboarding.start(...)`
- `client.onboarding.reply(...)`
- `client.runs.list(...)`
- `client.runs.get(...)`
- `client.artifacts.list(...)`
- `client.artifacts.get(...)`
- `client.artifacts.workspace(...)`

## Development

Run the SDK tests from the repository root:

```bash
python -m pytest packages/artana_api/tests
```

Install editable dependencies locally:

```bash
pip install -e packages/artana_api
```
