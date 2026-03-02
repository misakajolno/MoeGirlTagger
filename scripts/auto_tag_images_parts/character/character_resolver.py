"""Final character resolution logic over weighted query vectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from scripts.auto_tag_images_parts.constants import (
        CORRELATION_PROFILE_MIN_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        FULL_IMAGE_CHARACTER_WEIGHT,
        HUGE_CHARACTER_LIBRARY_ROWS,
        HUGE_LIBRARY_SECONDARY_RATIO_DELTA,
        LARGE_CHARACTER_LIBRARY_ROWS,
        LARGE_LIBRARY_SECONDARY_RATIO_DELTA,
        MIN_CHARACTER_MATCH_CANDIDATES,
        MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO,
        MULTI_CHARACTER_SECONDARY_SCORE_RATIO,
        SINGLE_REFERENCE_MULTI_SCORE_FACTOR,
    )
    from scripts.auto_tag_images_parts.tagger import normalize_token
    from scripts.auto_tag_images_parts.character.character_profiles import (
        _CharacterCorrelationProfile,
        _get_character_correlation_profiles,
    )
    from scripts.auto_tag_images_parts.character.character_scoring import (
        _attribute_score_adjustment,
        _correlation_multiplier,
        _extract_dominant_group,
    )
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.auto_tag_images_parts.constants import (
        CORRELATION_PROFILE_MIN_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        FULL_IMAGE_CHARACTER_WEIGHT,
        HUGE_CHARACTER_LIBRARY_ROWS,
        HUGE_LIBRARY_SECONDARY_RATIO_DELTA,
        LARGE_CHARACTER_LIBRARY_ROWS,
        LARGE_LIBRARY_SECONDARY_RATIO_DELTA,
        MIN_CHARACTER_MATCH_CANDIDATES,
        MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO,
        MULTI_CHARACTER_SECONDARY_SCORE_RATIO,
        SINGLE_REFERENCE_MULTI_SCORE_FACTOR,
    )
    from scripts.auto_tag_images_parts.tagger import normalize_token
    from scripts.auto_tag_images_parts.character.character_profiles import (
        _CharacterCorrelationProfile,
        _get_character_correlation_profiles,
    )
    from scripts.auto_tag_images_parts.character.character_scoring import (
        _attribute_score_adjustment,
        _correlation_multiplier,
        _extract_dominant_group,
    )
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex

@dataclass
class _CharacterEvidence:
    character_id: str
    character_name: str
    best_score: float = 0.0
    best_head_score: float = 0.0
    best_head_region: int = -1
    region_scores: dict[int, float] = field(default_factory=dict)
    reference_rows: set[int] = field(default_factory=set)


def resolve_custom_characters_with_region_queries(
    query_items: Iterable[tuple[np.ndarray, float]],
    custom_index: CharacterVectorIndex | None,
    min_similarity: float,
    top_k: int = 1,
    min_margin: float = 0.0,
    tag_index: dict[str, int] | None = None,
    normalized_tag_index: dict[str, int] | None = None,
    correlation_profiles: dict[str, _CharacterCorrelationProfile] | None = None,
) -> list[str]:
    """Resolve custom characters using weighted multi-region queries."""
    if custom_index is None:
        return []
    query_item_list = list(query_items)
    if not query_item_list:
        return []

    safe_top_k = max(1, int(top_k))
    head_query_count = max(0, len(query_item_list) - 1)
    prepared_tag_index: dict[str, int] = {}
    if normalized_tag_index is not None:
        for raw_name, raw_index in normalized_tag_index.items():
            normalized_name = str(raw_name).strip()
            if not normalized_name:
                continue
            try:
                prepared_tag_index[normalized_name] = int(raw_index)
            except Exception:
                continue
    elif tag_index:
        for raw_name, raw_index in tag_index.items():
            normalized_name = normalize_token(str(raw_name))
            if not normalized_name:
                continue
            try:
                prepared_tag_index[normalized_name] = int(raw_index)
            except Exception:
                continue

    prepared_profiles: dict[str, _CharacterCorrelationProfile] = (
        correlation_profiles if isinstance(correlation_profiles, dict) else {}
    )
    if correlation_profiles is None and prepared_tag_index:
        prepared_profiles = _get_character_correlation_profiles(custom_index, prepared_tag_index)

    reference_count_by_id = getattr(custom_index, "reference_count_by_id", {})
    evidence_by_id: dict[str, _CharacterEvidence] = {}

    for query_index, (query_vector, weight) in enumerate(query_item_list):
        query_array = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        query_weight = max(0.0, float(weight))
        if query_weight <= 0.0:
            continue
        query_hair_group = ""
        query_hair_score = 0.0
        query_eye_group = ""
        query_eye_score = 0.0
        if prepared_tag_index:
            query_hair_group, query_hair_score = _extract_dominant_group(
                vector=query_array,
                tag_index=prepared_tag_index,
                candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
                group_map=HAIR_COLOR_GROUP_MAP,
                min_score=CORRELATION_PROFILE_MIN_SCORE,
            )
            query_eye_group, query_eye_score = _extract_dominant_group(
                vector=query_array,
                tag_index=prepared_tag_index,
                candidates=ATTRIBUTE_EYE_COLOR_TAGS,
                group_map=EYE_COLOR_GROUP_MAP,
                min_score=CORRELATION_PROFILE_MIN_SCORE,
            )
        candidate_limit = max(MIN_CHARACTER_MATCH_CANDIDATES, safe_top_k * 64)
        if custom_index.embeddings.ndim == 2:
            candidate_limit = min(candidate_limit, int(custom_index.embeddings.shape[0]))
        matches = custom_index.query_many(
            query_vector=query_array,
            min_similarity=0.0,
            top_k=candidate_limit,
        )
        for match in matches:
            name = str(match.character_name).strip()
            if not name:
                continue
            character_id = str(match.character_id).strip()
            if not character_id:
                continue
            adjusted_similarity = float(match.similarity)
            profile = prepared_profiles.get(character_id)
            adjusted_similarity *= _correlation_multiplier(
                hair_group=query_hair_group,
                hair_score=query_hair_score,
                eye_group=query_eye_group,
                eye_score=query_eye_score,
                profile=profile,
            )
            if prepared_tag_index:
                row_index = int(match.row_index)
                if 0 <= row_index < custom_index.embeddings.shape[0]:
                    reference_vector = np.asarray(custom_index.embeddings[row_index], dtype=np.float32).reshape(-1)
                    adjustment = _attribute_score_adjustment(
                        query_vector=query_array,
                        reference_vector=reference_vector,
                        tag_index=prepared_tag_index,
                    )
                    if query_weight <= (FULL_IMAGE_CHARACTER_WEIGHT + 0.05):
                        adjustment *= 0.40
                    elif query_weight < 0.90:
                        adjustment *= 0.70
                    adjusted_similarity += adjustment
            adjusted_similarity = max(0.0, min(1.0, adjusted_similarity))
            if adjusted_similarity <= 0.0:
                continue
            score = adjusted_similarity * query_weight
            evidence = evidence_by_id.get(character_id)
            if evidence is None:
                evidence = _CharacterEvidence(character_id=character_id, character_name=name)
                evidence_by_id[character_id] = evidence
            evidence.character_name = name
            if score > evidence.best_score:
                evidence.best_score = score
            if query_index > 0 and score > evidence.best_head_score:
                evidence.best_head_score = score
                evidence.best_head_region = int(query_index)
            previous_region_score = evidence.region_scores.get(query_index)
            if previous_region_score is None or score > previous_region_score:
                evidence.region_scores[query_index] = score
            evidence.reference_rows.add(int(match.row_index))

    if not evidence_by_id:
        return []

    ranked_records: list[tuple[str, str, float, int, float]] = []
    similarity_floor = max(0.0, float(min_similarity))
    for character_id, evidence in evidence_by_id.items():
        final_score = float(evidence.best_score)
        supported_regions = sum(
            1
            for region_index, region_score in evidence.region_scores.items()
            if region_index > 0 and float(region_score) >= (similarity_floor * 0.92)
        )
        if supported_regions >= 2:
            final_score += 0.03 * min(2, supported_regions - 1)
        if len(evidence.reference_rows) >= 2:
            final_score += 0.012 * min(3, len(evidence.reference_rows) - 1)

        reference_count = int(reference_count_by_id.get(character_id, 1))
        if safe_top_k > 1 and head_query_count >= 2 and reference_count <= 1 and evidence.best_head_score < 0.62:
            final_score *= float(SINGLE_REFERENCE_MULTI_SCORE_FACTOR)

        ranked_records.append(
            (
                character_id,
                evidence.character_name,
                final_score,
                evidence.best_head_region,
                evidence.best_head_score,
            )
        )

    ranked = sorted(ranked_records, key=lambda item: item[2], reverse=True)
    best_score = float(ranked[0][2])
    if best_score < float(min_similarity):
        return []
    if safe_top_k <= 1 and len(ranked) >= 2:
        second_score = float(ranked[1][2])
        if (best_score - second_score) < float(min_margin):
            return []
    required_score = float(min_similarity)
    if safe_top_k > 1:
        secondary_ratio = float(MULTI_CHARACTER_SECONDARY_SCORE_RATIO)
        library_rows = int(custom_index.embeddings.shape[0]) if custom_index.embeddings.ndim == 2 else 0
        if library_rows >= HUGE_CHARACTER_LIBRARY_ROWS:
            secondary_ratio += float(HUGE_LIBRARY_SECONDARY_RATIO_DELTA)
        elif library_rows >= LARGE_CHARACTER_LIBRARY_ROWS:
            secondary_ratio += float(LARGE_LIBRARY_SECONDARY_RATIO_DELTA)
        required_score = max(required_score, best_score * secondary_ratio)
    candidates = [item for item in ranked if float(item[2]) >= required_score]
    if safe_top_k <= 1:
        return [candidates[0][1]] if candidates else []

    selected: list[tuple[str, str, float, int, float]] = []
    used_head_regions: set[int] = set()
    for character_id, character_name, score, head_region, head_score in candidates:
        _ = character_id
        if len(selected) >= safe_top_k:
            break
        if not selected:
            selected.append((character_id, character_name, score, head_region, head_score))
            if head_region > 0:
                used_head_regions.add(head_region)
            continue
        if head_region > 0 and head_region in used_head_regions:
            if float(head_score) < (best_score * float(MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO)):
                continue
        selected.append((character_id, character_name, score, head_region, head_score))
        if head_region > 0:
            used_head_regions.add(head_region)
    return [item[1] for item in selected[:safe_top_k]]


def resolve_custom_characters(
    query_vector: np.ndarray,
    custom_index: CharacterVectorIndex | None,
    min_similarity: float,
    top_k: int = 1,
    min_margin: float = 0.0,
    tag_index: dict[str, int] | None = None,
    normalized_tag_index: dict[str, int] | None = None,
    correlation_profiles: dict[str, _CharacterCorrelationProfile] | None = None,
) -> list[str]:
    """Resolve custom character names using vector retrieval."""
    return resolve_custom_characters_with_region_queries(
        query_items=[(query_vector, 1.0)],
        custom_index=custom_index,
        min_similarity=min_similarity,
        top_k=top_k,
        min_margin=min_margin,
        tag_index=tag_index,
        normalized_tag_index=normalized_tag_index,
        correlation_profiles=correlation_profiles,
    )
