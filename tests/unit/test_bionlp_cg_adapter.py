from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.public_gold.bionlp_cg_adapter import (
    load_development_directory,
)


def _write_fixture(root: Path) -> Path:
    devel = root / "devel"
    devel.mkdir()
    (devel / "PMID-1.txt").write_text("Drug inhibits growth.")
    (devel / "PMID-1.a1").write_text("T1\tSimple_chemical 0 4\tDrug\n")
    (devel / "PMID-1.a2").write_text(
        "T2\tNegative_regulation 5 13\tinhibits\n"
        "T3\tGrowth 14 20\tgrowth\n"
        "E1\tGrowth:T3\n"
        "E2\tNegative_regulation:T2 Cause:T1 Theme:E1\n"
        "M1\tNegation E1\n",
    )
    return devel


def test_preserves_nested_events_roles_and_modifiers(tmp_path: Path) -> None:
    document = load_development_directory(_write_fixture(tmp_path))[0]

    assert document.triggers[0].text == "inhibits"
    assert document.events[1].arguments[1].role == "Theme"
    assert document.events[1].arguments[1].target_id == "E1"
    assert document.modifiers[0].modifier_type == "Negation"


def test_refuses_non_development_split(tmp_path: Path) -> None:
    test = tmp_path / "test"
    test.mkdir()

    with pytest.raises(ValueError, match="development split only"):
        load_development_directory(test)
