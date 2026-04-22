"""
Value objects for protein structural data.

These objects encapsulate structural biology concepts required for
mechanism modeling, such as protein domains, interfaces, and 3D coordinates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Coordinates3D(BaseModel):
    """3D coordinates for a protein structure (e.g. from AlphaFold/PDB)."""

    x: float
    y: float
    z: float
    confidence: float | None = None  # e.g. pLDDT score

    model_config = ConfigDict(frozen=True)


class ProteinDomain(BaseModel):
    """
    Represents a functional or structural domain within a protein.

    Examples: "Cyclin C binding interface", "IDR", "Kinase domain".
    """

    name: str
    source_id: str | None = None  # e.g. InterPro ID, Pfam ID
    start_residue: int = Field(ge=1)
    end_residue: int = Field(ge=1)
    domain_type: Literal[
        "structural",
        "functional",
        "binding_site",
        "disordered",
    ] = "structural"
    description: str | None = None
    coordinates: list[Coordinates3D] | None = None  # Representative coordinates

    model_config = ConfigDict(frozen=True)

    def contains_residue(self, residue_position: int) -> bool:
        """Check if a residue position falls within this domain."""
        return self.start_residue <= residue_position <= self.end_residue
