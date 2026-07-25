"""Measure run-to-run variance of the sealed V17 exposed panel.

Every version in the V6->V18 series drew exactly one sample per case, and the
only replicate study this repository ever ran (PR6, 2026-07-13) returned
`repeatability proof: FAIL` on this same model family.  So the series' central
claims -- V16 failed, V17 fixed the comparison, V17 still failed uncertainty --
rest on single observations from a model with unmeasured variance.

This harness replays the byte-identical sealed V17 prompt N times per case and
reports how often each verdict reproduces.  It changes no prompt, no evaluator,
and no sealed artifact: prompts are verified against the recorded
`provider_input_sha256` before any call, and all output goes to a scratch
directory outside the repository.

If a verdict flips across replicates of an identical prompt, the version series
measured sampling noise and no version-to-version comparison in it is sound.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    DEFAULT_PATHS,
    MODEL,
    REASONING_EFFORT,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    evaluate_v17_case,
    failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.prompt import (
    ordered_cases,
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.provider import (
    execute_case,
)

EXECUTED_CASES = (
    "generalization-comparison-canary",
    "generalization-drug-sensitivity",
    "generalization-uncertainty",
)
SEALED_VERDICT = {
    "generalization-comparison-canary": "PASS",
    "generalization-drug-sensitivity": "PASS",
    "generalization-uncertainty": "FAIL",
}


def sealed_prompt_digests() -> dict[str, str]:
    """Read the provider-input digest the sealed V17 run recorded per case."""

    digests: dict[str, str] = {}
    for case_id in EXECUTED_CASES:
        path = Path(
            "docs/validation/evaluations/"
            f"2026-07-24-staged-generalization-v17-exposed-run-v1-{case_id}"
            "-evaluation.json",
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        digests[case_id] = record["custody"]["provider_input_sha256"]
    return digests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--max-cost-usd", type=float, default=2.00)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not arguments.dry_run:
        print("OPENAI_API_KEY is absent", file=sys.stderr)
        return 1

    import hashlib

    sealed = sealed_prompt_digests()
    prompts: dict[str, str] = {}
    for case_id in EXECUTED_CASES:
        value = provider_input(case_id)
        digest = hashlib.sha256(value.encode()).hexdigest()
        if digest != sealed[case_id]:
            print(f"prompt drift on {case_id}: refusing to run", file=sys.stderr)
            return 1
        prompts[case_id] = value
    print(f"all {len(EXECUTED_CASES)} prompts match the sealed V17 digests")

    if arguments.dry_run:
        print(f"dry run: would issue {arguments.replicates * len(EXECUTED_CASES)} calls")
        return 0

    cases = {case.case_id: case for case in ordered_cases()}
    policy = verify_v13_frozen_policy(
        DEFAULT_PATHS.v16.v15.v14.v13.grading,
        cases=tuple(cases.values()),
    )
    contract = load_contract(
        DEFAULT_PATHS.v16.v15.v14.v13.nested_two_lane_contract,
        adjudication_path=DEFAULT_PATHS.v16.v15.v14.v13.nested_adjudication,
        v12_contract_path=DEFAULT_PATHS.v16.v15.v14.v13.v12_drug_two_lane_contract,
    )

    arguments.scratch.mkdir(parents=True, exist_ok=True)
    observations: list[dict[str, object]] = []
    spent = 0.0

    for replicate in range(arguments.replicates):
        for case_id in EXECUTED_CASES:
            if spent >= arguments.max_cost_usd:
                print(f"cost cap {arguments.max_cost_usd} reached; stopping")
                return _report(observations, arguments, spent)
            stem = arguments.scratch / f"r{replicate:02d}-{case_id}"
            paths = CaseExecutionPaths(
                attempt=Path(f"{stem}-attempt.json"),
                bundle=Path(f"{stem}-custody.json"),
                receipt=Path(f"{stem}.json"),
                raw_output=Path(f"{stem}-raw.json"),
                evaluation=Path(f"{stem}-evaluation.json"),
            )
            from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
                reserve_attempt,
            )

            reserve_attempt(
                paths.attempt,
                stage=f"NOISE_FLOOR_V17:{case_id}",
                provider_input=prompts[case_id],
                preregistration_sha256="0" * 64,
            )
            try:
                execution = execute_case(
                    api_key=api_key,
                    case_id=case_id,
                    provider_input=prompts[case_id],
                    preregistration_sha256="0" * 64,
                    paths=paths,
                )
            except Exception as error:  # noqa: BLE001 - record and continue
                observations.append(
                    {
                        "replicate": replicate,
                        "case_id": case_id,
                        "verdict": "ERROR",
                        "detail": f"{type(error).__name__}: {error}",
                    },
                )
                print(f"  r{replicate:02d} {case_id:34} ERROR {type(error).__name__}")
                continue

            evaluation = evaluate_v17_case(
                cases[case_id],
                execution.extraction,
                case_policy(policy, case_id),
                contract,
                v14_consensus_path=DEFAULT_PATHS.v16.v15.v14.consensus,
            )
            verdict = evaluation.metrics.source_semantic_status
            usage = execution.receipt.get("usage") or {}
            cost = float(usage.get("cost_usd") or 0.0)
            spent += cost
            observations.append(
                {
                    "replicate": replicate,
                    "case_id": case_id,
                    "verdict": verdict,
                    "passed": evaluation.metrics.passed,
                    "failure": failure_classification(evaluation),
                    "failure_reasons": list(evaluation.metrics.failure_reasons),
                    "response_id": execution.receipt.get("identity", {}).get(
                        "response_id",
                    ),
                    "cost_usd": cost,
                },
            )
            flag = "" if verdict == SEALED_VERDICT[case_id] else "   <-- FLIPPED"
            print(
                f"  r{replicate:02d} {case_id:34} {verdict:5} "
                f"${cost:.4f}  cum ${spent:.4f}{flag}",
            )

    return _report(observations, arguments, spent)


def _report(
    observations: list[dict[str, object]],
    arguments: argparse.Namespace,
    spent: float,
) -> int:
    print("\n" + "=" * 78)
    print("NOISE FLOOR -- sealed V17 prompt, replayed byte-identically")
    print("=" * 78)
    any_flip = False
    summary: dict[str, object] = {}
    for case_id in EXECUTED_CASES:
        verdicts = [o["verdict"] for o in observations if o["case_id"] == case_id]
        counts = Counter(verdicts)
        sealed = SEALED_VERDICT[case_id]
        agree = counts.get(sealed, 0)
        total = len(verdicts)
        stable = len(set(verdicts)) <= 1
        any_flip = any_flip or not stable
        summary[case_id] = {
            "sealed": sealed,
            "counts": dict(counts),
            "reproduced": f"{agree}/{total}",
            "stable": stable,
        }
        mark = "STABLE" if stable else "UNSTABLE"
        print(
            f"  {case_id:34} sealed={sealed:5} "
            f"observed={dict(counts)}  reproduced {agree}/{total}  {mark}",
        )
    print(f"\n  total spend: ${spent:.4f}")
    print(
        "\n  VERDICT: "
        + (
            "at least one case flipped -- the V6->V18 series compared single "
            "samples across an unmeasured noise floor, so its version-to-version "
            "conclusions are not sound."
            if any_flip
            else "every case reproduced its sealed verdict -- the panel is "
            "stable at this sample size, and the series' comparisons were "
            "measuring the prompt rather than sampling noise."
        ),
    )
    payload = {
        "schema_version": "artana.staged_generalization.v17_noise_floor.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "replicates_requested": arguments.replicates,
        "prompt_verified_against_sealed_digests": True,
        "sealed_verdicts": SEALED_VERDICT,
        "summary": summary,
        "any_case_unstable": any_flip,
        "total_cost_usd": round(spent, 6),
        "observations": observations,
    }
    out = arguments.scratch / "noise-floor-result.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
