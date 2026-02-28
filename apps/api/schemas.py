"""API schemas for docker runtime."""

from pydantic import BaseModel, Field


class RunTaggingRequest(BaseModel):
    """Request payload for one auto-tag run."""

    image_dir: str = Field(default="image")
    queue_output: str = Field(default="data/annotation_queue/pending_annotations.jsonl")
    taxonomy: str = Field(default="data/character_library/feature_taxonomy.json")
    synonyms: str = Field(default="data/character_library/feature_synonyms.json")
    priority_rules: str = Field(default="data/character_library/feature_priority_rules.json")
    model_dir: str = Field(default="tools/wd14")
    exiftool_dir: str = Field(default="tools/exiftool")
    input_list: str = Field(default="")
    feature_threshold: float = Field(default=0.62, ge=0.0, le=1.0)
    copyright_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    custom_character_language: str = Field(default="zh-CN")


class RunTaggingResponse(BaseModel):
    """Response payload for auto-tag run."""

    ok: bool
    summary: dict[str, int]
    stdout: str
