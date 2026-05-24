"""Document deletion contracts and runtime support."""

from .contracts import (
    HarnessDocumentDeleteResult,
    HarnessDocumentDeleteScope,
)
from .runtime import (
    DocumentDeletionNotFoundError,
    DocumentDeletionScopeError,
    delete_documents_for_scope,
)

__all__ = [
    "DocumentDeletionNotFoundError",
    "DocumentDeletionScopeError",
    "HarnessDocumentDeleteResult",
    "HarnessDocumentDeleteScope",
    "delete_documents_for_scope",
]
