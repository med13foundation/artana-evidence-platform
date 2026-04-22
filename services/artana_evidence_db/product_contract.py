"""Service-local product-boundary metadata for the standalone graph service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GRAPH_SERVICE_VERSION = "0.1.0"
GRAPH_API_MAJOR_VERSION = 1
GRAPH_API_PREFIX = f"/v{GRAPH_API_MAJOR_VERSION}"
GRAPH_OPENAPI_URL = "/openapi.json"
GRAPH_HEALTH_PATH = "/health"

GRAPH_OPENAPI_ARTIFACT = Path("services/artana_evidence_db/openapi.json")
GRAPH_GENERATED_TS_CLIENT_ARTIFACT = Path(
    "services/artana_evidence_db/artana-evidence-db.generated.ts",
)
GRAPH_RELEASE_POLICY_DOC = Path("docs/graph/reference/release-policy.md")
GRAPH_RELEASE_CHECKLIST_DOC = Path("docs/graph/reference/release-checklist.md")
GRAPH_UPGRADE_GUIDE_DOC = Path("docs/graph/reference/upgrade-guide.md")


@dataclass(frozen=True)
class GraphProductContract:
    """Release-boundary metadata shared by graph-service runtime and tooling."""

    service_version: str
    api_prefix: str
    openapi_url: str
    health_path: str
    openapi_artifact: Path
    generated_ts_client_artifact: Path
    release_policy_doc: Path
    release_checklist_doc: Path
    upgrade_guide_doc: Path


GRAPH_PRODUCT_CONTRACT = GraphProductContract(
    service_version=GRAPH_SERVICE_VERSION,
    api_prefix=GRAPH_API_PREFIX,
    openapi_url=GRAPH_OPENAPI_URL,
    health_path=GRAPH_HEALTH_PATH,
    openapi_artifact=GRAPH_OPENAPI_ARTIFACT,
    generated_ts_client_artifact=GRAPH_GENERATED_TS_CLIENT_ARTIFACT,
    release_policy_doc=GRAPH_RELEASE_POLICY_DOC,
    release_checklist_doc=GRAPH_RELEASE_CHECKLIST_DOC,
    upgrade_guide_doc=GRAPH_UPGRADE_GUIDE_DOC,
)


__all__ = [
    "GRAPH_API_MAJOR_VERSION",
    "GRAPH_API_PREFIX",
    "GRAPH_GENERATED_TS_CLIENT_ARTIFACT",
    "GRAPH_HEALTH_PATH",
    "GRAPH_OPENAPI_ARTIFACT",
    "GRAPH_OPENAPI_URL",
    "GRAPH_PRODUCT_CONTRACT",
    "GRAPH_RELEASE_CHECKLIST_DOC",
    "GRAPH_RELEASE_POLICY_DOC",
    "GRAPH_SERVICE_VERSION",
    "GRAPH_UPGRADE_GUIDE_DOC",
    "GraphProductContract",
]
