"""Work/source editing dialog widgets for MoeGirlTagger window."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_WINDOW_CLOSE_ICON_PATH = _ICONS_DIR / "window_close.svg"
_LIST_DELETE_ICON_PATH = _ICONS_DIR / "list_delete.svg"


def _load_optional_icon(path: Path) -> QIcon:
    if path.exists():
        return QIcon(str(path))
    return QIcon()


def _load_tinted_optional_icon(path: Path, color: QColor, size: QSize) -> QIcon:
    icon = _load_optional_icon(path)
    if icon.isNull():
        return QIcon()
    source = icon.pixmap(size)
    if source.isNull():
        return icon
    tinted = QPixmap(source.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), color)
    painter.end()
    return QIcon(tinted)


class WorkAliasEditorDialog(QDialog):
    """Small editor dialog for one work's multilingual aliases."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        close_tooltip: str,
        add_alias_text: str,
        save_text: str,
        language_options: list[tuple[str, str]],
        aliases: list[dict],
        current_language: str,
        validation_error_text: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkAliasEditorDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._language_options = [(str(code).strip(), str(label).strip()) for code, label in language_options if str(code).strip()]
        self._validation_error_text = str(validation_error_text or "").strip()
        self._result_aliases: list[dict] = []

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 18)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("WorkAliasEditorCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("WorkAliasEditorTitle")

        close_button = QPushButton()
        close_button.setObjectName("WorkAliasDialogCloseButton")
        close_button.setToolTip(close_tooltip)
        close_button.setFixedSize(28, 28)
        close_icon = _load_optional_icon(_WINDOW_CLOSE_ICON_PATH)
        if not close_icon.isNull():
            close_button.setIcon(close_icon)
            close_button.setIconSize(QSize(14, 14))
        else:
            close_button.setText("×")
        close_button.clicked.connect(self.reject)

        header_row.addWidget(title_label, 1)
        header_row.addWidget(close_button, 0)
        card_layout.addLayout(header_row)

        self.alias_tree = QTreeWidget()
        self.alias_tree.setObjectName("WorkAliasEditorTree")
        self.alias_tree.setColumnCount(3)
        self.alias_tree.setHeaderHidden(True)
        self.alias_tree.setRootIsDecorated(False)
        self.alias_tree.setAlternatingRowColors(False)
        self.alias_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.alias_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.alias_tree.setColumnWidth(1, 150)
        self.alias_tree.setColumnWidth(2, 42)
        self.alias_tree.setIndentation(0)
        alias_header = self.alias_tree.header()
        alias_header.setStretchLastSection(False)
        alias_header.setSectionResizeMode(0, QHeaderView.Stretch)
        alias_header.setSectionResizeMode(1, QHeaderView.Fixed)
        alias_header.setSectionResizeMode(2, QHeaderView.Fixed)
        alias_header.resizeSection(1, 150)
        alias_header.resizeSection(2, 42)
        card_layout.addWidget(self.alias_tree, 1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("WorkAliasEditorError")
        self.error_label.hide()
        card_layout.addWidget(self.error_label)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(8)

        self.add_alias_button = QPushButton(add_alias_text)
        self.add_alias_button.setObjectName("WorkAliasAddButton")
        self.add_alias_button.clicked.connect(self._on_add_alias_clicked)

        save_button = QPushButton(save_text)
        save_button.setObjectName("WorkAliasSaveButton")
        save_button.setDefault(True)
        save_button.setAutoDefault(True)
        save_button.clicked.connect(self._on_save_clicked)

        bottom_row.addWidget(self.add_alias_button, 0)
        bottom_row.addStretch(1)
        bottom_row.addWidget(save_button, 0)
        card_layout.addLayout(bottom_row)

        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(16, 24, 38, 30))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(160)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(760)
        self.setMinimumHeight(420)
        self.resize(860, 500)

        self.setStyleSheet(
            """
            QDialog#WorkAliasEditorDialog { background: transparent; }
            QFrame#WorkAliasEditorCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#WorkAliasEditorTitle {
                color: #1f2530;
                font-size: 18px;
                font-weight: 700;
            }
            QPushButton#WorkAliasDialogCloseButton {
                background: #dfe7f5;
                border: 1px solid #c4d2ea;
                border-radius: 8px;
                color: #2b3b52;
            }
            QPushButton#WorkAliasDialogCloseButton:hover { background: #d3ddf0; }
            QPushButton#WorkAliasDialogCloseButton:pressed { background: #c8d5eb; }
            QTreeWidget#WorkAliasEditorTree {
                background: #ffffff;
                border: 1px solid #d4ddeb;
                border-radius: 10px;
                padding: 0px;
                outline: none;
            }
            QTreeWidget#WorkAliasEditorTree::item { padding: 0px 0px; }
            QLineEdit#WorkAliasNameInput {
                min-height: 26px;
                border: 1px solid #d4ddeb;
                border-radius: 7px;
                background: #ffffff;
                color: #2d3a50;
                padding: 0 8px;
            }
            QLineEdit#WorkAliasNameInput:focus {
                border: 1px solid #6ea2ff;
            }
            QLabel#WorkAliasLanguageLabel {
                color: #2d3a50;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#WorkAliasDeleteButton {
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                background: transparent;
                border: none;
                padding: 0;
            }
            QPushButton#WorkAliasDeleteButton:hover { background: transparent; }
            QPushButton#WorkAliasDeleteButton:pressed { background: transparent; }
            QLabel#WorkAliasEditorError {
                color: #d64545;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#WorkAliasAddButton,
            QPushButton#WorkAliasSaveButton {
                min-width: 92px;
                min-height: 32px;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#WorkAliasAddButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#WorkAliasAddButton:hover { background: #d4def0; }
            QPushButton#WorkAliasAddButton:pressed { background: #c9d6eb; }
            QPushButton#WorkAliasSaveButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#WorkAliasSaveButton:hover { background: #1f70f3; }
            QPushButton#WorkAliasSaveButton:pressed { background: #135fdb; }
            """
        )

        normalized_aliases: list[dict] = []
        for entry in aliases if isinstance(aliases, list) else []:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("language", "")).strip()
            name = str(entry.get("name", "")).strip()
            if not code or not name:
                continue
            normalized_aliases.append({"language": code, "name": name})
        if not normalized_aliases and self._language_options:
            default_code = str(current_language or "zh-CN").strip() or "zh-CN"
            if not any(code == default_code for code, _label in self._language_options):
                default_code = self._language_options[0][0]
            normalized_aliases.append({"language": default_code, "name": ""})

        for entry in normalized_aliases:
            self._append_alias_row(str(entry.get("language", "")), str(entry.get("name", "")))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()

    def _language_label(self, language_code: str) -> str:
        target = str(language_code or "").strip()
        for code, label in self._language_options:
            if code == target:
                return label or code
        return target

    def _used_language_codes(self) -> set[str]:
        used: set[str] = set()
        for row in range(self.alias_tree.topLevelItemCount()):
            item = self.alias_tree.topLevelItem(row)
            if item is None:
                continue
            code = str(item.data(0, Qt.UserRole) or "").strip()
            if code:
                used.add(code)
        return used

    def _append_alias_row(self, language_code: str, name: str) -> None:
        code = str(language_code or "").strip()
        if not code:
            return
        item = QTreeWidgetItem(["", "", ""])
        item.setData(0, Qt.UserRole, code)
        row_height = 46
        item.setSizeHint(0, QSize(0, row_height))
        item.setSizeHint(1, QSize(0, row_height))
        item.setSizeHint(2, QSize(0, row_height))
        self.alias_tree.addTopLevelItem(item)

        language_label = QLabel(self._language_label(code))
        language_label.setObjectName("WorkAliasLanguageLabel")
        language_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        language_container = QWidget()
        language_layout = QHBoxLayout(language_container)
        language_layout.setContentsMargins(16, 0, 0, 0)
        language_layout.setSpacing(0)
        language_layout.addWidget(language_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
        self.alias_tree.setItemWidget(item, 1, language_container)

        name_input = QLineEdit(str(name or "").strip())
        name_input.setObjectName("WorkAliasNameInput")
        name_input.setFixedHeight(34)
        name_container = QWidget()
        name_layout = QHBoxLayout(name_container)
        name_layout.setContentsMargins(12, 0, 0, 0)
        name_layout.setSpacing(0)
        name_layout.addWidget(name_input, 1, Qt.AlignVCenter)
        self.alias_tree.setItemWidget(item, 0, name_container)

        delete_button = QPushButton()
        delete_button.setObjectName("WorkAliasDeleteButton")
        delete_button.setToolTip("Delete")
        delete_button.setFlat(True)
        delete_button.setFixedSize(36, 36)
        delete_icon = _load_tinted_optional_icon(_LIST_DELETE_ICON_PATH, QColor("#7f90ab"), QSize(36, 36))
        if not delete_icon.isNull():
            delete_button.setIcon(delete_icon)
            delete_button.setIconSize(QSize(36, 36))
        else:
            delete_button.setText("×")
            delete_button.setStyleSheet("color: #7f90ab; font-size: 22px; border: none; background: transparent;")
        delete_button.clicked.connect(lambda _checked=False, target=item: self._remove_alias_row(target))
        delete_container = QWidget()
        delete_layout = QHBoxLayout(delete_container)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.setSpacing(0)
        delete_layout.addWidget(delete_button, 0, Qt.AlignCenter)
        self.alias_tree.setItemWidget(item, 2, delete_container)

        self.alias_tree.setCurrentItem(item)
        name_input.setFocus()
        self.error_label.hide()

    def _remove_alias_row(self, item: QTreeWidgetItem) -> None:
        index = self.alias_tree.indexOfTopLevelItem(item)
        if index < 0:
            return
        self.alias_tree.takeTopLevelItem(index)

    def _on_add_alias_clicked(self) -> None:
        used = self._used_language_codes()
        menu = QMenu(self)
        for code, label in self._language_options:
            if code in used:
                continue
            action = menu.addAction(label or code)
            action.setData(code)
        if menu.isEmpty():
            return
        action = menu.exec(self.add_alias_button.mapToGlobal(self.add_alias_button.rect().bottomLeft()))
        if action is None:
            return
        code = str(action.data() or "").strip()
        if not code:
            return
        self._append_alias_row(code, "")

    def _collect_aliases(self) -> list[dict]:
        result: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for row in range(self.alias_tree.topLevelItemCount()):
            item = self.alias_tree.topLevelItem(row)
            if item is None:
                continue
            code = str(item.data(0, Qt.UserRole) or "").strip()
            editor_widget = self.alias_tree.itemWidget(item, 0)
            name_input = None
            if isinstance(editor_widget, QLineEdit):
                name_input = editor_widget
            elif isinstance(editor_widget, QWidget):
                name_input = editor_widget.findChild(QLineEdit)
            name = str(name_input.text() if isinstance(name_input, QLineEdit) else "").strip()
            if not code or not name:
                continue
            key = (name.casefold(), code)
            if key in seen:
                continue
            seen.add(key)
            result.append({"language": code, "name": name})
        return result

    def _on_save_clicked(self) -> None:
        aliases = self._collect_aliases()
        if not aliases:
            self.error_label.setText(self._validation_error_text)
            self.error_label.show()
            return
        self._result_aliases = aliases
        self.accept()

    def result_payload(self) -> list[dict]:
        return list(self._result_aliases)


class WorkTitleEditorDialog(QDialog):
    """Small dialog for editing one source_title."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        close_tooltip: str,
        save_text: str,
        placeholder_text: str,
        source_title: str,
        validation_error_text: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkTitleEditorDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._validation_error_text = str(validation_error_text or "").strip()
        self._result_source_title = str(source_title or "").strip()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 18)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("WorkTitleEditorCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 12)
        card_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("WorkTitleEditorTitle")

        close_button = QPushButton()
        close_button.setObjectName("WorkTitleDialogCloseButton")
        close_button.setToolTip(close_tooltip)
        close_button.setFixedSize(28, 28)
        close_icon = _load_optional_icon(_WINDOW_CLOSE_ICON_PATH)
        if not close_icon.isNull():
            close_button.setIcon(close_icon)
            close_button.setIconSize(QSize(14, 14))
        else:
            close_button.setText("×")
        close_button.clicked.connect(self.reject)

        header_row.addWidget(title_label, 1)
        header_row.addWidget(close_button, 0)
        card_layout.addLayout(header_row)

        self.title_input = QLineEdit(str(source_title or "").strip())
        self.title_input.setObjectName("WorkTitleInput")
        self.title_input.setPlaceholderText(placeholder_text)
        self.title_input.setFixedHeight(36)
        card_layout.addWidget(self.title_input)

        self.error_label = QLabel("")
        self.error_label.setObjectName("WorkTitleEditorError")
        self.error_label.hide()
        card_layout.addWidget(self.error_label)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(8)
        bottom_row.addStretch(1)

        save_button = QPushButton(save_text)
        save_button.setObjectName("WorkTitleSaveButton")
        save_button.setDefault(True)
        save_button.setAutoDefault(True)
        save_button.clicked.connect(self._on_save_clicked)
        bottom_row.addWidget(save_button, 0)

        card_layout.addLayout(bottom_row)
        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(16, 24, 38, 30))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(160)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(620)
        self.resize(680, 210)

        self.setStyleSheet(
            """
            QDialog#WorkTitleEditorDialog { background: transparent; }
            QFrame#WorkTitleEditorCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#WorkTitleEditorTitle {
                color: #1f2530;
                font-size: 18px;
                font-weight: 700;
            }
            QPushButton#WorkTitleDialogCloseButton {
                background: #dfe7f5;
                border: 1px solid #c4d2ea;
                border-radius: 8px;
                color: #2b3b52;
            }
            QPushButton#WorkTitleDialogCloseButton:hover { background: #d3ddf0; }
            QPushButton#WorkTitleDialogCloseButton:pressed { background: #c8d5eb; }
            QLineEdit#WorkTitleInput {
                min-height: 28px;
                border: 1px solid #d4ddeb;
                border-radius: 8px;
                background: #ffffff;
                color: #2d3a50;
                padding: 0 10px;
                font-size: 13px;
            }
            QLineEdit#WorkTitleInput:focus {
                border: 1px solid #6ea2ff;
            }
            QLabel#WorkTitleEditorError {
                color: #d64545;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#WorkTitleSaveButton {
                min-width: 96px;
                min-height: 32px;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#WorkTitleSaveButton:hover { background: #1f70f3; }
            QPushButton#WorkTitleSaveButton:pressed { background: #135fdb; }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()

    def _on_save_clicked(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            self.error_label.setText(self._validation_error_text)
            self.error_label.show()
            return
        self._result_source_title = title
        self.accept()

    def result_title(self) -> str:
        return str(self._result_source_title or "").strip()


class WorkListDialog(QDialog):
    """Dialog for listing works and opening title/alias editors."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        close_tooltip: str,
        edit_title_button_text: str,
        edit_alias_button_text: str,
        works: list[dict],
        edit_title_callback: Callable[[dict], dict | None],
        edit_alias_callback: Callable[[dict], dict | None],
        reload_callback: Callable[[], list[dict]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkListDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._edit_title_callback = edit_title_callback
        self._edit_alias_callback = edit_alias_callback
        self._reload_callback = reload_callback
        self._edit_title_button_text = str(edit_title_button_text or "Edit Work").strip() or "Edit Work"
        self._edit_alias_button_text = str(edit_alias_button_text or "Edit Alias").strip() or "Edit Alias"
        self._work_by_key: dict[str, dict] = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 18)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("WorkListCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 12)
        card_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("WorkListDialogTitle")

        close_button = QPushButton()
        close_button.setObjectName("WorkListDialogCloseButton")
        close_button.setToolTip(close_tooltip)
        close_button.setFixedSize(28, 28)
        close_icon = _load_optional_icon(_WINDOW_CLOSE_ICON_PATH)
        if not close_icon.isNull():
            close_button.setIcon(close_icon)
            close_button.setIconSize(QSize(14, 14))
        else:
            close_button.setText("×")
        close_button.clicked.connect(self.reject)

        header_row.addWidget(title_label, 1)
        header_row.addWidget(close_button, 0)
        card_layout.addLayout(header_row)

        self.work_tree = QTreeWidget()
        self.work_tree.setObjectName("WorkListTree")
        self.work_tree.setColumnCount(2)
        self.work_tree.setHeaderHidden(True)
        self.work_tree.setRootIsDecorated(False)
        self.work_tree.setAlternatingRowColors(False)
        self.work_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.work_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.work_tree.setTextElideMode(Qt.ElideNone)
        self.work_tree.setIndentation(0)
        work_header = self.work_tree.header()
        work_header.setStretchLastSection(False)
        work_header.setSectionResizeMode(0, QHeaderView.Stretch)
        work_header.setSectionResizeMode(1, QHeaderView.Fixed)
        work_header.resizeSection(1, 230)
        self.work_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        card_layout.addWidget(self.work_tree, 1)

        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(16, 24, 38, 30))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(160)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(860)
        self.setMinimumHeight(440)
        self.resize(980, 560)

        self.setStyleSheet(
            """
            QDialog#WorkListDialog { background: transparent; }
            QFrame#WorkListCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#WorkListDialogTitle {
                color: #1f2530;
                font-size: 18px;
                font-weight: 700;
            }
            QPushButton#WorkListDialogCloseButton {
                background: #dfe7f5;
                border: 1px solid #c4d2ea;
                border-radius: 8px;
                color: #2b3b52;
            }
            QPushButton#WorkListDialogCloseButton:hover { background: #d3ddf0; }
            QPushButton#WorkListDialogCloseButton:pressed { background: #c8d5eb; }
            QTreeWidget#WorkListTree {
                background: #ffffff;
                border: 1px solid #d4ddeb;
                border-radius: 10px;
                padding: 4px;
                outline: none;
            }
            QTreeWidget#WorkListTree::item {
                padding: 0px 8px;
                border-radius: 0px;
            }
            QTreeWidget#WorkListTree::item:hover {
                background: #e8eef8;
                color: #2d3a50;
            }
            QTreeWidget#WorkListTree::item:selected {
                background: #dce9ff;
                color: #1f4f96;
            }
            QPushButton#WorkListEditTitleButton,
            QPushButton#WorkListEditAliasButton {
                min-width: 78px;
                max-width: 78px;
                min-height: 32px;
                max-height: 32px;
                border-radius: 10px;
                padding: 0;
                color: #243248;
                border: 1px solid #b8c6de;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#WorkListEditTitleButton {
                background: #d7e5ff;
            }
            QPushButton#WorkListEditTitleButton:hover { background: #cbddfd; }
            QPushButton#WorkListEditTitleButton:pressed { background: #bfd4fb; }
            QPushButton#WorkListEditAliasButton {
                background: #dfe7f5;
            }
            QPushButton#WorkListEditAliasButton:hover { background: #d4def0; }
            QPushButton#WorkListEditAliasButton:pressed { background: #c9d6eb; }
            """
        )

        self._set_works(works)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()

    @staticmethod
    def _work_key(work: dict) -> str:
        source_key = str(work.get("source_key", "")).strip()
        if source_key:
            return source_key
        return str(work.get("source_title", "")).strip()

    @staticmethod
    def _format_work_text(work: dict) -> str:
        title = str(work.get("source_title", "")).strip() or str(work.get("display_name", "")).strip()
        count = int(work.get("character_count", 0) or 0)
        return f"{title} ({count})" if count > 0 else title

    def _set_works(self, works: list[dict]) -> None:
        self.work_tree.clear()
        self._work_by_key.clear()
        for work in works if isinstance(works, list) else []:
            self._upsert_work(work)

    def _upsert_work(self, work: dict) -> None:
        source_key = self._work_key(work)
        if not source_key:
            return
        self._work_by_key[source_key] = dict(work)

        for row in range(self.work_tree.topLevelItemCount()):
            item = self.work_tree.topLevelItem(row)
            if item is None:
                continue
            if str(item.data(0, Qt.UserRole) or "").strip() == source_key:
                display_text = self._format_work_text(work)
                item.setText(0, display_text)
                item.setToolTip(0, display_text)
                return

        display_text = self._format_work_text(work)
        item = QTreeWidgetItem([display_text, ""])
        item.setToolTip(0, display_text)
        item.setData(0, Qt.UserRole, source_key)
        row_height = 44
        item.setSizeHint(0, QSize(0, row_height))
        item.setSizeHint(1, QSize(0, row_height))
        self.work_tree.addTopLevelItem(item)

        title_button = QPushButton(self._edit_title_button_text)
        title_button.setObjectName("WorkListEditTitleButton")
        title_button.clicked.connect(lambda _checked=False, key=source_key: self._edit_title_by_source_key(key))

        alias_button = QPushButton(self._edit_alias_button_text)
        alias_button.setObjectName("WorkListEditAliasButton")
        alias_button.clicked.connect(lambda _checked=False, key=source_key: self._edit_alias_by_source_key(key))

        action_container = QWidget()
        action_layout = QHBoxLayout(action_container)
        action_layout.setContentsMargins(6, 0, 6, 0)
        action_layout.setSpacing(8)
        action_layout.addWidget(title_button, 0, Qt.AlignCenter)
        action_layout.addWidget(alias_button, 0, Qt.AlignCenter)
        self.work_tree.setItemWidget(item, 1, action_container)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        source_key = str(item.data(0, Qt.UserRole) or "").strip()
        if source_key:
            self._edit_alias_by_source_key(source_key)

    def _apply_callback_result(self, updated: dict | None) -> None:
        if updated is None:
            return
        if callable(self._reload_callback):
            try:
                latest_works = self._reload_callback()
            except Exception:
                latest_works = []
            self._set_works(latest_works if isinstance(latest_works, list) else [])
            return
        if isinstance(updated, dict):
            self._upsert_work(updated)

    def _edit_alias_by_source_key(self, source_key: str) -> None:
        key = str(source_key or "").strip()
        if not key:
            return
        current = self._work_by_key.get(key)
        if current is None:
            return
        updated = self._edit_alias_callback(dict(current))
        self._apply_callback_result(updated)

    def _edit_title_by_source_key(self, source_key: str) -> None:
        key = str(source_key or "").strip()
        if not key:
            return
        current = self._work_by_key.get(key)
        if current is None:
            return
        updated = self._edit_title_callback(dict(current))
        self._apply_callback_result(updated)
