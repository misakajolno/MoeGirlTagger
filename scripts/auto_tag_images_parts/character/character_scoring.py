"""Scoring primitives and attribute/correlation adjustments."""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from scripts.auto_tag_images_parts.constants import (
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_FACE_DETAIL_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        ATTRIBUTE_MAX_ADJUSTMENT,
        ATTRIBUTE_MULTI_PERSON_TAGS,
        ATTRIBUTE_REFERENCE_MATCH_SCORE,
        ATTRIBUTE_REFERENCE_MISS_SCORE,
        ATTRIBUTE_STRONG_QUERY_SCORE,
        ATTRIBUTE_STYLE_DETAIL_TAGS,
        CORRELATION_QUERY_MIN_EYE_SCORE,
        CORRELATION_QUERY_MIN_HAIR_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
    )
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.auto_tag_images_parts.constants import (
        ATTRIBUTE_EYE_COLOR_TAGS,
        ATTRIBUTE_FACE_DETAIL_TAGS,
        ATTRIBUTE_HAIR_COLOR_TAGS,
        ATTRIBUTE_MAX_ADJUSTMENT,
        ATTRIBUTE_MULTI_PERSON_TAGS,
        ATTRIBUTE_REFERENCE_MATCH_SCORE,
        ATTRIBUTE_REFERENCE_MISS_SCORE,
        ATTRIBUTE_STRONG_QUERY_SCORE,
        ATTRIBUTE_STYLE_DETAIL_TAGS,
        CORRELATION_QUERY_MIN_EYE_SCORE,
        CORRELATION_QUERY_MIN_HAIR_SCORE,
        EYE_COLOR_GROUP_MAP,
        HAIR_COLOR_GROUP_MAP,
    )

def _box_iou(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = float((right - left) * (bottom - top))
    first_area = float(max(1, (first[2] - first[0]) * (first[3] - first[1])))
    second_area = float(max(1, (second[2] - second[0]) * (second[3] - second[1])))
    union = max(1e-6, first_area + second_area - intersection)
    return intersection / union


def _cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    left = np.asarray(first, dtype=np.float32).reshape(-1)
    right = np.asarray(second, dtype=np.float32).reshape(-1)
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return float(np.dot(left / left_norm, right / right_norm))


def _tag_score_from_vector(vector: np.ndarray, tag_index: dict[str, int], tag_name: str) -> float:
    index = tag_index.get(tag_name)
    if index is None:
        return 0.0
    idx = int(index)
    if idx < 0 or idx >= vector.size:
        return 0.0
    score = float(vector[idx])
    if score <= 0.0:
        return 0.0
    return min(1.0, score)


def _group_from_tag(tag_name: str, group_map: dict[str, str] | None) -> str:
    if not group_map:
        return ""
    return str(group_map.get(tag_name, "")).strip()


def _exclusive_attribute_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    match_bonus: float,
    conflict_penalty: float,
    group_map: dict[str, str] | None = None,
) -> float:
    available = [name for name in candidates if name in tag_index]
    if len(available) < 2:
        return 0.0

    query_scores = np.asarray(
        [_tag_score_from_vector(query_vector, tag_index, name) for name in available],
        dtype=np.float32,
    )
    query_best_idx = int(np.argmax(query_scores))
    query_best_score = float(query_scores[query_best_idx])
    if query_best_score < ATTRIBUTE_STRONG_QUERY_SCORE:
        return 0.0

    query_second_score = 0.0
    if query_scores.size >= 2:
        sorted_scores = np.sort(query_scores)
        query_second_score = float(sorted_scores[-2])
    query_confidence = max(0.0, query_best_score - query_second_score)
    if query_confidence < 0.10:
        return 0.0

    reference_scores = np.asarray(
        [_tag_score_from_vector(reference_vector, tag_index, name) for name in available],
        dtype=np.float32,
    )
    reference_best_idx = int(np.argmax(reference_scores))
    reference_best_score = float(reference_scores[reference_best_idx])
    if reference_best_score < ATTRIBUTE_REFERENCE_MATCH_SCORE:
        return 0.0

    query_best_name = str(available[query_best_idx])
    reference_best_name = str(available[reference_best_idx])
    if reference_best_idx == query_best_idx:
        return float(match_bonus) * min(query_best_score, reference_best_score)

    query_group = _group_from_tag(query_best_name, group_map)
    reference_group = _group_from_tag(reference_best_name, group_map)
    if query_group and reference_group and query_group == reference_group:
        return float(match_bonus) * min(query_best_score, reference_best_score) * 0.80
    if query_group == "multi" or reference_group == "multi":
        return 0.0

    disagreement = min(query_best_score, reference_best_score)
    return -float(conflict_penalty) * disagreement * min(1.0, query_confidence + 0.35)


