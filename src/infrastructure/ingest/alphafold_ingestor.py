"""AlphaFold DB API client for fetching protein structure predictions.

Uses the AlphaFold Protein Structure Database REST API (open access,
no authentication required) at https://alphafold.ebi.ac.uk/api/.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.infrastructure.ingest.base_ingestor import BaseIngestor

logger = logging.getLogger(__name__)

_ALPHAFOLD_BASE_URL = "https://alphafold.ebi.ac.uk/api"
_ALPHAFOLD_RATE_LIMIT = 60  # requests per minute (generous, EBI is lenient)
_ALPHAFOLD_TIMEOUT = 30


@dataclass(frozen=True)
class AlphaFoldPrediction:
    """One AlphaFold structure prediction."""

    uniprot_id: str
    protein_name: str
    organism: str
    gene_name: str
    model_url: str
    pdb_url: str
    confidence_avg: float
    domains: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class AlphaFoldFetchPage:
    """Result of an AlphaFold API fetch."""

    predictions: list[AlphaFoldPrediction] = field(default_factory=list)
    total: int = 0


class AlphaFoldIngestor(BaseIngestor):
    """Async HTTP client for the AlphaFold DB API."""

    def __init__(self) -> None:
        super().__init__(
            source_name="alphafold",
            base_url=_ALPHAFOLD_BASE_URL,
            requests_per_minute=_ALPHAFOLD_RATE_LIMIT,
            timeout_seconds=_ALPHAFOLD_TIMEOUT,
        )

    async def fetch_data(self, **kwargs: object) -> list[dict[str, object]]:  # type: ignore[override]
        """Fetch AlphaFold records (BaseIngestor abstract method)."""
        uniprot_id = str(kwargs.get("uniprot_id", ""))
        if not uniprot_id:
            return []
        prediction = await self.fetch_prediction(uniprot_id)
        if prediction is None:
            return []
        return [
            {
                "uniprot_id": prediction.uniprot_id,
                "protein_name": prediction.protein_name,
            },
        ]

    async def fetch_prediction(
        self,
        uniprot_id: str,
    ) -> AlphaFoldPrediction | None:
        """Fetch the AlphaFold prediction for a UniProt accession."""
        if not uniprot_id.strip():
            return None

        try:
            response = await self._make_request(
                "GET",
                f"prediction/{uniprot_id.strip()}",
            )
            data = response.json()
        except Exception:  # noqa: BLE001
            logger.warning(
                "AlphaFold API request failed for %s",
                uniprot_id,
                exc_info=True,
            )
            return None

        return self._parse_prediction(data, uniprot_id)

    async def fetch_predictions_batch(
        self,
        uniprot_ids: list[str],
    ) -> AlphaFoldFetchPage:
        """Fetch predictions for multiple UniProt IDs."""
        predictions: list[AlphaFoldPrediction] = []
        for uid in uniprot_ids:
            prediction = await self.fetch_prediction(uid)
            if prediction is not None:
                predictions.append(prediction)
        return AlphaFoldFetchPage(
            predictions=predictions,
            total=len(predictions),
        )

    @staticmethod
    def _parse_prediction(
        data: object,
        uniprot_id: str,
    ) -> AlphaFoldPrediction | None:
        """Parse AlphaFold API response into a structured prediction."""
        # AlphaFold API returns a list of entries for each UniProt ID
        entries = (
            data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        )
        if not entries:
            return None

        entry = entries[0] if isinstance(entries[0], dict) else {}
        if not entry:
            return None

        # Extract model and PDB URLs
        model_url = str(entry.get("cifUrl", entry.get("pdbUrl", "")))
        pdb_url = str(entry.get("pdbUrl", ""))

        # Extract confidence (pLDDT) if available
        confidence_avg = 0.0
        plddt = entry.get("confidenceAvgLocalScore") or entry.get("globalMetricValue")
        if isinstance(plddt, int | float):
            confidence_avg = float(plddt)

        # Parse domain annotations if present
        domains: list[dict[str, object]] = []
        domain_data = entry.get("domains", entry.get("annotations", []))
        if isinstance(domain_data, list):
            for d in domain_data:
                if not isinstance(d, dict):
                    continue
                domains.append(
                    {
                        "name": str(d.get("name", d.get("label", "unknown"))),
                        "start": int(d.get("start") or d.get("begin") or 0),
                        "end": int(d.get("end") or 0),
                        "confidence": float(
                            d.get("confidence") or d.get("plddt") or 0.0,
                        ),
                    },
                )

        return AlphaFoldPrediction(
            uniprot_id=uniprot_id.strip(),
            protein_name=str(entry.get("uniprotDescription", entry.get("entryId", ""))),
            organism=str(entry.get("organismScientificName", "Unknown")),
            gene_name=str(entry.get("gene", "")),
            model_url=model_url,
            pdb_url=pdb_url,
            confidence_avg=confidence_avg,
            domains=domains,
        )


__all__ = ["AlphaFoldFetchPage", "AlphaFoldIngestor", "AlphaFoldPrediction"]
