"""Pydantic schemas for engineering drawing extraction output."""

from typing import Any, Dict, List, Literal, Optional

try:
    from pydantic import BaseModel, Field, model_validator
except ImportError as e:
    raise ImportError(
        "pydantic is required for engineering extraction schemas. "
        "Install with: pip install 'docstrange[engineering]'"
    ) from e


class BBoxSchema(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ExtractionMetadata(BaseModel):
    """Structured metadata attached to every EngineeringDrawingResult."""
    source: str = ""
    pages: int = 0
    page: Optional[int] = None          # set on per-page intermediate results
    extractor_version: str = "1.0.0"

    model_config = {"extra": "allow"}   # absorb unknown keys from legacy callers


class ExtractionElement(BaseModel):
    """Base schema for a single extracted entity with spatial context."""
    text: str
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBoxSchema
    page: int = 1


class DimensionElement(ExtractionElement):
    type: Literal["dimension"] = "dimension"
    nominal: Optional[float] = None
    upper_tolerance: Optional[float] = None
    lower_tolerance: Optional[float] = None
    unit: Optional[str] = None
    dimension_type: Optional[str] = None   # "linear" | "angular" | "radial" | "diameter"


class TitleBlockField(ExtractionElement):
    type: Literal["title_block"] = "title_block"
    field_name: str
    field_value: str


class NoteElement(ExtractionElement):
    type: Literal["note"] = "note"
    note_number: Optional[int] = None
    is_general: bool = False


class GDTElement(ExtractionElement):
    type: Literal["gdt"] = "gdt"
    symbol: str
    tolerance_value: Optional[str] = None
    datum_reference: Optional[str] = None


class BOMRow(BaseModel):
    """A single row from a Bill of Materials table."""
    type: Literal["bom"] = "bom"
    text: str = ""                         # summary text; auto-filled from raw_cells
    item_number: Optional[str] = None
    quantity: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    material: Optional[str] = None
    raw_cells: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBoxSchema
    page: int = 1

    @model_validator(mode="after")
    def _fill_text(self):
        if not self.text and self.raw_cells:
            self.text = " | ".join(c for c in self.raw_cells if c)
        return self


class RevisionEntry(BaseModel):
    """A single entry from a revision history block."""
    type: Literal["revision"] = "revision"
    text: str = ""                         # summary text; auto-filled from fields
    revision: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    approved_by: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBoxSchema
    page: int = 1

    @model_validator(mode="after")
    def _fill_text(self):
        if not self.text:
            parts = [p for p in [self.revision, self.date, self.description] if p]
            self.text = " | ".join(parts)
        return self


class EngineeringDrawingResult(BaseModel):
    title_block: List[TitleBlockField] = []
    dimensions: List[DimensionElement] = []
    notes: List[NoteElement] = []
    gdt: List[GDTElement] = []
    bom: List[BOMRow] = []
    revisions: List[RevisionEntry] = []
    metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)

    @model_validator(mode="before")
    @classmethod
    def _coerce_metadata(cls, data):
        if isinstance(data, dict) and isinstance(data.get("metadata"), dict):
            data["metadata"] = ExtractionMetadata(**data["metadata"])
        return data
