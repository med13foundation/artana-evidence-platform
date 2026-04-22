"""Utility helpers to generate deterministic sample data for tests."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import ClassVar

from src.type_definitions.common import JSONObject


@dataclass
class SyntheticDataset:
    data: list[JSONObject]


class TestDataGenerator:
    __test__: ClassVar[bool] = False

    def __init__(self, seed: int | None = None) -> None:
        # Use a deterministic PRNG when a seed is provided; otherwise prefer
        # SystemRandom for better randomness in ad-hoc generation.
        self._random: random.Random
        if seed is None:
            self._random = (
                random.SystemRandom()
            )  # nosec B311 - test utility, not crypto
        else:
            # Deterministic PRNG for tests only; not used for security.
            self._random = random.Random(seed)  # noqa: S311  # nosec B311

    def generate_gene_dataset(self, count: int, quality: str) -> SyntheticDataset:
        records: list[JSONObject] = []
        for index in range(count):
            if quality == "poor":
                record: JSONObject = {
                    "symbol": f"gene{index}",  # lower-case to trigger validation error
                    "source": "test",
                    "confidence_score": -0.5,
                }
            else:
                record = {
                    "symbol": f"GENE{index}",
                    "source": "test",
                    "confidence_score": 0.85,
                }
                if quality in {"good", "mixed"}:
                    record["hgnc_id"] = f"HGNC:{1000 + index}"
            records.append(record)

        if quality == "mixed" and records:
            records[0]["symbol"] = "invalid"
            records[0]["confidence_score"] = 1.5

        return SyntheticDataset(data=records)


__all__ = ["SyntheticDataset", "TestDataGenerator"]
