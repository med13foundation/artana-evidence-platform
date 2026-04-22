"""Current clean baseline for the MED13 schema.

Revision ID: 001_current_baseline
Create Date: 2026-03-11
"""

# ruff: noqa: S608

from __future__ import annotations

import artana_evidence_db.claim_relation_persistence_model  # noqa: F401
import artana_evidence_db.entity_embedding_model  # noqa: F401
import artana_evidence_db.entity_lookup_models  # noqa: F401
import artana_evidence_db.kernel_claim_models  # noqa: F401
import artana_evidence_db.kernel_concept_models  # noqa: F401
import artana_evidence_db.kernel_dictionary_models  # noqa: F401
import artana_evidence_db.kernel_entity_models  # noqa: F401
import artana_evidence_db.kernel_relation_models  # noqa: F401
import artana_evidence_db.observation_persistence_model  # noqa: F401
import artana_evidence_db.operation_run_models  # noqa: F401
import artana_evidence_db.provenance_model  # noqa: F401
import artana_evidence_db.read_models  # noqa: F401
import artana_evidence_db.reasoning_path_persistence_models  # noqa: F401
import artana_evidence_db.space_models  # noqa: F401
import sqlalchemy as sa
from alembic import op
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_schema_name,
    qualify_graph_table_name,
)

revision = "001_current_baseline"
down_revision = None
branch_labels = None
depends_on = None

_SPACE_POLICY_TABLES: tuple[str, ...] = (
    "entities",
    "observations",
    "provenance",
    "relations",
    "relation_claims",
    "claim_participants",
    "entity_embeddings",
    "relation_projection_sources",
)
_ENTITY_IDENTIFIERS_TABLE = "entity_identifiers"
_RELATION_EVIDENCE_TABLE = "relation_evidence"
_CLAIM_EVIDENCE_TABLE = "claim_evidence"
_PROJECTION_DIAGNOSTIC_FUNCTION = "find_orphan_relations_without_projection"
_PROJECTION_TRIGGER_FUNCTION = "enforce_relation_projection_lineage"
_PROJECTION_TRIGGER_NAME = "trg_enforce_relation_projection_lineage"
_EXCLUDED_FROM_BASELINE: frozenset[str] = frozenset(
    {
        "reasoning_paths",
        "reasoning_path_steps",
        "entity_relation_summary",
        "entity_claim_summary",
        "entity_neighbors",
        "entity_mechanism_paths",
        "harness_runs",
        "harness_run_intents",
        "harness_run_approvals",
        "harness_proposals",
        "harness_chat_sessions",
        "harness_chat_messages",
        "harness_schedules",
        "harness_research_state",
        "harness_graph_snapshots",
        "source_documents",
    },
)

_BYPASS_RLS = (
    "COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)"
)
_IS_ADMIN = (
    "COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)"
)
_HAS_PHI_ACCESS = (
    "COALESCE(NULLIF(current_setting('app.has_phi_access', true), '')::boolean, false)"
)
_CURRENT_USER_ID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
_ENTITIES_TABLE = qualify_graph_table_name("entities")
_RELATIONS_TABLE = qualify_graph_table_name("relations")
_RELATION_EVIDENCE_TABLE_QUALIFIED = qualify_graph_table_name("relation_evidence")
_RELATION_CLAIMS_TABLE = qualify_graph_table_name("relation_claims")
_RELATION_PROJECTION_SOURCES_TABLE = qualify_graph_table_name(
    "relation_projection_sources",
)
_DICTIONARY_ENTITY_TYPES_TABLE = qualify_graph_table_name("dictionary_entity_types")
_DICTIONARY_RELATION_TYPES_TABLE = qualify_graph_table_name("dictionary_relation_types")
_DICTIONARY_RELATION_SYNONYMS_TABLE = qualify_graph_table_name(
    "dictionary_relation_synonyms",
)
_RELATION_CONSTRAINTS_TABLE = qualify_graph_table_name("relation_constraints")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        graph_schema = graph_schema_name()
        if graph_schema is not None:
            op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'))
        op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")

    _baseline_metadata_tables().create_all(bind=bind)

    if bind.dialect.name != "postgresql":
        return

    for table_name in _SPACE_POLICY_TABLES:
        _create_policy(
            table_name,
            _space_access_condition(f"{table_name}.research_space_id"),
        )
    _create_policy(_ENTITY_IDENTIFIERS_TABLE, _entity_identifier_access_condition())
    _create_policy(_RELATION_EVIDENCE_TABLE, _relation_evidence_access_condition())
    _create_policy(_CLAIM_EVIDENCE_TABLE, _claim_evidence_access_condition())
    _create_graph_integrity_functions()
    _create_graph_integrity_triggers()
    _create_projection_enforcement()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _drop_projection_enforcement()
        _drop_graph_integrity_triggers()
        _drop_graph_integrity_functions()
        for table_name in (
            *_SPACE_POLICY_TABLES,
            _ENTITY_IDENTIFIERS_TABLE,
            _RELATION_EVIDENCE_TABLE,
            _CLAIM_EVIDENCE_TABLE,
        ):
            _drop_policy_and_disable_rls(table_name)

    _baseline_metadata_tables().drop_all(bind=bind)


