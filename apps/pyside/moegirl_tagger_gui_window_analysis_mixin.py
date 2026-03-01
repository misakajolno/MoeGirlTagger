"""Image analysis and metadata behavior mixin for MoeGirlTagger window."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QModelIndex, QItemSelectionModel, QThread
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
from apps.pyside.moegirl_tagger_gui_workers import CallableWorker, ClearTagsWorker
from apps.pyside.moegirl_tagger_gui_dialogs import ClearTagsConfirmDialog
from apps.pyside.moegirl_tagger_gui_tag_editor_dialog import (
    TagEditorDialog,
    pick_localized_alias,
    pick_localized_name,
)


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
        self.edit_tags_button.setVisible(has_items)
        self.clear_tags_button.setVisible(has_items)
        self.remove_tagged_button.setVisible(has_items)
        self._update_batch_edit_button_state()

    def _selected_image_path_keys(self) -> list[str]:
        selection_model = self.list_widget.selectionModel()
        if selection_model is None:
            return []
        keys: list[str] = []
        seen: set[str] = set()
        for index in selection_model.selectedRows():
            key = str(index.data(ImageListModel.ROLE_PATH_KEY) or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
        return keys

    def _update_batch_edit_button_state(self) -> None:
        if not hasattr(self, "edit_tags_button"):
            return
        has_items = bool(self.image_paths_by_key)
        selected_count = len(self._selected_image_path_keys())
        enabled = has_items and selected_count >= 2 and (not self._is_busy())
        self.edit_tags_button.setEnabled(enabled)

    def _on_analysis_selection_changed(self, *_args) -> None:
        self._update_batch_edit_button_state()

    def _is_busy(self) -> bool:
        analysis_running = self.worker_thread is not None and self.worker_thread.isRunning()
        clear_running = self.clear_thread is not None and self.clear_thread.isRunning()
        tag_apply_running = self.tag_apply_thread is not None and self.tag_apply_thread.isRunning()
        return analysis_running or clear_running or tag_apply_running

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
        self.edit_tags_button.setEnabled(False)
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
        self.clear_tags_button.setEnabled(bool(self.image_paths_by_key))
        self.remove_tagged_button.setEnabled(bool(self.image_paths_by_key))
        self._update_batch_edit_button_state()
        self.start_button.setEnabled(True)

    def _lock_image_items(self, keys: set[str]) -> None:
        if not keys:
            return
        self.image_model.set_locked_by_keys(keys, True)
        selection_model = self.list_widget.selectionModel()
        if selection_model is None:
            return
        for key in keys:
            row = self.image_model.row_for_key(key)
            if row is None:
                continue
            index = self.image_model.index(row, 0)
            selection_model.select(index, QItemSelectionModel.Deselect)

    def _unlock_image_items(self, keys: set[str]) -> None:
        if not keys:
            return
        self.image_model.set_locked_by_keys(keys, False)

    def _start_tag_apply_job(self, *, locked_keys: set[str], job, success_handler) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        self.tag_apply_locked_keys = set(locked_keys)
        self._lock_image_items(self.tag_apply_locked_keys)
        self.folder_button.setEnabled(False)
        self.images_button.setEnabled(False)
        self.remove_all_button.setEnabled(False)
        self.edit_tags_button.setEnabled(False)
        self.clear_tags_button.setEnabled(False)
        self.remove_tagged_button.setEnabled(False)
        self.start_button.setEnabled(False)

        self.tag_apply_thread = QThread(self)
        self.tag_apply_worker = CallableWorker(job)
        self.tag_apply_worker.moveToThread(self.tag_apply_thread)

        self.tag_apply_thread.started.connect(self.tag_apply_worker.run)
        self.tag_apply_worker.finished.connect(
            lambda ok, message, payload: self._on_tag_apply_finished(
                ok=ok,
                message=message,
                payload=payload,
                success_handler=success_handler,
            )
        )
        self.tag_apply_worker.finished.connect(self.tag_apply_thread.quit)
        self.tag_apply_worker.finished.connect(self.tag_apply_worker.deleteLater)
        self.tag_apply_thread.finished.connect(self.tag_apply_thread.deleteLater)
        self.tag_apply_thread.finished.connect(self._on_tag_apply_thread_finished)
        self.tag_apply_thread.start()

    def _on_tag_apply_finished(self, *, ok: bool, message: str, payload: object, success_handler) -> None:
        if not ok:
            detail = str(message or "").strip() or "unknown error"
            self._set_status(detail, is_error=True)
            return
        try:
            success_handler(payload)
        except Exception as error:
            self._set_status(str(error).strip() or "unknown error", is_error=True)

    def _on_tag_apply_thread_finished(self) -> None:
        self.tag_apply_thread = None
        self.tag_apply_worker = None
        self._unlock_image_items(set(self.tag_apply_locked_keys))
        self.tag_apply_locked_keys = set()
        self.folder_button.setEnabled(True)
        self.images_button.setEnabled(True)
        self.remove_all_button.setEnabled(True)
        self.clear_tags_button.setEnabled(bool(self.image_paths_by_key))
        self.remove_tagged_button.setEnabled(bool(self.image_paths_by_key))
        self._update_batch_edit_button_state()
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
        if self.tag_apply_thread is not None:
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
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
        self.edit_tags_button.setEnabled(False)
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
        recognize_characters = bool(self.character_recognition_enabled)
        if hasattr(self, "recognize_characters_checkbox"):
            recognize_characters = bool(self.recognize_characters_checkbox.isChecked())
            self.character_recognition_enabled = recognize_characters
        self.worker = AnalysisWorker(
            self.repo_root,
            selected_paths,
            self.queue_output,
            thresholds=self.threshold_values.copy(),
            language_code=self.current_language,
            recognize_characters=recognize_characters,
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_status)
        self.worker.record_ready.connect(self._on_analysis_record_ready)
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
        self.clear_tags_button.setEnabled(bool(self.image_paths_by_key))
        self.remove_tagged_button.setEnabled(bool(self.image_paths_by_key))
        self._update_batch_edit_button_state()
        self.start_button.setText(self._tr("btn_start_analysis"))
        self.start_button.setStyleSheet("")
        self.start_button.setEnabled(True)

    def _append_status(self, text: str) -> None:
        """Append transient status line.

        Args:
            text: Status text.
        """
        self._set_status(f"{self._tr('status_prefix')}: {text}")

    def _on_analysis_record_ready(self, path_key: str, record: object) -> None:
        """Update one row as soon as analysis result for that image is ready."""
        if path_key not in self.image_paths_by_key:
            return
        if not isinstance(record, dict):
            return
        has_tags = any(str(value).strip() for value in record.get("characters", [])) or any(
            str(value).strip() for value in record.get("feature_tags", [])
        )
        self.image_model.set_existing_tags_by_key(path_key, self._format_feature_text(record), has_tags)

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
        def collect_values(fields: list[str]) -> list[str]:
            values: list[str] = []
            for field in fields:
                value = payload.get(field)
                if value is None:
                    continue
                if isinstance(value, list):
                    values.extend([str(item).strip() for item in value if str(item).strip()])
                    continue
                values.append(str(value).strip())
            return values

        def normalize_tokens(values: list[str]) -> list[str]:
            result: list[str] = []
            seen: set[str] = set()
            for raw in values:
                for token in self._split_tags_text(raw):
                    text = str(token or "").strip()
                    if not text or self._is_malformed_metadata_tag(text):
                        continue
                    if text in seen:
                        continue
                    seen.add(text)
                    result.append(text)
            return result

        primary_tags = normalize_tokens(collect_values(["Subject", "Keywords", "XMP-dc:Subject"]))
        if primary_tags:
            return primary_tags
        return normalize_tokens(collect_values(["XPKeywords"]))

    def _is_malformed_metadata_tag(self, text: str) -> bool:
        token = str(text or "").strip()
        if not token:
            return True
        # Skip placeholder-like mojibake tokens, e.g. "??" introduced by bad XPKeywords decoding.
        if all(ch in {"?", "？", "�"} for ch in token):
            return True
        return False

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

    def _open_tag_editor_dialog(self, path_key: str | None = None) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        selected_path_key = str(path_key or "").strip()
        if selected_path_key:
            row = self.image_model.row_for_key(selected_path_key)
            if row is not None:
                self.list_widget.setCurrentIndex(self.image_model.index(row, 0))

        current_index = self.list_widget.currentIndex()
        if not current_index.isValid() and selected_path_key:
            row = self.image_model.row_for_key(selected_path_key)
            if row is not None:
                current_index = self.image_model.index(row, 0)
        if not current_index.isValid():
            self._set_status(self._tr("status_tag_editor_no_selection"), is_error=True)
            return

        path_key = str(current_index.data(ImageListModel.ROLE_PATH_KEY) or "").strip()
        image_path = self.image_paths_by_key.get(path_key)
        if image_path is None:
            self._set_status(self._tr("status_tag_editor_no_selection"), is_error=True)
            return

        feature_groups = self._build_tag_editor_feature_groups()
        feature_token_set = self._collect_feature_token_ids(feature_groups)
        feature_alias_to_id = self._collect_feature_alias_to_id(feature_groups)
        character_groups, name_to_character_id, character_id_to_store_value = self._build_tag_editor_character_groups()
        records = self._load_queue_records([image_path])
        record = records.get(path_key, {})
        existing_tags_by_key = self._load_existing_image_tags([image_path])
        existing_tags = existing_tags_by_key.get(path_key, [])

        initial_feature_tags = self._merge_dedup_lists(
            self._resolve_feature_tags_from_existing(
                self._dedupe_non_empty(record.get("feature_tags", [])),
                feature_token_set,
                feature_alias_to_id,
            ),
            self._resolve_feature_tags_from_existing(
                existing_tags,
                feature_token_set,
                feature_alias_to_id,
            ),
        )
        initial_character_ids = self._resolve_initial_character_ids(
            self._merge_dedup_lists(
                self._dedupe_non_empty(record.get("characters", [])),
                self._resolve_character_names_from_existing(existing_tags, name_to_character_id),
            ),
            name_to_character_id,
        )

        dialog = TagEditorDialog(
            parent=self,
            title=self._tr("tag_editor_dialog_title"),
            left_title=self._tr("tag_editor_left_title"),
            right_title=self._tr("tag_editor_right_title"),
            rules_text=self._tr("tag_editor_rules"),
            apply_text=self._tr("tag_editor_apply"),
            cancel_text=self._tr("tag_editor_cancel"),
            feature_groups=feature_groups,
            character_groups=character_groups,
            initial_feature_tags=initial_feature_tags,
            initial_characters=initial_character_ids,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        selected_features = dialog.selected_feature_tags()
        selected_character_ids = dialog.selected_characters()
        selected_characters: list[str] = []
        for character_id in selected_character_ids:
            normalized_id = str(character_id).strip()
            if not normalized_id:
                continue
            store_value = character_id_to_store_value.get(normalized_id, normalized_id)
            if store_value not in selected_characters:
                selected_characters.append(store_value)

        selected_features = list(selected_features)
        selected_characters = list(selected_characters)
        selected_count = len(selected_features) + len(selected_characters)

        def run_single_apply_job() -> dict:
            metadata_feature_tags = self._feature_ids_to_metadata_tags(selected_features)
            metadata_tags = self._merge_dedup_lists(metadata_feature_tags, selected_characters)
            metadata_write_error: str | None = None
            exiftool = self._find_exiftool_binary()
            if exiftool is not None and image_path.exists():
                try:
                    self._write_image_metadata_tags(exiftool, {image_path: metadata_tags})
                except Exception as error:
                    metadata_write_error = str(error).strip() or "unknown error"

            updated_record = self._save_queue_record_for_image(
                image_path=image_path,
                feature_tags=selected_features,
                characters=selected_characters,
            )
            return {
                "path_key": path_key,
                "updated_record": updated_record,
                "selected_count": selected_count,
                "metadata_write_error": metadata_write_error,
            }

        def on_single_apply_success(payload: object) -> None:
            if not isinstance(payload, dict):
                raise RuntimeError("invalid tag-apply payload")
            result_key = str(payload.get("path_key", "")).strip() or path_key
            updated_record = payload.get("updated_record", {})
            if not isinstance(updated_record, dict):
                updated_record = {}
            has_tags = any(str(value).strip() for value in updated_record.get("characters", [])) or any(
                str(value).strip() for value in updated_record.get("feature_tags", [])
            )
            self.image_model.set_existing_tags_by_key(result_key, self._format_feature_text(updated_record), has_tags)

            metadata_write_error = str(payload.get("metadata_write_error", "") or "").strip()
            if metadata_write_error:
                self._set_status(
                    self._tr("status_tag_editor_batch_write_failed", error=metadata_write_error),
                    is_error=True,
                )
                return
            count_value = int(payload.get("selected_count", selected_count))
            self._set_status(self._tr("status_tag_editor_saved", count=count_value))

        self._start_tag_apply_job(
            locked_keys={path_key},
            job=run_single_apply_job,
            success_handler=on_single_apply_success,
        )

    def _open_batch_tag_editor_dialog(self) -> None:
        if self._is_busy():
            self._set_status(self._tr("status_busy_modify_list"), is_error=True)
            return

        selected_keys = self._selected_image_path_keys()
        if len(selected_keys) < 2:
            self._set_status(self._tr("status_tag_editor_multi_required"), is_error=True)
            self._update_batch_edit_button_state()
            return

        selected_items: list[tuple[str, Path]] = []
        for key in selected_keys:
            image_path = self.image_paths_by_key.get(key)
            if image_path is not None:
                selected_items.append((key, image_path))
        selected_paths = [path for _, path in selected_items]
        if len(selected_paths) < 2:
            self._set_status(self._tr("status_tag_editor_multi_required"), is_error=True)
            self._update_batch_edit_button_state()
            return

        feature_groups = self._build_tag_editor_feature_groups()
        character_groups, _name_to_character_id, character_id_to_store_value = self._build_tag_editor_character_groups()

        dialog = TagEditorDialog(
            parent=self,
            title=self._tr("tag_editor_dialog_title"),
            left_title=self._tr("tag_editor_left_title"),
            right_title=self._tr("tag_editor_right_title"),
            rules_text=self._tr("tag_editor_rules"),
            apply_text=self._tr("tag_editor_apply"),
            cancel_text=self._tr("tag_editor_cancel"),
            feature_groups=feature_groups,
            character_groups=character_groups,
            initial_feature_tags=[],
            initial_characters=[],
        )
        if dialog.exec() != QDialog.Accepted:
            return

        selected_features = dialog.selected_feature_tags()
        selected_character_ids = dialog.selected_characters()
        selected_characters: list[str] = []
        for character_id in selected_character_ids:
            normalized_id = str(character_id).strip()
            if not normalized_id:
                continue
            store_value = character_id_to_store_value.get(normalized_id, normalized_id)
            if store_value not in selected_characters:
                selected_characters.append(store_value)

        if not selected_features and not selected_characters:
            self._set_status(self._tr("status_tag_editor_batch_no_changes"))
            return

        exiftool = self._find_exiftool_binary()
        if exiftool is None:
            self._set_status(self._tr("status_tag_editor_batch_missing_exiftool"), is_error=True)
            return
        selected_features = list(selected_features)
        selected_characters = list(selected_characters)
        selected_items = [(str(key).strip(), path) for key, path in selected_items if str(key).strip()]
        selected_paths = [path for _, path in selected_items]
        locked_keys = {key for key, _ in selected_items}

        def run_batch_apply_job() -> dict:
            existing_tags_by_key = self._load_existing_image_tags(selected_paths)
            metadata_feature_tags = self._feature_ids_to_metadata_tags(selected_features)
            metadata_append_tokens = self._merge_dedup_lists(metadata_feature_tags, selected_characters)

            image_to_tags: dict[Path, list[str]] = {}
            for key, image_path in selected_items:
                existing_tags = existing_tags_by_key.get(key, [])
                image_to_tags[image_path] = self._merge_dedup_lists(existing_tags, metadata_append_tokens)

            try:
                self._write_image_metadata_tags(exiftool, image_to_tags)
            except Exception as error:
                raise RuntimeError(
                    self._tr("status_tag_editor_batch_write_failed", error=str(error).strip() or "unknown error")
                ) from error

            records_by_key = self._append_queue_tags_for_images(
                image_paths=selected_paths,
                feature_tags=selected_features,
                characters=selected_characters,
            )
            return {
                "selected_items": selected_items,
                "image_to_tags": image_to_tags,
                "records_by_key": records_by_key,
                "count": len(selected_paths),
                "feature_count": len(selected_features),
                "character_count": len(selected_characters),
            }

        def on_batch_apply_success(payload: object) -> None:
            if not isinstance(payload, dict):
                raise RuntimeError("invalid tag-apply payload")
            payload_items = payload.get("selected_items", [])
            image_to_tags = payload.get("image_to_tags", {})
            records_by_key = payload.get("records_by_key", {})
            if not isinstance(payload_items, list) or not isinstance(image_to_tags, dict) or not isinstance(
                records_by_key, dict
            ):
                raise RuntimeError("invalid tag-apply payload")

            for key, image_path in payload_items:
                normalized_key = str(key).strip()
                if not normalized_key:
                    continue
                merged_tags = self._dedupe_non_empty(image_to_tags.get(image_path, []))
                if merged_tags:
                    self.image_model.set_existing_tags_by_key(normalized_key, self._format_edit_tags_text(merged_tags), True)
                    continue
                record = records_by_key.get(normalized_key)
                if not isinstance(record, dict):
                    continue
                has_tags = any(str(value).strip() for value in record.get("characters", [])) or any(
                    str(value).strip() for value in record.get("feature_tags", [])
                )
                self.image_model.set_existing_tags_by_key(normalized_key, self._format_feature_text(record), has_tags)

            self._set_status(
                self._tr(
                    "status_tag_editor_batch_saved",
                    count=int(payload.get("count", len(selected_paths))),
                    feature_count=int(payload.get("feature_count", len(selected_features))),
                    character_count=int(payload.get("character_count", len(selected_characters))),
                )
            )

        self._start_tag_apply_job(
            locked_keys=locked_keys,
            job=run_batch_apply_job,
            success_handler=on_batch_apply_success,
        )

    def _build_tag_editor_feature_groups(self) -> list[dict]:
        taxonomy_path = (self.repo_root / "data/character_library/feature_taxonomy.json").resolve()
        if not taxonomy_path.exists():
            return []
        try:
            payload = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        categories = payload.get("categories", []) if isinstance(payload, dict) else []
        if not isinstance(categories, list):
            return []

        groups: list[dict] = []
        for category in categories:
            if not isinstance(category, dict):
                continue
            category_id = str(category.get("id", "")).strip()
            category_name = pick_localized_name(
                language_code=self.current_language,
                name_i18n=self._collect_name_i18n(category),
                fallback_text=category_id,
            )
            if not category_name:
                category_name = category_id
            tags_payload = category.get("tags", [])
            if not isinstance(tags_payload, list):
                continue

            items: list[dict] = []
            for tag in tags_payload:
                if not isinstance(tag, dict):
                    continue
                tag_id = str(tag.get("id", "")).strip()
                if not tag_id:
                    continue
                tag_name = pick_localized_name(
                    language_code=self.current_language,
                    name_i18n=self._collect_name_i18n(tag),
                    fallback_text=tag_id,
                )
                items.append(
                    {
                        "value": tag_id,
                        "display": tag_name,
                        "store_value": tag_id,
                        "aliases": self._build_feature_aliases(tag, tag_id, tag_name),
                    }
                )
            if not items:
                continue
            groups.append(
                {
                    "group_key": f"feature:{category_id}",
                    "group_name": f"{self._tr('tag_editor_feature_group_prefix')}{category_name}",
                    "items": items,
                }
            )
        return groups

    def _build_tag_editor_character_groups(self) -> tuple[list[dict], dict[str, str], dict[str, str]]:
        records = self.character_manager_service.list_characters()
        groups_by_source: dict[str, dict] = {}
        name_to_character_id: dict[str, str] = {}
        character_id_to_store_value: dict[str, str] = {}

        for record in records:
            if not isinstance(record, dict):
                continue
            if not bool(record.get("enabled", True)):
                continue
            character_id = str(record.get("id", "")).strip()
            if not character_id:
                continue

            source_fallback = str(record.get("source_title", "")).strip()
            source_display = pick_localized_alias(
                language_code=self.current_language,
                aliases=record.get("source_aliases"),
                fallback_text=source_fallback,
            )
            if not source_display:
                source_display = source_fallback or "Unknown"

            character_fallback = str(record.get("display_name", "")).strip()
            character_display = pick_localized_alias(
                language_code=self.current_language,
                aliases=record.get("aliases"),
                fallback_text=character_fallback,
            )
            if not character_display:
                character_display = character_fallback or character_id

            group_key = f"source:{source_display.casefold()}"
            group = groups_by_source.get(group_key)
            if group is None:
                group = {
                    "group_key": group_key,
                    "group_name": f"{self._tr('tag_editor_character_group_prefix')}{source_display}",
                    "source_name": source_display,
                    "items": [],
                }
                groups_by_source[group_key] = group

            group["items"].append(
                {
                    "value": character_id,
                    "display": character_display,
                    "store_value": character_id,
                }
            )

            store_value = character_fallback or character_display
            character_id_to_store_value[character_id] = store_value
            self._index_character_name(name_to_character_id, character_id, store_value)
            self._index_character_name(name_to_character_id, character_id, character_display)
            aliases = record.get("aliases")
            if isinstance(aliases, list):
                for alias_entry in aliases:
                    if not isinstance(alias_entry, dict):
                        continue
                    self._index_character_name(name_to_character_id, character_id, alias_entry.get("name"))

        groups = sorted(groups_by_source.values(), key=lambda group: str(group.get("source_name", "")))
        for group in groups:
            items = group.get("items", [])
            if not isinstance(items, list):
                continue
            group["items"] = sorted(items, key=lambda entry: str(entry.get("display", "")))
        return groups, name_to_character_id, character_id_to_store_value

    def _collect_name_i18n(self, payload: dict) -> dict[str, object]:
        result: dict[str, object] = {}
        source = payload.get("name_i18n")
        if isinstance(source, dict):
            result.update(source)

        def put_once(language_code: str, value: object) -> None:
            text = str(value or "").strip()
            if not text:
                return
            if language_code not in result:
                result[language_code] = text

        put_once("zh-CN", payload.get("name_zh_cn"))
        put_once("zh-CN", payload.get("name_zh"))
        put_once("en-US", payload.get("name_en_us"))
        put_once("en-US", payload.get("name_en"))
        put_once("ja-JP", payload.get("name_ja_jp"))
        put_once("ja-JP", payload.get("name_ja"))
        put_once("ko-KR", payload.get("name_ko_kr"))
        put_once("ko-KR", payload.get("name_ko"))
        return result

    def _index_character_name(self, name_to_character_id: dict[str, str], character_id: str, name: object) -> None:
        text = str(name or "").strip()
        if not text:
            return
        lowered = text.casefold()
        if lowered and lowered not in name_to_character_id:
            name_to_character_id[lowered] = character_id

    def _resolve_initial_character_ids(self, characters: object, name_to_character_id: dict[str, str]) -> list[str]:
        result: list[str] = []
        values = characters if isinstance(characters, list) else []
        for value in values:
            key = str(value or "").strip().casefold()
            if not key:
                continue
            character_id = name_to_character_id.get(key, "")
            if character_id and character_id not in result:
                result.append(character_id)
        return result

    def _collect_feature_token_ids(self, feature_groups: list[dict]) -> set[str]:
        result: set[str] = set()
        for group in feature_groups:
            if not isinstance(group, dict):
                continue
            items = group.get("items")
            if not isinstance(items, list):
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                value = str(entry.get("value", "")).strip()
                if value:
                    result.add(value)
        return result

    def _collect_feature_alias_to_id(self, feature_groups: list[dict]) -> dict[str, str]:
        result: dict[str, str] = {}
        for group in feature_groups:
            if not isinstance(group, dict):
                continue
            items = group.get("items")
            if not isinstance(items, list):
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                tag_id = str(entry.get("value", "")).strip()
                if not tag_id:
                    continue
                for alias in entry.get("aliases", []):
                    text = str(alias or "").strip()
                    if not text:
                        continue
                    key = text.casefold()
                    if key and key not in result:
                        result[key] = tag_id
        return result

    def _resolve_feature_tags_from_existing(
        self,
        tags: list[str],
        feature_token_set: set[str],
        feature_alias_to_id: dict[str, str],
    ) -> list[str]:
        result: list[str] = []
        if not feature_token_set:
            return result
        for token in tags:
            raw = self._strip_known_tag_prefix(str(token or "").strip())
            if not raw:
                continue
            if raw in feature_token_set and raw not in result:
                result.append(raw)
                continue
            normalized = re.sub(r"[_\\-\\s]+", "_", raw).strip("_").lower()
            if normalized in feature_token_set and normalized not in result:
                result.append(normalized)
                continue
            alias_key = raw.casefold()
            mapped = feature_alias_to_id.get(alias_key, "")
            if mapped and mapped not in result:
                result.append(mapped)
                continue
            mapped = feature_alias_to_id.get(normalized.casefold(), "")
            if mapped and mapped not in result:
                result.append(mapped)
        return result

    def _resolve_character_names_from_existing(
        self,
        tags: list[str],
        name_to_character_id: dict[str, str],
    ) -> list[str]:
        result: list[str] = []
        if not name_to_character_id:
            return result
        for token in tags:
            raw = self._strip_known_tag_prefix(str(token or "").strip())
            if not raw:
                continue
            key = raw.casefold()
            if key in name_to_character_id and raw not in result:
                result.append(raw)
        return result

    def _resolve_character_store_names_from_existing(
        self,
        tags: list[str],
        name_to_character_id: dict[str, str],
        character_id_to_store_value: dict[str, str],
    ) -> list[str]:
        result: list[str] = []
        for token in tags:
            raw = self._strip_known_tag_prefix(str(token or "").strip())
            if not raw:
                continue
            key = raw.casefold()
            character_id = name_to_character_id.get(key, "")
            if not character_id:
                continue
            store_value = character_id_to_store_value.get(character_id, raw)
            if store_value and store_value not in result:
                result.append(store_value)
        return result

    def _build_feature_aliases(self, tag_payload: dict, tag_id: str, display_name: str) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()

        def append(value: object) -> None:
            text = str(value or "").strip()
            if not text:
                return
            key = text.casefold()
            if key in seen:
                return
            seen.add(key)
            aliases.append(text)

        append(tag_id)
        append(display_name)
        localized_names = self._collect_name_i18n(tag_payload)
        for value in localized_names.values():
            append(value)
        append(tag_payload.get("name_zh"))
        append(tag_payload.get("name_en"))
        append(tag_payload.get("name_ja"))
        append(tag_payload.get("name_ko"))
        return aliases

    def _strip_known_tag_prefix(self, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""
        prefixes = {
            "标签：",
            "标签:",
            "Tags:",
            "Tags：",
            "タグ:",
            "タグ：",
            "태그:",
            "태그：",
            *(entry.get("section_tags", "") for entry in TRANSLATIONS.values()),
        }
        for prefix in prefixes:
            normalized_prefix = str(prefix or "").strip()
            if not normalized_prefix:
                continue
            if value.startswith(normalized_prefix):
                return value[len(normalized_prefix) :].strip()
        return value

    def _dedupe_non_empty(self, values: object) -> list[str]:
        entries = values if isinstance(values, list) else []
        result: list[str] = []
        seen: set[str] = set()
        for value in entries:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    def _save_queue_record_for_image(
        self,
        *,
        image_path: Path,
        feature_tags: list[str],
        characters: list[str],
    ) -> dict:
        target_key = normalize_path_key(image_path)
        queue_records: list[dict] = []
        updated_record: dict | None = None
        timestamp = dt.datetime.now().replace(microsecond=0).isoformat()
        normalized_feature_tags = self._dedupe_non_empty(feature_tags)
        normalized_characters = self._dedupe_non_empty(characters)

        if self.queue_output.exists():
            with self.queue_output.open("r", encoding="utf-8") as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    payload_key = self._resolve_queue_payload_path_key(payload)
                    if payload_key == target_key:
                        payload["feature_tags"] = normalized_feature_tags
                        payload["characters"] = normalized_characters
                        payload["updated_at"] = timestamp
                        if "status" not in payload:
                            payload["status"] = "labeled_draft"
                        if "review_required" not in payload:
                            payload["review_required"] = bool(normalized_feature_tags or normalized_characters)
                        updated_record = payload
                    queue_records.append(payload)

        if updated_record is None:
            updated_record = {
                "image_id": "",
                "image_path": str(image_path),
                "characters": normalized_characters,
                "feature_tags": normalized_feature_tags,
                "source_game": [],
                "review_required": bool(normalized_feature_tags or normalized_characters),
                "status": "labeled_draft",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            queue_records.append(updated_record)

        self.queue_output.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.queue_output.with_suffix(self.queue_output.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            for payload in queue_records:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        temp_path.replace(self.queue_output)
        return updated_record

    def _feature_ids_to_metadata_tags(self, feature_ids: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for feature_id in feature_ids:
            token = str(feature_id or "").strip()
            if not token:
                continue
            display = self._resolve_feature_tag_display_name(token).strip() or token
            key = display.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(display)
        return result

    def _write_image_metadata_tags(self, exiftool: Path, image_to_tags: dict[Path, list[str]]) -> None:
        for image_path, tags in image_to_tags.items():
            normalized_tags = self._dedupe_non_empty(tags)
            tag_text = "; ".join(normalized_tags)
            args_lines = [
                "-overwrite_original",
                "-P",
                "-m",
                "-charset",
                "exiftool=utf8",
                f"-XMP-dc:Subject={tag_text}",
                f"-Keywords={tag_text}",
            ]
            if image_path.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff"}:
                args_lines.append(f"-XPKeywords={tag_text}")
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

    def _append_queue_tags_for_images(
        self,
        *,
        image_paths: list[Path],
        feature_tags: list[str],
        characters: list[str],
    ) -> dict[str, dict]:
        target_by_key = {normalize_path_key(path): path for path in image_paths}
        target_keys = set(target_by_key.keys())
        if not target_keys:
            return {}

        queue_records: list[dict] = []
        updated_records: dict[str, dict] = {}
        timestamp = dt.datetime.now().replace(microsecond=0).isoformat()
        normalized_feature_tags = self._dedupe_non_empty(feature_tags)
        normalized_characters = self._dedupe_non_empty(characters)

        if self.queue_output.exists():
            with self.queue_output.open("r", encoding="utf-8") as file:
                for raw_line in file:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue

                    payload_key = self._resolve_queue_payload_path_key(payload)
                    if payload_key in target_keys:
                        existing_features = self._dedupe_non_empty(payload.get("feature_tags", []))
                        existing_characters = self._dedupe_non_empty(payload.get("characters", []))
                        payload["feature_tags"] = self._merge_dedup_lists(existing_features, normalized_feature_tags)
                        payload["characters"] = self._merge_dedup_lists(existing_characters, normalized_characters)
                        payload["updated_at"] = timestamp
                        if "status" not in payload:
                            payload["status"] = "labeled_draft"
                        if "review_required" not in payload:
                            payload["review_required"] = bool(payload["feature_tags"] or payload["characters"])
                        updated_records[payload_key] = payload

                    queue_records.append(payload)

        for target_key in target_keys:
            if target_key in updated_records:
                continue
            image_path = target_by_key.get(target_key)
            if image_path is None:
                continue
            created = {
                "image_id": "",
                "image_path": str(image_path),
                "characters": list(normalized_characters),
                "feature_tags": list(normalized_feature_tags),
                "source_game": [],
                "review_required": bool(normalized_feature_tags or normalized_characters),
                "status": "labeled_draft",
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            queue_records.append(created)
            updated_records[target_key] = created

        self.queue_output.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.queue_output.with_suffix(self.queue_output.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            for payload in queue_records:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        temp_path.replace(self.queue_output)
        return updated_records

    def _merge_dedup_lists(self, base: list[str], appended: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in base + appended:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
        return merged

    def _resolve_queue_payload_path_key(self, payload: dict) -> str:
        raw_path = str(payload.get("image_path", "")).strip()
        if not raw_path:
            return ""
        image_path = Path(raw_path)
        resolved = image_path if image_path.is_absolute() else (self.repo_root / image_path)
        return normalize_path_key(resolved)

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
