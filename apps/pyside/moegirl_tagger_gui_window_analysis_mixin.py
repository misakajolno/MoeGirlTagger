"""Image analysis and metadata behavior mixin for MoeGirlTagger window."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QModelIndex, QThread
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from apps.pyside.moegirl_tagger_gui_common import (
    DEFAULT_FEATURE_TEXT,
    FEATURE_FORCE_VISIBLE,
    FEATURE_PREVIEW_LIMIT,
    TRANSLATIONS,
    collect_images_from_folder,
    normalize_path_key,
)
from apps.pyside.moegirl_tagger_gui_model import ImageListModel
from apps.pyside.moegirl_tagger_gui_worker import AnalysisWorker
from apps.pyside.moegirl_tagger_gui_workers import ClearTagsWorker
from apps.pyside.moegirl_tagger_gui_dialogs import ClearTagsConfirmDialog


class MoeGirlTaggerWindowAnalysisMixin:
    """Handle image list, analysis, preview and metadata tag operations."""

    def _resolve_feature_tag_display_name(self, raw_tag: str) -> str:
        """Resolve one feature tag into current-language display text when possible."""
        tag = str(raw_tag).strip()
        if not tag:
            return ""
        localized = self.taxonomy_name_map.get(tag)
        if localized:
            return localized
        normalized = re.sub(r"[_\\-\\s]+", "_", tag).strip("_").lower()
        if normalized:
            localized = self.taxonomy_name_map.get(normalized)
            if localized:
                return localized
        return tag

    def _choose_folder(self) -> None:
        """Select folder and import all supported images."""
        chosen = QFileDialog.getExistingDirectory(
            self,
            self._tr("dialog_choose_folder"),
            str(self._get_dialog_start_dir()),
        )
        if not chosen:
            return
        self._remember_dialog_dir(Path(chosen))
        images = collect_images_from_folder(Path(chosen).resolve())
        self._set_images(images)
        self._set_status(self._tr("status_loaded_folder", folder=chosen, count=len(images)))

    def _choose_images(self) -> None:
        """Select multiple images manually."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._tr("dialog_choose_images"),
            str(self._get_dialog_start_dir()),
            self._tr("dialog_image_files_filter"),
        )
        if not files:
            return
        self._remember_dialog_dir(Path(files[0]).parent)
        images = [Path(file).resolve() for file in files]
        self._set_images(images)
        self._set_status(self._tr("status_selected_images", count=len(images)))

    def _set_images(self, images: list[Path]) -> None:
        """Replace list content with selected images.

        Args:
            images: Candidate image list.
        """
        deduped: list[Path] = []
        seen: set[str] = set()
        for image in images:
            key = normalize_path_key(image)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(image)

        self.image_model.set_images(deduped)
        self.image_paths_by_key = {normalize_path_key(path): path for path in deduped}
        self._apply_existing_tags(deduped)
        localized_default_feature = self._tr("feature_edit_tags")
        for path_key in self.image_paths_by_key:
            if self.image_model.feature_for_key(path_key) == DEFAULT_FEATURE_TEXT:
                self.image_model.set_feature_by_key(path_key, localized_default_feature)

        self.count_label.setText(self._tr("selected_count", count=len(deduped)))
        self._update_remove_buttons_visibility()
        if deduped:
            self.list_widget.setCurrentIndex(self.image_model.index(0, 0))
            self._show_preview(deduped[0])
        else:
            self.preview_label.set_placeholder(self._tr("preview_placeholder"))
            self._set_status(self._tr("status_waiting_select"))

    def _update_remove_buttons_visibility(self) -> None:
        has_items = bool(self.image_paths_by_key)
        self.remove_all_button.setVisible(has_items)
        self.clear_tags_button.setVisible(has_items)
        self.remove_tagged_button.setVisible(has_items)

    def _is_busy(self) -> bool:
        analysis_running = self.worker_thread is not None and self.worker_thread.isRunning()
        clear_running = self.clear_thread is not None and self.clear_thread.isRunning()
        return analysis_running or clear_running

    def _remove_all_images(self) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return
        self._set_images([])

    def _remove_tagged_images(self) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        tagged_keys = set(self.image_model.path_keys_with_existing_tags())
        if not tagged_keys:
            self._set_status(self._tr("status_no_tagged_images"))
            return

        current_index = self.list_widget.currentIndex()
        current_key = ""
        if current_index.isValid():
            current_key = str(current_index.data(ImageListModel.ROLE_PATH_KEY) or "")

        self.image_model.remove_by_keys(tagged_keys)
        for key in tagged_keys:
            self.image_paths_by_key.pop(key, None)

        remaining = self.image_model.rowCount()
        self.count_label.setText(self._tr("selected_count", count=remaining))
        self._update_remove_buttons_visibility()

        if remaining <= 0:
            self.preview_label.set_placeholder(self._tr("preview_placeholder"))
            self._set_status(self._tr("status_waiting_select"))
            return

        focus_row = 0
        if current_key and current_key not in tagged_keys:
            row = self.image_model.row_for_key(current_key)
            if row is not None:
                focus_row = row
        self.list_widget.setCurrentIndex(self.image_model.index(focus_row, 0))

    def _clear_tagged_images(self) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        tagged_paths: list[Path] = []
        for path_key in self.image_model.path_keys_with_existing_tags():
            image_path = self.image_paths_by_key.get(path_key)
            if image_path is not None:
                tagged_paths.append(image_path)

        if not tagged_paths:
            self._set_status(self._tr("status_no_tagged_images"))
            return

        if not self._confirm_clear_tags(len(tagged_paths)):
            return

        exiftool = self._find_exiftool_binary()
        if exiftool is None:
            self._set_status(self._tr("status_exiftool_missing"), is_error=True)
            return

        self._start_clear_tags_job(exiftool, tagged_paths)

    def _confirm_clear_tags(self, count: int) -> bool:
        dialog = ClearTagsConfirmDialog(
            self,
            title=self._tr("dialog_clear_tags_title"),
            message=self._tr("dialog_clear_tags_message", count=count),
            confirm_text=self._tr("dialog_clear_tags_confirm"),
            cancel_text=self._tr("dialog_clear_tags_cancel"),
        )
        return dialog.exec() == QDialog.Accepted

    def _start_clear_tags_job(self, exiftool: Path, tagged_paths: list[Path]) -> None:
        self.folder_button.setEnabled(False)
        self.images_button.setEnabled(False)
        self.remove_all_button.setEnabled(False)
        self.clear_tags_button.setEnabled(False)
        self.remove_tagged_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._set_status(self._tr("status_clearing_tags", count=len(tagged_paths)))

        self.clear_thread = QThread(self)
        self.clear_worker = ClearTagsWorker(self._clear_image_metadata_tags, exiftool, tagged_paths)
        self.clear_worker.moveToThread(self.clear_thread)

        self.clear_thread.started.connect(self.clear_worker.run)
        self.clear_worker.finished.connect(self._on_clear_tags_finished)
        self.clear_worker.finished.connect(self.clear_thread.quit)
        self.clear_worker.finished.connect(self.clear_worker.deleteLater)
        self.clear_thread.finished.connect(self.clear_thread.deleteLater)
        self.clear_thread.finished.connect(self._on_clear_thread_finished)
        self.clear_thread.start()

    def _on_clear_tags_finished(self, ok: bool, message: str, cleared_keys: list) -> None:
        if not ok:
            self._set_status(self._tr("status_clear_tags_failed", error=message), is_error=True)
            return
        for path_key in cleared_keys:
            self.image_model.set_existing_tags_by_key(str(path_key), self._tr("status_pending_analysis"), False)
        self._set_status(self._tr("status_tags_cleared", count=len(cleared_keys)))

    def _on_clear_thread_finished(self) -> None:
        self.clear_thread = None
        self.clear_worker = None
        self.folder_button.setEnabled(True)
        self.images_button.setEnabled(True)
        self.remove_all_button.setEnabled(True)
        self.clear_tags_button.setEnabled(True)
        self.remove_tagged_button.setEnabled(True)
        self.start_button.setEnabled(True)

    def _delete_image_by_key(self, path_key: str) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        row = self.image_model.row_for_key(path_key)
        if row is None:
            return
        remaining_before = self.image_model.rowCount()
        if remaining_before <= 0:
            return

        focus_row = row if row < remaining_before - 1 else row - 1
        removed_key = self.image_model.remove_row(row)
        if removed_key:
            self.image_paths_by_key.pop(removed_key, None)

        remaining = self.image_model.rowCount()
        self.count_label.setText(self._tr("selected_count", count=remaining))
        self._update_remove_buttons_visibility()

        if remaining <= 0:
            self.preview_label.set_placeholder(self._tr("preview_placeholder"))
            self._set_status(self._tr("status_waiting_select"))
            return

        focus_row = max(0, min(focus_row, remaining - 1))
        self.list_widget.setCurrentIndex(self.image_model.index(focus_row, 0))

    def _on_current_item_changed(self, current: QModelIndex, _: QModelIndex) -> None:
        """Update preview when selection changes.

        Args:
            current: Current selected item.
            _: Previous item.
        """
        if not current.isValid():
            return
        key = str(current.data(ImageListModel.ROLE_PATH_KEY) or "")
        path = self.image_paths_by_key.get(key)
        if path:
            self._show_preview(path)

    def _show_preview(self, image_path: Path) -> None:
        """Render selected image in preview area.

        Args:
            image_path: Target image path.
        """
        if not self.preview_label.set_image_path(image_path):
            self.preview_label.set_placeholder(self._tr("status_preview_failed", name=image_path.name))
            return

    def resizeEvent(self, event) -> None:
        """Refresh preview scale on resize.

        Args:
            event: Resize event.
        """
        super().resizeEvent(event)
        current = self.list_widget.currentIndex()
        if not current.isValid():
            return
        key = str(current.data(ImageListModel.ROLE_PATH_KEY) or "")
        path = self.image_paths_by_key.get(key)
        if path:
            self._show_preview(path)

    def _start_analysis(self) -> None:
        """Start or stop background analysis for selected images."""
        if not self.image_paths_by_key:
            self._set_status(self._tr("status_please_select_images"), is_error=True)
            return
        if self.clear_thread is not None:
            self._set_status(self._tr("status_clearing_tags_busy"), is_error=True)
            return
        if self.worker_thread is not None:
            self._set_status(self._tr("status_stopping_analysis"))
            if self.worker is not None:
                self.worker.request_stop()
            return

        selected_paths = self.image_model.image_paths()
        for path_key in self.image_paths_by_key:
            self.image_model.set_feature_by_key(path_key, self._tr("status_analysis_in_progress"))

        self.folder_button.setEnabled(False)
        self.images_button.setEnabled(False)
        self.remove_all_button.setEnabled(False)
        self.clear_tags_button.setEnabled(False)
        self.remove_tagged_button.setEnabled(False)
        self.start_button.setText(self._tr("btn_stop_analysis"))
        self.start_button.setStyleSheet(
            "QPushButton { background: #e5484d; color: #ffffff; font-weight: 600; }"
            "QPushButton:hover { background: #d93d42; }"
            "QPushButton:pressed { background: #c43439; }"
        )
        self._set_status(self._tr("status_analysis_started", count=len(selected_paths)))

        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(
            self.repo_root,
            selected_paths,
            self.queue_output,
            thresholds=self.threshold_values.copy(),
            language_code=self.current_language,
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_status)
        self.worker.finished.connect(self._on_analysis_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._on_thread_finished)
        self.worker_thread.start()

    def _on_thread_finished(self) -> None:
        """Clear thread references after finish."""
        self.worker_thread = None
        self.worker = None
        self.folder_button.setEnabled(True)
        self.images_button.setEnabled(True)
        self.remove_all_button.setEnabled(True)
        self.clear_tags_button.setEnabled(True)
        self.remove_tagged_button.setEnabled(True)
        self.start_button.setText(self._tr("btn_start_analysis"))
        self.start_button.setStyleSheet("")
        self.start_button.setEnabled(True)

    def _append_status(self, text: str) -> None:
        """Append transient status line.

        Args:
            text: Status text.
        """
        self._set_status(f"{self._tr('status_prefix')}: {text}")

    def _on_analysis_finished(self, ok: bool, message: str, records: dict) -> None:
        """Handle analysis completion and update list rows.

        Args:
            ok: Whether script succeeded.
            message: Completion message.
            records: Parsed queue records.
        """
        if not ok:
            stopped_texts = {
                text_map.get("status_analysis_stopped", "")
                for text_map in TRANSLATIONS.values()
            }
            if message in stopped_texts:
                self._set_status(self._tr("status_analysis_stopped"))
                in_progress_texts = {texts["status_analysis_in_progress"] for texts in TRANSLATIONS.values()}
                for path_key in self.image_paths_by_key:
                    if self.image_model.feature_for_key(path_key) in in_progress_texts:
                        self.image_model.set_feature_by_key(path_key, self._tr("feature_edit_tags"))
                return
            self._set_status(message, is_error=True)
            in_progress_texts = {texts["status_analysis_in_progress"] for texts in TRANSLATIONS.values()}
            for path_key in self.image_paths_by_key:
                if self.image_model.feature_for_key(path_key) in in_progress_texts:
                    self.image_model.set_feature_by_key(path_key, self._tr("status_exec_failed"))
            return

        for key in self.image_paths_by_key:
            record = records.get(key)
            if record is None:
                self.image_model.set_existing_tags_by_key(key, self._tr("status_no_obvious_features"), False)
                continue
            has_tags = any(str(value).strip() for value in record.get("characters", [])) or any(
                str(value).strip() for value in record.get("feature_tags", [])
            )
            self.image_model.set_existing_tags_by_key(key, self._format_feature_text(record), has_tags)

        done_text = self._tr("status_analysis_completed")
        completed_texts = {
            text_map.get("status_analysis_completed", "")
            for text_map in TRANSLATIONS.values()
        }
        if message not in completed_texts:
            done_text = message
        self._set_status(f"{done_text} ({self.queue_output})")

    def _load_queue_records(self, images: list[Path]) -> dict[str, dict]:
        """Load queue records for selected images from current queue file.

        Args:
            images: Selected image paths.

        Returns:
            Mapping from normalized image path key to queue record.
        """
        if not self.queue_output.exists():
            return {}

        selected_keys = {normalize_path_key(path) for path in images}
        records: dict[str, dict] = {}
        with self.queue_output.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                image_path = Path(str(payload.get("image_path", "")).strip())
                resolved = image_path if image_path.is_absolute() else (self.repo_root / image_path)
                key = normalize_path_key(resolved)
                if key in selected_keys:
                    records[key] = payload
        return records

    def _format_feature_text(self, record: dict) -> str:
        """Build Chinese summary string from queue record.

        Args:
            record: Queue record.

        Returns:
            Display text for subtitle row.
        """
        characters = [str(value).strip() for value in record.get("characters", []) if str(value).strip()]
        features = [str(value).strip() for value in record.get("feature_tags", []) if str(value).strip()]
        preview_features = features[:FEATURE_PREVIEW_LIMIT]
        if features and len(features) > FEATURE_PREVIEW_LIMIT:
            for forced_tag in FEATURE_FORCE_VISIBLE:
                if forced_tag in features and forced_tag not in preview_features:
                    if preview_features:
                        preview_features[-1] = forced_tag
                    else:
                        preview_features.append(forced_tag)
                    break
        translated = [self._resolve_feature_tag_display_name(tag) for tag in preview_features]

        sections: list[str] = []
        if characters:
            sections.append(self._tr("section_character") + "、".join(characters[:3]))
        if translated:
            sections.append(self._tr("section_feature") + "、".join(translated))
        if not sections:
            return self._tr("status_no_obvious_features")
        return "；".join(sections)

    def _apply_existing_tags(self, images: list[Path]) -> None:
        """Fill list subtitles with existing tags when available.

        Args:
            images: Selected images.
        """
        tags_by_key = self._load_existing_image_tags(images)
        if not tags_by_key:
            return
        for path_key, tags in tags_by_key.items():
            text = self._format_edit_tags_text(tags)
            if text != self._tr("feature_edit_tags"):
                self.image_model.set_existing_tags_by_key(path_key, text, True)

    def _find_exiftool_binary(self) -> Path | None:
        """Find available exiftool binary.

        Returns:
            Exiftool path or None.
        """
        resolved = shutil.which("exiftool")
        if resolved:
            return Path(resolved).resolve()

        candidates = [
            self.repo_root / "tools/exiftool/exiftool.exe",
            self.repo_root / "tools/exiftool/exiftool(-k).exe",
            self.repo_root / "tools/exiftool/exiftool",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _load_existing_image_tags(self, images: list[Path]) -> dict[str, list[str]]:
        """Load existing tags from image metadata.

        Args:
            images: Selected images.

        Returns:
            Mapping from path key to tags.
        """
        exiftool = self._find_exiftool_binary()
        if exiftool is None:
            return {}

        selected_by_key = {normalize_path_key(path): path for path in images}
        selected_keys = set(selected_by_key.keys())
        tags_by_key: dict[str, list[str]] = {}

        chunk_size = 60
        for start in range(0, len(images), chunk_size):
            chunk = images[start : start + chunk_size]
            command = [
                str(exiftool),
                "-json",
                "-m",
                "-sep",
                "; ",
                "-charset",
                "exiftool=utf8",
                "-XMP-dc:Subject",
                "-XPKeywords",
                "-Keywords",
            ] + [str(path) for path in chunk]

            process = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if not process.stdout.strip():
                continue

            try:
                payloads = json.loads(process.stdout)
            except json.JSONDecodeError:
                continue

            if not isinstance(payloads, list):
                continue
            for payload_index, payload in enumerate(payloads):
                if not isinstance(payload, dict):
                    continue
                key = ""

                source_file = str(payload.get("SourceFile", "")).strip()
                if source_file:
                    key_candidate = normalize_path_key(Path(source_file))
                    if key_candidate in selected_keys:
                        key = key_candidate

                if not key:
                    if payload_index >= len(chunk):
                        continue
                    key_candidate = normalize_path_key(chunk[payload_index])
                    if key_candidate not in selected_keys:
                        continue
                    key = key_candidate

                tags = self._extract_tags_from_exiftool_payload(payload)
                if tags:
                    tags_by_key[key] = tags

        return tags_by_key

    def _clear_image_metadata_tags(self, exiftool: Path, images: list[Path]) -> None:
        """Clear tag fields in metadata while preserving other image info.

        Args:
            exiftool: ExifTool executable path.
            images: Image paths to clear tag fields.

        Raises:
            RuntimeError: If any image fails to clear.
        """
        if not images:
            return

        for image_path in images:
            QApplication.processEvents()
            args_lines = [
                "-overwrite_original",
                "-P",
                "-m",
                "-charset",
                "exiftool=utf8",
                "-XMP-dc:Subject=",
                "-Keywords=",
            ]
            if image_path.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
                args_lines.append("-XPKeywords=")
            args_lines.append(str(image_path))

            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".args", delete=False) as temp_args_file:
                temp_args_path = Path(temp_args_file.name)
                temp_args_file.write("\n".join(args_lines) + "\n")

            command = [str(exiftool), "-@", str(temp_args_path)]
            try:
                process = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if process.returncode != 0:
                    detail = process.stderr.strip() or process.stdout.strip() or "unknown exiftool error"
                    raise RuntimeError(f"{image_path.name}: {detail}")
            finally:
                if temp_args_path.exists():
                    temp_args_path.unlink()

    def _extract_tags_from_exiftool_payload(self, payload: dict) -> list[str]:
        """Extract tags from one ExifTool JSON payload.

        Args:
            payload: ExifTool JSON dict for one file.

        Returns:
            Deduped tag list.
        """
        raw_values: list[str] = []
        for field in ["Subject", "XPKeywords", "Keywords", "XMP-dc:Subject"]:
            value = payload.get(field)
            if value is None:
                continue
            if isinstance(value, list):
                raw_values.extend([str(item).strip() for item in value if str(item).strip()])
                continue
            raw_values.append(str(value).strip())

        tags: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            for token in self._split_tags_text(raw):
                if token and token not in seen:
                    tags.append(token)
                    seen.add(token)
        return tags

    def _split_tags_text(self, text: str) -> list[str]:
        """Split raw metadata tag string into tokens.

        Args:
            text: Raw tag string.

        Returns:
            Tag list.
        """
        normalized = text.replace("；", ";").replace("，", ",")
        normalized = normalized.replace("/", ",").replace("、", ",")
        parts: list[str] = []
        for part in normalized.split(";"):
            parts.extend(part.split(","))
        return [value.strip() for value in parts if value.strip()]

    def _format_edit_tags_text(self, tags: list[str]) -> str:
        """Build editable tag line from existing tags.

        Args:
            tags: Existing tags read from image metadata.

        Returns:
            Subtitle text.
        """
        if not tags:
            return self._tr("feature_edit_tags")
        return self._tr("section_tags") + "、".join(tags)

    def _refresh_feature_text_language(self) -> None:
        """Refresh language-dependent list subtitles where safe to translate in place."""
        feature_edit_candidates = {
            DEFAULT_FEATURE_TEXT,
            *(text_map.get("feature_edit_tags", "") for text_map in TRANSLATIONS.values()),
        }
        pending_candidates = {
            text_map.get("status_pending_analysis", "")
            for text_map in TRANSLATIONS.values()
        }
        no_feature_candidates = {
            text_map.get("status_no_obvious_features", "")
            for text_map in TRANSLATIONS.values()
        }
        in_progress_candidates = {
            text_map.get("status_analysis_in_progress", "")
            for text_map in TRANSLATIONS.values()
        }
        exec_failed_candidates = {
            text_map.get("status_exec_failed", "")
            for text_map in TRANSLATIONS.values()
        }

        for path_key in self.image_paths_by_key:
            current_text = self.image_model.feature_for_key(path_key)
            if current_text in feature_edit_candidates:
                self.image_model.set_feature_by_key(path_key, self._tr("feature_edit_tags"))
                continue
            if current_text in pending_candidates:
                self.image_model.set_feature_by_key(path_key, self._tr("status_pending_analysis"))
                continue
            if current_text in no_feature_candidates:
                self.image_model.set_feature_by_key(path_key, self._tr("status_no_obvious_features"))
                continue
            if current_text in in_progress_candidates:
                self.image_model.set_feature_by_key(path_key, self._tr("status_analysis_in_progress"))
                continue
            if current_text in exec_failed_candidates:
                self.image_model.set_feature_by_key(path_key, self._tr("status_exec_failed"))

        # Rebuild analyzed rows from queue records so section prefixes and tag names follow current language.
        if self.image_paths_by_key:
            records = self._load_queue_records(list(self.image_paths_by_key.values()))
            for path_key, record in records.items():
                has_tags = any(str(value).strip() for value in record.get("characters", [])) or any(
                    str(value).strip() for value in record.get("feature_tags", [])
                )
                self.image_model.set_existing_tags_by_key(path_key, self._format_feature_text(record), has_tags)

    def _set_status(self, text: str, is_error: bool = False) -> None:
        """Update status label text and color.

        Args:
            text: Display text.
            is_error: Whether this status is an error.
        """
        self.status_label.setText(text)
        if is_error:
            self.status_label.setStyleSheet("color: #c2362d;")
        else:
            self.status_label.setStyleSheet("color: #637083;")
