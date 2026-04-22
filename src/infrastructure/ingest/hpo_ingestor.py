"""
HPO (Human Phenotype Ontology) loader for Artana Resource Library.
Loads phenotype ontology data from HPO releases.
"""

from __future__ import annotations

import gzip
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from defusedxml import ElementTree

from .base_ingestor import BaseIngestor

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element  # nosec B405

    from src.type_definitions.common import JSONObject, JSONValue, RawRecord

logger = logging.getLogger(__name__)


class HPOIngestor(BaseIngestor):
    """
    HPO ontology loader for phenotype data.

    Downloads and parses HPO ontology files to extract phenotype terms,
    definitions, and hierarchical relationships.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="hpo",
            base_url=(
                "https://github.com/obophenotype/human-phenotype-ontology/releases"
            ),
            requests_per_minute=60,  # GitHub API is more permissive
            timeout_seconds=120,  # Large file downloads
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """Fetch HPO terms using the real OBO parser via HPOGateway."""
        from src.infrastructure.ingest.hpo_gateway import HPOGateway

        gateway = HPOGateway()
        max_terms_raw = kwargs.get("max_terms")
        resolved_max_terms = (
            int(str(max_terms_raw))
            if isinstance(max_terms_raw, int | float | str)
            else None
        )
        result = await gateway.fetch_release(max_terms=resolved_max_terms)

        phenotype_records: list[RawRecord] = [
            {
                "hpo_id": term.id,
                "name": term.name,
                "definition": term.definition,
                "synonyms": list(term.synonyms),
                "parents": list(term.parents),
                "xrefs": list(term.xrefs),
                "is_obsolete": term.is_obsolete,
                "namespace": term.namespace,
                "comment": term.comment,
                "source": "hpo",
                "format": "obo",
            }
            for term in result.terms
            if not term.is_obsolete
        ]

        if kwargs.get("med13_only", False):
            phenotype_records = self._filter_med13_relevant_terms(phenotype_records)

        return phenotype_records

    async def _get_latest_release(self) -> JSONObject | None:
        try:
            # GitHub API for latest release
            response = await self._make_request(
                "GET",
                "latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            release_data = self._ensure_raw_record(response.json())

            # Find ontology file in assets
            ontology_url = None
            assets = release_data.get("assets", [])
            if isinstance(assets, list):
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    filename = str(asset.get("name", ""))
                    if filename.endswith((".owl", ".obo")):
                        ontology_url = asset.get("browser_download_url")
                        break

            # Fallback to direct download if no assets found
            if not ontology_url:
                # Use a known stable URL for HPO ontology
                ontology_url = (
                    "https://raw.githubusercontent.com/obophenotype/"
                    "human-phenotype-ontology/master/hp.obo"
                )

            return {
                "version": release_data.get("tag_name", "latest"),
                "published_at": release_data.get("published_at"),
                "ontology_url": ontology_url,
            }

        except Exception:  # noqa: BLE001
            # Fallback to direct download - use the main HPO OBO file
            return {
                "version": "fallback",
                "published_at": None,
                "ontology_url": "https://purl.obolibrary.org/obo/hp.obo",
            }

    async def _download_ontology_file(self, url: str) -> str | None:
        try:
            response = await self._make_request(
                "GET",
                "",
                params={"url": url} if urlparse(url).scheme else None,
            )

            # Handle compressed files
            if (
                url.endswith(".gz")
                or response.headers.get("content-encoding") == "gzip"
            ):
                content = gzip.decompress(response.content).decode("utf-8")
            else:
                content = response.text

        except Exception:  # noqa: BLE001
            return None
        else:
            return content

    def _parse_hpo_ontology(self, ontology_content: str) -> list[RawRecord]:
        phenotypes: list[RawRecord] = []

        try:
            # Determine file format and parse accordingly
            if ontology_content.startswith("[Term]"):
                # OBO format
                phenotypes = self._parse_obo_format(ontology_content)
            elif ontology_content.startswith("<?xml"):
                # OWL/XML format (more complex)
                phenotypes = self._parse_owl_format(ontology_content)
            # Try to detect format or default to OBO
            elif "format-version:" in ontology_content:
                phenotypes = self._parse_obo_format(ontology_content)
            else:
                phenotypes = self._parse_simple_format(ontology_content)

        except Exception as e:  # noqa: BLE001
            # Return error record
            phenotypes = [
                {
                    "parsing_error": str(e),
                    "hpo_id": "ERROR",
                    "name": "Parsing Error",
                    "definition": f"Failed to parse HPO ontology: {e!s}",
                    "raw_content": ontology_content[
                        :1000
                    ],  # First 1000 chars for debugging
                },
            ]

        return phenotypes

    def _parse_obo_format(self, content: str) -> list[RawRecord]:
        phenotypes: list[RawRecord] = []
        term_blocks = content.split("[Term]")

        def new_term_dict() -> dict[str, str | list[str]]:
            return {}

        for block in term_blocks:
            block_content = block.strip()
            if not block_content:
                continue

            current_term = new_term_dict()
            for raw_line in block_content.splitlines():
                line = raw_line.strip()
                if not line or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                existing = current_term.get(key)
                if existing is None:
                    current_term[key] = value
                elif isinstance(existing, list):
                    existing.append(value)
                else:
                    current_term[key] = [existing, value]

            if current_term and "id" in current_term:
                phenotypes.append(self._normalize_obo_term(current_term))

        return phenotypes

    def _normalize_obo_term(
        self,
        term: dict[str, str | list[str]],
    ) -> RawRecord:
        # Ensure lists for multi-value fields
        for field in ["is_a", "synonym", "xref"]:
            value = term.get(field)
            if value is None:
                continue
            if isinstance(value, list):
                continue
            if isinstance(value, str):
                term[field] = [value]

        is_obsolete_raw = term.get("is_obsolete", "false")
        if isinstance(is_obsolete_raw, list):
            is_obsolete_text = " ".join(is_obsolete_raw)
        else:
            is_obsolete_text = str(is_obsolete_raw)

        return {
            "hpo_id": term.get("id", ""),
            "name": term.get("name", ""),
            "definition": term.get("def", ""),
            "synonyms": term.get("synonym", []),
            "parents": term.get("is_a", []),
            "xrefs": term.get("xref", []),
            "is_obsolete": is_obsolete_text.lower() == "true",
            "namespace": term.get("namespace", "HP"),
            "comment": term.get("comment", ""),
            "source": "hpo",
            "format": "obo",
        }

    def _parse_owl_format(self, content: str) -> list[RawRecord]:
        # Simplified OWL parsing - in production would use proper OWL library
        # This is a basic implementation that extracts basic information

        phenotypes: list[RawRecord] = []
        try:
            # Very basic XML parsing for OWL format
            # In production, would use libraries like owlready2 or rdflib
            root = ElementTree.fromstring(content)

            # Extract Class elements (phenotype terms)
            for class_elem in root.findall(".//{http://www.w3.org/2002/07/owl#}Class"):
                phenotype = self._parse_owl_class(class_elem)
                if phenotype:
                    phenotypes.append(phenotype)

        except Exception:  # noqa: BLE001
            # Fallback error record
            phenotypes = [
                {
                    "parsing_error": "Failed to parse OWL format",
                    "hpo_id": "ERROR",
                    "name": "OWL Parsing Error",
                    "source": "hpo",
                    "format": "owl",
                },
            ]

        return phenotypes

    def _parse_owl_class(self, class_elem: Element) -> RawRecord | None:
        # Simplified OWL class parsing
        # In production would be much more comprehensive
        try:
            hpo_id = None
            name = None

            # Look for ID and label
            for child in class_elem:
                if child.tag.endswith("id"):
                    hpo_id = child.text
                elif child.tag.endswith("label"):
                    name = child.text

            if hpo_id and name:
                return {
                    "hpo_id": hpo_id,
                    "name": name,
                    "definition": "",  # Would need more complex parsing
                    "synonyms": [],
                    "parents": [],
                    "xrefs": [],
                    "is_obsolete": False,
                    "source": "hpo",
                    "format": "owl",
                }

        except Exception:
            logger.exception("Failed to parse OWL class")

        return None

    def _parse_simple_format(self, content: str) -> list[RawRecord]:
        return [
            {
                "parsing_error": "Unrecognized ontology format",
                "hpo_id": "ERROR",
                "name": "Format Error",
                "definition": "Could not determine ontology file format",
                "source": "hpo",
                "raw_content": content[:500],
            },
        ]

    def _filter_med13_relevant_terms(
        self,
        phenotypes: list[RawRecord],
    ) -> list[RawRecord]:
        # MED13-related phenotypes based on known associations
        med13_keywords: list[str] = [
            "intellectual disability",
            "developmental delay",
            "autism",
            "schizophrenia",
            "epilepsy",
            "microcephaly",
            "growth retardation",
            "facial dysmorphism",
            "heart defect",
            "kidney anomaly",
        ]

        relevant_terms: list[RawRecord] = []
        for phenotype in phenotypes:
            name_raw = phenotype.get("name", "")
            name = (
                name_raw.lower() if isinstance(name_raw, str) else str(name_raw).lower()
            )

            definition_raw = phenotype.get("definition", "")
            if isinstance(definition_raw, list):
                definition_text = " ".join(str(item) for item in definition_raw)
            else:
                definition_text = str(definition_raw)
            definition = definition_text.lower()

            # Check if any MED13-related keywords are present
            is_relevant = any(
                keyword in name or keyword in definition for keyword in med13_keywords
            )

            if is_relevant:
                phenotype["med13_relevance"] = {
                    "is_relevant": True,
                    "matched_keywords": [
                        kw for kw in med13_keywords if kw in name or kw in definition
                    ],
                }
                relevant_terms.append(phenotype)

        return relevant_terms

    async def fetch_phenotype_hierarchy(
        self,
        root_term: str = "HP:0000118",
    ) -> JSONObject:
        all_phenotypes = await self.fetch_data()
        if not all_phenotypes:
            return {"error": "No phenotypes loaded"}

        # Build hierarchy
        return self._build_phenotype_hierarchy(all_phenotypes, root_term)

    def _build_phenotype_hierarchy(  # noqa: C901
        self,
        phenotypes: list[RawRecord],
        root_id: str,
    ) -> JSONObject:
        # Create lookup by ID
        phenotype_dict: dict[str, RawRecord] = {}
        for phenotype in phenotypes:
            hpo_id = phenotype.get("hpo_id")
            if isinstance(hpo_id, str):
                phenotype_dict[hpo_id] = phenotype

        # Build parent-child relationships

        def build_subtree(term_id: str, visited: set[str]) -> JSONObject:
            if term_id in visited:
                return {"error": "Circular reference", "hpo_id": term_id}

            visited.add(term_id)
            term = phenotype_dict.get(term_id)

            if not term:
                return {"error": "Term not found", "hpo_id": term_id}

            # Get children (terms that have this as parent)
            children: list[JSONObject] = []
            for pid, pterm in phenotype_dict.items():
                if pid == term_id:
                    continue
                parents_raw = pterm.get("parents", [])
                if isinstance(parents_raw, str):
                    parents = [parents_raw]
                elif isinstance(parents_raw, list):
                    parents = [
                        parent for parent in parents_raw if isinstance(parent, str)
                    ]
                else:
                    parents = []

                if term_id in parents:
                    children.append(build_subtree(pid, visited.copy()))

            return {
                "hpo_id": term_id,
                "name": term.get("name", ""),
                "definition": term.get("definition", ""),
                "children": children,
                "synonyms": term.get("synonyms", []),
            }

        visited: set[str] = set()
        return build_subtree(root_id, visited)

    async def search_phenotypes(
        self,
        query: str,
        **kwargs: JSONValue,
    ) -> list[RawRecord]:
        all_phenotypes = await self.fetch_data(**kwargs)

        query_lower = query.lower()
        matches: list[RawRecord] = []

        for phenotype in all_phenotypes:
            name_value = phenotype.get("name", "")
            name = (
                name_value.lower()
                if isinstance(name_value, str)
                else str(name_value).lower()
            )
            definition_value = phenotype.get("definition", "")
            definition = (
                definition_value.lower()
                if isinstance(definition_value, str)
                else str(definition_value).lower()
            )

            if query_lower in name or query_lower in definition:
                phenotype["search_score"] = (
                    2
                    if query_lower in name
                    else 0 + 1 if query_lower in definition else 0
                )
                matches.append(phenotype)

        # Sort by relevance score
        def _match_score(value: RawRecord) -> int:
            score_value = value.get("search_score")
            return int(score_value) if isinstance(score_value, int | float) else 0

        matches.sort(key=_match_score, reverse=True)
        return matches
