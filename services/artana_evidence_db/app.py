"""FastAPI application factory for the standalone graph service."""

from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .product_contract import GRAPH_OPENAPI_URL, GRAPH_SERVICE_VERSION
from .routers.ai_full_mode import router as ai_full_mode_router
from .routers.claims import router as claims_router
from .routers.concepts import router as concepts_router
from .routers.dictionary import router as dictionary_router
from .routers.dictionary_proposals import router as dictionary_proposals_router
from .routers.dictionary_transforms import router as dictionary_transforms_router
from .routers.domain_packs import router as domain_packs_router
from .routers.entities import router as entities_router
from .routers.graph_documents import router as graph_documents_router
from .routers.graph_views import router as graph_views_router
from .routers.health import router as health_router
from .routers.hypotheses import router as hypotheses_router
from .routers.observations import router as observations_router
from .routers.operations import router as operations_router
from .routers.provenance import router as provenance_router
from .routers.reasoning_paths import router as reasoning_paths_router
from .routers.relations import router as relations_router
from .routers.search import router as search_router
from .routers.spaces import router as spaces_router
from .routers.validation import router as validation_router
from .routers.workflows import router as workflows_router
from .runtime.pack_registry import create_graph_domain_pack


def create_app() -> FastAPI:
    """Create the standalone graph API application."""
    graph_domain_pack = create_graph_domain_pack()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=GRAPH_SERVICE_VERSION,
        docs_url="/docs",
        openapi_url=GRAPH_OPENAPI_URL,
    )
    app.state.graph_domain_pack = graph_domain_pack
    app.include_router(health_router)
    app.include_router(ai_full_mode_router)
    app.include_router(claims_router)
    app.include_router(concepts_router)
    app.include_router(dictionary_router)
    app.include_router(dictionary_proposals_router)
    app.include_router(dictionary_transforms_router)
    app.include_router(domain_packs_router)
    app.include_router(entities_router)
    app.include_router(graph_documents_router)
    app.include_router(graph_views_router)
    app.include_router(operations_router)
    app.include_router(hypotheses_router)
    app.include_router(observations_router)
    app.include_router(provenance_router)
    app.include_router(relations_router)
    app.include_router(reasoning_paths_router)
    app.include_router(search_router)
    app.include_router(spaces_router)
    app.include_router(validation_router)
    app.include_router(workflows_router)
    return app


__all__ = ["create_app"]
