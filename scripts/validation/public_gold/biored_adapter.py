"""Read BioRED annotations without invoking Artana or a provider."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Split = Literal["Train", "Dev", "Test"]


@dataclass(frozen=True, slots=True)
class BioREDEntity:
    identifier: str
    entity_type: str
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class BioREDRelation:
    document_id: str
    relation_id: str
    relation_type: str
    novelty: Literal["NOVEL", "BACKGROUND"]
    first_identifier: str
    second_identifier: str


@dataclass(frozen=True, slots=True)
class BioREDDocument:
    document_id: str
    text: str
    entities: tuple[BioREDEntity, ...]
    relations: tuple[BioREDRelation, ...]


def load_biored_split(
    path: Path, *, split: Split, allow_test: bool = False
) -> tuple[BioREDDocument, ...]:
    """Load one official BioC JSON split and keep the test split sealed by default."""

    if split == "Test" and not allow_test:
        raise ValueError(
            "BioRED test split is sealed until a preregistration authorizes it"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    documents = raw.get("documents")
    if not isinstance(documents, list):
        raise TypeError("BioRED BioC JSON must contain a documents list")
    return tuple(_normalize_document(document) for document in documents)


def write_development_projection(source: Path, output: Path) -> dict[str, object]:
    """Write a deterministic, development-only projection with source receipt."""

    source_bytes = source.read_bytes()
    documents = load_biored_split(source, split="Dev")
    payload: dict[str, object] = {
        "schema_version": "artana.public_gold.biored_projection.v1",
        "split": "Dev",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "documents": [
            {
                "document_id": document.document_id,
                "text": document.text,
                "entities": [asdict(entity) for entity in document.entities],
                "relations": [asdict(relation) for relation in document.relations],
            }
            for document in documents
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def _normalize_document(raw: object) -> BioREDDocument:
    if not isinstance(raw, dict):
        raise TypeError("BioRED document must be an object")
    document_id = _string(raw.get("id"), "document id")
    passages = raw.get("passages")
    if not isinstance(passages, list):
        raise TypeError(f"BioRED document {document_id} lacks passages")
    text_parts: list[str] = []
    entities: list[BioREDEntity] = []
    for passage in passages:
        if not isinstance(passage, dict):
            raise TypeError("BioRED passage must be an object")
        passage_text = _string(passage.get("text"), "passage text")
        passage_offset = _integer(passage.get("offset"), "passage offset")
        text_parts.append(passage_text)
        annotations = passage.get("annotations", [])
        if not isinstance(annotations, list):
            raise TypeError("BioRED annotations must be a list")
        for annotation in annotations:
            entities.extend(
                _normalize_annotation(annotation, passage_text, passage_offset)
            )
    relations = tuple(
        _normalize_relation(item, document_id) for item in raw.get("relations", [])
    )
    return BioREDDocument(document_id, "".join(text_parts), tuple(entities), relations)


def _normalize_annotation(
    raw: object, passage_text: str, passage_offset: int
) -> tuple[BioREDEntity, ...]:
    if not isinstance(raw, dict):
        raise TypeError("BioRED annotation must be an object")
    infons = raw.get("infons")
    locations = raw.get("locations")
    if not isinstance(infons, dict) or not isinstance(locations, list):
        raise TypeError("BioRED annotation lacks infons or locations")
    identifier = _string(infons.get("identifier"), "entity identifier")
    entity_type = _string(infons.get("type"), "entity type")
    annotation_text = _string(raw.get("text"), "entity text")
    entities: list[BioREDEntity] = []
    for location in locations:
        if not isinstance(location, dict):
            raise TypeError("BioRED location must be an object")
        start = _integer(location.get("offset"), "entity offset")
        length = _integer(location.get("length"), "entity length")
        relative_start = start - passage_offset
        if passage_text[relative_start : relative_start + length] != annotation_text:
            raise ValueError("BioRED entity offsets do not resolve to annotation text")
        entities.append(
            BioREDEntity(
                identifier, entity_type, start, start + length, annotation_text
            )
        )
    return tuple(entities)


def _normalize_relation(raw: object, document_id: str) -> BioREDRelation:
    if not isinstance(raw, dict) or not isinstance(raw.get("infons"), dict):
        raise TypeError("BioRED relation must have infons")
    infons = raw["infons"]
    novelty = _normalize_novelty(infons.get("novel"))
    return BioREDRelation(
        document_id=document_id,
        relation_id=_string(raw.get("id"), "relation id"),
        relation_type=_string(infons.get("type"), "relation type"),
        novelty=novelty,
        first_identifier=_string(infons.get("entity1"), "first relation entity"),
        second_identifier=_string(infons.get("entity2"), "second relation entity"),
    )


def _normalize_novelty(value: object) -> Literal["NOVEL", "BACKGROUND"]:
    label = _string(value, "relation novelty")
    if label == "Novel":
        return "NOVEL"
    if label == "No":
        return "BACKGROUND"
    raise ValueError(f"unsupported BioRED relation novelty: {label}")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"BioRED {label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"BioRED {label} must be a non-negative integer")
    return value
