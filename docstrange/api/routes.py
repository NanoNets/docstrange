"""FastAPI routes for engineering drawing extraction.

Install:  pip install 'docstrange[engineering]'
Run:      uvicorn docstrange.api.main:app --reload --port 8000
Docs:     http://localhost:8000/docs
"""

import asyncio
import functools
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
# Lazy singletons (initialized on first request, not at import time)
# ---------------------------------------------------------------------------

_pipeline = None
_overlay_gen = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from ..pipelines.engineering import EngineeringDrawingPipeline
        _pipeline = EngineeringDrawingPipeline()
    return _pipeline


def _get_overlay_gen():
    global _overlay_gen
    if _overlay_gen is None:
        from ..overlays.generator import OverlayGenerator
        _overlay_gen = OverlayGenerator()
    return _overlay_gen


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


async def _save_upload(file: UploadFile) -> str:
    """Validate, read, and write the uploaded file to a temp path."""
    ext = Path(file.filename or "").suffix.lower() or ".pdf"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) // (1024*1024)} MB). Maximum is 50 MB.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(content)
    finally:
        tmp.close()
    return tmp.name


async def _extract(file_path: str, extractors: Optional[List[str]] = None):
    """Run the pipeline in a thread pool so the event loop is not blocked."""
    pipeline = _get_pipeline()
    ext = Path(file_path).suffix.lower()
    loop = asyncio.get_running_loop()

    try:
        if ext == ".pdf":
            fn = functools.partial(pipeline.extract_from_pdf, file_path, extractors=extractors)
        else:
            fn = functools.partial(pipeline.extract_from_image, file_path, extractors=extractors)
        return await loop.run_in_executor(None, fn)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Extraction failed for %s: %s", file_path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Extraction failed. Check server logs.") from exc


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> "FastAPI":
    """Create and return the FastAPI application instance."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is required for the HTTP API. "
            "Install with: pip install 'docstrange[engineering]'"
        )

    from .models import (
        BOMRow, DimensionElement, FullExtractionResponse, GDTElement,
        HealthResponse, NoteElement, OverlayResponse, RevisionEntry, TitleBlockField,
    )

    app = FastAPI(
        title="DocStrange Engineering API",
        description=(
            "Modular engineering drawing extraction server. "
            "Upload a PDF or image to extract title block fields, dimensions, GD&T symbols, "
            "Bill of Materials rows, notes, and revision history — each with bounding boxes "
            "and confidence scores."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Extraction endpoints
    # ------------------------------------------------------------------

    @app.post(
        "/extract/title-block",
        response_model=List[TitleBlockField],
        summary="Extract title block fields",
        tags=["extraction"],
    )
    async def extract_title_block(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["title_block"])
            return result.title_block
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/dimensions",
        response_model=List[DimensionElement],
        summary="Extract dimension annotations",
        tags=["extraction"],
    )
    async def extract_dimensions(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["dimensions"])
            return result.dimensions
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/notes",
        response_model=List[NoteElement],
        summary="Extract general notes and numbered annotations",
        tags=["extraction"],
    )
    async def extract_notes(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["notes"])
            return result.notes
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/gdt",
        response_model=List[GDTElement],
        summary="Extract GD&T symbols and feature control frames",
        tags=["extraction"],
    )
    async def extract_gdt(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["gdt"])
            return result.gdt
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/bom",
        response_model=List[BOMRow],
        summary="Extract Bill of Materials rows",
        tags=["extraction"],
    )
    async def extract_bom(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["bom"])
            return result.bom
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/revisions",
        response_model=List[RevisionEntry],
        summary="Extract revision block entries",
        tags=["extraction"],
    )
    async def extract_revisions(file: UploadFile = File(...)):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp, extractors=["revisions"])
            return result.revisions
        finally:
            _cleanup(tmp)

    @app.post(
        "/extract/full",
        response_model=FullExtractionResponse,
        summary="Run all extractors and return the complete result",
        tags=["extraction"],
    )
    async def extract_full(
        file: UploadFile = File(...),
        include_overlays: bool = Query(
            default=False, description="Attach UI overlay JSON to the response"
        ),
        image_width: int = Query(
            default=0, ge=0, description="Source image width in pixels (for overlay normalisation)"
        ),
        image_height: int = Query(
            default=0, ge=0, description="Source image height in pixels (for overlay normalisation)"
        ),
        page: Optional[int] = Query(
            default=None, ge=1, description="Filter overlay annotations to a single page"
        ),
    ):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp)
            data = result.model_dump()
            if include_overlays:
                gen = _get_overlay_gen()
                data["overlay_json"] = gen.generate(
                    result,
                    image_width=image_width,
                    image_height=image_height,
                    image_path=tmp,
                    page=page,
                )
            return data
        finally:
            _cleanup(tmp)

    # ------------------------------------------------------------------
    # Overlay endpoint
    # ------------------------------------------------------------------

    @app.post(
        "/generate/overlays",
        response_model=OverlayResponse,
        summary="Generate UI-ready overlay JSON with bounding boxes",
        tags=["overlays"],
    )
    async def generate_overlays(
        file: UploadFile = File(...),
        image_width: int = Query(default=0, ge=0, description="Image width in pixels"),
        image_height: int = Query(default=0, ge=0, description="Image height in pixels"),
        page: Optional[int] = Query(
            default=None, ge=1, description="Return annotations for a single page only"
        ),
    ):
        tmp = await _save_upload(file)
        try:
            result = await _extract(tmp)
            gen = _get_overlay_gen()
            return gen.generate(
                result,
                image_width=image_width,
                image_height=image_height,
                image_path=tmp,
                page=page,
            )
        finally:
            _cleanup(tmp)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Service health check",
        tags=["meta"],
    )
    async def health():
        return HealthResponse(status="ok", service="docstrange-engineering", version="1.0.0")

    return app
