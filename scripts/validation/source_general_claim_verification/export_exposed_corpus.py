#!/usr/bin/env python3
"""Export the already exposed 31-scope corpus into a self-contained artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.validation.source_general_claim_verification.contracts import (
    CorpusArtifact,
    ExactSpan,
    ExposedScope,
    SourceDocument,
)
from scripts.validation.source_general_claim_verification.corpus import validate_corpus

EXPOSED_EXPERIMENT_ROOT = Path(
    "/Users/alvaro/.codex/artana-evidence-experiments/tg04",
)


def export_corpus(output: Path) -> CorpusArtifact:
    sys.path.insert(0, str(EXPOSED_EXPERIMENT_ROOT))
    from recall_only_discovery_comparison_v1.corpus import (  # type: ignore[import-not-found]
        load_corpus,
    )

    sources, scopes = load_corpus()
    artifact = CorpusArtifact(
        schema_version="source_general_claim_verification.corpus.v1",
        exposed_only=True,
        sources=tuple(
            SourceDocument(
                source_id=source.label,
                source_sha256=source.source_sha256,
                text=source.source,
            )
            for source in sources
        ),
        scopes=tuple(
            ExposedScope(
                scope_id=scope.scope_id,
                source_id=scope.source_label,
                source_sha256=next(
                    source.source_sha256
                    for source in sources
                    if source.label == scope.source_label
                ),
                scope=ExactSpan(
                    start=scope.passage_start,
                    end=scope.passage_end,
                    text=scope.passage,
                ),
            )
            for scope in scopes
        ),
    )
    validate_corpus(artifact)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export_corpus(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
