"""Confirmation-related dialog widgets for MoeGirlTagger window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"
_WINDOW_CLOSE_ICON_PATH = _ICONS_DIR / "window_close.svg"


def _load_optional_icon(path: Path) -> QIcon:
    """Load an icon when the asset exists."""
    if path.exists():
        return QIcon(str(path))
    return QIcon()


class ThemedDecisionDialog(QDialog):
    """Project-themed confirmation dialog with optional detail content."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        message: str,
        confirm_text: str,
        cancel_text: str,
        close_tooltip: str,
        hint_text: str = "",
        details_text: str = "",
        primary_role: str = "primary",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ThemedDecisionDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        normalized_hint = str(hint_text or "").strip()
        normalized_details = str(details_text or "").strip()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(22, 18, 22, 22)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ThemedDecisionCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 14)
        card_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("ThemedDecisionTitle")
        title_label.setWordWrap(True)

        close_button = QPushButton()
        close_button.setObjectName("ThemedDecisionCloseButton")
        close_button.setToolTip(close_tooltip)
        close_button.setFixedSize(28, 28)
        close_icon = _load_optional_icon(_WINDOW_CLOSE_ICON_PATH)
        if not close_icon.isNull():
            close_button.setIcon(close_icon)
            close_button.setIconSize(QSize(14, 14))
        else:
            close_button.setText("x")
        close_button.clicked.connect(self.reject)

        header_row.addWidget(title_label, 1)
        header_row.addWidget(close_button, 0)
        card_layout.addLayout(header_row)

        message_label = QLabel(message)
        message_label.setObjectName("ThemedDecisionMessage")
        message_label.setWordWrap(True)
        card_layout.addWidget(message_label)

        if normalized_hint:
            hint_frame = QFrame()
            hint_frame.setObjectName("ThemedDecisionHintFrame")
            hint_layout = QHBoxLayout(hint_frame)
            hint_layout.setContentsMargins(12, 10, 12, 10)
            hint_layout.setSpacing(0)

            hint_label = QLabel(normalized_hint)
            hint_label.setObjectName("ThemedDecisionHint")
            hint_label.setWordWrap(True)
            hint_layout.addWidget(hint_label, 1)
            card_layout.addWidget(hint_frame)

        if normalized_details:
            details_frame = QFrame()
            details_frame.setObjectName("ThemedDecisionDetailsFrame")
            details_layout = QVBoxLayout(details_frame)
            details_layout.setContentsMargins(0, 0, 0, 0)
            details_layout.setSpacing(0)

            details_edit = QPlainTextEdit()
            details_edit.setObjectName("ThemedDecisionDetails")
            details_edit.setReadOnly(True)
            details_edit.setPlainText(normalized_details)
            details_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            details_edit.setMinimumHeight(240)
            details_layout.addWidget(details_edit)
            card_layout.addWidget(details_frame, 1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("ThemedDecisionSecondaryButton")
        cancel_button.clicked.connect(self.reject)

        confirm_button = QPushButton(confirm_text)
        confirm_button.setObjectName(
            "ThemedDecisionDangerButton" if str(primary_role or "").strip() == "danger" else "ThemedDecisionPrimaryButton"
        )
        confirm_button.setDefault(True)
        confirm_button.setAutoDefault(True)
        confirm_button.clicked.connect(self.accept)

        button_row.addWidget(cancel_button, 0)
        button_row.addWidget(confirm_button, 0)
        card_layout.addLayout(button_row)

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

        if normalized_details:
            self.setMinimumWidth(820)
            self.setMinimumHeight(520)
            self.resize(900, 580)
        else:
            self.setMinimumWidth(620)
            self.resize(680, 260)

        self.setStyleSheet(
            """
            QDialog#ThemedDecisionDialog { background: transparent; }
            QFrame#ThemedDecisionCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#ThemedDecisionTitle {
                color: #1f2530;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#ThemedDecisionMessage {
                color: #2f3c52;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#ThemedDecisionCloseButton {
                background: #dfe7f5;
                border: 1px solid #c4d2ea;
                border-radius: 8px;
                color: #2b3b52;
            }
            QPushButton#ThemedDecisionCloseButton:hover { background: #d3ddf0; }
            QPushButton#ThemedDecisionCloseButton:pressed { background: #c8d5eb; }
            QFrame#ThemedDecisionHintFrame {
                background: #f5f9ff;
                border: 1px solid #d7e4f6;
                border-radius: 10px;
            }
            QLabel#ThemedDecisionHint {
                color: #3d5779;
                font-size: 12px;
                font-weight: 600;
            }
            QFrame#ThemedDecisionDetailsFrame {
                background: #ffffff;
                border: 1px solid #d4ddeb;
                border-radius: 10px;
            }
            QPlainTextEdit#ThemedDecisionDetails {
                background: transparent;
                border: none;
                color: #31425c;
                font-size: 12px;
                font-weight: 500;
                padding: 10px 12px;
            }
            QPushButton#ThemedDecisionPrimaryButton,
            QPushButton#ThemedDecisionSecondaryButton,
            QPushButton#ThemedDecisionDangerButton {
                min-width: 96px;
                min-height: 32px;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#ThemedDecisionPrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#ThemedDecisionPrimaryButton:hover { background: #1f70f3; }
            QPushButton#ThemedDecisionPrimaryButton:pressed { background: #135fdb; }
            QPushButton#ThemedDecisionDangerButton {
                background: #ff6a6a;
                color: #ffffff;
                border: none;
            }
            QPushButton#ThemedDecisionDangerButton:hover { background: #f55f5f; }
            QPushButton#ThemedDecisionDangerButton:pressed { background: #eb5555; }
            QPushButton#ThemedDecisionSecondaryButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#ThemedDecisionSecondaryButton:hover { background: #d4def0; }
            QPushButton#ThemedDecisionSecondaryButton:pressed { background: #c9d6eb; }
            """
        )

    def showEvent(self, event) -> None:
        """Play a subtle fade-in animation when opened."""
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()


class ClearTagsConfirmDialog(QDialog):
    """Project-styled confirmation dialog for clearing image tags."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        confirm_text: str,
        cancel_text: str,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ClearTagsConfirmDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root_layout = QVBoxLayout(self)
        # Keep enough transparent padding so blurred shadow is not clipped.
        root_layout.setContentsMargins(34, 28, 34, 34)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ConfirmDialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("ConfirmDialogTitle")
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName("ConfirmDialogMessage")
        message_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        confirm_button = QPushButton(confirm_text)
        confirm_button.setObjectName("ConfirmDialogDangerButton")
        confirm_button.clicked.connect(self.accept)
        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("ConfirmDialogSecondaryButton")
        cancel_button.clicked.connect(self.reject)
        confirm_button.setDefault(True)
        confirm_button.setAutoDefault(True)

        button_row.addWidget(confirm_button)
        button_row.addWidget(cancel_button)

        card_layout.addWidget(title_label)
        card_layout.addWidget(message_label)
        card_layout.addLayout(button_row)
        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(18, 28, 45, 52))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(560)
        self.setStyleSheet(
            """
            QDialog#ClearTagsConfirmDialog { background: transparent; }
            QFrame#ConfirmDialogCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#ConfirmDialogTitle {
                color: #1f2530;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#ConfirmDialogMessage {
                color: #2f3c52;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#ConfirmDialogDangerButton,
            QPushButton#ConfirmDialogSecondaryButton {
                min-width: 98px;
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#ConfirmDialogDangerButton {
                background: #FF6A6A;
                color: #ffffff;
                border: none;
            }
            QPushButton#ConfirmDialogDangerButton:hover { background: #f55f5f; }
            QPushButton#ConfirmDialogDangerButton:pressed { background: #eb5555; }
            QPushButton#ConfirmDialogSecondaryButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#ConfirmDialogSecondaryButton:hover { background: #d4def0; }
            QPushButton#ConfirmDialogSecondaryButton:pressed { background: #c9d6eb; }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()


