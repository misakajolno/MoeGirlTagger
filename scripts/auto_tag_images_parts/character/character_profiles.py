"""Persistent correlation profile cache for custom characters."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    from scripts.auto_tag_images_parts.constants import (
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        CORRELATION_PROFILE_SCHEMA_VERSION,
        CORRELATION_PROFILE_MIN_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
    )
    from scripts.auto_tag_images_parts.character.character_scoring import _extract_dominant_group
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.auto_tag_images_parts.constants import (
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        CORRELATION_PROFILE_SCHEMA_VERSION,
        CORRELATION_PROFILE_MIN_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
    )
    from scripts.auto_tag_images_parts.character.character_scoring import _extract_dominant_group
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex

@dataclass(frozen=True)
class _CharacterCorrelationProfile:
    hair_groups: frozenset[str]
    eye_groups: frozenset[str]


def _tag_index_signature(tag_index: dict[str, int]) -> str:
    hasher = hashlib.sha1()
    for name, index in sorted(tag_index.items(), key=lambda item: item[1]):
        hasher.update(str(name).encode("utf-8"))
        hasher.update(b":")
        hasher.update(str(int(index)).encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def _character_index_signature(custom_index: CharacterVectorIndex) -> str:
    cached = getattr(custom_index, "_character_index_signature", None)
    if isinstance(cached, str) and cached:
        return cached
    hasher = hashlib.sha1()
    row_count = int(custom_index.embeddings.shape[0]) if custom_index.embeddings.ndim == 2 else 0
    dim_count = int(custom_index.embeddings.shape[1]) if custom_index.embeddings.ndim == 2 else 0
    hasher.update(f"{row_count}:{dim_count}\n".encode("utf-8"))
    for character_id, image_path in zip(custom_index.character_ids, custom_index.image_paths):
        hasher.update(str(character_id).encode("utf-8"))
        hasher.update(b"|")
        hasher.update(str(image_path).encode("utf-8"))
        hasher.update(b"\n")
    signature = hasher.hexdigest()
    custom_index._character_index_signature = signature  # type: ignore[attr-defined]
    return signature


def _serialize_correlation_profiles(
    profiles: dict[str, _CharacterCorrelationProfile],
) -> dict[str, dict[str, list[str]]]:
    payload: dict[str, dict[str, list[str]]] = {}
    for character_id, profile in profiles.items():
        payload[str(character_id)] = {
            "hair_groups": sorted(str(name) for name in profile.hair_groups if str(name)),
            "eye_groups": sorted(str(name) for name in profile.eye_groups if str(name)),
        }
    return payload


def _deserialize_correlation_profiles(payload: object) -> dict[str, _CharacterCorrelationProfile]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, _CharacterCorrelationProfile] = {}
    for raw_character_id, raw_value in payload.items():
        character_id = str(raw_character_id).strip()
        if not character_id or not isinstance(raw_value, dict):
            continue
        raw_hair = raw_value.get("hair_groups", [])
        raw_eyes = raw_value.get("eye_groups", [])
        hair_groups = frozenset(str(item).strip() for item in raw_hair if str(item).strip())
        eye_groups = frozenset(str(item).strip() for item in raw_eyes if str(item).strip())
        result[character_id] = _CharacterCorrelationProfile(
            hair_groups=hair_groups,
            eye_groups=eye_groups,
        )
    return result


def _load_correlation_profiles_from_file(
    profile_path: Path,
    expected_tag_signature: str,
    expected_index_signature: str,
) -> dict[str, _CharacterCorrelationProfile] | None:
    if not profile_path.exists():
        return None
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version", 0)) != CORRELATION_PROFILE_SCHEMA_VERSION:
        return None
    if str(payload.get("tag_index_signature", "")).strip() != expected_tag_signature:
        return None
    if str(payload.get("index_signature", "")).strip() != expected_index_signature:
        return None
    profiles = _deserialize_correlation_profiles(payload.get("profiles"))
    if not profiles:
        return None
    return profiles


def _save_correlation_profiles_to_file(
    profile_path: Path,
    profiles: dict[str, _CharacterCorrelationProfile],
    tag_signature: str,
    index_signature: str,
) -> None:
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CORRELATION_PROFILE_SCHEMA_VERSION,
        "tag_index_signature": tag_signature,
        "index_signature": index_signature,
        "build_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "profiles": _serialize_correlation_profiles(profiles),
    }
    temp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(profile_path)


def _build_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    profile_counts: dict[str, dict[str, dict[str, int]]] = {}
    if custom_index.embeddings.ndim != 2:
        return {}
    for row_index, character_id in enumerate(custom_index.character_ids):
        normalized_character_id = str(character_id).strip()
        if not normalized_character_id:
            continue
        vector = np.asarray(custom_index.embeddings[row_index], dtype=np.float32).reshape(-1)
        hair_group, _hair_score = _extract_dominant_group(
            vector=vector,
            tag_index=tag_index,
            candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
            group_map=HAIR_COLOR_GROUP_MAP,
            min_score=CORRELATION_PROFILE_MIN_SCORE,
        )
        eye_group, _eye_score = _extract_dominant_group(
            vector=vector,
            tag_index=tag_index,
            candidates=ATTRIBUTE_EYE_COLOR_TAGS,
            group_map=EYE_COLOR_GROUP_MAP,
            min_score=CORRELATION_PROFILE_MIN_SCORE,
        )
        bucket = profile_counts.setdefault(normalized_character_id, {"hair": {}, "eyes": {}})
        if hair_group:
            bucket["hair"][hair_group] = int(bucket["hair"].get(hair_group, 0)) + 1
        if eye_group:
            bucket["eyes"][eye_group] = int(bucket["eyes"].get(eye_group, 0)) + 1

    profiles: dict[str, _CharacterCorrelationProfile] = {}
    for character_id, value in profile_counts.items():
        hair_groups = frozenset(str(name) for name in value["hair"].keys() if str(name))
        eye_groups = frozenset(str(name) for name in value["eyes"].keys() if str(name))
        profiles[character_id] = _CharacterCorrelationProfile(
            hair_groups=hair_groups,
            eye_groups=eye_groups,
        )
    return profiles


def _get_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    tag_signature = _tag_index_signature(tag_index)
    index_signature = _character_index_signature(custom_index)
    cache_key = f"{tag_signature}:{index_signature}"
    cached_key = getattr(custom_index, "_correlation_profile_cache_key", None)
    cached_profiles = getattr(custom_index, "_correlation_profiles", None)
    if cached_key == cache_key and isinstance(cached_profiles, dict) and cached_profiles:
        return cached_profiles

    profile_path_value = getattr(custom_index, "_correlation_profile_path", None)
    profile_path = Path(profile_path_value) if isinstance(profile_path_value, Path) else None
    if profile_path is not None:
        loaded = _load_correlation_profiles_from_file(
            profile_path=profile_path,
            expected_tag_signature=tag_signature,
            expected_index_signature=index_signature,
        )
        if loaded:
            custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
            custom_index._correlation_profiles = loaded  # type: ignore[attr-defined]
            return loaded

    profiles = _build_character_correlation_profiles(custom_index, tag_index)
    if profile_path is not None and profiles:
        try:
            _save_correlation_profiles_to_file(
                profile_path=profile_path,
                profiles=profiles,
                tag_signature=tag_signature,
                index_signature=index_signature,
            )
        except Exception:
            pass
    custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
    custom_index._correlation_profiles = profiles  # type: ignore[attr-defined]
    return profiles


def rebuild_character_correlation_profiles(
    custom_index: CharacterVectorIndex,
    tag_index: dict[str, int],
) -> dict[str, _CharacterCorrelationProfile]:
    """Force rebuild and persist character correlation profiles."""
    tag_signature = _tag_index_signature(tag_index)
    index_signature = _character_index_signature(custom_index)
    cache_key = f"{tag_signature}:{index_signature}"
    profiles = _build_character_correlation_profiles(custom_index, tag_index)

    profile_path_value = getattr(custom_index, "_correlation_profile_path", None)
    profile_path = Path(profile_path_value) if isinstance(profile_path_value, Path) else None
    if profile_path is not None and profiles:
        try:
            _save_correlation_profiles_to_file(
                profile_path=profile_path,
                profiles=profiles,
                tag_signature=tag_signature,
                index_signature=index_signature,
            )
        except Exception:
            pass
    custom_index._correlation_profile_cache_key = cache_key  # type: ignore[attr-defined]
    custom_index._correlation_profiles = profiles  # type: ignore[attr-defined]
    return profiles