def _baseline_metadata_tables() -> sa.MetaData:
    metadata = Base.metadata
    include_tables = [
        table
        for table in metadata.tables.values()
        if table.name not in _EXCLUDED_FROM_BASELINE
    ]
    baseline_metadata = sa.MetaData(naming_convention=metadata.naming_convention)
    for table in include_tables:
        table.to_metadata(baseline_metadata)
    return baseline_metadata


def _create_policy(table_name: str, condition: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(f'DROP POLICY IF EXISTS "rls_{table_name}_access" ON "{table_name}"'),
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "rls_{table_name}_access"
            ON "{table_name}"
            FOR ALL
            USING ({condition})
            WITH CHECK ({condition})
            """,
        ),
    )


def _drop_policy_and_disable_rls(table_name: str) -> None:
    op.execute(
        sa.text(f'DROP POLICY IF EXISTS "rls_{table_name}_access" ON "{table_name}"'),
    )
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _space_access_condition(space_column: str) -> str:
    graph_space_memberships = qualify_graph_table_name("graph_space_memberships")
    graph_spaces = qualify_graph_table_name("graph_spaces")
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                {_CURRENT_USER_ID} IS NOT NULL
                AND {space_column} IN (
                    SELECT gsm.space_id
                    FROM {graph_space_memberships} AS gsm
                    WHERE gsm.user_id = {_CURRENT_USER_ID}
                      AND gsm.is_active = TRUE
                    UNION
                    SELECT gs.id
                    FROM {graph_spaces} AS gs
                    WHERE gs.owner_id = {_CURRENT_USER_ID}
                )
            )
        )
    """


def _entity_identifier_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                EXISTS (
                    SELECT 1
                    FROM {_ENTITIES_TABLE} AS e
                    WHERE e.id = entity_identifiers.entity_id
                      AND {_space_access_condition("e.research_space_id")}
                )
                AND (
                    entity_identifiers.sensitivity <> 'PHI'
                    OR {_HAS_PHI_ACCESS}
                )
            )
        )
    """


def _relation_evidence_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR EXISTS (
                SELECT 1
                FROM {_RELATIONS_TABLE} AS r
                WHERE r.id = relation_evidence.relation_id
                  AND {_space_access_condition("r.research_space_id")}
            )
        )
    """


