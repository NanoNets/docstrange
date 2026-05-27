"""Integration tests for EngineeringDrawingPipeline using mocked OCR service."""

from unittest.mock import MagicMock, patch
import pytest


def make_element(text, x=0.0, y=0.0, w=100.0, h=20.0, confidence=0.9):
    from docstrange.pipeline.layout_detector import LayoutElement
    return LayoutElement(text=text, x=x, y=y, width=w, height=h,
                         element_type="paragraph", confidence=confidence)


@pytest.fixture
def mock_elements():
    """A minimal set of synthetic layout elements covering multiple extractor types."""
    return [
        # Title block zone elements
        make_element("SCALE 1:1", x=750.0, y=900.0, w=80.0, h=15.0),
        make_element("DWG NO. ASSY-001", x=750.0, y=920.0, w=120.0, h=15.0),
        # Dimensions
        make_element("25.4 mm", x=200.0, y=300.0),
        make_element("⌀10.0", x=350.0, y=400.0),
        # Notes section
        make_element("GENERAL NOTES:", x=50.0, y=700.0),
        make_element("1. ALL DIMENSIONS IN MM", x=50.0, y=720.0),
        # GD&T
        make_element("⊥ 0.05 A", x=400.0, y=500.0),
        # BOM
        make_element("BILL OF MATERIALS", x=50.0, y=100.0, w=200.0),
        make_element("1  2  M6-BOLT  Hex bolt", x=50.0, y=130.0, w=400.0),
    ]


@pytest.fixture
def mock_ocr_service(mock_elements):
    service = MagicMock()
    service.extract_layout_elements.return_value = mock_elements
    return service


class TestEngineeringDrawingPipeline:

    def test_extract_from_image_calls_ocr(self, tmp_path, mock_ocr_service, mock_elements):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        # Create a dummy image file so path exists
        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        mock_ocr_service.extract_layout_elements.assert_called_once_with(str(img_file))
        assert result is not None

    def test_dimensions_extracted(self, tmp_path, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        assert len(result.dimensions) > 0

    def test_title_block_extracted(self, tmp_path, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        assert len(result.title_block) > 0

    def test_selective_extractors(self, tmp_path, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file), extractors=["dimensions"])

        # Only dimensions should be populated
        assert len(result.dimensions) > 0
        assert result.notes == []
        assert result.title_block == []

    def test_result_is_serialisable(self, tmp_path, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        import json
        serialised = json.dumps(result.model_dump())
        assert isinstance(serialised, str)

    def test_file_not_found_raises(self, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        with pytest.raises(FileNotFoundError):
            pipeline.extract_from_image("/nonexistent/drawing.png")

    def test_merge_page_results(self, mock_ocr_service):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        from docstrange.schemas.engineering import EngineeringDrawingResult, DimensionElement, BBoxSchema

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        bbox = BBoxSchema(x=0, y=0, width=10, height=10)
        p1 = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="10mm", nominal=10, dimension_type="linear",
                                         confidence=0.9, bbox=bbox)]
        )
        p2 = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="20mm", nominal=20, dimension_type="linear",
                                         confidence=0.85, bbox=bbox)]
        )
        merged = pipeline._merge_page_results([p1, p2], metadata={})
        assert len(merged.dimensions) == 2


class TestOverlayGenerator:

    def test_generate_returns_annotations(self, mock_elements, mock_ocr_service, tmp_path):
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        gen = OverlayGenerator()
        overlay = gen.generate(result, image_width=1000, image_height=800)

        assert "annotations" in overlay
        assert "image_size" in overlay
        assert overlay["image_size"]["width"] == 1000
        assert overlay["total_annotations"] == len(overlay["annotations"])

    def test_normalised_coordinates_in_range(self, mock_elements, mock_ocr_service, tmp_path):
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        gen = OverlayGenerator()
        overlay = gen.generate(result, image_width=1000, image_height=800)

        for ann in overlay["annotations"]:
            nb = ann["bbox_normalized"]
            assert 0.0 <= nb["x"] <= 1.0
            assert 0.0 <= nb["y"] <= 1.0

    def test_annotations_carry_page_field(self, mock_ocr_service, tmp_path):
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline

        img_file = tmp_path / "drawing.png"
        img_file.write_bytes(b"fake")

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        result = pipeline.extract_from_image(str(img_file))

        gen = OverlayGenerator()
        overlay = gen.generate(result, image_width=1000, image_height=800)

        for ann in overlay["annotations"]:
            assert "page" in ann
            assert isinstance(ann["page"], int)

    def test_page_filter_excludes_other_pages(self, mock_ocr_service, tmp_path):
        """Page filter must return only annotations from the requested page."""
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        from docstrange.schemas.engineering import EngineeringDrawingResult, DimensionElement, BBoxSchema

        pipeline = EngineeringDrawingPipeline(ocr_service=mock_ocr_service)
        bbox = BBoxSchema(x=0, y=0, width=50, height=20)
        result = EngineeringDrawingResult(
            dimensions=[
                DimensionElement(text="10mm", nominal=10, dimension_type="linear",
                                 confidence=0.9, bbox=bbox, page=1),
                DimensionElement(text="20mm", nominal=20, dimension_type="linear",
                                 confidence=0.85, bbox=bbox, page=2),
            ]
        )

        gen = OverlayGenerator()
        overlay_p1 = gen.generate(result, image_width=1000, image_height=800, page=1)
        overlay_p2 = gen.generate(result, image_width=1000, image_height=800, page=2)
        overlay_all = gen.generate(result, image_width=1000, image_height=800)

        assert overlay_p1["total_annotations"] == 1
        assert overlay_p1["annotations"][0]["text"] == "10mm"
        assert overlay_p2["total_annotations"] == 1
        assert overlay_p2["annotations"][0]["text"] == "20mm"
        assert overlay_all["total_annotations"] == 2

    def test_bom_row_annotation_uses_text_field(self, mock_ocr_service, tmp_path):
        """BOMRow overlay annotation must use the auto-filled .text field from Phase 2."""
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.schemas.engineering import EngineeringDrawingResult, BOMRow, BBoxSchema

        bbox = BBoxSchema(x=10, y=50, width=300, height=20)
        result = EngineeringDrawingResult(
            bom=[BOMRow(
                confidence=0.9,
                bbox=bbox,
                item_number="1",
                description="Hex bolt",
                raw_cells=["1", "2", "Hex bolt"],
            )]
        )

        gen = OverlayGenerator()
        overlay = gen.generate(result, image_width=1000, image_height=800)

        assert overlay["total_annotations"] == 1
        ann = overlay["annotations"][0]
        assert ann["type"] == "bom"
        assert "Hex bolt" in ann["text"]

    def test_overlay_no_normalisation_when_dimensions_zero(self, mock_ocr_service):
        """When image dimensions are 0 and no path given, bbox_normalized is all-zeros."""
        from docstrange.overlays.generator import OverlayGenerator
        from docstrange.schemas.engineering import EngineeringDrawingResult, DimensionElement, BBoxSchema

        bbox = BBoxSchema(x=10, y=20, width=50, height=15)
        result = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="5mm", nominal=5,
                                         dimension_type="linear", confidence=0.8, bbox=bbox)]
        )
        gen = OverlayGenerator()
        overlay = gen.generate(result)   # no image_width / image_height

        assert overlay["annotations"][0]["bbox_normalized"] == {
            "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0
        }
