"""Routers for the standalone graph API service."""

from .claims import router as claims_router
from .graph_views import router as graph_views_router
from .health import router as health_router
from .operations import router as operations_router
from .reasoning_paths import router as reasoning_paths_router
from .relations import router as relations_router

__all__ = [
    "claims_router",
    "graph_views_router",
    "health_router",
    "operations_router",
    "reasoning_paths_router",
    "relations_router",
]
