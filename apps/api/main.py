"""Minimal FastAPI service for dockerized auto-tagging."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from apps.api.schemas import RunTaggingRequest, RunTaggingResponse
from core.moegirl_tagger import AutoTagOptions, run_auto_tag_pipeline
from core.version import APP_VERSION

app = FastAPI(
    title="MoeGirl Tagger API",
    version=APP_VERSION,
    description="Docker-ready API for anime image tagging pipeline.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/v1/tagging/run", response_model=RunTaggingResponse)
def run_tagging(payload: RunTaggingRequest) -> RunTaggingResponse:
    """Run one auto-tag pipeline job."""
    try:
        result = run_auto_tag_pipeline(
            options=AutoTagOptions(
                image_dir=payload.image_dir,
                queue_output=payload.queue_output,
                taxonomy=payload.taxonomy,
                synonyms=payload.synonyms,
                priority_rules=payload.priority_rules,
                model_dir=payload.model_dir,
                exiftool_dir=payload.exiftool_dir,
                input_list=payload.input_list,
                feature_threshold=payload.feature_threshold,
                copyright_threshold=payload.copyright_threshold,
                custom_character_language=payload.custom_character_language,
            ),
            project_root=Path.cwd(),
        )
        return RunTaggingResponse(
            ok=True,
            summary=result["summary"],
            stdout=result["stdout"],
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
