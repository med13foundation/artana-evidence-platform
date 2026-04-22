"""
Triple validator for the ingestion pipeline.
Validates if a relation between two entities is allowed by the schema.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

logger = logging.getLogger(__name__)


class TripleValidator:
    """
    Validates relations (triples) against the relation constraints in the dictionary.
    """

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def validate(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """
        Check if the triple (Source -> Relation -> Target) is allowed.
        """
        allowed = self.dictionary_repo.is_relation_allowed(
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
        )

        if not allowed:
            logger.warning(
                "Triple not allowed: %s -[%s]-> %s",
                source_type,
                relation_type,
                target_type,
            )

        return allowed
