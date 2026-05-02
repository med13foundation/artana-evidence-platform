from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_db.read_model_support import (
    GraphReadModelAuthoritativeSource,
    GraphReadModelDefinition,
    GraphReadModelOwner,
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    ProjectorBackedGraphReadModelUpdateDispatcher,
)


@dataclass
class RecordingProjector:
    rebuild_calls: list[str | None]
    update_calls: list[GraphReadModelUpdate]

    @property
    def definition(self) -> GraphReadModelDefinition:
        return GraphReadModelDefinition(
            name="test_model",
            description="Test model",
            owner=GraphReadModelOwner.GRAPH_CORE,
            authoritative_sources=(GraphReadModelAuthoritativeSource.CLAIM_LEDGER,),
            triggers=(GraphReadModelTrigger.FULL_REBUILD,),
        )

    def rebuild(self, *, space_id: str | None = None) -> int:
        self.rebuild_calls.append(space_id)
        return 1

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        self.update_calls.append(update)
        return 1


def test_dispatcher_routes_full_rebuild_by_enum_value() -> None:
    projector = RecordingProjector(rebuild_calls=[], update_calls=[])
    dispatcher = ProjectorBackedGraphReadModelUpdateDispatcher(
        projectors={projector.definition.name: projector},
    )

    result = dispatcher.dispatch(
        GraphReadModelUpdate(
            model_name="test_model",
            trigger=GraphReadModelTrigger.FULL_REBUILD,
            space_id="space-1",
        ),
    )

    assert result == 1
    assert projector.rebuild_calls == ["space-1"]
    assert projector.update_calls == []
