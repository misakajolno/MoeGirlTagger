"""Region proposal and query vector construction for character matching."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image

try:
    from scripts.auto_tag_images_parts.constants import (
        CHARACTER_REGION_SPECS,
        FULL_IMAGE_CHARACTER_WEIGHT,
        HEAD_BASE_REGION_SPECS,
        HEAD_CANDIDATE_FALLBACK_EVAL_MULTI,
        HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE,
        HEAD_FALLBACK_TRIGGER_SCORE,
        HEAD_NEGATIVE_TAG_WEIGHTS,
        HEAD_NMS_IOU_THRESHOLD,
        HEAD_PROBE_CENTERS,
        HEAD_PROBE_HALF_WIDTHS,
        HEAD_PROBE_VERTICAL_RANGES,
        HEAD_SCORE_MIN_THRESHOLD,
        HEAD_SIGNAL_TAG_WEIGHTS,
        HEAD_VECTOR_DUPLICATE_SIMILARITY,
        MAX_HEAD_CANDIDATE_EVAL_MULTI,
        MAX_HEAD_CANDIDATE_EVAL_SINGLE,
        MAX_HEAD_QUERY_REGIONS,
        MIN_CHARACTER_REGION_SIDE,
    )
    from scripts.auto_tag_images_parts.tagger import ModelTag, WD14Tagger, normalize_token
    from scripts.auto_tag_images_parts.character.character_scoring import _box_iou, _cosine_similarity
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from scripts.auto_tag_images_parts.constants import (
        CHARACTER_REGION_SPECS,
        FULL_IMAGE_CHARACTER_WEIGHT,
        HEAD_BASE_REGION_SPECS,
        HEAD_CANDIDATE_FALLBACK_EVAL_MULTI,
        HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE,
        HEAD_FALLBACK_TRIGGER_SCORE,
        HEAD_NEGATIVE_TAG_WEIGHTS,
        HEAD_NMS_IOU_THRESHOLD,
        HEAD_PROBE_CENTERS,
        HEAD_PROBE_HALF_WIDTHS,
        HEAD_PROBE_VERTICAL_RANGES,
        HEAD_SCORE_MIN_THRESHOLD,
        HEAD_SIGNAL_TAG_WEIGHTS,
        HEAD_VECTOR_DUPLICATE_SIMILARITY,
        MAX_HEAD_CANDIDATE_EVAL_MULTI,
        MAX_HEAD_CANDIDATE_EVAL_SINGLE,
        MAX_HEAD_QUERY_REGIONS,
        MIN_CHARACTER_REGION_SIDE,
    )
    from scripts.auto_tag_images_parts.tagger import ModelTag, WD14Tagger, normalize_token
    from scripts.auto_tag_images_parts.character.character_scoring import _box_iou, _cosine_similarity

def _normalized_crop_box(
    width: int,
    height: int,
    left_ratio: float,
    top_ratio: float,
    right_ratio: float,
    bottom_ratio: float,
) -> tuple[int, int, int, int] | None:
    if width <= 0 or height <= 0:
        return None

    left = max(0, min(width - 1, int(round(width * left_ratio))))
    top = max(0, min(height - 1, int(round(height * top_ratio))))
    right = max(left + 1, min(width, int(round(width * right_ratio))))
    bottom = max(top + 1, min(height, int(round(height * bottom_ratio))))
    if right - left < MIN_CHARACTER_REGION_SIDE or bottom - top < MIN_CHARACTER_REGION_SIDE:
        return None
    return left, top, right, bottom

def _head_candidate_score(predicted_tags: Iterable[ModelTag]) -> float:
    score_by_name: dict[str, float] = {}
    for tag in predicted_tags:
        if str(tag.category).strip() != "general":
            continue
        score_by_name[normalize_token(tag.name)] = float(tag.score)

    score = 0.0
    for name, weight in HEAD_SIGNAL_TAG_WEIGHTS.items():
        score += weight * float(score_by_name.get(name, 0.0))
    for name, weight in HEAD_NEGATIVE_TAG_WEIGHTS.items():
        score += weight * float(score_by_name.get(name, 0.0))
    return max(0.0, float(score))


def _build_split_head_ratio_boxes(inferred_count: int) -> list[tuple[float, float, float, float]]:
    count = max(1, min(int(inferred_count), MAX_HEAD_QUERY_REGIONS))
    if count <= 1:
        return []

    boxes: list[tuple[float, float, float, float]] = []
    step = 1.0 / float(count)
    lane_width = min(0.50, max(0.28, step * 0.95))
    half = lane_width / 2.0
    for index in range(count):
        center = (index + 0.5) * step
        left = max(0.0, center - half)
        right = min(1.0, center + half)
        boxes.append((left, 0.00, right, 0.56))
        boxes.append((left, 0.08, right, 0.66))
    return boxes


def _build_probe_head_ratio_boxes() -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    for center in HEAD_PROBE_CENTERS:
        for half_width in HEAD_PROBE_HALF_WIDTHS:
            left = max(0.0, center - half_width)
            right = min(1.0, center + half_width)
            if right - left <= 0.0:
                continue
            for top, bottom in HEAD_PROBE_VERTICAL_RANGES:
                boxes.append((left, top, right, bottom))
    return boxes


def _generate_head_candidate_boxes(
    width: int,
    height: int,
    inferred_count: int,
) -> list[tuple[int, int, int, int]]:
    ratio_specs = _build_split_head_ratio_boxes(inferred_count)
    ratio_specs.extend(list(HEAD_BASE_REGION_SPECS))
    ratio_specs.extend(_build_probe_head_ratio_boxes())
    boxes: list[tuple[int, int, int, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for left_ratio, top_ratio, right_ratio, bottom_ratio in ratio_specs:
        box = _normalized_crop_box(
            width=width,
            height=height,
            left_ratio=left_ratio,
            top_ratio=top_ratio,
            right_ratio=right_ratio,
            bottom_ratio=bottom_ratio,
        )
        if box is None or box in seen:
            continue
        seen.add(box)
        boxes.append(box)
    return boxes


def _select_head_regions(
    image: Image.Image,
    tagger: WD14Tagger,
    inferred_count: int,
) -> list[tuple[np.ndarray, float]]:
    width, height = image.size
    raw_boxes = _generate_head_candidate_boxes(width=width, height=height, inferred_count=inferred_count)
    if not raw_boxes:
        return []
    candidate_eval_limit = (
        MAX_HEAD_CANDIDATE_EVAL_MULTI if int(inferred_count) > 1 else MAX_HEAD_CANDIDATE_EVAL_SINGLE
    )
    candidate_eval_limit = max(1, int(candidate_eval_limit))
    target_count = max(1, min(int(inferred_count), MAX_HEAD_QUERY_REGIONS))
    scored: list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]] = []

    def _append_scored(boxes: Iterable[tuple[int, int, int, int]]) -> None:
        for box in boxes:
            crop = image.crop(box)
            try:
                predicted, vector = tagger.predict_with_vector_from_image(crop)
            except Exception:
                continue
            head_score = _head_candidate_score(predicted)
            width_box = max(1, box[2] - box[0])
            height_box = max(1, box[3] - box[1])
            area_ratio = float(width_box * height_box) / float(max(1, width * height))
            effective_head_score = head_score - max(0.0, area_ratio - 0.18) * 0.60
            scored.append(
                (
                    float(effective_head_score),
                    float(head_score),
                    area_ratio,
                    box,
                    np.asarray(vector, dtype=np.float32).reshape(-1),
                )
            )

    def _select_from_scored() -> list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]]:
        if not scored:
            return []
        ranked = sorted(scored, key=lambda item: (item[0], -item[2]), reverse=True)
        selected_local: list[tuple[float, float, float, tuple[int, int, int, int], np.ndarray]] = []
        for candidate in ranked:
            _effective_head_score, head_score, _area_ratio, box, vector = candidate
            if any(
                _box_iou(box, existing_box) >= HEAD_NMS_IOU_THRESHOLD
                for _, _, _, existing_box, _ in selected_local
            ):
                continue
            if any(
                _cosine_similarity(vector, existing_vector) >= HEAD_VECTOR_DUPLICATE_SIMILARITY
                for _, _, _, _, existing_vector in selected_local
            ):
                continue
            if head_score < HEAD_SCORE_MIN_THRESHOLD and len(selected_local) >= target_count:
                continue
            selected_local.append(candidate)
            if len(selected_local) >= target_count:
                break
        return selected_local

    _append_scored(raw_boxes[:candidate_eval_limit])
    selected = _select_from_scored()

    best_head_score = float(selected[0][1]) if selected else 0.0
    need_fallback = len(selected) < target_count or best_head_score < float(HEAD_FALLBACK_TRIGGER_SCORE)
    if need_fallback and len(raw_boxes) > candidate_eval_limit:
        fallback_eval = (
            HEAD_CANDIDATE_FALLBACK_EVAL_MULTI
            if int(inferred_count) > 1
            else HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE
        )
        fallback_eval = max(0, int(fallback_eval))
        if fallback_eval > 0:
            tail_end = min(len(raw_boxes), candidate_eval_limit + fallback_eval)
            _append_scored(raw_boxes[candidate_eval_limit:tail_end])
            selected = _select_from_scored()

    result: list[tuple[np.ndarray, float]] = []
    for _effective_head_score, head_score, _area_ratio, _box, vector in selected:
        weight = 0.95 + min(0.30, max(0.0, float(head_score)))
        result.append((vector, float(weight)))
    return result


def build_custom_character_query_items(
    image_path: Path,
    full_query_vector: np.ndarray,
    tagger: WD14Tagger,
    inferred_character_count: int = 1,
) -> list[tuple[np.ndarray, float]]:
    """Build weighted query vectors for custom-character retrieval.

    Uses full-image vector as fallback and detected head regions as primary
    queries so facial/hair cues dominate character matching.
    """
    items: list[tuple[np.ndarray, float]] = [
        (np.asarray(full_query_vector, dtype=np.float32).reshape(-1), float(FULL_IMAGE_CHARACTER_WEIGHT))
    ]

    try:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            items.extend(
                _select_head_regions(
                    image=image,
                    tagger=tagger,
                    inferred_count=max(1, int(inferred_character_count)),
                )
            )
    except Exception:
        return items

    if len(items) <= 1:
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                for _name, (left_ratio, top_ratio, right_ratio, bottom_ratio), weight in CHARACTER_REGION_SPECS:
                    box = _normalized_crop_box(
                        width=width,
                        height=height,
                        left_ratio=left_ratio,
                        top_ratio=top_ratio,
                        right_ratio=right_ratio,
                        bottom_ratio=bottom_ratio,
                    )
                    if box is None:
                        continue
                    crop = image.crop(box)
                    try:
                        _, vector = tagger.predict_with_vector_from_image(crop)
                    except Exception:
                        continue
                    items.append((np.asarray(vector, dtype=np.float32).reshape(-1), float(weight)))
        except Exception:
            return items

    return items

