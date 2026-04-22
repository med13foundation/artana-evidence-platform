"""
JSON-LD serialization for provenance metadata.

Converts provenance information into JSON-LD format for
FAIR compliance and semantic web integration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.provenance import Provenance
    from src.type_definitions.common import JSONObject, JSONValue

from src.type_definitions.json_utils import to_json_value


@dataclass
class ProvenanceSerializer:
    """Serializer for converting provenance data to JSON-LD."""

    @staticmethod
    def get_jsonld_context() -> JSONObject:
        """Get the JSON-LD context for provenance metadata."""
        return {
            "@context": {
                "@version": 1.1,
                "prov": "http://www.w3.org/ns/prov#",
                "dct": "http://purl.org/dc/terms/",
                "foaf": "http://xmlns.com/foaf/0.1/",
                "xsd": "http://www.w3.org/2001/XMLSchema#",
                # Basic provenance terms
                "entity": "prov:entity",
                "activity": "prov:activity",
                "agent": "prov:agent",
                "wasGeneratedBy": "prov:wasGeneratedBy",
                "wasDerivedFrom": "prov:wasDerivedFrom",
                "wasAttributedTo": "prov:wasAttributedTo",
                "startedAtTime": "prov:startedAtTime",
                "endedAtTime": "prov:endedAtTime",
                # Dublin Core terms
                "title": "dct:title",
                "description": "dct:description",
                "creator": "dct:creator",
                "created": "dct:created",
                "modified": "dct:modified",
                # Custom terms for MED13
                "dataSource": "https://med13.org/terms/dataSource",
                "processingStep": "https://med13.org/terms/processingStep",
                "qualityScore": "https://med13.org/terms/qualityScore",
                "validationStatus": "https://med13.org/terms/validationStatus",
            },
        }

    def serialize_provenance(self, provenance: Provenance) -> JSONObject:
        """Serialize a single provenance record to JSON-LD."""
        context = self.get_jsonld_context()
        source_name = provenance.source.value

        entity_id = f"urn:artana:dataset:{source_name}"
        dataset_node: JSONObject = {
            "@id": entity_id,
            "@type": "prov:Entity",
            "title": f"MED13 Dataset from {source_name}",
            "description": f"Biomedical data acquired from {source_name}",
            "dataSource": source_name,
            "created": provenance.acquired_at.isoformat(),
        }

        if provenance.source_url:
            dataset_node["dct:source"] = provenance.source_url
        if provenance.source_version:
            dataset_node["dct:hasVersion"] = provenance.source_version
        if provenance.metadata:
            dataset_node["prov:qualifiedAttribution"] = provenance.metadata

        graph_nodes: list[JSONObject] = [dataset_node]
        jsonld_data: JSONObject = {**context, "@graph": graph_nodes}

        # Add acquisition activity node
        activity_id = f"urn:artana:activity:acquisition:{source_name}"
        acquisition_activity: JSONObject = {
            "@id": activity_id,
            "@type": "prov:Activity",
            "prov:label": f"Data acquisition from {source_name}",
            "startedAtTime": provenance.acquired_at.isoformat(),
            "endedAtTime": provenance.acquired_at.isoformat(),
        }
        graph_nodes.append(acquisition_activity)
        dataset_node["wasGeneratedBy"] = {"@id": activity_id}

        # Add agent (acquired_by)
        agent_id = f"urn:artana:agent:{provenance.acquired_by}"
        agent_node: JSONObject = {
            "@id": agent_id,
            "@type": "prov:Agent",
            "foaf:name": provenance.acquired_by,
        }
        graph_nodes.append(agent_node)
        acquisition_activity["wasAttributedTo"] = {"@id": agent_id}

        # Add processing steps as chained activities
        for step_index, step in enumerate(provenance.processing_steps):
            step_activity_id = (
                f"urn:artana:activity:processing:{source_name}:{step_index}"
            )
            step_activity: JSONObject = {
                "@id": step_activity_id,
                "@type": "prov:Activity",
                "prov:label": f"Processing step: {step}",
                "processingStep": step,
            }

            if step_index == 0:
                step_activity["prov:used"] = {"@id": entity_id}
            else:
                prev_step_entity_id = (
                    f"urn:artana:entity:processed:{source_name}:{step_index - 1}"
                )
                step_activity["prov:used"] = {"@id": prev_step_entity_id}

            graph_nodes.append(step_activity)

            output_entity_id = f"urn:artana:entity:processed:{source_name}:{step_index}"
            output_entity: JSONObject = {
                "@id": output_entity_id,
                "@type": "prov:Entity",
                "prov:label": f"Dataset after {step}",
                "wasDerivedFrom": {"@id": entity_id},
                "wasGeneratedBy": {"@id": step_activity_id},
            }
            graph_nodes.append(output_entity)

        if provenance.quality_score is not None:
            dataset_node["qualityScore"] = provenance.quality_score
        dataset_node["validationStatus"] = provenance.validation_status

        return jsonld_data

    def serialize_provenance_chain(
        self,
        provenance_records: list[Provenance],
    ) -> JSONObject:
        """Serialize multiple provenance records as a chain."""
        context = self.get_jsonld_context()

        graph: list[JSONObject] = []
        for provenance in provenance_records:
            serialized = self.serialize_provenance(provenance)
            # Merge graphs, avoiding duplicates
            serialized_graph = serialized.get("@graph", [])
            if isinstance(serialized_graph, list):
                for node in serialized_graph:
                    if node not in graph:
                        graph.append(node)

        return {**context, "@graph": graph}

    def to_json(self, data: JSONObject, indent: int | None = 2) -> str:
        """Convert JSON-LD data to JSON string."""
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def validate_jsonld(self, jsonld_data: JSONObject) -> list[str]:
        """Validate JSON-LD structure and content."""
        issues = []

        # Check for required @context
        if "@context" not in jsonld_data:
            issues.append("Missing @context in JSON-LD")
            return issues

        # Check for @graph
        if "@graph" not in jsonld_data:
            issues.append("Missing @graph in JSON-LD")
            return issues

        graph = jsonld_data["@graph"]
        if not isinstance(graph, list):
            issues.append("@graph must be a list")
            return issues

        # Validate each node has @id and @type
        for i, node in enumerate(graph):
            if not isinstance(node, dict):
                issues.append(f"Node {i} must be a dictionary")
                continue

            if "@id" not in node:
                issues.append(f"Node {i} missing @id")
            if "@type" not in node:
                issues.append(f"Node {i} missing @type")

        return issues


class FAIRMetadataSerializer:
    """Specialized serializer for FAIR-compliant metadata."""

    def __init__(self) -> None:
        self.provenance_serializer = ProvenanceSerializer()

    def create_fair_metadata_bundle(
        self,
        dataset_metadata: JSONObject,
        provenance: Provenance,
        license_info: JSONObject | None = None,
    ) -> JSONObject:
        """Create a complete FAIR metadata bundle."""
        base_context = self.provenance_serializer.get_jsonld_context().get("@context")
        combined_context: dict[str, JSONValue] = {}
        if isinstance(base_context, dict):
            combined_context = {
                str(key): to_json_value(value) for key, value in base_context.items()
            }
        combined_context.update(
            {
                "fair": "https://www.go-fair.org/fair-principles/",
                "license": "dct:license",
                "accessRights": "dct:accessRights",
                "conformsTo": "dct:conformsTo",
            },
        )
        context: JSONObject = {"@context": combined_context}

        # Combine all metadata
        dataset_node: JSONObject = {
            "@id": "urn:artana:dataset:main",
            "@type": ["prov:Entity", "dct:Dataset"],
            "conformsTo": [
                {"@id": "fair:findable"},
                {"@id": "fair:accessible"},
                {"@id": "fair:interoperable"},
                {"@id": "fair:reusable"},
            ],
        }
        dataset_node.update(dataset_metadata)

        graph_nodes: list[JSONObject] = [dataset_node]

        bundle: JSONObject = {
            "@context": context["@context"],
            "@graph": graph_nodes,
        }

        # Add license information
        if license_info:
            graph_nodes[0]["license"] = license_info

        # Add provenance graph
        provenance_data = self.provenance_serializer.serialize_provenance(provenance)
        provenance_graph = provenance_data.get("@graph", [])
        if isinstance(provenance_graph, list):
            graph_nodes.extend(provenance_graph)

        # Link main dataset to provenance
        graph_nodes[0]["prov:wasDerivedFrom"] = {
            "@id": f"urn:artana:dataset:{provenance.source.value}",
        }

        return bundle


__all__ = ["FAIRMetadataSerializer", "ProvenanceSerializer"]
