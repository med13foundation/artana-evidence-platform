"""
Publishing module initialization.
"""

from .notification.email_service import EmailService
from .notification.webhook_service import WebhookService
from .versioning.release_manager import ReleaseManager
from .versioning.semantic_versioner import SemanticVersioner, VersionType
from .zenodo.client import ZenodoClient
from .zenodo.doi_service import DOIService
from .zenodo.uploader import ZenodoUploader

__all__ = [
    "DOIService",
    "EmailService",
    "ReleaseManager",
    "SemanticVersioner",
    "VersionType",
    "WebhookService",
    "ZenodoClient",
    "ZenodoUploader",
]
