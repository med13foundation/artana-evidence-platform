import importlib.util
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "016_add_reviews_table.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "artana_evidence_api_reviews_migration",
        _MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeBind:
    class _Dialect:
        name = "postgresql"

    dialect = _Dialect()


class _FakeInspector:
    def __init__(self, *, has_table: bool) -> None:
        self._has_table = has_table
        self.calls: list[tuple[str, str | None]] = []

    def has_table(self, table_name: str, schema: str | None = None) -> bool:
        self.calls.append((table_name, schema))
        return self._has_table


def test_research_space_column_omits_fk_when_shared_table_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    inspector = _FakeInspector(has_table=False)
    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    column = migration._research_space_id_column(schema="public")

    assert inspector.calls == [("research_spaces", "public")]
    assert column.name == "research_space_id"
    assert column.foreign_keys == set()


def test_research_space_column_keeps_fk_when_shared_table_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    inspector = _FakeInspector(has_table=True)
    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)

    column = migration._research_space_id_column(schema="public")

    assert inspector.calls == [("research_spaces", "public")]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "public.research_spaces.id"


def test_upgrade_creates_review_table_with_audit_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration_module()
    captured_columns: list[object] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: _FakeBind())
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda _name, *columns, **_kwargs: captured_columns.extend(columns),
    )
    monkeypatch.setattr(migration.op, "create_index", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        migration.sa,
        "inspect",
        lambda _bind: _FakeInspector(has_table=True),
    )

    migration.upgrade()

    column_names = {
        column.name for column in captured_columns if hasattr(column, "name")
    }
    assert {"created_at", "updated_at", "last_updated"}.issubset(column_names)
