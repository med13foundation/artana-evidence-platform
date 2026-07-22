"""Run the frozen target-specific DeepEventMine checkpoint exactly once."""

from __future__ import annotations

import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/"
    "2026-07-22-target-deepeventmine-participant-experiment-v1.json"
)
RUN_DIR = Path(
    "/Users/alvaro/.codex/artana-evidence-experiments/tg04/"
    "target_deepeventmine_pmid_16428936_v1"
)
IMAGE = (
    "sha256:84aecdb25d2336d3ae48514dcc75fc7e2e075c42a9276763895192909e973100"
)
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
TIMEOUT_SECONDS = 900


class SpecialistExecutionError(RuntimeError):
    """The frozen one-shot specialist execution is invalid."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute() -> int:
    if RUN_DIR.exists():
        raise SpecialistExecutionError("one-shot run directory already exists")
    if sha256(SOURCE) != SOURCE_SHA256:
        raise SpecialistExecutionError("frozen source hash changed")
    preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if preregistration["source"]["sha256"] != SOURCE_SHA256:
        raise SpecialistExecutionError("preregistration source hash mismatch")

    input_dir = RUN_DIR / "input"
    evidence_dir = RUN_DIR / "evidence"
    input_dir.mkdir(parents=True)
    evidence_dir.mkdir()
    input_path = input_dir / "PMID-16428936.txt"
    input_path.write_bytes(SOURCE.read_bytes())

    container_script = """
set -eu
target=pmid-16428936-target-v1
rm -rf /app/data/$target /app/experiments/$target
mkdir -p /app/data/$target/text
cp /evidence/input/PMID-16428936.txt /app/data/$target/text/PMID-16428936.txt
bash pubmed.sh e2e rawtext $target ge11 -1
mkdir -p /evidence/evidence
cp -a /app/data/$target/processed-text /evidence/evidence/
cp -a /app/experiments/$target /evidence/evidence/experiment
""".strip()
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
        "--volume",
        f"{RUN_DIR}:/evidence",
        IMAGE,
        "bash",
        "-lc",
        container_script,
    ]
    (RUN_DIR / "command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    started = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        (RUN_DIR / "execution.json").write_text(
            json.dumps(
                {
                    "decision": "INVALID_SPECIALIST_EXECUTION",
                    "failure": "TIMEOUT",
                    "timeout_seconds": TIMEOUT_SECONDS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        raise SpecialistExecutionError("DeepEventMine execution timed out") from exc
    elapsed = time.monotonic() - started
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    (RUN_DIR / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (RUN_DIR / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    evidence_files = sorted(path for path in evidence_dir.rglob("*") if path.is_file())
    result = {
        "exit_status": completed.returncode,
        "elapsed_seconds": elapsed,
        "child_user_seconds": usage_after.ru_utime - usage_before.ru_utime,
        "child_system_seconds": usage_after.ru_stime - usage_before.ru_stime,
        "platform": platform.platform(),
        "python": sys.version,
        "image": IMAGE,
        "input_sha256": sha256(input_path),
        "output_sha256": {
            str(path.relative_to(RUN_DIR)): sha256(path) for path in evidence_files
        },
    }
    (RUN_DIR / "execution.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if completed.returncode != 0:
        raise SpecialistExecutionError(
            f"DeepEventMine exited with status {completed.returncode}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(execute())
