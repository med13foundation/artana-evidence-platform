"""Log command monitoring for live evidence session audits."""

from __future__ import annotations

import re
import subprocess
import threading
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from scripts.full_ai_real_space_canary.utils import _safe_filename
from scripts.live_evidence_session_audit.constants import _DEFAULT_LOG_TAIL_LINES
from scripts.live_evidence_session_audit.models import (
    LiveEvidenceSessionAuditConfig,
    LogCommandConfig,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


@dataclass(slots=True)
class _CapturedLogLine:
    channel: str
    text: str
    matched_error_pattern: bool

    def render(self) -> str:
        return f"[{self.channel}] {self.text}"


@dataclass(slots=True)
class _LogCommandMonitor:
    config: LogCommandConfig
    output_path: Path
    error_patterns: tuple[re.Pattern[str], ...]
    ignore_patterns: tuple[re.Pattern[str], ...]
    tail_lines: int = _DEFAULT_LOG_TAIL_LINES
    process: subprocess.Popen[str] | None = field(init=False, default=None)
    _threads: list[threading.Thread] = field(init=False, default_factory=list)
    _writer: TextIO | None = field(init=False, default=None)
    _tail: deque[str] = field(init=False)
    _suspicious: deque[str] = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    total_lines: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._tail = deque(maxlen=self.tail_lines)
        self._suspicious = deque(maxlen=max(self.tail_lines, 40))

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer = self.output_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            ["/bin/sh", "-lc", self.config.command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        for channel, stream in (
            ("stdout", self.process.stdout),
            ("stderr", self.process.stderr),
        ):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._consume_stream,
                args=(channel, stream),
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def _consume_stream(self, channel: str, stream: TextIO) -> None:
        try:
            for raw_line in stream:
                line = raw_line.rstrip("\n")
                matched = self._line_matches_error(line)
                captured = _CapturedLogLine(
                    channel=channel,
                    text=line,
                    matched_error_pattern=matched,
                )
                rendered = captured.render()
                with self._lock:
                    self.total_lines += 1
                    self._tail.append(rendered)
                    if matched:
                        self._suspicious.append(rendered)
                    if self._writer is not None:
                        self._writer.write(rendered + "\n")
                        self._writer.flush()
        finally:
            stream.close()

    def _line_matches_error(self, line: str) -> bool:
        if line.strip() == "":
            return False
        if any(pattern.search(line) for pattern in self.ignore_patterns):
            return False
        return any(pattern.search(line) for pattern in self.error_patterns)

    def stop(self, *, timeout_seconds: float = 5.0) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=timeout_seconds)
        for thread in self._threads:
            thread.join(timeout=timeout_seconds)
        if self._writer is not None:
            self._writer.close()
            self._writer = None

    def summary(self) -> JSONObject:
        with self._lock:
            suspicious_lines = list(self._suspicious)
            tail_lines = list(self._tail)
        process = self.process
        exit_code = process.returncode if process is not None else None
        return {
            "name": self.config.name,
            "command": self.config.command,
            "output_path": str(self.output_path),
            "total_lines": self.total_lines,
            "suspicious_line_count": len(suspicious_lines),
            "suspicious_lines": suspicious_lines,
            "tail_lines": tail_lines,
            "exit_code": exit_code,
        }


def _start_log_monitors(
    *,
    config: LiveEvidenceSessionAuditConfig,
    session_dir: Path,
) -> list[_LogCommandMonitor]:
    error_patterns = tuple(
        re.compile(pattern) for pattern in config.log_error_patterns if pattern.strip()
    )
    ignore_patterns = tuple(
        re.compile(pattern) for pattern in config.log_ignore_patterns if pattern.strip()
    )
    monitors: list[_LogCommandMonitor] = []
    for index, command in enumerate(config.log_commands, start=1):
        output_path = (
            session_dir / "logs" / f"{index:02d}_{_safe_filename(command.name)}.log"
        )
        monitor = _LogCommandMonitor(
            config=command,
            output_path=output_path,
            error_patterns=error_patterns,
            ignore_patterns=ignore_patterns,
        )
        monitor.start()
        monitors.append(monitor)
    return monitors


def _stop_log_monitors(monitors: Sequence[_LogCommandMonitor]) -> list[JSONObject]:
    summaries: list[JSONObject] = []
    for monitor in monitors:
        monitor.stop()
        summaries.append(monitor.summary())
    return summaries


def _normalize_log_commands(values: list[str]) -> tuple[LogCommandConfig, ...]:
    commands: list[LogCommandConfig] = []
    for index, raw_value in enumerate(values, start=1):
        command = raw_value.strip()
        if command == "":
            continue
        first_token = command.split()[0]
        commands.append(
            LogCommandConfig(
                command=command,
                name=f"log-command-{index}-{first_token}",
            ),
        )
    return tuple(commands)


__all__ = [
    "_CapturedLogLine",
    "_LogCommandMonitor",
    "_normalize_log_commands",
    "_start_log_monitors",
    "_stop_log_monitors",
]
