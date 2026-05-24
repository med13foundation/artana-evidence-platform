#!/usr/bin/env python3
"""Build a configurable Mediator-complex ClinVar variant registry."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Final

_GENE_SETS: Final[dict[str, tuple[str, ...]]] = {
    "cdk8-module": ("MED12", "MED13", "MED13L"),
    "cardiac-septal": ("MED6", "MED11", "MED18", "MED23", "MED25"),
}


def _add_services_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    services_root = repo_root / "services"
    for path in (repo_root, services_root):
        resolved = str(path)
        if resolved not in sys.path:
            sys.path.append(resolved)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch strict ClinVar records and write a Mediator-complex variant "
            "registry CSV with convergence-node and model-score columns."
        ),
    )
    parser.add_argument(
        "--gene-set",
        action="append",
        choices=tuple(_GENE_SETS),
        default=[],
        help="Named gene set to include. Defaults to cdk8-module when no genes are set.",
    )
    parser.add_argument(
        "--gene",
        action="append",
        default=[],
        help="Additional gene symbol to include. Can be repeated.",
    )
    parser.add_argument(
        "--node",
        default="",
        help="Convergence-node label to apply to all selected genes.",
    )
    parser.add_argument(
        "--node-map",
        action="append",
        default=[],
        metavar="GENE=NODE",
        help="Per-gene node override, for example MED23=cardiac-septal.",
    )
    parser.add_argument(
        "--clinical-significance",
        action="append",
        default=[],
        help="Optional ClinVar clinical-significance filter. Can be repeated.",
    )
    parser.add_argument(
        "--max-results-per-gene",
        type=int,
        default=1000,
        help="Maximum ClinVar records to fetch for each gene.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV output path. Defaults to stdout.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> str:
    _add_services_to_path()
    from artana_evidence_api.research_init.mediator_variant_registry import (
        MediatorVariantRegistryConfig,
        fetch_registry_rows,
        normalize_gene_symbols,
        registry_rows_to_csv,
    )
    from artana_evidence_api.source_enrichment_bridges import build_clinvar_gateway

    selected_gene_sets = args.gene_set or ["cdk8-module"]
    genes = [
        gene
        for gene_set in selected_gene_sets
        for gene in _GENE_SETS.get(str(gene_set), ())
    ]
    genes.extend(str(gene) for gene in args.gene)
    normalized_genes = normalize_gene_symbols(genes)
    node_by_gene = _node_by_gene(
        genes=normalized_genes,
        default_node=str(args.node),
        node_map_values=[str(value) for value in args.node_map],
    )
    gateway = build_clinvar_gateway()
    rows = await fetch_registry_rows(
        config=MediatorVariantRegistryConfig(
            genes=normalized_genes,
            node_by_gene=node_by_gene,
        ),
        gateway=gateway,
        max_results_per_gene=int(args.max_results_per_gene),
        clinical_significance=tuple(str(value) for value in args.clinical_significance),
    )
    return registry_rows_to_csv(rows)


def _node_by_gene(
    *,
    genes: tuple[str, ...],
    default_node: str,
    node_map_values: list[str],
) -> dict[str, str]:
    node_by_gene = {gene: default_node for gene in genes if default_node}
    for value in node_map_values:
        gene, separator, node = value.partition("=")
        if not separator or not gene.strip() or not node.strip():
            msg = f"Invalid --node-map value: {value!r}; expected GENE=NODE"
            raise SystemExit(msg)
        node_by_gene[gene.strip().upper()] = node.strip()
    return node_by_gene


def main() -> None:
    args = _parse_args()
    csv_payload = asyncio.run(_run(args))
    if args.output is None:
        print(csv_payload, end="")  # noqa: T201
        return
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(csv_payload, encoding="utf-8")
    print(f"Wrote Mediator variant registry: {output}")  # noqa: T201


if __name__ == "__main__":
    main()
