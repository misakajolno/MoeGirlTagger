"""Tag editor dialog for selecting feature tags and characters."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QMimeData, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from shiboken6 import isValid as _is_valid_qt_object
except Exception:  # pragma: no cover - fallback when shiboken is unavailable
    def _is_valid_qt_object(_obj) -> bool:
        return True

MIME_TAG_EDITOR_TOKEN = "application/x-moegirl-tag-editor-token"


def _normalized_language(value: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower().replace("_", "-")
    if lowered.startswith("ja"):
        return "ja-JP"
    if lowered.startswith("en"):
        return "en-US"
    if lowered.startswith("ko"):
        return "ko-KR"
    return "zh-CN"


def _language_priority(language_code: str) -> list[str]:
    current = _normalized_language(language_code)
    ordered = [current, "ja-JP", "en-US", "zh-CN", "ko-KR"]
    result: list[str] = []
    for code in ordered:
        if code not in result:
            result.append(code)
    return result


def pick_localized_name(
    language_code: str,
    name_i18n: dict[str, object] | None,
    fallback_text: str,
) -> str:
    """Pick display text with current-language -> Japanese -> English fallback."""
    payload = name_i18n if isinstance(name_i18n, dict) else {}
    for code in _language_priority(language_code):
        value = str(payload.get(code, "")).strip()
        if value:
            return value

    for value in payload.values():
        text = str(value).strip()
        if text:
            return text

    return str(fallback_text or "").strip()


def pick_localized_alias(language_code: str, aliases: object, fallback_text: str) -> str:
    """Pick alias text with current-language -> Japanese -> English fallback."""
    entries = aliases if isinstance(aliases, list) else []
    by_language: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        lang = _normalized_language(str(entry.get("language", "")).strip())
        if lang not in by_language:
            by_language[lang] = name

    for code in _language_priority(language_code):
        value = by_language.get(code, "")
        if value:
            return value

    for value in by_language.values():
        if value:
            return value

    return str(fallback_text or "").strip()


def _decode_token_payload(mime_data: QMimeData) -> list[str]:
    if not mime_data.hasFormat(MIME_TAG_EDITOR_TOKEN):
        return []
    raw = bytes(mime_data.data(MIME_TAG_EDITOR_TOKEN)).decode("utf-8", errors="ignore")
    return [line.strip() for line in raw.splitlines() if line.strip()]


@dataclass(frozen=True)
class _TagToken:
    token_key: str
    kind: str
    value: str
    display_text: str
    search_text: str


class _TagSourceTree(QTreeWidget):
    tokenAddRequested = Signal(str)
    tokenRemoveRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TagEditorSourceTree")
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setExpandsOnDoubleClick(False)
        self.setMouseTracking(True)
        self.setIndentation(0)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        token = str(item.data(0, Qt.UserRole) or "").strip()
        if not token:
            return
        if not bool(item.flags() & Qt.ItemIsEnabled):
            return
        self.tokenAddRequested.emit(token)

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        mime_data = QMimeData()
        tokens: list[str] = []
        for item in items:
            token = str(item.data(0, Qt.UserRole) or "").strip()
            if token:
                tokens.append(token)
        if tokens:
            mime_data.setData(MIME_TAG_EDITOR_TOKEN, "\n".join(tokens).encode("utf-8"))
        return mime_data

    def dragEnterEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        if event.mimeData().hasFormat(MIME_TAG_EDITOR_TOKEN):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        if event.mimeData().hasFormat(MIME_TAG_EDITOR_TOKEN):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        tokens = _decode_token_payload(event.mimeData())
        if not tokens:
            super().dropEvent(event)
            return
        for token in tokens:
            self.tokenRemoveRequested.emit(token)
        event.acceptProposedAction()


class _TagSelectionList(QListWidget):
    tokenAddRequested = Signal(str)
    tokenRemoveRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TagEditorSelectionList")
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setMouseTracking(True)
        self._drag_token_key = ""
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def mousePressEvent(self, event) -> None:
        self._drag_token_key = ""
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            self._drag_token_key = str(item.data(Qt.UserRole) or "").strip()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_token_key = ""
        super().mouseReleaseEvent(event)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        token = str(item.data(Qt.UserRole) or "").strip()
        if token:
            self.tokenRemoveRequested.emit(token)

    def mimeData(self, items: list[QListWidgetItem]) -> QMimeData:
        mime_data = QMimeData()
        if self._drag_token_key:
            mime_data.setData(MIME_TAG_EDITOR_TOKEN, self._drag_token_key.encode("utf-8"))
            return mime_data
        tokens: list[str] = []
        for item in items:
            token = str(item.data(Qt.UserRole) or "").strip()
            if token:
                tokens.append(token)
        if tokens:
            mime_data.setData(MIME_TAG_EDITOR_TOKEN, "\n".join(tokens).encode("utf-8"))
        return mime_data

    def dragEnterEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        if event.mimeData().hasFormat(MIME_TAG_EDITOR_TOKEN):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        if event.mimeData().hasFormat(MIME_TAG_EDITOR_TOKEN):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        source = event.source()
        if source in {self, self.viewport()}:
            event.ignore()
            return
        tokens = _decode_token_payload(event.mimeData())
        if not tokens:
            super().dropEvent(event)
            return
        for token in tokens:
            self.tokenAddRequested.emit(token)
        event.acceptProposedAction()


class TagEditorDialog(QDialog):
    """Project-styled transfer dialog for editing tags."""

    def __init__(
        self,
        *,
        parent: QWidget,
        title: str,
        left_title: str,
        right_title: str,
        search_placeholder: str,
        rules_text: str,
        apply_text: str,
        cancel_text: str,
        feature_groups: list[dict],
        character_groups: list[dict],
        initial_feature_tags: list[str],
        initial_characters: list[str],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TagEditorDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._token_by_key: dict[str, _TagToken] = {}
        self._selected_tokens: list[str] = []
        self._source_leaf_items: dict[str, QTreeWidgetItem] = {}
        self._source_leaf_flags: dict[str, Qt.ItemFlags] = {}
        self._drag_offset = None

        root_layout = QVBoxLayout(self)
        # Leave more transparent padding so shadow falloff is not clipped.
        root_layout.setContentsMargins(18, 14, 18, 20)
        root_layout.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("TagEditorCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(12)

        self._drag_handle = QFrame()
        self._drag_handle.setObjectName("TagEditorDragHandle")
        drag_layout = QHBoxLayout(self._drag_handle)
        drag_layout.setContentsMargins(0, 0, 0, 0)
        drag_layout.setSpacing(0)

        title_label = QLabel(title)
        title_label.setObjectName("TagEditorTitle")
        title_label.setWordWrap(True)
        drag_layout.addWidget(title_label, 1)
        card_layout.addWidget(self._drag_handle)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)

        left_panel = QFrame()
        left_panel.setObjectName("TagEditorPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)
        left_header = QHBoxLayout()
        left_header.setContentsMargins(0, 0, 0, 0)
        left_header.setSpacing(8)

        left_caption = QLabel(left_title)
        left_caption.setObjectName("TagEditorPanelTitle")
        self.search_input = QLineEdit(left_panel)
        self.search_input.setObjectName("TagEditorSearchInput")
        self.search_input.setPlaceholderText(search_placeholder)
        self.search_input.setClearButtonEnabled(True)

        left_header.addWidget(left_caption)
        left_header.addWidget(self.search_input, 1)

        self.source_tree = _TagSourceTree(left_panel)
        left_layout.addLayout(left_header)
        left_layout.addWidget(self.source_tree, 1)

        right_panel = QFrame()
        right_panel.setObjectName("TagEditorPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(6)
        right_caption = QLabel(right_title)
        right_caption.setObjectName("TagEditorPanelTitle")
        self.selected_list = _TagSelectionList(right_panel)
        right_layout.addWidget(right_caption)
        right_layout.addWidget(self.selected_list, 1)

        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(right_panel, 1)
        card_layout.addLayout(body_layout, 1)

        rules_label = QLabel(rules_text)
        rules_label.setObjectName("TagEditorRules")
        rules_label.setWordWrap(True)
        card_layout.addWidget(rules_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 2, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        apply_button = QPushButton(apply_text)
        apply_button.setObjectName("TagEditorApplyButton")
        apply_button.clicked.connect(self.accept)
        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("TagEditorCancelButton")
        cancel_button.clicked.connect(self.reject)
        apply_button.setDefault(True)
        apply_button.setAutoDefault(True)

        button_row.addWidget(apply_button)
        button_row.addWidget(cancel_button)
        card_layout.addLayout(button_row)

        root_layout.addWidget(self.card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(16, 24, 38, 24))
        self.card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setStyleSheet(
            """
            QDialog#TagEditorDialog { background: transparent; }
            QFrame#TagEditorCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 16px;
            }
            QLabel#TagEditorTitle {
                color: #1f2530;
                font-size: 20px;
                font-weight: 700;
            }
            QFrame#TagEditorPanel {
                background: #f8fbff;
                border: 1px solid #d9e2f2;
                border-radius: 12px;
            }
            QLabel#TagEditorPanelTitle {
                color: #2c3850;
                font-size: 13px;
                font-weight: 700;
            }
            QLineEdit#TagEditorSearchInput {
                min-height: 28px;
                background: #ffffff;
                border: 1px solid #d4ddeb;
                border-radius: 8px;
                color: #2d3a50;
                padding: 0 10px;
                font-size: 12px;
            }
            QLineEdit#TagEditorSearchInput:focus {
                border: 1px solid #6ea2ff;
            }
            QLabel#TagEditorRules {
                color: #5f6f88;
                background: #eef3fc;
                border: 1px solid #d8e1f1;
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QTreeWidget#TagEditorSourceTree,
            QListWidget#TagEditorSelectionList {
                background: #ffffff;
                border: 1px solid #d4ddeb;
                border-radius: 10px;
                padding: 4px;
                outline: none;
                show-decoration-selected: 1;
            }
            QTreeWidget#TagEditorSourceTree::branch { width: 0px; }
            QTreeWidget#TagEditorSourceTree::branch:selected,
            QTreeWidget#TagEditorSourceTree::branch:hover {
                background: #e8eef8;
            }
            QTreeWidget#TagEditorSourceTree::item {
                padding: 4px 6px;
                border-radius: 7px;
            }
            QTreeWidget#TagEditorSourceTree::item:hover,
            QListWidget#TagEditorSelectionList::item:hover {
                background: #e8eef8;
                color: #2d3a50;
            }
            QTreeWidget#TagEditorSourceTree::item:selected,
            QListWidget#TagEditorSelectionList::item:selected {
                background: #dce9ff;
                color: #1f4f96;
            }
            QListWidget#TagEditorSelectionList::item {
                padding: 4px 6px;
                border-radius: 7px;
            }
            QPushButton#TagEditorApplyButton,
            QPushButton#TagEditorCancelButton {
                min-width: 66px;
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#TagEditorApplyButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#TagEditorApplyButton:hover { background: #1f70f3; }
            QPushButton#TagEditorApplyButton:pressed { background: #135fdb; }
            QPushButton#TagEditorCancelButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#TagEditorCancelButton:hover { background: #d4def0; }
            QPushButton#TagEditorCancelButton:pressed { background: #c9d6eb; }
            """
        )

        self.source_tree.tokenAddRequested.connect(self._add_token)
        self.source_tree.tokenRemoveRequested.connect(self._remove_token)
        self.source_tree.itemClicked.connect(self._on_source_item_clicked)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.selected_list.tokenAddRequested.connect(self._add_token)
        self.selected_list.tokenRemoveRequested.connect(self._remove_token)

        self._populate_source_tree(feature_groups, character_groups)
        self._apply_initial_selection(initial_feature_tags, initial_characters)
        self._apply_source_filter("")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_geometry()
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent_rect = parent.frameGeometry()
            width = 700
            height = max(520, int(parent.height() * 0.75))
            self.resize(width, height)
            self.move(
                parent_rect.center().x() - width // 2,
                parent_rect.center().y() - height // 2,
            )
            return

        screen = self.screen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        width = 700
        height = max(520, int(rect.height() * 0.75))
        self.resize(width, height)
        self.move(rect.center().x() - width // 2, rect.center().y() - height // 2)

    def _populate_source_tree(self, feature_groups: list[dict], character_groups: list[dict]) -> None:
        self.source_tree.clear()
        self._token_by_key.clear()
        self._source_leaf_items.clear()
        self._source_leaf_flags.clear()

        for group in feature_groups:
            self._append_group(group=group, kind="feature")
        for group in character_groups:
            self._append_group(group=group, kind="character")

    def _append_group(self, *, group: dict, kind: str) -> None:
        group_name = str(group.get("group_name", "")).strip()
        if not group_name:
            return
        top_item = QTreeWidgetItem([group_name])
        top_item.setFlags(Qt.ItemIsEnabled)
        top_item.setData(0, Qt.UserRole, "")
        group_font = top_item.font(0)
        group_font.setBold(True)
        top_item.setFont(0, group_font)
        self.source_tree.addTopLevelItem(top_item)

        items = group.get("items")
        if not isinstance(items, list):
            return
        for entry in items:
            if not isinstance(entry, dict):
                continue
            value = str(entry.get("value", "")).strip()
            display = str(entry.get("display", "")).strip() or value
            if not value:
                continue
            token_key = f"{kind}:{value}"
            token_value = str(entry.get("store_value", "")).strip() or value
            search_terms: list[str] = [display, value, token_value]
            aliases = entry.get("aliases", [])
            if isinstance(aliases, list):
                search_terms.extend(str(alias).strip() for alias in aliases if str(alias).strip())
            search_text = " ".join(dict.fromkeys(term.casefold() for term in search_terms if term.strip()))
            token = _TagToken(
                token_key=token_key,
                kind=kind,
                value=token_value,
                display_text=display,
                search_text=search_text,
            )
            self._token_by_key[token_key] = token

            leaf = QTreeWidgetItem([display])
            leaf_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
            leaf.setFlags(leaf_flags)
            leaf.setData(0, Qt.UserRole, token_key)
            top_item.addChild(leaf)
            self._source_leaf_items[token_key] = leaf
            self._source_leaf_flags[token_key] = leaf_flags

    def _apply_initial_selection(self, initial_feature_tags: list[str], initial_characters: list[str]) -> None:
        for value in initial_feature_tags:
            token = f"feature:{str(value).strip()}"
            self._add_token(token)
        for value in initial_characters:
            token = f"character:{str(value).strip()}"
            self._add_token(token)

    def _on_source_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is not None:
            return

        search_keyword = str(self.search_input.text() if hasattr(self, "search_input") else "").strip()
        if search_keyword:
            item.setExpanded(True)
            self.source_tree.scrollToItem(item, QAbstractItemView.PositionAtTop)
            return

        should_expand = not item.isExpanded()
        for index in range(self.source_tree.topLevelItemCount()):
            candidate = self.source_tree.topLevelItem(index)
            if candidate is not None:
                candidate.setExpanded(False)
        if not should_expand:
            return
        item.setExpanded(True)
        self.source_tree.scrollToItem(item, QAbstractItemView.PositionAtTop)

    def _on_search_text_changed(self, _text: str) -> None:
        self._apply_source_filter(str(self.search_input.text()))

    def _is_source_item_match(self, token_key: str, fallback_text: str, keyword: str) -> bool:
        if not keyword:
            return True
        token = self._token_by_key.get(token_key)
        if token is not None and keyword in token.search_text:
            return True
        return keyword in str(fallback_text).casefold()

    def _apply_source_filter(self, text: str) -> None:
        keyword = str(text or "").strip().casefold()
        if not keyword:
            for index in range(self.source_tree.topLevelItemCount()):
                top_item = self.source_tree.topLevelItem(index)
                if top_item is None:
                    continue
                top_item.setHidden(False)
                top_item.setExpanded(False)
                for child_index in range(top_item.childCount()):
                    child_item = top_item.child(child_index)
                    if child_item is not None:
                        child_item.setHidden(False)
            return

        for index in range(self.source_tree.topLevelItemCount()):
            top_item = self.source_tree.topLevelItem(index)
            if top_item is None:
                continue

            group_text = str(top_item.text(0) or "").casefold()
            group_match = bool(group_text and keyword in group_text)
            has_visible_child = False

            for child_index in range(top_item.childCount()):
                child_item = top_item.child(child_index)
                if child_item is None:
                    continue
                token_key = str(child_item.data(0, Qt.UserRole) or "").strip()
                child_text = str(child_item.text(0) or "")
                matched = group_match or self._is_source_item_match(token_key, child_text, keyword)
                child_item.setHidden(not matched)
                if matched:
                    has_visible_child = True

            top_item.setHidden(not has_visible_child)
            top_item.setExpanded(has_visible_child)

    def _add_token(self, token_key: str) -> None:
        if not _is_valid_qt_object(self):
            return
        token = self._token_by_key.get(str(token_key).strip())
        if token is None:
            return
        if token.token_key in self._selected_tokens:
            return
        self._selected_tokens.append(token.token_key)
        item = QListWidgetItem(token.display_text)
        item.setData(Qt.UserRole, token.token_key)
        self.selected_list.addItem(item)
        self._sync_source_states()

    def _remove_token(self, token_key: str) -> None:
        if not _is_valid_qt_object(self):
            return
        key = str(token_key).strip()
        if key not in self._selected_tokens:
            return
        self._selected_tokens = [token for token in self._selected_tokens if token != key]
        for row in range(self.selected_list.count() - 1, -1, -1):
            item = self.selected_list.item(row)
            if str(item.data(Qt.UserRole) or "").strip() == key:
                self.selected_list.takeItem(row)
        self._sync_source_states()

    def _sync_source_states(self) -> None:
        selected = set(self._selected_tokens)
        for token_key, leaf in list(self._source_leaf_items.items()):
            if not _is_valid_qt_object(leaf):
                self._source_leaf_items.pop(token_key, None)
                self._source_leaf_flags.pop(token_key, None)
                continue
            default_flags = self._source_leaf_flags.get(token_key, Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            try:
                if token_key in selected:
                    leaf.setFlags(default_flags & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable & ~Qt.ItemIsDragEnabled)
                    leaf.setForeground(0, QColor("#9aa6bb"))
                else:
                    leaf.setFlags(default_flags)
                    leaf.setForeground(0, QColor("#2d3a50"))
            except RuntimeError:
                self._source_leaf_items.pop(token_key, None)
                self._source_leaf_flags.pop(token_key, None)

    def selected_feature_tags(self) -> list[str]:
        result: list[str] = []
        for token_key in self._selected_tokens:
            token = self._token_by_key.get(token_key)
            if token is not None and token.kind == "feature":
                result.append(token.value)
        return result

    def selected_characters(self) -> list[str]:
        result: list[str] = []
        for token_key in self._selected_tokens:
            token = self._token_by_key.get(token_key)
            if token is not None and token.kind == "character":
                result.append(token.value)
        return result

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and event.position().y() <= 64:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)
