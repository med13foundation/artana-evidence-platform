"""Atomically publish blinded expert-pilot packets and private sidecars."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from .pilot_contracts import (
    EvidenceSelectionExpertPilotPublicationManifest,
    EvidenceSelectionExpertPilotPublishedArtifact,
)
from .pilot_loader import LoadedEvidenceSelectionExpertPilot
from .pilot_packets import (
    build_expert_pilot_packet_bundles,
    verify_expert_pilot_packet_bundle,
)


def publish_expert_pilot_packets(
    *,
    loaded: LoadedEvidenceSelectionExpertPilot,
    output_dir: Path,
) -> EvidenceSelectionExpertPilotPublicationManifest:
    """Publish a complete packet set through one atomic directory rename."""

    resolved_output = output_dir.resolve()
    if resolved_output.exists():
        raise ValueError("expert-pilot output directory must not already exist")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{resolved_output.name}.staging-",
            dir=resolved_output.parent,
        )
    )
    try:
        bundles = build_expert_pilot_packet_bundles(loaded)
        artifacts: list[EvidenceSelectionExpertPilotPublishedArtifact] = []
        candidate_review_count = 0
        for bundle in bundles:
            verify_expert_pilot_packet_bundle(bundle)
            packet = bundle.reviewer_packet
            reviewer_slot = _safe_path_segment(
                packet.reviewer_slot,
                field_name="reviewer_slot",
            )
            review_case_id = _safe_path_segment(
                packet.review_case_id,
                field_name="review_case_id",
            )
            packet_path = (
                Path("reviewer_packets") / reviewer_slot / f"{review_case_id}.json"
            )
            sidecar_path = (
                Path("machine_sidecars") / reviewer_slot / f"{review_case_id}.json"
            )
            artifacts.extend(
                (
                    _write_artifact(
                        staging=staging,
                        relative_path=packet_path,
                        artifact_kind="reviewer_packet",
                        content=packet.model_dump_json(indent=2) + "\n",
                    ),
                    _write_artifact(
                        staging=staging,
                        relative_path=sidecar_path,
                        artifact_kind="machine_sidecar",
                        content=bundle.machine_sidecar.model_dump_json(indent=2) + "\n",
                    ),
                )
            )
            candidate_review_count += len(packet.candidates)
        manifest = EvidenceSelectionExpertPilotPublicationManifest(
            schema_version="evidence_selection_expert_pilot_publication.v1",
            study_id=loaded.protocol.study_id,
            protocol_sha256=loaded.protocol_sha256,
            benchmark_fixture_sha256=loaded.benchmark.fixture_sha256,
            supplement_manifest_sha256=loaded.supplement_manifest_sha256,
            independent_reviewer_count=len(
                loaded.protocol.independent_reviewer_slots
            ),
            reviewer_packet_count=len(bundles),
            candidate_review_count=candidate_review_count,
            artifacts=tuple(artifacts),
        )
        manifest_path = staging / "publication_manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)
        _publish_directory_no_replace(staging=staging, destination=resolved_output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def _write_artifact(
    *,
    staging: Path,
    relative_path: Path,
    artifact_kind: Literal["reviewer_packet", "machine_sidecar"],
    content: str,
) -> EvidenceSelectionExpertPilotPublishedArtifact:
    destination = staging / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    destination.chmod(0o600)
    return EvidenceSelectionExpertPilotPublishedArtifact(
        artifact_kind=artifact_kind,
        path=relative_path.as_posix(),
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _safe_path_segment(value: str, *, field_name: str) -> str:
    if value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError(f"expert-pilot {field_name} is not path-safe")
    return value


def publish_directory_no_replace(*, staging: Path, destination: Path) -> None:
    """Publish an already staged directory through the platform no-replace API."""

    _publish_directory_no_replace(staging=staging, destination=destination)


def _publish_directory_no_replace(*, staging: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing a racing destination."""

    platform_name = platform.system()
    if platform_name == "Darwin":
        _call_rename_no_replace(
            function_name="renamex_np",
            arguments=(os.fsencode(staging), os.fsencode(destination), 4),
            argument_types=(ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint),
            destination=destination,
        )
        return
    if platform_name == "Linux":
        _call_rename_no_replace(
            function_name="renameat2",
            arguments=(
                -100,
                os.fsencode(staging),
                -100,
                os.fsencode(destination),
                1,
            ),
            argument_types=(
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ),
            destination=destination,
        )
        return
    if platform_name == "Windows":
        staging.rename(destination)
        return
    raise OSError(
        errno.ENOTSUP,
        "atomic no-replace directory publication is unsupported",
        str(destination),
    )


def _call_rename_no_replace(
    *,
    function_name: str,
    arguments: tuple[object, ...],
    argument_types: tuple[object, ...],
    destination: Path,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    operation = getattr(libc, function_name, None)
    if operation is None:
        raise OSError(
            errno.ENOTSUP,
            f"atomic no-replace operation {function_name} is unavailable",
            str(destination),
        )
    operation.argtypes = list(argument_types)
    operation.restype = ctypes.c_int
    if operation(*arguments) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(destination))


__all__ = ["publish_directory_no_replace", "publish_expert_pilot_packets"]
