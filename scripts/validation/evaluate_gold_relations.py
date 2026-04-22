"""Evaluate extracted relations against a gold standard with exact and semantic scoring."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

Triplet = tuple[str, str, str]
SemanticKey = tuple[str, str, str]
_TRIPLET_LENGTH = 3

PREDICATE_FAMILIES: dict[str, set[str]] = {
    "ACTIVATES": {
        "ACTIVATES",
        "UPREGULATES",
        "POSITIVELY_REGULATES",
        "INDUCES",
        "STIMULATES",
    },
    "INHIBITS": {
        "INHIBITS",
        "DOWNREGULATES",
        "NEGATIVELY_REGULATES",
        "REPRESSES",
        "SUPPRESSES",
        "REDUCES",
    },
    "ASSOCIATED_WITH": {"ASSOCIATED_WITH", "LINKS_TO", "LINKED_TO", "CORRELATED_WITH"},
    "INTERACTS_WITH": {"INTERACTS_WITH", "PHYSICALLY_INTERACTS_WITH", "BINDS_TO"},
    "PART_OF": {"PART_OF", "SUBUNIT_OF", "COMPONENT_OF"},
    "REGULATES": {"REGULATES"},
}

PREDICATE_CANONICAL_BY_VARIANT: dict[str, str] = {}
for canonical, variants in PREDICATE_FAMILIES.items():
    for variant in variants:
        PREDICATE_CANONICAL_BY_VARIANT[variant] = canonical


@dataclass(frozen=True)
class Score:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def _metric(tp: int, fp: int, fn: int) -> Score:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    )
    return Score(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def _normalize_entity(value: str, aliases: dict[str, str]) -> str:
    compact = re.sub(r"[^A-Z0-9]+", "", _normalize_whitespace(value))
    return aliases.get(compact, compact)


def _normalize_predicate(value: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "_", _normalize_whitespace(value)).strip("_")
    if token.startswith("DERIVED_"):
        suffix = token.removeprefix("DERIVED_")
        mapped = PREDICATE_CANONICAL_BY_VARIANT.get(suffix, suffix)
        return f"DERIVED_{mapped}"
    return PREDICATE_CANONICAL_BY_VARIANT.get(token, token)


def _to_exact_key(triple: Triplet) -> Triplet:
    source, predicate, target = triple
    return (
        _normalize_whitespace(source),
        _normalize_whitespace(predicate),
        _normalize_whitespace(target),
    )


def _to_semantic_key(triple: Triplet, aliases: dict[str, str]) -> SemanticKey:
    source, predicate, target = triple
    return (
        _normalize_entity(source, aliases),
        _normalize_predicate(predicate),
        _normalize_entity(target, aliases),
    )


def _parse_triplet(item: object) -> Triplet | None:
    if isinstance(item, list | tuple) and len(item) >= _TRIPLET_LENGTH:
        return (str(item[0]), str(item[1]), str(item[2]))
    if isinstance(item, dict):
        source = item.get("source")
        predicate = item.get("predicate")
        target = item.get("target")
        if source is None or predicate is None or target is None:
            return None
        return (str(source), str(predicate), str(target))
    return None


def _unsupported_format_error(scope: str, path: Path) -> TypeError:
    message = f"Unsupported {scope} format in {path}"
    return TypeError(message)


def _load_relations_from_result(path: Path) -> list[Triplet]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        relations_obj = payload.get("actual_relations", [])
    elif isinstance(payload, list):
        relations_obj = payload
    else:
        scope = "result"
        raise _unsupported_format_error(scope, path)

    triples: list[Triplet] = []
    for item in relations_obj:
        parsed = _parse_triplet(item)
        if parsed is not None:
            triples.append(parsed)
    return triples


def _load_relations_from_gold(path: Path) -> list[Triplet]:
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        combined: list[object] = []
        combined.extend(payload.get("fact_edges", []))
        combined.extend(payload.get("derived_edges", []))
    elif isinstance(payload, list):
        combined = payload
    else:
        scope = "gold"
        raise _unsupported_format_error(scope, path)

    triples: list[Triplet] = []
    for item in combined:
        parsed = _parse_triplet(item)
        if parsed is not None:
            triples.append(parsed)
    return triples


def _load_aliases(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        message = f"Alias file must be a JSON object: {path}"
        raise TypeError(message)

    aliases: dict[str, str] = {}
    for raw_key, raw_value in payload.items():
        key = _normalize_entity(str(raw_key), {})
        value = _normalize_entity(str(raw_value), {})
        aliases[key] = value
    return aliases


def _unique_keys(
    triples: list[Triplet],
    transform: Callable[[Triplet], Triplet | SemanticKey],
) -> list[Triplet | SemanticKey]:
    seen: set[Triplet | SemanticKey] = set()
    ordered: list[Triplet | SemanticKey] = []
    for triple in triples:
        key = transform(triple)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _format_triple(triple: Triplet | SemanticKey) -> str:
    source, predicate, target = triple
    return f"({source}) -[{predicate}]-> ({target})"


def _append_relation_section(
    lines: list[str],
    *,
    heading: str,
    triples: list[Triplet | SemanticKey],
) -> None:
    lines.append(heading)
    if triples:
        lines.extend(f"- `{_format_triple(triple)}`" for triple in triples)
    else:
        lines.append("- none")
    lines.append("")


def _append_score_section(
    lines: list[str],
    *,
    heading: str,
    score: dict[str, float | int],
    gain: int | None = None,
) -> None:
    lines.append(heading)
    lines.append(f"- TP: {score['tp']}")
    lines.append(f"- FP: {score['fp']}")
    lines.append(f"- FN: {score['fn']}")
    lines.append(f"- Precision: {score['precision']:.4f}")
    lines.append(f"- Recall: {score['recall']:.4f}")
    lines.append(f"- F1: {score['f1']:.4f}")
    if gain is not None:
        lines.append(f"- Semantic-only TP gain vs exact: {gain}")
    lines.append("")


def evaluate(
    predicted_triples: list[Triplet],
    gold_triples: list[Triplet],
    aliases: dict[str, str],
) -> dict[str, object]:
    predicted_exact = _unique_keys(predicted_triples, _to_exact_key)
    gold_exact = _unique_keys(gold_triples, _to_exact_key)
    predicted_exact_set = set(predicted_exact)
    gold_exact_set = set(gold_exact)

    exact_match = sorted(predicted_exact_set & gold_exact_set)
    exact_pred_not_gold = sorted(predicted_exact_set - gold_exact_set)
    exact_gold_not_pred = sorted(gold_exact_set - predicted_exact_set)
    exact_score = _metric(
        tp=len(exact_match),
        fp=len(exact_pred_not_gold),
        fn=len(exact_gold_not_pred),
    )

    predicted_semantic = _unique_keys(
        predicted_triples,
        lambda triple: _to_semantic_key(triple, aliases),
    )
    gold_semantic = _unique_keys(
        gold_triples,
        lambda triple: _to_semantic_key(triple, aliases),
    )
    predicted_semantic_set = set(predicted_semantic)
    gold_semantic_set = set(gold_semantic)

    semantic_match = sorted(predicted_semantic_set & gold_semantic_set)
    semantic_pred_not_gold = sorted(predicted_semantic_set - gold_semantic_set)
    semantic_gold_not_pred = sorted(gold_semantic_set - predicted_semantic_set)
    semantic_score = _metric(
        tp=len(semantic_match),
        fp=len(semantic_pred_not_gold),
        fn=len(semantic_gold_not_pred),
    )

    semantic_only_gain = len(semantic_match) - len(exact_match)
    return {
        "counts": {
            "predicted_unique_exact": len(predicted_exact_set),
            "gold_unique_exact": len(gold_exact_set),
            "predicted_unique_semantic": len(predicted_semantic_set),
            "gold_unique_semantic": len(gold_semantic_set),
        },
        "exact": {
            "score": exact_score.__dict__,
            "matched": exact_match,
            "predicted_not_in_gold": exact_pred_not_gold,
            "gold_not_predicted": exact_gold_not_pred,
        },
        "semantic": {
            "score": semantic_score.__dict__,
            "matched": semantic_match,
            "predicted_not_in_gold": semantic_pred_not_gold,
            "gold_not_predicted": semantic_gold_not_pred,
            "semantic_only_gain_vs_exact_tp": semantic_only_gain,
            "notes": [
                "Semantic match normalizes entities (format/aliases) and predicate families.",
                "Directionality remains strict (source->target order must match).",
            ],
        },
    }


def build_markdown_report(label: str, evaluation: dict[str, object]) -> str:
    counts = evaluation["counts"]
    exact = evaluation["exact"]
    semantic = evaluation["semantic"]
    exact_score = exact["score"]
    semantic_score = semantic["score"]

    lines: list[str] = []
    lines.append(f"# Validation report: {label}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Predicted unique (exact): {counts['predicted_unique_exact']}")
    lines.append(f"- Gold unique (exact): {counts['gold_unique_exact']}")
    lines.append(
        f"- Predicted unique (semantic): {counts['predicted_unique_semantic']}",
    )
    lines.append(f"- Gold unique (semantic): {counts['gold_unique_semantic']}")
    lines.append("")
    _append_score_section(lines, heading="## Exact score", score=exact_score)
    _append_score_section(
        lines,
        heading="## Semantic score",
        score=semantic_score,
        gain=semantic["semantic_only_gain_vs_exact_tp"],
    )
    _append_relation_section(
        lines,
        heading="## Exact: matched",
        triples=exact["matched"],
    )
    _append_relation_section(
        lines,
        heading="## Exact: predicted not in gold",
        triples=exact["predicted_not_in_gold"],
    )
    _append_relation_section(
        lines,
        heading="## Exact: gold not predicted",
        triples=exact["gold_not_predicted"],
    )
    _append_relation_section(
        lines,
        heading="## Semantic: matched",
        triples=semantic["matched"],
    )
    _append_relation_section(
        lines,
        heading="## Semantic: predicted not in gold",
        triples=semantic["predicted_not_in_gold"],
    )
    _append_relation_section(
        lines,
        heading="## Semantic: gold not predicted",
        triples=semantic["gold_not_predicted"],
    )

    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare extracted relations against gold using exact and semantic scoring.",
    )
    parser.add_argument(
        "--result",
        type=Path,
        required=True,
        help="Path to run result JSON.",
    )
    parser.add_argument("--gold", type=Path, required=True, help="Path to gold JSON.")
    parser.add_argument(
        "--aliases",
        type=Path,
        default=None,
        help="Optional JSON file mapping entity aliases to canonical entity IDs.",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="validation",
        help="Report label.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional output JSON path for computed metrics.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional output markdown path for human-readable report.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    aliases = _load_aliases(args.aliases)
    predicted = _load_relations_from_result(args.result)
    gold = _load_relations_from_gold(args.gold)

    evaluation = evaluate(predicted, gold, aliases)
    exact = evaluation["exact"]["score"]
    semantic = evaluation["semantic"]["score"]

    print(
        f"[{args.label}] "
        f"exact_f1={exact['f1']:.4f} (tp={exact['tp']} fp={exact['fp']} fn={exact['fn']}) | "
        f"semantic_f1={semantic['f1']:.4f} (tp={semantic['tp']} fp={semantic['fp']} fn={semantic['fn']})",
    )

    if args.output_json is not None:
        args.output_json.write_text(json.dumps(evaluation, indent=2) + "\n")
        print(f"Wrote JSON report: {args.output_json}")

    if args.output_md is not None:
        markdown = build_markdown_report(args.label, evaluation)
        args.output_md.write_text(markdown)
        print(f"Wrote markdown report: {args.output_md}")


if __name__ == "__main__":
    main()
