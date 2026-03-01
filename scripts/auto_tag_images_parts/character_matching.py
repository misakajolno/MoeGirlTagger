"""Backward-compatible exports for custom character matching logic."""

from __future__ import annotations

from pathlib import Path

try:
    from scripts.auto_tag_images_parts.character.character_index import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_profiles import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_regions import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_resolver import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_scoring import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_profiles import _get_character_correlation_profiles
    from scripts.auto_tag_images_parts.character.character_regions import _head_candidate_score
    from scripts.auto_tag_images_parts.character.character_scoring import _attribute_score_adjustment
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.auto_tag_images_parts.character.character_index import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_profiles import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_regions import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_resolver import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_scoring import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character.character_profiles import _get_character_correlation_profiles
    from scripts.auto_tag_images_parts.character.character_regions import _head_candidate_score
    from scripts.auto_tag_images_parts.character.character_scoring import _attribute_score_adjustment

