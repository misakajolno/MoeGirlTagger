"""Automatically recognize anime tags and write localized metadata keywords."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

try:
    from core.version import APP_VERSION
    from scripts.auto_tag_images_parts.constants import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.tagger import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character_matching import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.pipeline import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character_matching import (
        _attribute_score_adjustment,
        _get_character_correlation_profiles,
        _head_candidate_score,
    )
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.version import APP_VERSION
    from scripts.auto_tag_images_parts.constants import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.tagger import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character_matching import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.pipeline import *  # noqa: F401,F403
    from scripts.auto_tag_images_parts.character_matching import (
        _attribute_score_adjustment,
        _get_character_correlation_profiles,
        _head_candidate_score,
    )

def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Auto-recognize image tags and write metadata.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR), help="Image directory.")
    parser.add_argument("--queue-output", default=str(DEFAULT_OUTPUT_QUEUE), help="Output queue JSONL.")
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY), help="Feature taxonomy JSON.")
    parser.add_argument("--synonyms", default=str(DEFAULT_SYNONYMS), help="Feature synonyms JSON.")
    parser.add_argument("--priority-rules", default=str(DEFAULT_PRIORITY_RULES), help="Priority rules JSON.")
    parser.add_argument(
        "--sensitive-terms",
        default=str(DEFAULT_SENSITIVE_TERMS),
        help="Optional sensitive terms extension JSON.",
    )
    parser.add_argument(
        "--custom-character-dir",
        default=str(DEFAULT_CUSTOM_CHARACTERS_DIR),
        help="Custom character library directory.",
    )
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR), help="WD14 model directory.")
    parser.add_argument("--exiftool-dir", default=str(DEFAULT_EXIFTOOL_DIR), help="Exiftool directory.")
    parser.add_argument(
        "--input-list",
        default="",
        help="Optional text file with one image path per line. Overrides --image-dir scanning.",
    )
    parser.add_argument("--feature-threshold", type=float, default=0.62, help="Feature score threshold.")
    parser.add_argument(
        "--adult-feature-threshold",
        type=float,
        default=0.55,
        help="Score threshold used for adult_content tags.",
    )
    parser.add_argument(
        "--footwear-feature-threshold",
        type=float,
        default=0.50,
        help="Score threshold used for footwear tags.",
    )
    parser.add_argument(
        "--barefoot-feature-threshold",
        type=float,
        default=0.35,
        help="Score threshold used for barefoot tag.",
    )
    parser.add_argument(
        "--custom-character-threshold",
        type=float,
        default=0.55,
        help="Similarity threshold for custom character retrieval.",
    )
    parser.add_argument(
        "--custom-character-margin",
        type=float,
        default=0.12,
        help="Minimum top1-top2 similarity gap required for accepting a custom character.",
    )
    parser.add_argument(
        "--custom-character-topk",
        type=int,
        default=1,
        help="Maximum custom character candidates per image.",
    )
    parser.add_argument(
        "--custom-character-language",
        default="zh-CN",
        help="Preferred language code for custom character names (e.g. zh-CN/en-US/ja-JP).",
    )
    parser.add_argument(
        "--onnx-provider",
        default="auto",
        choices=["auto", "cpu", "cuda", "directml", "dml"],
        help="ONNX Runtime execution provider preference with automatic fallback.",
    )
    parser.add_argument(
        "--disable-character-recognition",
        action="store_true",
        help="Disable custom character recognition and only keep feature/work analysis.",
    )
    parser.add_argument(
        "--stream-records",
        action="store_true",
        help="Emit one machine-readable record line per image for GUI real-time updates.",
    )
    parser.add_argument(
        "--multi-character-threshold-floor",
        type=float,
        default=DEFAULT_MULTI_CHARACTER_THRESHOLD_FLOOR,
        help="Lower-bound threshold used when multiple characters are inferred.",
    )
    parser.add_argument(
        "--rebuild-custom-index",
        action="store_true",
        help="Force rebuild custom character index instead of using cached index.npz.",
    )
    parser.add_argument(
        "--rebuild-correlation-profiles",
        action="store_true",
        help="Force rebuild cached custom correlation_profiles.json before matching.",
    )
    parser.add_argument("--copyright-threshold", type=float, default=0.70, help="Copyright score threshold.")
    parser.add_argument("--non-recursive", action="store_true", help="Disable recursive image scanning.")
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    root = Path.cwd().resolve()
    image_dir = (root / args.image_dir).resolve()
    queue_output = (root / args.queue_output).resolve()
    taxonomy_path = (root / args.taxonomy).resolve()
    synonyms_path = (root / args.synonyms).resolve()
    priority_rules_path = (root / args.priority_rules).resolve()
    sensitive_terms_path = (root / args.sensitive_terms).resolve() if str(args.sensitive_terms).strip() else None
    custom_character_dir = (root / args.custom_character_dir).resolve()
    model_dir = (root / args.model_dir).resolve()
    exiftool_dir = (root / args.exiftool_dir).resolve()

    model_path, tags_path = ensure_model_assets(model_dir)
    tagger = WD14Tagger(
        model_path=model_path,
        tags_path=tags_path,
        execution_provider=str(args.onnx_provider).strip() or "auto",
    )
    wd14_tag_index = {
        normalize_token(name): index for index, (name, _category) in enumerate(tagger.tags)
    }
    _, alias_map = load_feature_resources(
        taxonomy_path=taxonomy_path,
        synonyms_path=synonyms_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    tag_to_category, _ = load_taxonomy_structure(
        taxonomy_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    blocked_tags = load_blocked_tags(
        priority_rules_path,
        sensitive_terms_path=sensitive_terms_path,
    )
    custom_index = None
    normalized_wd14_tag_index: dict[str, int] = {}
    precomputed_correlation_profiles = None
    if not bool(args.disable_character_recognition):
        custom_store = CustomCharacterStore(custom_character_dir)
        custom_index = load_or_build_custom_character_index(
            store=custom_store,
            tagger=tagger,
            preferred_language=str(args.custom_character_language).strip() or "zh-CN",
            rebuild=bool(args.rebuild_custom_index),
        )
        if custom_index is not None and bool(args.rebuild_correlation_profiles):
            rebuild_character_correlation_profiles(custom_index, wd14_tag_index)
        for raw_name, raw_index in wd14_tag_index.items():
            normalized_name = normalize_token(str(raw_name))
            if not normalized_name:
                continue
            try:
                normalized_wd14_tag_index[normalized_name] = int(raw_index)
            except Exception:
                continue
        if custom_index is not None and normalized_wd14_tag_index:
            precomputed_correlation_profiles = _get_character_correlation_profiles(
                custom_index,
                normalized_wd14_tag_index,
            )
        else:
            precomputed_correlation_profiles = {}

    if args.input_list:
        input_list_path = (root / args.input_list).resolve()
        images = collect_images_from_list(list_path=input_list_path, root_dir=root)
    else:
        images = collect_images(image_dir=image_dir, recursive=not args.non_recursive)
    now_iso = dt.datetime.now().replace(microsecond=0).isoformat()
    records: list[dict] = []
    stream_prefix = "__MOEGIRL_RECORD__:"
    stream_records = bool(args.stream_records)

    for image_path in images:
        predicted, score_vector = tagger.predict_with_vector(image_path)
        feature_tags = canonicalize_feature_tags(
            predicted_tags=predicted,
            alias_map=alias_map,
            min_score=args.feature_threshold,
            blocked_tags=blocked_tags,
            tag_to_category=tag_to_category,
            category_min_scores={
                "adult_content": args.adult_feature_threshold,
                "footwear": args.footwear_feature_threshold,
            },
            tag_min_scores={"barefoot": args.barefoot_feature_threshold},
        )
        if bool(args.disable_character_recognition):
            characters = []
        else:
            inferred_character_count = infer_character_count(predicted, min_score=0.35, max_count=3)
            character_query_items = build_custom_character_query_items(
                image_path=image_path,
                full_query_vector=score_vector,
                tagger=tagger,
                inferred_character_count=inferred_character_count,
            )
            detected_head_count = max(0, len(character_query_items) - 1)
            effective_character_top_k = resolve_effective_character_top_k(
                base_top_k=int(args.custom_character_topk),
                inferred_count=inferred_character_count,
                detected_head_count=detected_head_count,
            )
            effective_character_threshold = resolve_effective_character_threshold(
                base_threshold=args.custom_character_threshold,
                inferred_count=inferred_character_count,
                multi_floor=args.multi_character_threshold_floor,
            )
            characters = resolve_custom_characters_with_region_queries(
                query_items=character_query_items,
                custom_index=custom_index,
                min_similarity=effective_character_threshold,
                top_k=effective_character_top_k,
                min_margin=max(0.0, float(args.custom_character_margin)),
                tag_index=wd14_tag_index,
                normalized_tag_index=normalized_wd14_tag_index,
                correlation_profiles=precomputed_correlation_profiles,
            )
        copyright_tags = [
            tag.name
            for tag in predicted
            if tag.category == "copyright" and tag.score >= args.copyright_threshold
        ]
        source_game = detect_source_game(copyright_tags=copyright_tags)

        record = build_record(
            image_path=image_path,
            root_path=root,
            characters=characters,
            feature_tags=feature_tags,
            source_game=source_game,
            now_iso=now_iso,
        )
        records.append(record)
        if stream_records:
            print(
                f"{stream_prefix}{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}",
                flush=True,
            )

    written = write_jsonl(queue_output, records)
    target, updated, skipped = process_and_write_metadata(
        queue_path=queue_output,
        image_root=root,
        taxonomy_path=taxonomy_path,
        priority_rules_path=priority_rules_path,
        exiftool_dir=exiftool_dir,
        sensitive_terms_path=sensitive_terms_path,
        metadata_language=str(args.custom_character_language).strip() or "zh-CN",
    )

    print(f"Images found: {len(images)}")
    print(f"Queue written: {written}")
    print(f"Metadata targets: {target}")
    print(f"Metadata updated: {updated}")
    print(f"Metadata skipped: {skipped}")
    print(f"ONNX providers: {', '.join(getattr(tagger, 'active_execution_providers', []))}")


if __name__ == "__main__":
    main()
