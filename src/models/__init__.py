# Artana Resource Library - Pydantic Models
# Strongly typed data models with validation

# re-export domain entity
from src.domain.entities.publication import (
    Publication as DomainPublication,
)

# re-export domain entity
from .gene import Gene, GeneCreate, GeneResponse

__all__ = [
    "DomainPublication",
    "Gene",
    "GeneCreate",
    "GeneResponse",
]
