"""Audit local custom character library quality for large-scale recognition."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.moegirl_tagger.custom_character_index import CharacterVectorIndex
    from core.moegirl_tagger.custom_character_store import CustomCharacterStore, select_localized_alias

DEFAULT_CUSTOM_CHARACTERS_DIR = Path("data/character_library/custom")
DEFAULT_MODEL_DIR = Path("tools/wd14")
DEFAULT_OUTPUT_REPORT = "audit_report.json"

HAIR_COLOR_TAGS: tuple[str, ...] = (
    "black_hair",
    "blonde_hair",
    "brown_hair",
    "blue_hair",
    "green_hair",
    "grey_hair",
    "orange_hair",
    "pink_hair",
    "purple_hair",
    "red_hair",
    "silver_hair",
    "white_hair",
    "aqua_hair",
    "multicolored_hair",
    "two-tone_hair",
    "colored_inner_hair",
)
EYE_COLOR_TAGS: tuple[str, ...] = (
    "black_eyes",
    "brown_eyes",
    "blue_eyes",
    "green_eyes",
    "grey_eyes",
    "orange_eyes",
    "pink_eyes",
    "purple_eyes",
    "red_eyes",
    "yellow_eyes",
    "aqua_eyes",
    "multicolored_eyes",
    "heterochromia",
)
MULTI_PERSON_TAGS: tuple[str, ...] = (
    "multiple_girls",
    "multiple_boys",
    "multiple_boys_and_girls",
    "2girls",
    "3girls",
    "4girls",
    "5girls",
    "2boys",
    "3boys",
)
SCREENSHOT_NOISE_TAGS: tuple[str, ...] = (
    "english_text",
    "korean_text",
    "chat_log",
    "timestamp",
    "fake_screenshot",
    "comic",
    "text_focus",
)
SINGLE_SUBJECT_TAGS: tuple[str, ...] = ("1girl", "1boy", "solo")


@dataclass(frozen=True)
class AuditConfig:
    """Thresholds for library quality checks."""

    min_single_subject_score: float = 0.55
    multi_person_threshold: float = 0.45
    screenshot_noise_threshold: float = 0.45
    no_humans_threshold: float = 0.55
    dominant_attribute_score: float = 0.55
    outlier_similarity_threshold: float = 0.78
    low_consistency_threshold: float = 0.76
    include_clean_characters: bool = False
    language_code: str = "zh-CN"


def normalize_token(value: str) -> str:
    lowered = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return "".join(char for char in lowered if char.isalnum() or char == "_")


def load_tag_index(tags_csv_path: Path) -> dict[str, int]:
    """Load normalized WD14 tag -> index mapping from selected_tags.csv."""
    if not tags_csv_path.exists():
        raise FileNotFoundError(f"selected_tags.csv not found: {tags_csv_path}")

    tag_index: dict[str, int] = {}
    with tags_csv_path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        row_index = 0
        for row in reader:
            name = normalize_token(str(row.get("name", "")))
            if not name:
                continue
            if name not in tag_index:
                tag_index[name] = row_index
            row_index += 1
    return tag_index


def vector_tag_score(vector: np.ndarray, tag_index: dict[str, int], tag_name: str) -> float:
    """Read one tag score from vector safely."""
    normalized = normalize_token(tag_name)
    if not normalized:
        return 0.0
    index = tag_index.get(normalized)
    if index is None:
        return 0.0
    if int(index) < 0 or int(index) >= vector.size:
        return 0.0
    score = float(vector[int(index)])
    if score <= 0.0:
        return 0.0
    return min(1.0, score)


def max_tag_score(vector: np.ndarray, tag_index: dict[str, int], tag_names: Iterable[str]) -> float:
    return max((vector_tag_score(vector, tag_index, name) for name in tag_names), default=0.0)


def dominant_tag(
    vector: np.ndarray,
    tag_index: dict[str, int],
    candidates: Iterable[str],
    min_score: float,
) -> str:
    best_name = ""
    best_score = 0.0
    for name in candidates:
        score = vector_tag_score(vector, tag_index, name)
        if score > best_score:
            best_name = normalize_token(name)
            best_score = score
    if best_score < float(min_score):
        return ""
    return best_name


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    first = np.asarray(left, dtype=np.float32).reshape(-1)
    second = np.asarray(right, dtype=np.float32).reshape(-1)
    if first.size == 0 or second.size == 0 or first.size != second.size:
        return 0.0
    first_norm = float(np.linalg.norm(first))
    second_norm = float(np.linalg.norm(second))
    if first_norm <= 0.0 or second_norm <= 0.0:
        return 0.0
    return float(np.dot(first / first_norm, second / second_norm))


def detect_attribute_conflict(labels: list[str]) -> list[str]:
    """Return conflicting dominant labels when no stable majority exists."""
    values = [normalize_token(value) for value in labels if normalize_token(value)]
    if len(values) < 2:
        return []
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if len(counts) <= 1:
        return []
    top_count = max(counts.values())
    dominance = float(top_count) / float(len(values))
    if len(values) >= 3 and dominance >= 0.75:
        return []
    return sorted(counts.keys())


def detect_vector_outliers(
    vectors: list[np.ndarray],
    image_paths: list[str],
    outlier_threshold: float,
) -> list[str]:
    """Detect references far from character centroid."""
    if len(vectors) <= 1:
        return []
    matrix = np.stack([np.asarray(vector, dtype=np.float32).reshape(-1) for vector in vectors]).astype(np.float32)
    centroid = np.mean(matrix, axis=0)
    centroid_norm = float(np.linalg.norm(centroid))
    if centroid_norm <= 0.0:
        return []
    centroid_unit = centroid / centroid_norm
    outliers: list[str] = []
    for index, vector in enumerate(matrix):
        similarity = float(np.dot(vector / max(1e-6, float(np.linalg.norm(vector))), centroid_unit))
        if similarity < float(outlier_threshold):
            outliers.append(str(image_paths[index]))
    return outliers


def mean_pairwise_similarity(vectors: list[np.ndarray]) -> float:
    if len(vectors) <= 1:
        return 1.0
    sims: list[float] = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            sims.append(cosine_similarity(vectors[i], vectors[j]))
    if not sims:
        return 1.0
    return float(sum(sims) / len(sims))


def _record_issue(container: list[dict], issue_type: str, detail: str) -> None:
    container.append({"type": issue_type, "detail": detail})


def audit_custom_character_library(
    index: CharacterVectorIndex,
    character_records: list[dict],
    tag_index: dict[str, int],
    config: AuditConfig,
) -> dict:
    """Build full quality report for custom character references."""
    records_by_id = {str(record.get("id", "")).strip(): record for record in character_records}
    rows_by_id: dict[str, list[int]] = {}
    for row_index, character_id in enumerate(index.character_ids):
        normalized_id = str(character_id).strip()
        if not normalized_id:
            continue
        rows_by_id.setdefault(normalized_id, []).append(row_index)

    summary = {
        "character_count": len(rows_by_id),
        "reference_row_count": int(index.embeddings.shape[0]) if index.embeddings.ndim == 2 else 0,
        "single_reference_characters": 0,
        "multi_person_references": 0,
        "screenshot_noise_references": 0,
        "low_subject_references": 0,
        "feature_conflict_characters": 0,
        "outlier_reference_characters": 0,
        "low_consistency_characters": 0,
        "characters_with_any_issue": 0,
    }

    report_items: list[dict] = []
    for character_id in sorted(rows_by_id.keys()):
        row_indexes = rows_by_id[character_id]
        record = records_by_id.get(character_id, {})
        display_name = select_localized_alias(record, config.language_code) if record else character_id

        reference_items: list[dict] = []
        character_issues: list[dict] = []
        hair_labels: list[str] = []
        eye_labels: list[str] = []
        vectors: list[np.ndarray] = []
        paths: list[str] = []

        for row_index in row_indexes:
            vector = np.asarray(index.embeddings[row_index], dtype=np.float32).reshape(-1)
            image_path = str(index.image_paths[row_index])
            vectors.append(vector)
            paths.append(image_path)

            single_subject = max_tag_score(vector, tag_index, SINGLE_SUBJECT_TAGS)
            multi_person = max_tag_score(vector, tag_index, MULTI_PERSON_TAGS)
            screenshot_noise = max_tag_score(vector, tag_index, SCREENSHOT_NOISE_TAGS)
            no_humans = vector_tag_score(vector, tag_index, "no_humans")
            dominant_hair = dominant_tag(
                vector,
                tag_index,
                HAIR_COLOR_TAGS,
                min_score=config.dominant_attribute_score,
            )
            dominant_eye = dominant_tag(
                vector,
                tag_index,
                EYE_COLOR_TAGS,
                min_score=config.dominant_attribute_score,
            )
            hair_labels.append(dominant_hair)
            eye_labels.append(dominant_eye)

            issues: list[dict] = []
            if single_subject < float(config.min_single_subject_score):
                summary["low_subject_references"] += 1
                _record_issue(
                    issues,
                    "low_subject_focus",
                    f"single-subject score={single_subject:.3f} < {config.min_single_subject_score:.3f}",
                )
            if multi_person >= float(config.multi_person_threshold):
                summary["multi_person_references"] += 1
                _record_issue(
                    issues,
                    "multi_person_content",
                    f"multi-person score={multi_person:.3f} >= {config.multi_person_threshold:.3f}",
                )
            if screenshot_noise >= float(config.screenshot_noise_threshold):
                summary["screenshot_noise_references"] += 1
                _record_issue(
                    issues,
                    "screenshot_noise",
                    f"screenshot-noise score={screenshot_noise:.3f} >= {config.screenshot_noise_threshold:.3f}",
                )
            if no_humans >= float(config.no_humans_threshold):
                _record_issue(
                    issues,
                    "no_humans",
                    f"no_humans score={no_humans:.3f} >= {config.no_humans_threshold:.3f}",
                )

            reference_items.append(
                {
                    "row_index": int(row_index),
                    "image_path": image_path,
                    "issues": issues,
                    "signals": {
                        "single_subject": round(single_subject, 4),
                        "multi_person": round(multi_person, 4),
                        "screenshot_noise": round(screenshot_noise, 4),
                        "no_humans": round(no_humans, 4),
                        "dominant_hair": dominant_hair,
                        "dominant_eyes": dominant_eye,
                    },
                }
            )

        if len(row_indexes) <= 1:
            summary["single_reference_characters"] += 1
            _record_issue(character_issues, "single_reference", "Only one reference image in library.")

        hair_conflict = detect_attribute_conflict(hair_labels)
        if hair_conflict:
            summary["feature_conflict_characters"] += 1
            _record_issue(
                character_issues,
                "hair_color_conflict",
                f"Conflicting dominant hair tags: {', '.join(hair_conflict)}",
            )

        eye_conflict = detect_attribute_conflict(eye_labels)
        if eye_conflict:
            _record_issue(
                character_issues,
                "eye_color_conflict",
                f"Conflicting dominant eye tags: {', '.join(eye_conflict)}",
            )

        outlier_paths = detect_vector_outliers(
            vectors=vectors,
            image_paths=paths,
            outlier_threshold=config.outlier_similarity_threshold,
        )
        if outlier_paths:
            summary["outlier_reference_characters"] += 1
            _record_issue(
                character_issues,
                "outlier_reference",
                f"Outlier references: {len(outlier_paths)}",
            )
            for item in reference_items:
                if str(item["image_path"]) in outlier_paths:
                    _record_issue(item["issues"], "vector_outlier", "Low similarity to character centroid.")

        internal_similarity = mean_pairwise_similarity(vectors)
        if internal_similarity < float(config.low_consistency_threshold):
            summary["low_consistency_characters"] += 1
            _record_issue(
                character_issues,
                "low_internal_consistency",
                f"Mean pairwise similarity={internal_similarity:.3f} < {config.low_consistency_threshold:.3f}",
            )

        has_reference_issue = any(bool(item.get("issues")) for item in reference_items)
        has_character_issue = bool(character_issues)
        if has_reference_issue or has_character_issue:
            summary["characters_with_any_issue"] += 1

        if not config.include_clean_characters and not (has_reference_issue or has_character_issue):
            continue

        report_items.append(
            {
                "character_id": character_id,
                "display_name": display_name,
                "reference_count": len(row_indexes),
                "character_issues": character_issues,
                "reference_items": reference_items,
            }
        )

    report_items.sort(
        key=lambda item: (
            -len(item.get("character_issues", [])),
            -sum(1 for ref in item.get("reference_items", []) if ref.get("issues")),
            str(item.get("display_name", "")),
        )
    )
    return {
        "summary": summary,
        "characters": report_items,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit custom character library quality.")
    parser.add_argument("--custom-character-dir", default=str(DEFAULT_CUSTOM_CHARACTERS_DIR))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--output-report", default=DEFAULT_OUTPUT_REPORT)
    parser.add_argument("--language", default="zh-CN")
    parser.add_argument("--include-clean", action="store_true")
    parser.add_argument("--min-single-subject", type=float, default=0.55)
    parser.add_argument("--multi-person-threshold", type=float, default=0.45)
    parser.add_argument("--screenshot-noise-threshold", type=float, default=0.45)
    parser.add_argument("--no-humans-threshold", type=float, default=0.55)
    parser.add_argument("--dominant-attribute-score", type=float, default=0.55)
    parser.add_argument("--outlier-similarity-threshold", type=float, default=0.78)
    parser.add_argument("--low-consistency-threshold", type=float, default=0.76)
    return parser.parse_args()


def write_report(output_path: Path, report: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = Path.cwd().resolve()
    custom_dir = (root / args.custom_character_dir).resolve()
    model_dir = (root / args.model_dir).resolve()
    output_report = Path(str(args.output_report))
    if not output_report.is_absolute():
        output_report = (custom_dir / output_report).resolve()

    store = CustomCharacterStore(custom_dir)
    index_path = custom_dir / "index.npz"
    index_meta_path = custom_dir / "index_meta.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Missing custom index: {index_path}")
    index = CharacterVectorIndex.load(index_path=index_path, meta_path=index_meta_path if index_meta_path.exists() else None)

    tag_index = load_tag_index(model_dir / "selected_tags.csv")
    report = audit_custom_character_library(
        index=index,
        character_records=store.list_characters(),
        tag_index=tag_index,
        config=AuditConfig(
            min_single_subject_score=float(args.min_single_subject),
            multi_person_threshold=float(args.multi_person_threshold),
            screenshot_noise_threshold=float(args.screenshot_noise_threshold),
            no_humans_threshold=float(args.no_humans_threshold),
            dominant_attribute_score=float(args.dominant_attribute_score),
            outlier_similarity_threshold=float(args.outlier_similarity_threshold),
            low_consistency_threshold=float(args.low_consistency_threshold),
            include_clean_characters=bool(args.include_clean),
            language_code=str(args.language).strip() or "zh-CN",
        ),
    )
    write_report(output_report, report)

    summary = report["summary"]
    print(f"Report: {output_report}")
    print(f"Characters: {summary['character_count']}, References: {summary['reference_row_count']}")
    print(f"Characters with issues: {summary['characters_with_any_issue']}")
    print(f"Single-reference characters: {summary['single_reference_characters']}")
    print(f"Multi-person references: {summary['multi_person_references']}")
    print(f"Screenshot-noise references: {summary['screenshot_noise_references']}")
    print(f"Low-subject references: {summary['low_subject_references']}")
    print(f"Feature-conflict characters: {summary['feature_conflict_characters']}")
    print(f"Outlier-reference characters: {summary['outlier_reference_characters']}")
    print(f"Low-consistency characters: {summary['low_consistency_characters']}")


if __name__ == "__main__":
    main()

