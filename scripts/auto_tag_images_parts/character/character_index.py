"""Custom character index build/load helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from scripts.auto_tag_images_parts.constants import CORRELATION_PROFILE_FILE_NAME
    from scripts.auto_tag_images_parts.tagger import WD14Tagger
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.auto_tag_images_parts.constants import CORRELATION_PROFILE_FILE_NAME
    from scripts.auto_tag_images_parts.tagger import WD14Tagger
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias

def build_custom_character_index(
    store: CustomCharacterStore,
    tagger: WD14Tagger,
    preferred_language: str = "zh-CN",
) -> CharacterVectorIndex | None:
    """Build custom-character vector index from reference images.

    Args:
        store: Custom character store.
        tagger: WD14 tagger used to extract vectors.
        preferred_language: Preferred UI language for character label selection.

    Returns:
        Built index or None when no valid references.
    """
    reference_items = store.iter_reference_items(enabled_only=True)
    if not reference_items:
        return None

    embeddings: list[np.ndarray] = []
    character_ids: list[str] = []
    character_names: list[str] = []
    image_paths: list[str] = []
    for record, image_path in reference_items:
        try:
            _, vector = tagger.predict_with_vector(image_path)
        except Exception:
            continue
        embeddings.append(np.asarray(vector, dtype=np.float32).reshape(-1))
        character_ids.append(str(record.get("id", "")).strip())
        character_names.append(select_localized_alias(record, preferred_language))
        image_paths.append(image_path.as_posix())

    if not embeddings:
        return None

    matrix = np.stack(embeddings).astype(np.float32)
    index = CharacterVectorIndex(
        embeddings=matrix,
        character_ids=character_ids,
        character_names=character_names,
        image_paths=image_paths,
    )
    index.save(store.root / "index.npz", store.root / "index_meta.json")
    index._correlation_profile_path = store.root / CORRELATION_PROFILE_FILE_NAME  # type: ignore[attr-defined]
    return index


def load_or_build_custom_character_index(
    store: CustomCharacterStore,
    tagger: WD14Tagger,
    preferred_language: str = "zh-CN",
    rebuild: bool = False,
) -> CharacterVectorIndex | None:
    """Load cached custom-character index when available, otherwise rebuild."""
    index_path = store.root / "index.npz"
    meta_path = store.root / "index_meta.json"
    if not bool(rebuild) and index_path.exists():
        try:
            index = CharacterVectorIndex.load(
                index_path=index_path,
                meta_path=meta_path if meta_path.exists() else None,
            )
            index._correlation_profile_path = store.root / CORRELATION_PROFILE_FILE_NAME  # type: ignore[attr-defined]
            return index
        except Exception:
            pass
    return build_custom_character_index(
        store=store,
        tagger=tagger,
        preferred_language=preferred_language,
    )