def _detail_attribute_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    match_bonus: float,
    miss_penalty: float,
    query_min_score: float = ATTRIBUTE_STRONG_QUERY_SCORE,
    reference_match_score: float = ATTRIBUTE_REFERENCE_MATCH_SCORE,
    reference_miss_score: float = ATTRIBUTE_REFERENCE_MISS_SCORE,
) -> float:
    adjustment = 0.0
    for name in candidates:
        query_score = _tag_score_from_vector(query_vector, tag_index, name)
        if query_score < float(query_min_score):
            continue
        reference_score = _tag_score_from_vector(reference_vector, tag_index, name)
        if reference_score >= float(reference_match_score):
            adjustment += float(match_bonus) * min(query_score, reference_score)
            continue
        if reference_score <= float(reference_miss_score):
            adjustment -= float(miss_penalty) * query_score
    return adjustment


def _attribute_score_adjustment(
    query_vector: np.ndarray,
    reference_vector: np.ndarray,
    tag_index: dict[str, int] | None,
) -> float:
    """Adjust retrieval score using high-discriminative face/hair attributes."""
    if not tag_index:
        return 0.0

    query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
    reference = np.asarray(reference_vector, dtype=np.float32).reshape(-1)
    if query.size == 0 or reference.size == 0 or query.size != reference.size:
        return 0.0

    # Caller already passes normalized WD14 tag index; avoid rebuilding for each match.
    normalized_tag_index = tag_index

    multi_person_score = max(
        (_tag_score_from_vector(query, normalized_tag_index, name) for name in ATTRIBUTE_MULTI_PERSON_TAGS),
        default=0.0,
    )
    scene_conflict_scale = max(0.35, 1.0 - (multi_person_score * 0.75))
    closed_eyes_score = _tag_score_from_vector(query, normalized_tag_index, "closed_eyes")
    eye_conflict_scale = scene_conflict_scale
    if closed_eyes_score >= 0.45:
        eye_conflict_scale *= max(0.25, 1.0 - closed_eyes_score)

    adjustment = 0.0
    adjustment += _exclusive_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_HAIR_COLOR_TAGS,
        match_bonus=0.11,
        conflict_penalty=0.30 * scene_conflict_scale,
        group_map=HAIR_COLOR_GROUP_MAP,
    )
    adjustment += _exclusive_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_EYE_COLOR_TAGS,
        match_bonus=0.08,
        conflict_penalty=0.22 * eye_conflict_scale,
        group_map=EYE_COLOR_GROUP_MAP,
    )
    adjustment += _detail_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_STYLE_DETAIL_TAGS,
        match_bonus=0.035,
        miss_penalty=0.050 * scene_conflict_scale,
    )
    adjustment += _detail_attribute_adjustment(
        query_vector=query,
        reference_vector=reference,
        tag_index=normalized_tag_index,
        candidates=ATTRIBUTE_FACE_DETAIL_TAGS,
        match_bonus=0.120,
        miss_penalty=0.120 * scene_conflict_scale,
        query_min_score=0.25,
        reference_match_score=0.28,
        reference_miss_score=0.10,
    )
    return float(max(-ATTRIBUTE_MAX_ADJUSTMENT, min(ATTRIBUTE_MAX_ADJUSTMENT, adjustment)))



def _extract_dominant_group(
    vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: tuple[str, ...],
    group_map: dict[str, str],
    min_score: float,
) -> tuple[str, float]:
    best_name = ""
    best_score = 0.0
    for candidate in candidates:
        score = _tag_score_from_vector(vector, tag_index, candidate)
        if score > best_score:
            best_name = str(candidate)
            best_score = score
    if best_score < float(min_score):
        return "", 0.0
    group = _group_from_tag(best_name, group_map)
    if not group:
        return "", 0.0
    return group, best_score

def _correlation_multiplier(
    hair_group: str,
    hair_score: float,
    eye_group: str,
    eye_score: float,
    profile: _CharacterCorrelationProfile | None,
) -> float:
    if profile is None:
        return 1.0
    factor = 1.0
    hair_mismatch = False
    eye_mismatch = False

    if hair_group and float(hair_score) >= CORRELATION_QUERY_MIN_HAIR_SCORE and profile.hair_groups:
        if hair_group in profile.hair_groups or "multi" in profile.hair_groups:
            factor *= 1.05
        else:
            factor *= 0.88
            hair_mismatch = True

    if eye_group and float(eye_score) >= CORRELATION_QUERY_MIN_EYE_SCORE and profile.eye_groups:
        if eye_group in profile.eye_groups or "multi" in profile.eye_groups:
            factor *= 1.03
        else:
            factor *= 0.92
            eye_mismatch = True

    if hair_mismatch and eye_mismatch:
        factor *= 0.90
    return float(max(0.70, min(1.18, factor)))

