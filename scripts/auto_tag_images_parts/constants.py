"""Shared constants for auto tag image pipeline."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DEFAULT_IMAGE_DIR = Path("image")
DEFAULT_OUTPUT_QUEUE = Path("data/annotation_queue/pending_annotations.jsonl")
DEFAULT_TAXONOMY = Path("data/character_library/feature_taxonomy.json")
DEFAULT_SYNONYMS = Path("data/character_library/feature_synonyms.json")
DEFAULT_PRIORITY_RULES = Path("data/character_library/feature_priority_rules.json")
DEFAULT_SENSITIVE_TERMS = Path("data/character_library/sensitive_terms.json")
DEFAULT_CUSTOM_CHARACTERS_DIR = Path("data/character_library/custom")
DEFAULT_MODEL_DIR = Path("tools/wd14")
DEFAULT_EXIFTOOL_DIR = Path("tools/exiftool")

MODEL_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2/resolve/main/model.onnx"
TAGS_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2/resolve/main/selected_tags.csv"

COPYRIGHT_GAME_MAP = {
    "genshin_impact": "genshin_impact",
    "zenless_zone_zero": "zenless_zone_zero",
    "zzz": "zenless_zone_zero",
}

# Prioritize head/face region for character retrieval while keeping
# full-image query as a lower-weight fallback.
FULL_IMAGE_CHARACTER_WEIGHT = 0.60
MIN_CHARACTER_REGION_SIDE = 96
CHARACTER_REGION_SPECS: tuple[tuple[str, tuple[float, float, float, float], float], ...] = (
    ("head_center", (0.20, 0.00, 0.80, 0.60), 1.00),
    ("head_left", (0.00, 0.00, 0.65, 0.70), 0.95),
    ("head_right", (0.35, 0.00, 1.00, 0.70), 0.95),
)
DEFAULT_MULTI_CHARACTER_THRESHOLD_FLOOR = 0.48
MAX_HEAD_QUERY_REGIONS = 3
MAX_HEAD_CANDIDATE_EVAL_SINGLE = 12
MAX_HEAD_CANDIDATE_EVAL_MULTI = 16
HEAD_CANDIDATE_FALLBACK_EVAL_SINGLE = 8
HEAD_CANDIDATE_FALLBACK_EVAL_MULTI = 10
HEAD_FALLBACK_TRIGGER_SCORE = 0.30
HEAD_SCORE_MIN_THRESHOLD = 0.22
HEAD_NMS_IOU_THRESHOLD = 0.28
HEAD_VECTOR_DUPLICATE_SIMILARITY = 0.985
MULTI_CHARACTER_SECONDARY_SCORE_RATIO = 0.70
MIN_CHARACTER_MATCH_CANDIDATES = 96
MULTI_CHARACTER_REGION_REUSE_MAX_SCORE_RATIO = 0.92
SINGLE_REFERENCE_MULTI_SCORE_FACTOR = 0.93
LARGE_CHARACTER_LIBRARY_ROWS = 1000
HUGE_CHARACTER_LIBRARY_ROWS = 2000
LARGE_LIBRARY_SECONDARY_RATIO_DELTA = 0.04
HUGE_LIBRARY_SECONDARY_RATIO_DELTA = 0.06
HEAD_BASE_REGION_SPECS: tuple[tuple[float, float, float, float], ...] = (
    (0.00, 0.00, 1.00, 0.72),
    (0.00, 0.00, 0.62, 0.72),
    (0.38, 0.00, 1.00, 0.72),
    (0.18, 0.00, 0.82, 0.74),
    (0.00, 0.05, 0.55, 0.78),
    (0.45, 0.05, 1.00, 0.78),
)
HEAD_PROBE_CENTERS: tuple[float, ...] = (0.18, 0.30, 0.42, 0.54, 0.66, 0.78)
HEAD_PROBE_HALF_WIDTHS: tuple[float, ...] = (0.14, 0.18, 0.22)
HEAD_PROBE_VERTICAL_RANGES: tuple[tuple[float, float], ...] = (
    (0.00, 0.52),
    (0.08, 0.62),
)
HEAD_SIGNAL_TAG_WEIGHTS: dict[str, float] = {
    "portrait": 0.35,
    "upper_body": 0.05,
    "looking_at_viewer": 0.04,
    "face_to_face": 0.03,
    "forehead": 0.12,
    "bangs": 0.14,
    "hair_between_eyes": 0.12,
    "ahoge": 0.18,
    "hair_intakes": 0.20,
    "streaked_hair": 0.18,
    "drill_hair": 0.18,
    "wavy_hair": 0.15,
    "curly_hair": 0.15,
    "multicolored_hair": 0.10,
    "two-tone_hair": 0.10,
    "colored_inner_hair": 0.10,
    "blue_eyes": 0.18,
    "red_eyes": 0.18,
    "green_eyes": 0.18,
    "purple_eyes": 0.18,
    "yellow_eyes": 0.18,
    "pink_eyes": 0.18,
    "brown_eyes": 0.18,
    "orange_eyes": 0.18,
    "aqua_eyes": 0.18,
    "grey_eyes": 0.18,
    "black_eyes": 0.18,
    "multicolored_eyes": 0.24,
    "heterochromia": 0.28,
    "slit_pupils": 0.20,
    "bright_pupils": 0.18,
    "white_pupils": 0.16,
    "constricted_pupils": 0.18,
    "red_pupils": 0.16,
    "blue_pupils": 0.16,
    "yellow_pupils": 0.16,
    "pink_pupils": 0.16,
    "mismatched_pupils": 0.22,
    "horizontal_pupils": 0.16,
    "ringed_eyes": 0.18,
    "eyelashes": 0.12,
    "colored_eyelashes": 0.20,
    "long_eyelashes": 0.16,
    "eyeshadow": 0.16,
    "red_eyeshadow": 0.15,
    "blue_eyeshadow": 0.15,
    "purple_eyeshadow": 0.15,
    "pink_eyeshadow": 0.15,
    "green_eyeshadow": 0.15,
    "facial_mark": 0.24,
    "forehead_mark": 0.22,
    "facepaint": 0.22,
    "tattoo": 0.18,
    "braid": 0.16,
    "single_braid": 0.16,
    "side_braid": 0.15,
    "twin_braids": 0.16,
    "hair_ornament": 0.12,
    "mini_hat": 0.12,
    "hat": 0.08,
}
HEAD_NEGATIVE_TAG_WEIGHTS: dict[str, float] = {
    "faceless": -0.45,
    "head_out_of_frame": -0.45,
    "headless": -0.60,
    "extra_faces": -0.35,
    "no_eyes": -0.40,
    "covered_eyes": -0.25,
    "hair_over_eyes": -0.20,
    "closed_eyes": -0.04,
    "breasts": -0.12,
    "large_breasts": -0.14,
    "huge_breasts": -0.18,
    "breast_press": -0.16,
    "cleavage": -0.10,
    "navel": -0.08,
    "thighs": -0.06,
}
ATTRIBUTE_HAIR_COLOR_TAGS: tuple[str, ...] = (
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
)
ATTRIBUTE_EYE_COLOR_TAGS: tuple[str, ...] = (
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
)
ATTRIBUTE_STYLE_DETAIL_TAGS: tuple[str, ...] = (
    "hair_intakes",
    "streaked_hair",
    "multicolored_hair",
    "two-tone_hair",
    "colored_inner_hair",
    "ahoge",
    "braid",
    "single_braid",
    "side_braid",
    "twin_braids",
    "drill_hair",
    "wavy_hair",
    "curly_hair",
    "twintails",
    "ponytail",
    "side_ponytail",
)
ATTRIBUTE_FACE_DETAIL_TAGS: tuple[str, ...] = (
    "facial_mark",
    "forehead_mark",
    "facepaint",
    "tattoo",
    "heterochromia",
    "multicolored_eyes",
    "mismatched_pupils",
    "ringed_eyes",
    "colored_eyelashes",
    "eyeshadow",
    "red_eyeshadow",
    "blue_eyeshadow",
    "purple_eyeshadow",
    "pink_eyeshadow",
    "green_eyeshadow",
)
ATTRIBUTE_STRONG_QUERY_SCORE = 0.55
ATTRIBUTE_REFERENCE_MATCH_SCORE = 0.42
ATTRIBUTE_REFERENCE_MISS_SCORE = 0.18
ATTRIBUTE_MAX_ADJUSTMENT = 0.28
ATTRIBUTE_MULTI_PERSON_TAGS: tuple[str, ...] = (
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
HAIR_COLOR_GROUP_MAP: dict[str, str] = {
    "black_hair": "neutral_dark",
    "brown_hair": "neutral_dark",
    "grey_hair": "neutral_dark",
    "blonde_hair": "light_neutral",
    "white_hair": "light_neutral",
    "silver_hair": "light_neutral",
    "blue_hair": "cool_blue",
    "aqua_hair": "cool_blue",
    "green_hair": "green_cyan",
    "purple_hair": "magenta_purple",
    "pink_hair": "magenta_purple",
    "red_hair": "warm_red_orange",
    "orange_hair": "warm_red_orange",
    "multicolored_hair": "multi",
    "two-tone_hair": "multi",
    "colored_inner_hair": "multi",
}
EYE_COLOR_GROUP_MAP: dict[str, str] = {
    "black_eyes": "neutral_dark",
    "brown_eyes": "neutral_dark",
    "grey_eyes": "neutral_dark",
    "blue_eyes": "cool_blue",
    "aqua_eyes": "cool_blue",
    "green_eyes": "green_cyan",
    "purple_eyes": "magenta_purple",
    "pink_eyes": "magenta_purple",
    "red_eyes": "warm_red_orange",
    "orange_eyes": "warm_red_orange",
    "yellow_eyes": "warm_red_orange",
    "multicolored_eyes": "multi",
    "heterochromia": "multi",
}
CORRELATION_PROFILE_MIN_SCORE = 0.42
CORRELATION_QUERY_MIN_HAIR_SCORE = 0.58
CORRELATION_QUERY_MIN_EYE_SCORE = 0.58
CORRELATION_PROFILE_SCHEMA_VERSION = 1
CORRELATION_PROFILE_FILE_NAME = "correlation_profiles.json"
