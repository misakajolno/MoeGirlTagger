"""PySide6 GUI entry point for anime image tagging."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


def _ensure_repo_root_in_syspath() -> None:
    """Ensure project root is importable when this file is run as a script."""
    if __package__:
        return
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


_ensure_repo_root_in_syspath()

from apps.pyside.moegirl_tagger_gui_common import load_app_icon
from apps.pyside.moegirl_tagger_gui_window import MoeGirlTaggerWindow

def main() -> None:
    """Run GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("MoeGirlTagger")
    icon = load_app_icon()
    if icon is not None:
        app.setWindowIcon(icon)
    window = MoeGirlTaggerWindow()
    if icon is not None:
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