def _claim_evidence_access_condition() -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR EXISTS (
                SELECT 1
                FROM {_RELATION_CLAIMS_TABLE} AS rc
                WHERE rc.id = claim_evidence.claim_id
                  AND {_space_access_condition("rc.research_space_id")}
            )
        )
    """


def _create_graph_integrity_functions() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION trg_normalize_and_validate_entity_type()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.entity_type := upper(btrim(NEW.entity_type));
                IF NEW.entity_type IS NULL OR NEW.entity_type = '' THEN
                    RAISE EXCEPTION 'entity_type is required';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM {_DICTIONARY_ENTITY_TYPES_TABLE} det
                    WHERE det.id = NEW.entity_type
                      AND det.is_active IS TRUE
                      AND det.review_status = 'ACTIVE'
                ) THEN
                    RAISE EXCEPTION 'entity_type % is not an ACTIVE dictionary_entity_type', NEW.entity_type;
                END IF;
                RETURN NEW;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION trg_normalize_and_validate_relation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                v_canonical_relation_type TEXT;
                v_source_type TEXT;
                v_target_type TEXT;
            BEGIN
                NEW.relation_type := upper(btrim(NEW.relation_type));
                IF NEW.relation_type IS NULL OR NEW.relation_type = '' THEN
                    RAISE EXCEPTION 'relation_type is required';
                END IF;
                SELECT drs.relation_type
                  INTO v_canonical_relation_type
                FROM {_DICTIONARY_RELATION_SYNONYMS_TABLE} drs
                WHERE drs.synonym = NEW.relation_type
                  AND drs.is_active IS TRUE
                  AND drs.review_status = 'ACTIVE'
                ORDER BY drs.id ASC
                LIMIT 1;
                IF v_canonical_relation_type IS NOT NULL THEN
                    NEW.relation_type := v_canonical_relation_type;
                END IF;
                SELECT e.entity_type INTO v_source_type
                FROM {_ENTITIES_TABLE} e
                WHERE e.id = NEW.source_id;
                SELECT e.entity_type INTO v_target_type
                FROM {_ENTITIES_TABLE} e
                WHERE e.id = NEW.target_id;
                IF v_source_type IS NULL OR v_target_type IS NULL THEN
                    RAISE EXCEPTION 'relation endpoints must reference existing entities';
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM {_DICTIONARY_RELATION_TYPES_TABLE} drt
                    WHERE drt.id = NEW.relation_type
                      AND drt.is_active IS TRUE
                      AND drt.review_status = 'ACTIVE'
                ) THEN
                    RAISE EXCEPTION 'relation_type % is not an ACTIVE dictionary_relation_type', NEW.relation_type;
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM {_RELATION_CONSTRAINTS_TABLE} rc
                    WHERE rc.source_type = v_source_type
                      AND rc.relation_type = NEW.relation_type
                      AND rc.target_type = v_target_type
                      AND rc.is_allowed IS TRUE
                      AND rc.is_active IS TRUE
                      AND rc.review_status = 'ACTIVE'
                ) THEN
                    RAISE EXCEPTION
                        'relation (% -> % -> %) is not allowed by ACTIVE relation constraints',
                        v_source_type,
                        NEW.relation_type,
                        v_target_type;
                END IF;
                RETURN NEW;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION trg_enforce_relation_requires_evidence()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                v_source_type TEXT;
                v_target_type TEXT;
                v_requires_evidence BOOLEAN;
            BEGIN
                SELECT e.entity_type INTO v_source_type
                FROM {_ENTITIES_TABLE} e
                WHERE e.id = NEW.source_id;
                SELECT e.entity_type INTO v_target_type
                FROM {_ENTITIES_TABLE} e
                WHERE e.id = NEW.target_id;
                SELECT rc.requires_evidence
                  INTO v_requires_evidence
                FROM {_RELATION_CONSTRAINTS_TABLE} rc
                WHERE rc.source_type = v_source_type
                  AND rc.relation_type = NEW.relation_type
                  AND rc.target_type = v_target_type
                  AND rc.is_allowed IS TRUE
                  AND rc.is_active IS TRUE
                  AND rc.review_status = 'ACTIVE'
                ORDER BY rc.id DESC
                LIMIT 1;
                IF COALESCE(v_requires_evidence, TRUE)
                   AND NOT EXISTS (
                        SELECT 1
                        FROM {_RELATION_EVIDENCE_TABLE_QUALIFIED} re
                        WHERE re.relation_id = NEW.id
                   ) THEN
                    RAISE EXCEPTION 'relation % requires evidence but none exists at commit', NEW.id;
                END IF;
                RETURN NEW;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION trg_prevent_deactivate_entity_type_with_usage()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.is_active IS TRUE
                   AND (
                        NEW.is_active IS NOT TRUE
                        OR NEW.review_status <> 'ACTIVE'
                   )
                   AND EXISTS (
                        SELECT 1 FROM {_ENTITIES_TABLE} e WHERE e.entity_type = OLD.id LIMIT 1
                   ) THEN
                    RAISE EXCEPTION
                        'Cannot deactivate/revoke dictionary_entity_type % while entities still reference it',
                        OLD.id;
                END IF;
                RETURN NEW;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION trg_prevent_deactivate_relation_type_with_usage()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF OLD.is_active IS TRUE
                   AND (
                        NEW.is_active IS NOT TRUE
                        OR NEW.review_status <> 'ACTIVE'
                   )
                   AND EXISTS (
                        SELECT 1 FROM {_RELATIONS_TABLE} r WHERE r.relation_type = OLD.id LIMIT 1
                   ) THEN
                    RAISE EXCEPTION
                        'Cannot deactivate/revoke dictionary_relation_type % while relations still reference it',
                        OLD.id;
                END IF;
                RETURN NEW;
            END;
            $$;
            """,
        ),
    )


