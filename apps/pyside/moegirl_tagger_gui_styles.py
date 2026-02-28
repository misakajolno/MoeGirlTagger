"""QSS helpers for MoeGirlTagger window."""

from __future__ import annotations


def build_window_qss(spin_up_icon: str, spin_down_icon: str) -> str:
    """Build main window QSS with runtime icon paths."""
    qss_template = """
        QWidget { font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif; color: #1f2530; }
        QFrame#WindowFrame { background: #eff2f8; border-radius: 22px; }
        QFrame#Card { background: #ffffff; border-radius: 18px; border: none; }
        QFrame#DragBar { background: transparent; border: none; }
        QLabel#CaptionLabel { color: #616975; }
        QPushButton {
            background: #edf2fb;
            border: none;
            border-radius: 11px;
            padding: 9px 16px;
            color: #222b36;
            font-size: 13px;
        }
        QPushButton#SecondaryButton { background: #edf2fb; color: #2e3642; }
        QPushButton#SecondaryButton:hover { background: #e3ebf8; }
        QPushButton#SecondaryButton:pressed { background: #d8e3f4; }
        QPushButton#DangerButton { background: #FF6A6A; color: #ffffff; font-weight: 600; }
        QPushButton#DangerButton:hover { background: #f55f5f; }
        QPushButton#DangerButton:pressed { background: #eb5555; }
        QPushButton#DangerButton:disabled { background: #f5b0b0; color: #fff7f7; }
        QPushButton#PrimaryButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 #1966ff);
            color: #ffffff;
            font-weight: 600;
        }
        QPushButton#PrimaryButton:hover { background: #1f70f3; }
        QPushButton#PrimaryButton:pressed { background: #135fdb; }
        QFrame#SideMenuPanel {
            background: #f6f9ff;
            border-radius: 14px;
        }
        QPushButton#SideMenuButton {
            background: #e9effb;
            border: 1px solid #d5e0f2;
            border-radius: 14px;
            min-width: 60px;
            max-width: 60px;
            min-height: 60px;
            max-height: 60px;
            padding: 0;
        }
        QPushButton#SideMenuButton:hover { background: #dce7fc; border: 1px solid #c2d5f3; }
        QPushButton#SideMenuButton:checked {
            background: #2d7dff;
            color: #ffffff;
            border: 1px solid #2d7dff;
        }
        QPushButton#LanguageButton {
            background: #f3f6fc;
            border: none;
            border-radius: 9px;
            padding: 8px 12px;
            color: #354156;
        }
        QPushButton#LanguageButton:hover { background: #e8eef9; }
        QPushButton#LanguageButton:checked {
            background: #dce9ff;
            color: #1750b2;
            font-weight: 600;
        }
        QPushButton#WindowButton {
            background: transparent;
            border-radius: 8px;
            padding: 0;
            color: #5d6673;
            font-size: 12px;
        }
        QPushButton#WindowButton:hover { background: #e7ebf1; color: #1f2530; }
        QLabel#CountLabel, QLabel#StatusLabel { color: #637083; }
        QLabel#SettingsTitle { color: #1f2530; font-size: 20px; font-weight: 700; }
        QLabel#SettingsSubtitle { color: #9c6320; background: #fff6e8; border-radius: 10px; padding: 8px 10px; }
        QLabel#SettingsSectionTitle { color: #273142; font-weight: 600; font-size: 14px; margin-top: 2px; }
        QLabel#SettingsHint { color: #617188; }
        QProgressBar#CharacterBulkProgress {
            background: #ecf1fb;
            border: 1px solid #d2ddef;
            border-radius: 8px;
            color: #2f3c54;
            text-align: center;
        }
        QProgressBar#CharacterBulkProgress::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4d93ff, stop:1 #2f7efb);
            border-radius: 7px;
        }
        QLabel#ThresholdName { color: #2e394b; }
        QLabel#ThresholdRange { color: #8491a3; }
        QDoubleSpinBox#ThresholdInput,
        QSpinBox#ThresholdInput {
            background: #ffffff;
            border: 1px solid #d6dfec;
            border-radius: 8px;
            padding: 5px 34px 5px 10px;
        }
        QDoubleSpinBox#ThresholdInput:focus,
        QSpinBox#ThresholdInput:focus { border: 1px solid #87a9eb; }
        QDoubleSpinBox#ThresholdInput::up-button,
        QSpinBox#ThresholdInput::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 24px;
            border-left: 1px solid #d6dfec;
            border-bottom: 1px solid #d6dfec;
            border-top-right-radius: 8px;
            background: #edf3ff;
        }
        QDoubleSpinBox#ThresholdInput::down-button,
        QSpinBox#ThresholdInput::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 24px;
            border-left: 1px solid #d6dfec;
            border-bottom-right-radius: 8px;
            background: #edf3ff;
        }
        QDoubleSpinBox#ThresholdInput::up-button:hover,
        QDoubleSpinBox#ThresholdInput::down-button:hover,
        QSpinBox#ThresholdInput::up-button:hover,
        QSpinBox#ThresholdInput::down-button:hover { background: #dce8ff; }
        QDoubleSpinBox#ThresholdInput::up-button:pressed,
        QDoubleSpinBox#ThresholdInput::down-button:pressed,
        QSpinBox#ThresholdInput::up-button:pressed,
        QSpinBox#ThresholdInput::down-button:pressed { background: #c9dcff; }
        QDoubleSpinBox#ThresholdInput::up-arrow,
        QSpinBox#ThresholdInput::up-arrow {
            image: url("__SPIN_UP_ICON__");
            width: 10px;
            height: 10px;
        }
        QDoubleSpinBox#ThresholdInput::down-arrow,
        QSpinBox#ThresholdInput::down-arrow {
            image: url("__SPIN_DOWN_ICON__");
            width: 10px;
            height: 10px;
        }
        QLabel#ToastLabel {
            color: #ffffff;
            background: rgba(25, 38, 60, 210);
            border-radius: 9px;
            padding: 8px 12px;
            min-height: 20px;
        }
        QWidget#PreviewLabel {
            background: transparent;
            border-radius: 16px;
            border: none;
            color: #758094;
            font-size: 18px;
        }
        QListView#ImageList {
            background: transparent;
            border: none;
            outline: none;
        }
        QListView#ImageList::item {
            background: transparent;
            border: none;
        }
        QListView#ImageList::item:selected {
            background: transparent;
            border: none;
        }
        QFrame#ImageRow {
            background: #f8faff;
            border-radius: 12px;
            border: 1px solid transparent;
        }
        QFrame#ImageRow:hover { background: #eef4ff; border: 1px solid #d3e2ff; }
        QFrame#ImageRow[selected="true"] { background: #e8f1ff; border: 1px solid #bcd1ff; }
        QLabel#RowTitle { color: #1d2430; }
        QLabel#RowSubtitle { color: #6b778a; }
    """
    return qss_template.replace("__SPIN_UP_ICON__", spin_up_icon).replace("__SPIN_DOWN_ICON__", spin_down_icon)
