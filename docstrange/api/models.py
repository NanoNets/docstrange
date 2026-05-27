"""Pydantic response models for the DocStrange Engineering API.

These are thin wrappers / re-exports that let FastAPI generate accurate
OpenAPI schemas for every endpoint without duplicating the core schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..schemas.engineering import (
    BBoxSchema,
    BOMRow,
    DimensionElement,
    EngineeringDrawingResult,
    ExtractionMetadata,
    GDTElement,
    NoteElement,
    RevisionEntry,
    TitleBlockField,
)

__all__ = [
    "HealthResponse",
    "FullExtractionResponse",
    "OverlayBBox",
    "OverlayAnnotation",
    "OverlayImageSize",
    "OverlayResponse",
    # Re-exported schema types used as list element response models
    "TitleBlockField",
    "DimensionElement",
    "NoteElement",
    "GDTElement",
    "BOMRow",
    "RevisionEntry",
]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class FullExtractionResponse(EngineeringDrawingResult):
    """EngineeringDrawingResult extended with an optional overlay payload."""
    overlay_json: Optional[Dict[str, Any]] = None


class OverlayBBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class OverlayAnnotation(BaseModel):
    id: str
    type: str
    text: str
    page: int
    confidence: float
    bbox_pixels: OverlayBBox
    bbox_normalized: OverlayBBox
    color: str
    label: str


class OverlayImageSize(BaseModel):
    width: int
    height: int


class OverlayResponse(BaseModel):
    image_size: OverlayImageSize
    page_filter: Optional[int] = None
    total_annotations: int
    annotations: List[OverlayAnnotation]