def _create_graph_integrity_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_entities_normalize_validate ON entities")
    op.execute(
        """
        CREATE TRIGGER trg_entities_normalize_validate
        BEFORE INSERT OR UPDATE OF entity_type
        ON entities
        FOR EACH ROW
        EXECUTE FUNCTION trg_normalize_and_validate_entity_type()
        """,
    )
    op.execute("DROP TRIGGER IF EXISTS trg_relations_normalize_validate ON relations")
    op.execute(
        """
        CREATE TRIGGER trg_relations_normalize_validate
        BEFORE INSERT OR UPDATE OF relation_type, source_id, target_id, research_space_id
        ON relations
        FOR EACH ROW
        EXECUTE FUNCTION trg_normalize_and_validate_relation()
        """,
    )
    op.execute("DROP TRIGGER IF EXISTS trg_relations_requires_evidence ON relations")
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_relations_requires_evidence
        AFTER INSERT OR UPDATE OF relation_type, source_id, target_id
        ON relations
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION trg_enforce_relation_requires_evidence()
        """,
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_dict_entity_type_usage_guard ON dictionary_entity_types",
    )
    op.execute(
        """
        CREATE TRIGGER trg_dict_entity_type_usage_guard
        BEFORE UPDATE OF is_active, review_status
        ON dictionary_entity_types
        FOR EACH ROW
        EXECUTE FUNCTION trg_prevent_deactivate_entity_type_with_usage()
        """,
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_dict_relation_type_usage_guard ON dictionary_relation_types",
    )
    op.execute(
        """
        CREATE TRIGGER trg_dict_relation_type_usage_guard
        BEFORE UPDATE OF is_active, review_status
        ON dictionary_relation_types
        FOR EACH ROW
        EXECUTE FUNCTION trg_prevent_deactivate_relation_type_with_usage()
        """,
    )


def _drop_graph_integrity_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_entities_normalize_validate ON entities")
    op.execute("DROP TRIGGER IF EXISTS trg_relations_normalize_validate ON relations")
    op.execute("DROP TRIGGER IF EXISTS trg_relations_requires_evidence ON relations")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_dict_entity_type_usage_guard ON dictionary_entity_types",
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_dict_relation_type_usage_guard ON dictionary_relation_types",
    )


def _drop_graph_integrity_functions() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS trg_normalize_and_validate_entity_type() CASCADE",
    )
    op.execute("DROP FUNCTION IF EXISTS trg_normalize_and_validate_relation() CASCADE")
    op.execute(
        "DROP FUNCTION IF EXISTS trg_enforce_relation_requires_evidence() CASCADE",
    )
    op.execute(
        "DROP FUNCTION IF EXISTS trg_prevent_deactivate_entity_type_with_usage() CASCADE",
    )
    op.execute(
        "DROP FUNCTION IF EXISTS trg_prevent_deactivate_relation_type_with_usage() CASCADE",
    )


def _create_projection_enforcement() -> None:
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_PROJECTION_DIAGNOSTIC_FUNCTION}(
                in_research_space_id uuid DEFAULT NULL,
                in_limit integer DEFAULT NULL,
                in_offset integer DEFAULT 0
            )
            RETURNS TABLE (
                relation_id uuid,
                research_space_id uuid
            )
            LANGUAGE sql
            STABLE
            AS $$
                SELECT r.id, r.research_space_id
                FROM {_RELATIONS_TABLE} AS r
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM {_RELATION_PROJECTION_SOURCES_TABLE} AS rps
                    WHERE rps.relation_id = r.id
                      AND rps.research_space_id = r.research_space_id
                )
                  AND (
                    in_research_space_id IS NULL
                    OR r.research_space_id = in_research_space_id
                  )
                ORDER BY r.created_at ASC, r.id ASC
                LIMIT COALESCE(in_limit, 2147483647)
                OFFSET COALESCE(in_offset, 0)
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_PROJECTION_TRIGGER_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM {_RELATION_PROJECTION_SOURCES_TABLE} AS rps
                    WHERE rps.relation_id = NEW.id
                      AND rps.research_space_id = NEW.research_space_id
                ) THEN
                    RAISE EXCEPTION
                        'Canonical relation % in research space % is missing claim-backed projection lineage',
                        NEW.id,
                        NEW.research_space_id
                        USING ERRCODE = '23514';
                END IF;
                RETURN NULL;
            END;
            $$;
            """,
        ),
    )
    op.execute(
        sa.text(f'DROP TRIGGER IF EXISTS "{_PROJECTION_TRIGGER_NAME}" ON "relations"'),
    )
    op.execute(
        sa.text(
            f"""
            CREATE CONSTRAINT TRIGGER "{_PROJECTION_TRIGGER_NAME}"
            AFTER INSERT OR UPDATE ON "relations"
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            EXECUTE FUNCTION {_PROJECTION_TRIGGER_FUNCTION}();
            """,
        ),
    )


def _drop_projection_enforcement() -> None:
    op.execute(
        sa.text(f'DROP TRIGGER IF EXISTS "{_PROJECTION_TRIGGER_NAME}" ON "relations"'),
    )
    op.execute(
        sa.text(f"DROP FUNCTION IF EXISTS {_PROJECTION_TRIGGER_FUNCTION}() CASCADE"),
    )
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS "
            f"{_PROJECTION_DIAGNOSTIC_FUNCTION}(uuid, integer, integer) CASCADE",
        ),
    )
