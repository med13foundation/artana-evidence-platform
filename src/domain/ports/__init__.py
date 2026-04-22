"""Domain-wide service port interfaces."""

from artana_evidence_db.evidence_sentence_harness_port import (
    EvidenceSentenceHarnessPort,
)
from artana_evidence_db.governance_ports import (
    ConceptDecisionHarnessPort,
    DictionarySearchHarnessPort,
)
from artana_evidence_db.kernel_domain_ports import (
    SourceDocumentReferencePort,
)
from artana_evidence_db.ports import (
    SpaceAccessPort,
    SpaceRegistryPort,
    SpaceSettingsPort,
)
from artana_evidence_db.query_ports import GraphQueryPort, ResearchQueryPort
from artana_evidence_db.semantic_ports import ConceptPort, DictionaryPort

from src.domain.ports.space_lifecycle_sync_port import SpaceLifecycleSyncPort
from src.domain.ports.text_embedding_port import TextEmbeddingPort

__all__ = [
    "ConceptDecisionHarnessPort",
    "ConceptPort",
    "DictionaryPort",
    "DictionarySearchHarnessPort",
    "EvidenceSentenceHarnessPort",
    "GraphQueryPort",
    "ResearchQueryPort",
    "SpaceAccessPort",
    "SpaceLifecycleSyncPort",
    "SpaceRegistryPort",
    "SpaceSettingsPort",
    "SourceDocumentReferencePort",
    "TextEmbeddingPort",
]
