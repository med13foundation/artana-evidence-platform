from __future__ import annotations

from artana_evidence_db.orm_base import Base


def test_orm_base_exports_local_metadata() -> None:
    assert Base.__name__ == "Base"
    assert hasattr(Base, "metadata")
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
