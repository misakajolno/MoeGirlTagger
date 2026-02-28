"""Character management behavior mixin for MoeGirlTagger window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtGui import QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QListWidgetItem

from apps.pyside.moegirl_tagger_gui_dialogs import CharacterMergeConfirmDialog, ClearTagsConfirmDialog
from apps.pyside.moegirl_tagger_gui_workers import (
    CharacterBulkBuildWorker,
    CharacterDeleteWorker,
    CharacterSearchWorker,
)
from core.moegirl_tagger.character_search_provider import SearchCandidate
from core.moegirl_tagger.custom_character_store import select_localized_alias, select_localized_source_title


def resolve_character_library_row(preferred_row: int | None, item_count: int) -> int:
    """Resolve target cursor row for library list after reload."""
    count = int(item_count)
    if count <= 0:
        return -1
    if preferred_row is None:
        return 0
    try:
        row = int(preferred_row)
    except (TypeError, ValueError):
        row = 0
    if row < 0:
        return 0
    if row >= count:
        return count - 1
    return row


def resolve_character_delete_anchor_row(current_row: int, selected_rows: list[int]) -> int:
    """Keep cursor location after delete; fallback to first selected row."""
    try:
        row = int(current_row)
    except (TypeError, ValueError):
        row = -1
    if row >= 0:
        return row
    candidates: list[int] = []
    for value in selected_rows:
        try:
            candidate = int(value)
        except (TypeError, ValueError):
            continue
        if candidate >= 0:
            candidates.append(candidate)
    if candidates:
        return min(candidates)
    return 0


def build_top_cover_rounded_avatar(source: QPixmap, *, size: int = 46, radius: int = 8) -> QPixmap:
    """Render avatar as square cover image cropped from top with rounded corners."""
    edge = max(1, int(size))
    rounded = max(0.0, min(float(radius), float(edge) / 2.0))
    target = QPixmap(edge, edge)
    target.fill(Qt.transparent)
    if source.isNull():
        return target

    scaled = source.scaled(edge, edge, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - edge) // 2)
    y = 0
    cropped = scaled.copy(x, y, edge, edge)

    painter = QPainter(target)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0.0, 0.0, float(edge), float(edge), rounded, rounded)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return target


class MoeGirlTaggerWindowCharacterMixin:
    """Handle character search/import/delete/bulk actions."""

    def _icon_from_avatar_bytes(self, avatar_bytes: bytes) -> QIcon:
        if not avatar_bytes:
            return QIcon()
        pixmap = QPixmap()
        if not pixmap.loadFromData(avatar_bytes):
            return QIcon()
        return self._build_character_avatar_icon(pixmap)

    def _character_avatar_edge(self) -> int:
        search_list = getattr(self, "character_search_list", None)
        if search_list is not None:
            size = search_list.iconSize()
            if size.width() > 0 and size.height() > 0:
                return max(1, min(int(size.width()), int(size.height())))
        library_list = getattr(self, "character_library_list", None)
        if library_list is not None:
            size = library_list.iconSize()
            if size.width() > 0 and size.height() > 0:
                return max(1, min(int(size.width()), int(size.height())))
        return 46

    def _build_character_avatar_icon(self, pixmap: QPixmap) -> QIcon:
        if pixmap.isNull():
            return QIcon()
        edge = self._character_avatar_edge()
        rounded = build_top_cover_rounded_avatar(pixmap, size=edge, radius=max(6, edge // 5))
        return QIcon(rounded)

    def _render_search_candidates(
        self,
        candidates: list[SearchCandidate],
        avatar_payloads: dict[int, bytes] | None = None,
    ) -> None:
        self.search_candidates = list(candidates)
        self.character_search_list.clear()
        payloads = avatar_payloads if avatar_payloads is not None else {}
        resolved_payloads: dict[int, bytes] = {}
        for raw_index, raw_payload in payloads.items():
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if index < 0:
                continue
            payload_bytes = bytes(raw_payload) if raw_payload else b""
            if payload_bytes:
                resolved_payloads[index] = payload_bytes
        self.search_candidate_avatar_payloads = resolved_payloads
        for index, candidate in enumerate(self.search_candidates):
            source = candidate.source_title if candidate.source_title else "-"
            item = QListWidgetItem(f"{candidate.display_name}  |  {source}")
            item.setData(Qt.UserRole, index)
            icon = self._icon_from_avatar_bytes(resolved_payloads.get(index, b""))
            if icon.isNull():
                url = str(candidate.avatar_url).strip()
                if url:
                    icon = self.character_icon_cache.get(url, QIcon())
            if not icon.isNull():
                item.setIcon(icon)
                url = str(candidate.avatar_url).strip()
                if url:
                    self.character_icon_cache[url] = icon
            item.setSizeHint(QSize(0, 50))
            self.character_search_list.addItem(item)
        if self.character_search_list.count() > 0:
            self.character_search_list.setCurrentRow(0)

    def _selected_search_candidate_entries(self) -> list[tuple[int, SearchCandidate]]:
        items = self.character_search_list.selectedItems()
        if not items:
            current_item = self.character_search_list.currentItem()
            if current_item is not None:
                items = [current_item]
        results: list[tuple[int, SearchCandidate]] = []
        seen_indices: set[int] = set()
        for item in items:
            raw_index = item.data(Qt.UserRole)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(self.search_candidates):
                continue
            if index in seen_indices:
                continue
            seen_indices.add(index)
            results.append((index, self.search_candidates[index]))
        return results

    def _reload_character_library_list(self, preferred_row: int | None = None) -> None:
        self.character_library_list.clear()
        records = self.character_manager_service.list_characters()
        language_code = str(getattr(self, "current_language", "zh-CN")).strip() or "zh-CN"
        for record in records:
            name = select_localized_alias(record, language_code).strip() or "?"
            source = select_localized_source_title(record, language_code).strip() or "-"
            refs_count = len([value for value in record.get("reference_images", []) if str(value).strip()])
            enabled = bool(record.get("enabled", True))
            disabled_suffix = "" if enabled else f" {self._tr('character_library_list_disabled_suffix')}"
            refs_label = self._tr("character_library_list_refs_label")
            item = QListWidgetItem(f"{name}{disabled_suffix}  |  {source}  |  {refs_label}{refs_count}")
            character_id = str(record.get("id", "")).strip()
            item.setData(Qt.UserRole, character_id)
            avatar_relative = str(record.get("avatar_local_path", "")).strip()
            if avatar_relative:
                avatar_path = (self.character_manager_service.custom_root / avatar_relative).resolve()
                if avatar_path.exists():
                    pixmap = QPixmap(str(avatar_path))
                    icon = self._build_character_avatar_icon(pixmap)
                    if not icon.isNull():
                        item.setIcon(icon)
            item.setSizeHint(QSize(0, 50))
            self.character_library_list.addItem(item)
        target_row = resolve_character_library_row(preferred_row, self.character_library_list.count())
        if target_row >= 0:
            self.character_library_list.setCurrentRow(target_row)

    def _selected_search_candidates(self) -> list[SearchCandidate]:
        return [candidate for _index, candidate in self._selected_search_candidate_entries()]

    def _selected_search_candidate(self) -> SearchCandidate | None:
        selected = self._selected_search_candidates()
        if not selected:
            return None
        return selected[0]

    def _selected_library_character_id(self) -> str:
        character_ids = self._selected_library_character_ids()
        if not character_ids:
            return ""
        return character_ids[0]

    def _selected_library_character_ids(self) -> list[str]:
        items = self.character_library_list.selectedItems()
        if not items:
            current_item = self.character_library_list.currentItem()
            if current_item is not None:
                items = [current_item]
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            character_id = str(item.data(Qt.UserRole) or "").strip()
            if not character_id or character_id in seen:
                continue
            seen.add(character_id)
            result.append(character_id)
        return result

    def _search_characters_online(self) -> None:
        keyword = self.character_search_input.text().strip()
        if not keyword:
            self._set_status(self._tr("status_character_search_empty_keyword"), is_error=True)
            return
        if self.character_search_thread is not None and self.character_search_thread.isRunning():
            self._set_status(self._tr("status_character_searching"))
            return

        self.character_search_button.setEnabled(False)
        self.character_import_button.setEnabled(False)
        self.character_search_list.setEnabled(False)
        self._set_status(self._tr("status_character_searching"))

        self.character_search_thread = QThread(self)
        self.character_search_worker = CharacterSearchWorker(
            self.character_manager_service,
            keyword=keyword,
            limit=50,
        )
        self.character_search_worker.moveToThread(self.character_search_thread)

        self.character_search_thread.started.connect(self.character_search_worker.run)
        self.character_search_worker.finished.connect(self._on_character_search_finished)
        self.character_search_worker.finished.connect(self.character_search_thread.quit)
        self.character_search_worker.finished.connect(self.character_search_worker.deleteLater)
        self.character_search_thread.finished.connect(self.character_search_thread.deleteLater)
        self.character_search_thread.finished.connect(self._on_character_search_thread_finished)
        self.character_search_thread.start()

    def _on_character_search_finished(
        self,
        ok: bool,
        message: str,
        candidates: object,
        avatar_payloads: object,
    ) -> None:
        if not ok:
            self._render_search_candidates([])
            self._set_status(self._tr("status_character_search_failed", error=message), is_error=True)
            return

        resolved_candidates = candidates if isinstance(candidates, list) else []
        resolved_avatars = avatar_payloads if isinstance(avatar_payloads, dict) else {}
        self._render_search_candidates(resolved_candidates, avatar_payloads=resolved_avatars)
        self._set_status(self._tr("status_character_search_done", count=len(resolved_candidates)))

    def _on_character_search_thread_finished(self) -> None:
        self.character_search_thread = None
        self.character_search_worker = None
        if self._is_character_bulk_build_running() or self._is_character_delete_running():
            return
        self.character_search_button.setEnabled(True)
        self.character_import_button.setEnabled(True)
        self.character_search_list.setEnabled(True)

    def _is_character_bulk_build_running(self) -> bool:
        return self.character_bulk_thread is not None and self.character_bulk_thread.isRunning()

    def _is_character_delete_running(self) -> bool:
        return self.character_delete_thread is not None and self.character_delete_thread.isRunning()

    def _reset_character_bulk_progress(self) -> None:
        self.character_bulk_progress.setRange(0, 1)
        self.character_bulk_progress.setValue(0)
        self.character_bulk_progress.setFormat("0 / 0")

    def _set_character_bulk_progress_busy(self) -> None:
        self.character_bulk_progress.setRange(0, 0)
        self.character_bulk_progress.setValue(0)
        self.character_bulk_progress.setFormat(self._tr("status_character_bulk_progress_waiting"))

    def _set_character_bulk_progress_value(self, processed: int, total: int) -> None:
        safe_total = max(1, int(total))
        bounded_processed = max(0, min(int(processed), safe_total))
        self.character_bulk_progress.setRange(0, safe_total)
        self.character_bulk_progress.setValue(bounded_processed)
        self.character_bulk_progress.setFormat(f"{bounded_processed} / {safe_total}")

    def _set_character_bulk_widgets_enabled(self, enabled: bool) -> None:
        self.character_search_button.setEnabled(enabled)
        self.character_search_input.setEnabled(enabled)
        self.character_import_button.setEnabled(enabled)
        self.character_add_refs_button.setEnabled(enabled)
        self.character_delete_button.setEnabled(enabled)
        self.character_refresh_button.setEnabled(enabled)
        self.character_bulk_button.setEnabled(enabled)
        self.character_bulk_count_spin.setEnabled(enabled)
        self.character_search_list.setEnabled(enabled)
        self.character_library_list.setEnabled(enabled)

    def _set_character_delete_widgets_enabled(self, enabled: bool) -> None:
        self.character_delete_button.setEnabled(enabled)
        self.character_library_list.setEnabled(enabled)

    def _confirm_first_bulk_build(self, limit: int) -> bool:
        dialog = ClearTagsConfirmDialog(
            self,
            self._tr("dialog_character_bulk_first_title"),
            self._tr("dialog_character_bulk_first_message", count=limit),
            self._tr("dialog_character_bulk_first_confirm"),
            self._tr("dialog_character_bulk_first_cancel"),
        )
        return dialog.exec() == QDialog.Accepted

    def _confirm_interrupt_bulk_build(self) -> bool:
        dialog = ClearTagsConfirmDialog(
            self,
            self._tr("dialog_character_bulk_interrupt_title"),
            self._tr("dialog_character_bulk_interrupt_message"),
            self._tr("dialog_character_bulk_interrupt_confirm"),
            self._tr("dialog_character_bulk_interrupt_cancel"),
        )
        return dialog.exec() == QDialog.Accepted

    def _confirm_interrupt_character_delete(self) -> bool:
        dialog = ClearTagsConfirmDialog(
            self,
            self._tr("dialog_character_delete_interrupt_title"),
            self._tr("dialog_character_delete_interrupt_message"),
            self._tr("dialog_character_delete_interrupt_confirm"),
            self._tr("dialog_character_delete_interrupt_cancel"),
        )
        return dialog.exec() == QDialog.Accepted

    def _confirm_delete_selected_characters(self, count: int) -> bool:
        dialog = ClearTagsConfirmDialog(
            self,
            self._tr("dialog_character_delete_confirm_title"),
            self._tr("dialog_character_delete_confirm_message", count=max(1, int(count))),
            self._tr("dialog_character_delete_confirm_confirm"),
            self._tr("dialog_character_delete_confirm_cancel"),
        )
        return dialog.exec() == QDialog.Accepted

    def _request_delete_selected_character(self) -> None:
        self._delete_selected_character(require_confirm=True)

    def _quick_delete_selected_character(self) -> None:
        self._delete_selected_character(require_confirm=False)

    def _start_bulk_character_build(self) -> None:
        if self._is_character_bulk_build_running():
            self._set_status(self._tr("status_character_bulk_running"))
            return
        if self._is_character_delete_running():
            self._set_status(self._tr("status_character_delete_busy"))
            return

        existing_count = len(self.character_manager_service.list_characters())
        if existing_count <= 0:
            self._reset_character_bulk_progress()
            self._set_status(self._tr("status_character_bulk_no_existing"), is_error=True)
            return

        limit = int(self.character_bulk_count_spin.value())
        if self.character_manager_service.is_first_bulk_build():
            if not self._confirm_first_bulk_build(limit):
                self._reset_character_bulk_progress()
                self._set_status(self._tr("status_character_bulk_cancelled"))
                return

        self._set_character_bulk_widgets_enabled(False)
        self._set_character_bulk_progress_busy()
        self._set_status(self._tr("status_character_bulk_start", count=existing_count, limit=limit))

        self.character_bulk_thread = QThread(self)
        self.character_bulk_worker = CharacterBulkBuildWorker(self.character_manager_service, limit=limit)
        self.character_bulk_worker.moveToThread(self.character_bulk_thread)
        self.character_bulk_thread.started.connect(self.character_bulk_worker.run)
        self.character_bulk_worker.progress.connect(self._on_character_bulk_progress)
        self.character_bulk_worker.finished.connect(self._on_character_bulk_finished)
        self.character_bulk_worker.finished.connect(self.character_bulk_thread.quit)
        self.character_bulk_worker.finished.connect(self.character_bulk_worker.deleteLater)
        self.character_bulk_thread.finished.connect(self.character_bulk_thread.deleteLater)
        self.character_bulk_thread.finished.connect(self._on_character_bulk_thread_finished)
        self.character_bulk_thread.start()

    def _on_character_bulk_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        processed = int(payload.get("processed_characters", 0) or 0)
        total = int(payload.get("total_characters", 0) or 0)
        added = int(payload.get("added_references", 0) or 0)
        updated = int(payload.get("updated_characters", 0) or 0)
        skipped = int(payload.get("skipped_characters", 0) or 0)
        if total <= 0:
            total = max(processed, 1)
        self._set_character_bulk_progress_value(processed=processed, total=total)
        current_name = str(payload.get("current_name", "")).strip()
        self._set_status(
            self._tr(
                "status_character_bulk_progress",
                processed=processed,
                total=total,
                updated=updated,
                added=added,
                skipped=skipped,
                name=current_name if current_name else "-",
            )
        )

    def _on_character_bulk_finished(self, ok: bool, message: str, summary: object) -> None:
        payload = summary if isinstance(summary, dict) else {}
        processed = int(payload.get("processed_characters", 0) or 0)
        total = int(payload.get("total_characters", 0) or 0)
        if total <= 0:
            total = processed
        self._reload_character_library_list()
        if not ok:
            if total > 0:
                self._set_character_bulk_progress_value(processed=processed, total=total)
            else:
                self._reset_character_bulk_progress()
            if bool(payload.get("interrupted", False)):
                self._set_status(self._tr("status_character_bulk_interrupted"), is_error=True)
                return
            self._set_status(
                self._tr("status_character_bulk_failed", error=message or self._tr("status_unknown_error")),
                is_error=True,
            )
            return

        if bool(payload.get("interrupted", False)):
            if total > 0:
                self._set_character_bulk_progress_value(processed=processed, total=total)
            else:
                self._reset_character_bulk_progress()
            self._set_status(self._tr("status_character_bulk_interrupted"), is_error=True)
            return
        if total > 0:
            self._set_character_bulk_progress_value(processed=total, total=total)
        else:
            self._reset_character_bulk_progress()
        self._set_status(
            self._tr(
                "status_character_bulk_done",
                updated=int(payload.get("updated_characters", 0) or 0),
                added=int(payload.get("added_references", 0) or 0),
                skipped=int(payload.get("skipped_characters", 0) or 0),
                failed=int(payload.get("failed_characters", 0) or 0),
            )
        )

    def _on_character_bulk_thread_finished(self) -> None:
        self.character_bulk_thread = None
        self.character_bulk_worker = None
        self._set_character_bulk_widgets_enabled(True)

    def _import_selected_character(self) -> None:
        selected_entries = self._selected_search_candidate_entries()
        if not selected_entries:
            self._set_status(self._tr("status_character_import_no_selection"), is_error=True)
            return
        success_count = 0
        failed_count = 0
        skipped_count = 0
        last_success_name = ""
        last_error = ""
        for index, candidate in selected_entries:
            try:
                avatar_payload = self.search_candidate_avatar_payloads.get(index, b"")
                merge_strategy = "auto"
                matched = self.character_manager_service.preview_identity_merge_target(candidate)
                if isinstance(matched, dict):
                    merge_strategy = self._ask_import_merge_strategy(
                        candidate,
                        matched,
                        candidate_avatar_payload=avatar_payload,
                    )
                    if merge_strategy == "cancel":
                        skipped_count += 1
                        continue
                created = self.character_manager_service.import_candidate(
                    candidate,
                    avatar_payload=avatar_payload,
                    allow_avatar_download=False,
                    merge_strategy=merge_strategy,
                )
                success_count += 1
                last_success_name = str(created.get("display_name", "")).strip()
            except Exception as error:
                failed_count += 1
                last_error = str(error)
        if success_count > 0:
            self._reload_character_library_list()
        if failed_count > 0:
            if success_count > 0 or skipped_count > 0:
                self._set_status(
                    self._tr(
                        "status_character_import_batch_result_with_skipped",
                        success=success_count,
                        failed=failed_count,
                        skipped=skipped_count,
                    ),
                    is_error=True,
                )
                return
            self._set_status(
                self._tr("status_character_import_failed", error=last_error or self._tr("status_unknown_error")),
                is_error=True,
            )
            return
        if success_count == 0 and skipped_count > 0:
            self._set_status(self._tr("status_character_import_cancelled_all"))
            return
        if success_count == 1:
            self._set_status(self._tr("status_character_import_success", name=last_success_name))
            return
        if skipped_count > 0:
            self._set_status(
                self._tr(
                    "status_character_import_batch_result_with_skipped",
                    success=success_count,
                    failed=failed_count,
                    skipped=skipped_count,
                )
            )
            return
        self._set_status(self._tr("status_character_import_batch_result", success=success_count, failed=failed_count))

    def _build_record_provider_links_text(self, record: dict) -> str:
        links_text = ""
        links = record.get("provider_links")
        if isinstance(links, list):
            parts: list[str] = []
            for item in links:
                if not isinstance(item, dict):
                    continue
                provider = str(item.get("provider", "")).strip()
                entity = str(item.get("provider_entity_id", "")).strip()
                if provider and entity:
                    parts.append(f"{provider}:{entity}")
            links_text = " / ".join(parts)
        if links_text:
            return links_text
        provider = str(record.get("provider", "")).strip()
        entity = str(record.get("provider_entity_id", "")).strip()
        return f"{provider}:{entity}" if provider and entity else "-"

    def _build_candidate_provider_text(self, candidate: SearchCandidate) -> str:
        provider = str(candidate.provider).strip()
        entity = str(candidate.provider_entity_id).strip()
        if provider and entity:
            return f"{provider}:{entity}"
        if provider:
            return provider
        return "-"

    def _load_record_avatar_pixmap(self, record: dict) -> QPixmap | None:
        avatar_relative = str(record.get("avatar_local_path", "")).strip()
        if avatar_relative:
            avatar_path = (self.character_manager_service.custom_root / avatar_relative).resolve()
            if avatar_path.exists() and avatar_path.is_file():
                pixmap = QPixmap(str(avatar_path))
                if not pixmap.isNull():
                    return pixmap
        avatar_url = str(record.get("avatar_url", "")).strip()
        if avatar_url:
            icon = self.character_icon_cache.get(avatar_url, QIcon())
            if not icon.isNull():
                pixmap = icon.pixmap(64, 64)
                if not pixmap.isNull():
                    return pixmap
        return None

    def _load_candidate_avatar_pixmap(self, candidate: SearchCandidate, payload: bytes) -> QPixmap | None:
        data = bytes(payload) if payload else b""
        if data:
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                return pixmap
        avatar_url = str(candidate.avatar_url).strip()
        if avatar_url:
            icon = self.character_icon_cache.get(avatar_url, QIcon())
            if not icon.isNull():
                pixmap = icon.pixmap(64, 64)
                if not pixmap.isNull():
                    return pixmap
        return None

    def _ask_import_merge_strategy(
        self,
        candidate: SearchCandidate,
        existing_record: dict,
        *,
        candidate_avatar_payload: bytes,
    ) -> str:
        incoming_name = str(candidate.display_name).strip() or "-"
        incoming_source = str(candidate.source_title).strip() or "-"
        existing_name = str(existing_record.get("display_name", "")).strip() or "-"
        existing_source = str(existing_record.get("source_title", "")).strip() or "-"
        existing_links = self._build_record_provider_links_text(existing_record)
        candidate_links = self._build_candidate_provider_text(candidate)
        candidate_avatar = self._load_candidate_avatar_pixmap(candidate, candidate_avatar_payload)
        existing_avatar = self._load_record_avatar_pixmap(existing_record)

        dialog = CharacterMergeConfirmDialog(
            self,
            title=self._tr("dialog_character_merge_confirm_title"),
            message=self._tr("dialog_character_merge_confirm_text"),
            candidate_section_title=self._tr("dialog_character_merge_candidate_title"),
            candidate_name=incoming_name,
            candidate_source=self._tr("dialog_character_merge_source_line", source=incoming_source),
            candidate_links=self._tr("dialog_character_merge_links_line", links=candidate_links),
            candidate_avatar=candidate_avatar,
            existing_section_title=self._tr("dialog_character_merge_existing_title"),
            existing_name=existing_name,
            existing_source=self._tr("dialog_character_merge_source_line", source=existing_source),
            existing_links=self._tr("dialog_character_merge_links_line", links=existing_links),
            existing_avatar=existing_avatar,
            merge_text=self._tr("dialog_character_merge_confirm_merge"),
            add_new_text=self._tr("dialog_character_merge_confirm_new"),
            cancel_text=self._tr("dialog_character_merge_confirm_cancel"),
        )
        accepted = dialog.exec() == QDialog.Accepted
        if not accepted:
            return "cancel"
        decision = dialog.decision()
        if decision in {"merge", "new"}:
            return decision
        return "cancel"

    def _delete_selected_character(self, *, require_confirm: bool = True) -> None:
        if self._is_character_delete_running():
            self._set_status(self._tr("status_character_delete_busy"))
            return
        if self._is_character_bulk_build_running():
            self._set_status(self._tr("status_character_bulk_running"))
            return

        character_ids = self._selected_library_character_ids()
        if not character_ids:
            self._set_status(self._tr("status_character_delete_no_selection"), is_error=True)
            return
        if require_confirm and not self._confirm_delete_selected_characters(len(character_ids)):
            return
        selected_rows = [
            int(self.character_library_list.row(item))
            for item in self.character_library_list.selectedItems()
            if self.character_library_list.row(item) >= 0
        ]
        self.character_delete_preferred_row = resolve_character_delete_anchor_row(
            self.character_library_list.currentRow(),
            selected_rows,
        )
        self._set_character_delete_widgets_enabled(False)
        self._set_status(self._tr("status_character_delete_background_start", count=len(character_ids)))

        self.character_delete_thread = QThread(self)
        self.character_delete_worker = CharacterDeleteWorker(self.character_manager_service, character_ids=character_ids)
        self.character_delete_worker.moveToThread(self.character_delete_thread)
        self.character_delete_thread.started.connect(self.character_delete_worker.run)
        self.character_delete_worker.progress.connect(self._on_character_delete_progress)
        self.character_delete_worker.finished.connect(self._on_character_delete_finished)
        self.character_delete_worker.finished.connect(self.character_delete_thread.quit)
        self.character_delete_worker.finished.connect(self.character_delete_worker.deleteLater)
        self.character_delete_thread.finished.connect(self.character_delete_thread.deleteLater)
        self.character_delete_thread.finished.connect(self._on_character_delete_thread_finished)
        self.character_delete_thread.start()

    def _on_character_delete_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self._set_status(
            self._tr(
                "status_character_delete_progress",
                processed=int(payload.get("processed", 0) or 0),
                total=int(payload.get("total", 0) or 0),
                name=str(payload.get("current_name", "")).strip() or "-",
            )
        )

    def _on_character_delete_finished(self, ok: bool, message: str, summary: object) -> None:
        payload = summary if isinstance(summary, dict) else {}
        preferred_row = getattr(self, "character_delete_preferred_row", None)
        self._reload_character_library_list(preferred_row=preferred_row)
        if not ok:
            self._set_status(
                self._tr("status_character_delete_failed", error=message or self._tr("status_unknown_error")),
                is_error=True,
            )
            return
        if bool(payload.get("interrupted", False)):
            self._set_status(self._tr("status_character_delete_interrupted"), is_error=True)
            return
        self._set_status(
            self._tr(
                "status_character_delete_batch_done",
                deleted=int(payload.get("deleted", 0) or 0),
                missing=int(payload.get("missing", 0) or 0),
                failed=int(payload.get("failed", 0) or 0),
            ),
            is_error=int(payload.get("failed", 0) or 0) > 0,
        )

    def _on_character_delete_thread_finished(self) -> None:
        self.character_delete_thread = None
        self.character_delete_worker = None
        self.character_delete_preferred_row = None
        self._set_character_delete_widgets_enabled(True)

    def _append_selected_character_references(self) -> None:
        selected_ids = self._selected_library_character_ids()
        if len(selected_ids) > 1:
            self._set_status(self._tr("status_character_refs_multi_selection"), is_error=True)
            return
        character_id = selected_ids[0] if selected_ids else ""
        if not character_id:
            self._set_status(self._tr("status_character_refs_no_selection"), is_error=True)
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._tr("dialog_choose_images"),
            str(self._get_dialog_start_dir()),
            self._tr("dialog_image_files_filter"),
        )
        if not files:
            return
        image_paths = [Path(file).resolve() for file in files]
        record = self.character_manager_service.get_character(character_id)
        name = str(record.get("display_name", "")).strip() if isinstance(record, dict) else character_id
        try:
            self.character_manager_service.append_reference_images(character_id, image_paths=image_paths)
        except Exception as error:
            self._set_status(self._tr("status_character_refs_failed", error=str(error)), is_error=True)
            return
        self._reload_character_library_list()
        self._set_status(self._tr("status_character_refs_added", name=name, count=len(image_paths)))

    def closeEvent(self, event) -> None:
        if self._is_character_bulk_build_running():
            if not self._confirm_interrupt_bulk_build():
                event.ignore()
                return
            if self.character_bulk_worker is not None:
                self.character_bulk_worker.request_stop()
            if self.character_bulk_thread is not None:
                self.character_bulk_thread.quit()
                self.character_bulk_thread.wait(2000)
        if self._is_character_delete_running():
            if not self._confirm_interrupt_character_delete():
                event.ignore()
                return
            if self.character_delete_worker is not None:
                self.character_delete_worker.request_stop()
            if self.character_delete_thread is not None:
                self.character_delete_thread.quit()
                self.character_delete_thread.wait(2000)
        super().closeEvent(event)
