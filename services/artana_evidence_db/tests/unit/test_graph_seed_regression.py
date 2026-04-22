"""Regression tests for graph seed and governance fixes (#127, #128, #129)."""

from __future__ import annotations

from unittest.mock import MagicMock

from artana_evidence_db.dictionary_management_service import (
    DictionaryManagementService,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_BUILTIN_ENTITY_TYPES,
)

# ---------------------------------------------------------------------------
# #127 — Resolution policies must be seeded for all builtin entity types
# ---------------------------------------------------------------------------


class TestResolutionPolicySeeding:
    """Verify that the seed creates resolution policies for every entity type."""

    def test_all_builtin_entity_types_have_default_policy(self) -> None:
        """Every builtin entity type should resolve to a policy via defaults."""
        for entity_type_def in GRAPH_SERVICE_BUILTIN_ENTITY_TYPES:
            strategy, anchors, threshold = (
                DictionaryManagementService._resolve_default_resolution_policy(
                    entity_type_def.entity_type,
                )
            )
            assert (
                strategy is not None
            ), f"Entity type {entity_type_def.entity_type} has no default resolution policy"
            assert isinstance(
                anchors,
                tuple,
            ), f"Entity type {entity_type_def.entity_type} anchors should be a tuple"
            assert isinstance(
                threshold,
                float,
            ), f"Entity type {entity_type_def.entity_type} threshold should be a float"

    def test_seed_covers_all_builtin_types(self) -> None:
        """The builtin entity types list should not be empty."""
        assert (
            len(GRAPH_SERVICE_BUILTIN_ENTITY_TYPES) >= 8
        ), f"Expected at least 8 builtin entity types, got {len(GRAPH_SERVICE_BUILTIN_ENTITY_TYPES)}"

    def test_gene_has_hgnc_anchor(self) -> None:
        strategy, anchors, _ = (
            DictionaryManagementService._resolve_default_resolution_policy("GENE")
        )
        assert strategy == "LOOKUP"
        assert "hgnc_id" in anchors

    def test_phenotype_has_hpo_anchor(self) -> None:
        strategy, anchors, _ = (
            DictionaryManagementService._resolve_default_resolution_policy("PHENOTYPE")
        )
        assert strategy == "LOOKUP"
        assert "hpo_id" in anchors

    def test_protein_has_uniprot_anchor(self) -> None:
        strategy, anchors, _ = (
            DictionaryManagementService._resolve_default_resolution_policy("PROTEIN")
        )
        assert strategy == "LOOKUP"
        assert "uniprot_id" in anchors


# ---------------------------------------------------------------------------
# #128 — VARIANT must require both gene_symbol AND hgvs_notation
# ---------------------------------------------------------------------------


class TestVariantResolutionPolicy:
    """Verify that VARIANT resolution prevents merging distinct variants."""

    def test_variant_uses_strict_match(self) -> None:
        strategy, anchors, threshold = (
            DictionaryManagementService._resolve_default_resolution_policy("VARIANT")
        )
        assert strategy == "STRICT_MATCH"

    def test_variant_requires_both_anchors(self) -> None:
        """Both gene_symbol and hgvs_notation must be required anchors."""
        _, anchors, _ = DictionaryManagementService._resolve_default_resolution_policy(
            "VARIANT",
        )
        assert "gene_symbol" in anchors, "VARIANT must require gene_symbol anchor"
        assert "hgvs_notation" in anchors, "VARIANT must require hgvs_notation anchor"

    def test_variant_anchors_has_exactly_two(self) -> None:
        """VARIANT should have exactly 2 anchors — no more, no less."""
        _, anchors, _ = DictionaryManagementService._resolve_default_resolution_policy(
            "VARIANT",
        )
        assert (
            len(anchors) == 2
        ), f"VARIANT should have exactly 2 required anchors, got {len(anchors)}: {anchors}"

    def test_variant_threshold_is_exact(self) -> None:
        """STRICT_MATCH should use threshold 1.0 (exact match only)."""
        _, _, threshold = (
            DictionaryManagementService._resolve_default_resolution_policy("VARIANT")
        )
        assert threshold == 1.0


# ---------------------------------------------------------------------------
# #129 — Missing constraint must default to ALLOWED (open-world)
# ---------------------------------------------------------------------------


class TestOpenWorldConstraintDefault:
    """Verify that missing constraints default to allowed, not forbidden."""

    def test_no_constraint_returns_allowed(self) -> None:
        """When no constraint exists for a triple, is_triple_allowed returns True."""
        from artana_evidence_db._dictionary_repository_constraints_merge_mixin import (
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )

        # Create a mock session that returns no results
        mock_session = MagicMock()
        mock_session.scalars.return_value.first.return_value = None

        # Create mixin instance with mock session
        mixin = GraphDictionaryRepositoryConstraintsMergeMixin.__new__(
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )
        mixin._session = mock_session

        result = mixin.is_triple_allowed("GENE", "ACTIVATES", "GENE")
        assert (
            result is True
        ), "Missing constraint should default to ALLOWED (open-world), not FORBIDDEN"

    def test_explicit_allow_constraint_returns_true(self) -> None:
        """An explicit is_allowed=True constraint should return True."""
        from artana_evidence_db._dictionary_repository_constraints_merge_mixin import (
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )

        mock_constraint = MagicMock()
        mock_constraint.is_allowed = True

        mock_session = MagicMock()
        mock_session.scalars.return_value.first.return_value = mock_constraint

        mixin = GraphDictionaryRepositoryConstraintsMergeMixin.__new__(
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )
        mixin._session = mock_session

        result = mixin.is_triple_allowed("GENE", "ACTIVATES", "GENE")
        assert result is True

    def test_explicit_forbid_constraint_returns_false(self) -> None:
        """An explicit is_allowed=False constraint should return False."""
        from artana_evidence_db._dictionary_repository_constraints_merge_mixin import (
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )

        mock_constraint = MagicMock()
        mock_constraint.is_allowed = False

        mock_session = MagicMock()
        mock_session.scalars.return_value.first.return_value = mock_constraint

        mixin = GraphDictionaryRepositoryConstraintsMergeMixin.__new__(
            GraphDictionaryRepositoryConstraintsMergeMixin,
        )
        mixin._session = mock_session

        result = mixin.is_triple_allowed("GENE", "ACTIVATES", "GENE")
        assert (
            result is False
        ), "Explicit is_allowed=False constraint should return FORBIDDEN"
