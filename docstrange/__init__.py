"""
Document Data Extractor - Extract structured data from any document into LLM-ready formats.

For engineering drawing extraction use EngineeringDrawingPipeline directly — it is the
dedicated entry point for PDFs and images containing title blocks, dimensions, GD&T, BOM,
notes, and revision history.
"""

from .extractor import DocumentExtractor
from .result import ConversionResult
from .processors import GPUConversionResult, CloudConversionResult
from .exceptions import ConversionError, UnsupportedFormatError
from .config import InternalConfig

# Engineering drawing extraction surface
from .pipelines.engineering import EngineeringDrawingPipeline
from .schemas.engineering import (
    BBoxSchema,
    ExtractionElement,
    EngineeringDrawingResult,
    DimensionElement,
    TitleBlockField,
    NoteElement,
    GDTElement,
    BOMRow,
    RevisionEntry,
)
from .extractors import (
    BaseExtractor,
    TitleBlockExtractor,
    DimensionExtractor,
    NoteExtractor,
    GDTExtractor,
    BOMExtractor,
    RevisionExtractor,
)

__version__ = "1.1.5"
__all__ = [
    # Generic document extraction
    "DocumentExtractor",
    "ConversionResult",
    "GPUConversionResult",
    "CloudConversionResult",
    "ConversionError",
    "UnsupportedFormatError",
    "InternalConfig",
    # Engineering drawing extraction
    "EngineeringDrawingPipeline",
    "EngineeringDrawingResult",
    "BBoxSchema",
    "ExtractionElement",
    "DimensionElement",
    "TitleBlockField",
    "NoteElement",
    "GDTElement",
    "BOMRow",
    "RevisionEntry",
    # Individual extractors (for custom pipelines)
    "BaseExtractor",
    "TitleBlockExtractor",
    "DimensionExtractor",
    "NoteExtractor",
    "GDTExtractor",
    "BOMExtractor",
    "RevisionExtractor",
]