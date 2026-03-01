"""Background worker for running auto-tagging script."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from apps.pyside.moegirl_tagger_gui_common import (
    DEFAULT_LANGUAGE,
    DEFAULT_THRESHOLDS,
    THRESHOLD_CLI_ARGS,
    THRESHOLD_MAX_VALUE,
    THRESHOLD_MIN_VALUE,
    TRANSLATIONS,
    normalize_path_key,
    normalize_language_code,
)

class AnalysisWorker(QObject):
    """Run auto-tagging script in background thread."""

    finished = Signal(bool, str, dict)
    log = Signal(str)
    record_ready = Signal(str, object)
    _RECORD_STREAM_PREFIX = "__MOEGIRL_RECORD__:"

    def __init__(
        self,
        repo_root: Path,
        images: list[Path],
        queue_output: Path,
        thresholds: dict[str, float],
        language_code: str = "zh-CN",
        recognize_characters: bool = True,
    ) -> None:
        """Initialize worker.

        Args:
            repo_root: Project root path.
            images: Selected image paths.
            queue_output: Output queue JSONL path.
            thresholds: Runtime threshold values.
            language_code: Preferred language for custom character labels.
            recognize_characters: Whether custom character recognition is enabled.
        """
        super().__init__()
        self.repo_root = repo_root
        self.images = images
        self.queue_output = queue_output
        self.thresholds = thresholds
        self.language_code = normalize_language_code(str(language_code or "").strip() or "zh-CN")
        self.recognize_characters = bool(recognize_characters)
        self.input_list_path: Path | None = None
        self._process: subprocess.Popen | None = None
        self._stop_requested = False

    def _tr(self, key: str, **kwargs) -> str:
        """Translate worker-facing log and status text."""
        language_map = TRANSLATIONS.get(self.language_code, TRANSLATIONS[DEFAULT_LANGUAGE])
        template = language_map.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def request_stop(self) -> None:
        """Request to stop analysis process."""
        self._stop_requested = True
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            process.kill()

    def run(self) -> None:
        """Execute script and parse queue results."""
        try:
            self.input_list_path = self._write_input_list()
            self.queue_output.parent.mkdir(parents=True, exist_ok=True)
            if self._stop_requested:
                self.finished.emit(False, self._tr("status_analysis_stopped"), {})
                return

            command = [
                sys.executable,
                "-X",
                "utf8",
                str((self.repo_root / "scripts/auto_tag_images.py").resolve()),
                "--input-list",
                str(self.input_list_path),
                "--queue-output",
                str(self.queue_output),
                "--custom-character-language",
                self.language_code,
                "--stream-records",
            ]
            for key, arg_name in THRESHOLD_CLI_ARGS.items():
                raw_value = float(self.thresholds.get(key, DEFAULT_THRESHOLDS[key]))
                threshold_value = min(THRESHOLD_MAX_VALUE, max(THRESHOLD_MIN_VALUE, raw_value))
                command.extend([arg_name, f"{threshold_value:.2f}"])
            if not self.recognize_characters:
                command.append("--disable-character-recognition")
            self.log.emit(self._tr("worker_log_running_command", command=" ".join(command)))

            streamed_records: dict[str, dict] = {}
            self._process = subprocess.Popen(
                command,
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            stream = self._process.stdout
            if stream is not None:
                for raw_line in stream:
                    line = raw_line.strip()
                    if not line:
                        continue
                    if self._handle_stream_record_line(line, streamed_records):
                        continue
                    self.log.emit(line)
            returncode = self._process.wait()
            self._process = None

            if self._stop_requested:
                self.finished.emit(False, self._tr("status_analysis_stopped"), {})
                return

            if returncode != 0:
                self.finished.emit(False, self._tr("worker_status_script_failed", code=returncode), {})
                return

            records = self._load_queue_records()
            if not records and streamed_records:
                records = streamed_records
            self.finished.emit(True, self._tr("status_analysis_completed"), records)
        except Exception as exc:
            self.finished.emit(False, self._tr("worker_status_exception", error=exc), {})
        finally:
            self._process = None
            if self.input_list_path and self.input_list_path.exists():
                self.input_list_path.unlink(missing_ok=True)

    def _handle_stream_record_line(self, line: str, records: dict[str, dict]) -> bool:
        """Parse and dispatch one streamed record line from analysis script."""
        if not line.startswith(self._RECORD_STREAM_PREFIX):
            return False

        payload_text = line[len(self._RECORD_STREAM_PREFIX) :].strip()
        if not payload_text:
            return True
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            self.log.emit(line)
            return True
        if not isinstance(payload, dict):
            return True

        path_key = self._resolve_record_path_key(payload)
        if not path_key:
            return True
        records[path_key] = payload
        self.record_ready.emit(path_key, payload)
        return True

    def _resolve_record_path_key(self, payload: dict) -> str:
        """Resolve normalized path key for one analysis record."""
        raw_path = str(payload.get("image_path", "")).strip()
        if not raw_path:
            return ""
        image_path = Path(raw_path)
        resolved = image_path if image_path.is_absolute() else (self.repo_root / image_path)
        return normalize_path_key(resolved)

    def _write_input_list(self) -> Path:
        """Write selected image list to temp file.

        Returns:
            Temporary list path.
        """
        handle, temp_name = tempfile.mkstemp(prefix="moegirl_images_", suffix=".txt")
        os.close(handle)
        output_path = Path(temp_name).resolve()
        with output_path.open("w", encoding="utf-8", newline="\n") as file:
            for image_path in self.images:
                file.write(f"{image_path.resolve()}\n")
        return output_path

    def _load_queue_records(self) -> dict[str, dict]:
        """Load queue records for selected images.

        Returns:
            Mapping with normalized image path key.
        """
        if not self.queue_output.exists():
            return {}

        selected_keys = {normalize_path_key(path) for path in self.images}
        records: dict[str, dict] = {}
        with self.queue_output.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                image_path = Path(str(payload.get("image_path", "")).strip())
                resolved = image_path if image_path.is_absolute() else (self.repo_root / image_path)
                key = normalize_path_key(resolved)
                if key in selected_keys:
                    records[key] = payload
        return records
