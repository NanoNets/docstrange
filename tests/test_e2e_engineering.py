"""Smoke tests — verify the OCR → LayoutElement → Extractor wiring works end-to-end.

These tests do NOT require real OCR models. They inject a synthetic OCR service and a
PIL-generated image so the full EngineeringDrawingPipeline can run without GPU or network.
"""

import os
import tempfile

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_synthetic_image(path: str) -> None:
    """Write a small white PNG to *path* using PIL."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "DRAWING TITLE: Test Part", fill=(0, 0, 0))
    draw.text((10, 40), "25.4 mm", fill=(0, 0, 0))
    draw.text((10, 70), "GENERAL NOTES:", fill=(0, 0, 0))
    draw.text((10, 90), "1. All dimensions in mm.", fill=(0, 0, 0))
    img.save(path, "PNG")


def _make_layout_elements():
    """Return a small list of LayoutElement objects covering each extractor."""
    from docstrange.pipeline.layout_detector import LayoutElement

    def el(text, x=10.0, y=10.0, w=200.0, h=20.0, confidence=0.9):
        return LayoutElement(text=text, x=x, y=y, width=w, height=h,
                             element_type="paragraph", confidence=confidence)

    return [
        # Title block zone (lower-right corner, 800×600 image)
        el("DRAWING NUMBER: DWG-001", x=560, y=500, w=220, h=18),
        el("TITLE: Test Part",        x=560, y=520, w=220, h=18),
        el("SCALE: 1:1",             x=560, y=540, w=220, h=18),
        # Dimension
        el("25.4 mm",                 x=100, y=100),
        el("⌀12.5",                  x=200, y=130),
        # Notes
        el("GENERAL NOTES:",          x=10,  y=200),
        el("1. All dimensions in mm.",x=10,  y=220),
        # Revision
        el("REVISION HISTORY",        x=10,  y=300),
        el("A  2024-01-15  Initial release  J. Smith", x=10, y=320),
    ]


class _MockOCRService:
    """Returns pre-defined LayoutElements without running any model."""

    def extract_layout_elements(self, image_path: str):
        return _make_layout_elements()

    def extract_text(self, image_path: str) -> str:
        return " ".join(el.text for el in _make_layout_elements())

    def extract_text_with_layout(self, image_path: str) -> str:
        return self.extract_text(image_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEngineeringPipelineE2E:

    def test_extract_from_image_returns_result_type(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        from docstrange.schemas.engineering import EngineeringDrawingResult

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path)

        assert isinstance(result, EngineeringDrawingResult)

    def test_extract_from_image_has_metadata(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        from docstrange.schemas.engineering import ExtractionMetadata

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path)

        assert isinstance(result.metadata, ExtractionMetadata)
        assert result.metadata.source == img_path
        assert result.metadata.pages == 1

    def test_dimensions_extracted(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path, extractors=["dimensions"])

        assert len(result.dimensions) >= 1
        texts = [d.text for d in result.dimensions]
        assert any("25.4" in t or "12.5" in t for t in texts)

    def test_notes_extracted(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path, extractors=["notes"])

        assert len(result.notes) >= 1

    def test_title_block_extracted(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path, extractors=["title_block"])

        assert len(result.title_block) >= 1

    def test_model_dump_is_serialisable(self, tmp_path):
        """Result must serialise to JSON-safe dict without errors."""
        import json
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path)

        dumped = result.model_dump()
        serialised = json.dumps(dumped)  # must not raise
        assert isinstance(serialised, str)

    def test_file_not_found_raises(self):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        with pytest.raises(FileNotFoundError):
            pipeline.extract_from_image("/nonexistent/drawing.png")

    def test_selective_extractors_only(self, tmp_path):
        """Requesting only 'dimensions' must leave other result fields empty."""
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_path = str(tmp_path / "test_drawing.png")
        _make_synthetic_image(img_path)

        pipeline = EngineeringDrawingPipeline(ocr_service=_MockOCRService())
        result = pipeline.extract_from_image(img_path, extractors=["dimensions"])

        assert result.title_block == []
        assert result.notes == []
        assert result.gdt == []
        assert result.bom == []
        assert result.revisions == []


# ---------------------------------------------------------------------------
# Public import surface tests
# ---------------------------------------------------------------------------

class TestPublicImports:

    def test_engineering_pipeline_importable_from_docstrange(self):
        from docstrange import EngineeringDrawingPipeline  # noqa: F401

    def test_engineering_result_importable_from_docstrange(self):
        from docstrange import EngineeringDrawingResult  # noqa: F401

    def test_extractors_importable_from_docstrange(self):
        from docstrange import (  # noqa: F401
            TitleBlockExtractor,
            DimensionExtractor,
            NoteExtractor,
            GDTExtractor,
            BOMExtractor,
            RevisionExtractor,
        )

    def test_mcp_server_importable(self):
        pytest.importorskip("mcp", reason="mcp package not installed")
        from docstrange.mcp_server import EngineeringMCPServer  # noqa: F401

    def test_ocr_factory_importable_from_pipeline(self):
        from docstrange.pipeline import OCRServiceFactory  # noqa: F401