class CharacterMergeConfirmDialog(QDialog):
    """Project-styled merge decision dialog for duplicate character import."""

    def __init__(
        self,
        parent: QWidget,
        *,
        title: str,
        message: str,
        candidate_section_title: str,
        candidate_name: str,
        candidate_source: str,
        candidate_links: str,
        candidate_avatar: QPixmap | None,
        existing_section_title: str,
        existing_name: str,
        existing_source: str,
        existing_links: str,
        existing_avatar: QPixmap | None,
        merge_text: str,
        add_new_text: str,
        cancel_text: str,
    ) -> None:
        super().__init__(parent)
        self._decision = "cancel"
        self.setObjectName("CharacterMergeConfirmDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(34, 28, 34, 34)
        root_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("CharacterMergeCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("CharacterMergeTitle")
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName("CharacterMergeMessage")
        message_label.setWordWrap(True)

        card_layout.addWidget(title_label)
        card_layout.addWidget(message_label)
        card_layout.addWidget(
            self._build_role_card(
                section_title=candidate_section_title,
                name=candidate_name,
                source=candidate_source,
                links=candidate_links,
                avatar=candidate_avatar,
            )
        )
        card_layout.addWidget(
            self._build_role_card(
                section_title=existing_section_title,
                name=existing_name,
                source=existing_source,
                links=existing_links,
                avatar=existing_avatar,
            )
        )

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 8, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)

        merge_button = QPushButton(merge_text)
        merge_button.setObjectName("CharacterMergePrimaryButton")
        merge_button.clicked.connect(self._on_merge_clicked)
        merge_button.setDefault(True)
        merge_button.setAutoDefault(True)

        add_new_button = QPushButton(add_new_text)
        add_new_button.setObjectName("CharacterMergeSecondaryButton")
        add_new_button.clicked.connect(self._on_new_clicked)

        cancel_button = QPushButton(cancel_text)
        cancel_button.setObjectName("CharacterMergeSecondaryButton")
        cancel_button.clicked.connect(self._on_cancel_clicked)

        button_row.addWidget(merge_button)
        button_row.addWidget(add_new_button)
        button_row.addWidget(cancel_button)
        card_layout.addLayout(button_row)

        root_layout.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(54)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(18, 28, 45, 52))
        card.setGraphicsEffect(shadow)

        self._fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.setWindowOpacity(0.0)

        self.setMinimumWidth(700)
        self.setStyleSheet(
            """
            QDialog#CharacterMergeConfirmDialog { background: transparent; }
            QFrame#CharacterMergeCard {
                background: #eff2f8;
                border: 1px solid #dbe3f1;
                border-radius: 14px;
            }
            QLabel#CharacterMergeTitle {
                color: #1f2530;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#CharacterMergeMessage {
                color: #2f3c52;
                font-size: 13px;
                font-weight: 500;
            }
            QFrame#CharacterMergeRoleCard {
                background: #f8fbff;
                border: 1px solid #dbe5f5;
                border-radius: 12px;
            }
            QLabel#CharacterMergeRoleTitle {
                color: #273247;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#CharacterMergeRoleName {
                color: #1f2530;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#CharacterMergeRoleSubtitle {
                color: #51627e;
                font-size: 12px;
                font-weight: 500;
            }
            QLabel#CharacterMergeAvatar {
                background: #eef3fb;
                border: 1px solid #d6e0f0;
                border-radius: 10px;
            }
            QPushButton#CharacterMergePrimaryButton,
            QPushButton#CharacterMergeSecondaryButton {
                min-width: 98px;
                min-height: 34px;
                border-radius: 10px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#CharacterMergePrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
                color: #ffffff;
                border: none;
            }
            QPushButton#CharacterMergePrimaryButton:hover { background: #1f70f3; }
            QPushButton#CharacterMergePrimaryButton:pressed { background: #135fdb; }
            QPushButton#CharacterMergeSecondaryButton {
                background: #dfe7f5;
                color: #243248;
                border: 1px solid #b8c6de;
            }
            QPushButton#CharacterMergeSecondaryButton:hover { background: #d4def0; }
            QPushButton#CharacterMergeSecondaryButton:pressed { background: #c9d6eb; }
            """
        )

    def _build_role_card(
        self,
        *,
        section_title: str,
        name: str,
        source: str,
        links: str,
        avatar: QPixmap | None,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("CharacterMergeRoleCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        avatar_label = QLabel()
        avatar_label.setObjectName("CharacterMergeAvatar")
        avatar_label.setAlignment(Qt.AlignCenter)
        avatar_label.setFixedSize(58, 58)
        if isinstance(avatar, QPixmap) and not avatar.isNull():
            avatar_label.setProperty("hasAvatar", True)
            avatar_label.setPixmap(self._rounded_avatar_pixmap(avatar, 56, 9))
        else:
            avatar_label.setProperty("hasAvatar", False)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)

        section_label = QLabel(section_title)
        section_label.setObjectName("CharacterMergeRoleTitle")
        name_label = QLabel(name)
        name_label.setObjectName("CharacterMergeRoleName")
        name_label.setWordWrap(True)
        source_label = QLabel(source)
        source_label.setObjectName("CharacterMergeRoleSubtitle")
        source_label.setWordWrap(True)
        links_label = QLabel(links)
        links_label.setObjectName("CharacterMergeRoleSubtitle")
        links_label.setWordWrap(True)

        text_column.addWidget(section_label)
        text_column.addWidget(name_label)
        text_column.addWidget(source_label)
        text_column.addWidget(links_label)

        layout.addWidget(avatar_label)
        layout.addLayout(text_column, 1)
        return card

    def _on_merge_clicked(self) -> None:
        self._decision = "merge"
        self.accept()

    def _on_new_clicked(self) -> None:
        self._decision = "new"
        self.accept()

    def _on_cancel_clicked(self) -> None:
        self._decision = "cancel"
        self.reject()

    def decision(self) -> str:
        return self._decision

    @staticmethod
    def _rounded_avatar_pixmap(source: QPixmap, size: int, radius: int) -> QPixmap:
        """Render avatar as rounded square pixmap to match list icon style."""
        side = max(1, int(size))
        corner = max(0, int(radius))
        scaled = source.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        cropped = scaled.copy(
            max(0, (scaled.width() - side) // 2),
            max(0, (scaled.height() - side) // 2),
            side,
            side,
        )

        output = QPixmap(side, side)
        output.fill(Qt.transparent)
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(0, 0, side, side, corner, corner)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()
        return output

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fade_in.stop()
        self.setWindowOpacity(0.0)
        self._fade_in.start()

