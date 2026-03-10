"""Backward-compatible dialog exports for MoeGirlTagger window."""

from __future__ import annotations

from apps.pyside.moegirl_tagger_gui_dialogs_confirm import (
    CharacterMergeConfirmDialog,
    ClearTagsConfirmDialog,
    ThemedDecisionDialog,
)
from apps.pyside.moegirl_tagger_gui_dialogs_work import (
    WorkAliasEditorDialog,
    WorkListDialog,
    WorkTitleEditorDialog,
)

__all__ = [
    "ClearTagsConfirmDialog",
    "CharacterMergeConfirmDialog",
    "ThemedDecisionDialog",
    "WorkAliasEditorDialog",
    "WorkTitleEditorDialog",
    "WorkListDialog",
]
