"""Phase 7 — Extraction accuracy, bounding box fidelity, multi-page stamping,
malformed input handling, and schema validation tests.

Focuses on gaps not covered by the existing extractor unit tests:
- Edge-case dimension notation (imperial, bilateral tolerance, DIA. text)
- GD&T variants (position, parallelism, feature control frames with multiple datums)
- Bounding box end-to-end precision
- Multi-page page-number stamping through the pipeline
- Degenerate / malformed input robustness
- Pydantic schema constraint validation
- Result completeness invariants
"""

import pytest
from unittest.mock import MagicMock

from docstrange.pipeline.layout_detector import LayoutElement
from docstrange.schemas.engineering import (
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def el(text, x=0.0, y=0.0, w=100.0, h=20.0, confidence=0.9, element_type="paragraph"):
    return LayoutElement(
        text=text, x=x, y=y, width=w, height=h,
        element_type=element_type, confidence=confidence,
    )


def _pipeline_with_elements(elements):
    """Return an EngineeringDrawingPipeline whose OCR service returns *elements*."""
    from docstrange.pipelines.engineering import EngineeringDrawingPipeline
    svc = MagicMock()
    svc.extract_layout_elements.return_value = elements
    return EngineeringDrawingPipeline(ocr_service=svc)


# ---------------------------------------------------------------------------
# Dimension accuracy — edge cases
# ---------------------------------------------------------------------------

class TestDimensionAccuracy:

    def test_imperial_inch_unit_double_quote(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el('1.375"')])
        linears = [r for r in results if r.dimension_type == "linear"]
        assert len(linears) >= 1
        assert linears[0].nominal == 1.375
        assert linears[0].unit == "in"

    def test_imperial_inch_unit_in_suffix(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el("2.500 in")])
        linears = [r for r in results if r.dimension_type == "linear"]
        assert len(linears) >= 1
        assert linears[0].unit == "in"

    def test_bilateral_tolerance_upper_and_lower(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el("25.4 +0.5/-0.2 mm")])
        linears = [r for r in results if r.dimension_type == "linear"]
        assert len(linears) >= 1
        d = linears[0]
        assert d.nominal == 25.4
        assert d.upper_tolerance == 0.5
        assert d.lower_tolerance == -0.2

    def test_diameter_text_notation(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el("DIA. 25.4")])
        diams = [r for r in results if r.dimension_type == "diameter"]
        assert len(diams) >= 1
        assert diams[0].nominal == 25.4

    def test_diameter_uppercase_o(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el("Ø12.5")])
        diams = [r for r in results if r.dimension_type == "diameter"]
        assert len(diams) >= 1
        assert diams[0].nominal == 12.5

    def test_empty_text_skipped(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el(""), el("   ")])
        assert results == []

    def test_no_unit_still_extracts_linear(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        results = DimensionExtractor().extract([el("50.0")])
        linears = [r for r in results if r.dimension_type == "linear"]
        assert len(linears) >= 1
        assert linears[0].nominal == 50.0
        assert linears[0].unit is None

    def test_very_large_integer_no_unit_skipped(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        # Pure large integer without a unit should not produce a result
        results = DimensionExtractor().extract([el("99999")])
        for r in results:
            assert not (r.dimension_type == "linear" and r.nominal == 99999 and r.unit is None)

    def test_whitespace_only_element_skipped(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        assert DimensionExtractor().extract([el("\t\n   ")]) == []

    def test_long_text_no_crash(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        long_text = "PART REF " + " ".join(f"{i}.{i}" for i in range(100))
        results = DimensionExtractor().extract([el(long_text)])
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# GD&T accuracy — edge cases
# ---------------------------------------------------------------------------

class TestGDTAccuracy:

    def test_position_unicode_symbol(self):
        from docstrange.extractors.gdt import GDTExtractor
        results = GDTExtractor().extract([el("⊙ 0.1 A")])
        pos = [r for r in results if r.symbol == "position"]
        assert len(pos) >= 1

    def test_parallelism_text_abbreviation(self):
        from docstrange.extractors.gdt import GDTExtractor
        results = GDTExtractor().extract([el("PAR 0.03")])
        par = [r for r in results if r.symbol == "parallelism"]
        assert len(par) >= 1
        assert par[0].tolerance_value == "0.03"

    def test_straightness_text_abbreviation(self):
        from docstrange.extractors.gdt import GDTExtractor
        results = GDTExtractor().extract([el("STRAIGHTNESS 0.01")])
        s = [r for r in results if r.symbol == "straightness"]
        assert len(s) >= 1

    def test_feature_control_frame_with_two_datums(self):
        from docstrange.extractors.gdt import GDTExtractor
        results = GDTExtractor().extract([el("|⊥|0.05|A|B|")])
        assert len(results) >= 1
        r = results[0]
        assert r.symbol == "perpendicularity"
        assert r.tolerance_value == "0.05"

    def test_datum_reference_extracted_from_feature_frame(self):
        from docstrange.extractors.gdt import GDTExtractor
        results = GDTExtractor().extract([el("|⊥|0.02|C|")])
        r = next((r for r in results if r.datum_reference is not None), None)
        assert r is not None
        assert r.datum_reference == "C"

    def test_empty_elements_skipped(self):
        from docstrange.extractors.gdt import GDTExtractor
        assert GDTExtractor().extract([el("")]) == []


# ---------------------------------------------------------------------------
# Bounding box end-to-end precision
# ---------------------------------------------------------------------------

class TestBoundingBoxPrecision:

    def test_dimension_extractor_preserves_exact_bbox(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        elem = el("10.0 mm", x=123.4, y=567.8, w=88.0, h=22.5)
        results = DimensionExtractor().extract([elem])
        assert len(results) >= 1
        b = results[0].bbox
        assert b.x == 123.4
        assert b.y == 567.8
        assert b.width == 88.0
        assert b.height == 22.5

    def test_two_elements_get_independent_bboxes(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        e1 = el("10.0 mm", x=10.0, y=20.0, w=50.0, h=15.0)
        e2 = el("20.0 mm", x=200.0, y=400.0, w=60.0, h=18.0)
        results = DimensionExtractor().extract([e1, e2])
        bboxes = [r.bbox for r in results if r.dimension_type == "linear"]
        xs = {b.x for b in bboxes}
        assert 10.0 in xs
        assert 200.0 in xs

    def test_gdt_extractor_bbox_from_source_element(self):
        from docstrange.extractors.gdt import GDTExtractor
        elem = el("⊥ 0.05 A", x=300.0, y=150.0, w=70.0, h=12.0)
        results = GDTExtractor().extract([elem])
        assert len(results) >= 1
        b = results[0].bbox
        assert b.x == 300.0
        assert b.y == 150.0

    def test_bom_row_bbox_preserved_in_schema(self):
        bbox = BBoxSchema(x=40.0, y=80.0, width=300.0, height=20.0)
        row = BOMRow(
            confidence=0.9, bbox=bbox,
            item_number="1", description="Hex bolt",
            raw_cells=["1", "2", "Hex bolt"],
        )
        assert row.bbox.x == 40.0
        assert row.bbox.y == 80.0
        assert row.bbox.width == 300.0

    def test_revision_entry_bbox_preserved(self):
        bbox = BBoxSchema(x=700.0, y=50.0, width=200.0, height=15.0)
        entry = RevisionEntry(
            revision="B", date="2024-06-01", description="Updated",
            confidence=0.85, bbox=bbox,
        )
        assert entry.bbox.x == 700.0


# ---------------------------------------------------------------------------
# Multi-page page stamping
# ---------------------------------------------------------------------------

class TestMultiPageStamping:

    def test_run_extractors_stamps_page_number(self):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        elements = [
            el("25.4 mm", x=200.0, y=300.0),
            el("GENERAL NOTES:", x=50.0, y=700.0),
            el("1. ALL DIMS IN MM", x=50.0, y=720.0),
        ]
        pipeline = _pipeline_with_elements(elements)
        result = pipeline._run_extractors(elements, None, metadata={"source": "test.pdf", "page": 3})

        for dim in result.dimensions:
            assert dim.page == 3
        for note in result.notes:
            assert note.page == 3

    def test_merge_preserves_per_page_numbers(self):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        pipeline = _pipeline_with_elements([])
        bbox = BBoxSchema(x=0, y=0, width=50, height=20)

        p1 = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="10mm", nominal=10, dimension_type="linear",
                                         confidence=0.9, bbox=bbox, page=1)]
        )
        p2 = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="20mm", nominal=20, dimension_type="linear",
                                         confidence=0.85, bbox=bbox, page=2)]
        )
        p3 = EngineeringDrawingResult(
            dimensions=[DimensionElement(text="30mm", nominal=30, dimension_type="linear",
                                         confidence=0.8, bbox=bbox, page=3)]
        )
        merged = pipeline._merge_page_results([p1, p2, p3], metadata={"pages": 3})

        assert len(merged.dimensions) == 3
        assert merged.dimensions[0].page == 1
        assert merged.dimensions[1].page == 2
        assert merged.dimensions[2].page == 3

    def test_merge_metadata_pages_count(self):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        pipeline = _pipeline_with_elements([])
        bbox = BBoxSchema(x=0, y=0, width=10, height=10)
        pages = [EngineeringDrawingResult() for _ in range(5)]
        merged = pipeline._merge_page_results(pages, metadata={"pages": 5, "source": "multi.pdf"})
        assert merged.metadata.pages == 5

    def test_page_1_default_for_single_image(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        elements = [el("50.0 mm")]
        pipeline = _pipeline_with_elements(elements)
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))
        for dim in result.dimensions:
            assert dim.page == 1

    def test_all_sections_empty_on_empty_page(self):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        pipeline = _pipeline_with_elements([])
        result = pipeline._run_extractors([], None, metadata={"source": "blank.pdf", "page": 1})
        assert result.dimensions == []
        assert result.title_block == []
        assert result.notes == []
        assert result.gdt == []
        assert result.bom == []
        assert result.revisions == []


# ---------------------------------------------------------------------------
# Malformed / degenerate input
# ---------------------------------------------------------------------------

class TestMalformedInput:

    def test_empty_elements_list_all_extractors(self, tmp_path):
        from docstrange.pipelines.engineering import EngineeringDrawingPipeline
        pipeline = _pipeline_with_elements([])
        img = tmp_path / "blank.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))
        assert result is not None
        assert len(result.dimensions) == 0
        assert len(result.gdt) == 0

    def test_elements_with_zero_confidence_no_crash(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        elem = el("25.4 mm", confidence=0.0)
        results = DimensionExtractor().extract([elem])
        assert isinstance(results, list)
        for r in results:
            assert 0.0 <= r.confidence <= 1.0

    def test_picture_type_element_skipped_by_dimension_extractor(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        elem = el("100.0 mm", element_type="picture")
        assert DimensionExtractor().extract([elem]) == []

    def test_extremely_long_text_no_crash_bom(self):
        from docstrange.extractors.bom import BOMExtractor
        long_row = " | ".join(["cell"] * 200)
        header = el("BILL OF MATERIALS", x=50.0, y=100.0, w=200.0)
        row = el(long_row, x=50.0, y=120.0, w=500.0)
        results = BOMExtractor().extract([header, row])
        assert isinstance(results, list)

    def test_note_section_ends_gracefully(self):
        from docstrange.extractors.notes import NoteExtractor
        # Texts must not contain "note" — _NOTE_HEADER regex (NOTES?:?) would
        # match that word and consume the lines as headers instead of content.
        elements = [
            el("NOTES:", x=50.0, y=100.0),
            el("1. ALL DIMS IN MM", x=50.0, y=120.0),
            el("2. REMOVE SHARP EDGES", x=50.0, y=140.0),
        ]
        results = NoteExtractor().extract(elements)
        numbered = [r for r in results if r.note_number is not None]
        assert len(numbered) == 2
        assert numbered[0].note_number == 1
        assert numbered[1].note_number == 2

    def test_dimension_extractor_handles_none_text_gracefully(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        # LayoutElement where text might come out as empty
        elem = el("")
        results = DimensionExtractor().extract([elem])
        assert results == []


# ---------------------------------------------------------------------------
# Note continuation merging
# ---------------------------------------------------------------------------

class TestNoteContinuation:

    def test_indented_continuation_merged_into_previous_note(self):
        from docstrange.extractors.notes import NoteExtractor
        header   = el("GENERAL NOTES:", x=50.0, y=100.0)
        note1    = el("1. DO NOT SCALE DRAWING", x=50.0, y=120.0)
        cont     = el("   REFER TO DXF FILE", x=50.0, y=135.0)  # 3 leading spaces
        results = NoteExtractor().extract([header, note1, cont])
        numbered = [r for r in results if r.note_number == 1]
        assert len(numbered) == 1
        assert "REFER TO DXF FILE" in numbered[0].text

    def test_multiple_numbered_notes_in_sequence(self):
        from docstrange.extractors.notes import NoteExtractor
        elems = [
            el("NOTES:", x=50.0, y=100.0),
            el("1. ALL DIMS IN MM", x=50.0, y=120.0),
            el("2. BREAK SHARP EDGES", x=50.0, y=140.0),
            el("3. FINISH: ANODIZE", x=50.0, y=160.0),
        ]
        results = NoteExtractor().extract(elems)
        nums = sorted(r.note_number for r in results if r.note_number)
        assert nums == [1, 2, 3]


# ---------------------------------------------------------------------------
# Schema validation — Pydantic constraint enforcement
# ---------------------------------------------------------------------------

class TestSchemaValidation:

    def test_confidence_above_one_raises(self):
        from pydantic import ValidationError
        bbox = BBoxSchema(x=0, y=0, width=10, height=10)
        with pytest.raises(ValidationError):
            DimensionElement(text="10mm", nominal=10, dimension_type="linear",
                             confidence=1.5, bbox=bbox)

    def test_confidence_below_zero_raises(self):
        from pydantic import ValidationError
        bbox = BBoxSchema(x=0, y=0, width=10, height=10)
        with pytest.raises(ValidationError):
            DimensionElement(text="10mm", nominal=10, dimension_type="linear",
                             confidence=-0.1, bbox=bbox)

    def test_extraction_metadata_version_default(self):
        m = ExtractionMetadata()
        assert m.extractor_version == "1.0.0"

    def test_extraction_metadata_version_non_empty(self):
        m = ExtractionMetadata(source="drawing.pdf", pages=2)
        assert m.extractor_version != ""

    def test_bom_row_text_auto_filled_from_raw_cells(self):
        bbox = BBoxSchema(x=0, y=0, width=100, height=20)
        row = BOMRow(
            confidence=0.9, bbox=bbox,
            item_number="3", quantity="5",
            description="Washer M8",
            raw_cells=["3", "5", "Washer M8"],
        )
        assert "Washer M8" in row.text

    def test_revision_entry_text_auto_filled(self):
        bbox = BBoxSchema(x=0, y=0, width=100, height=20)
        entry = RevisionEntry(
            revision="C", date="2025-03-01", description="Tolerance update",
            confidence=0.85, bbox=bbox,
        )
        assert entry.text != ""
        assert "C" in entry.text or "Tolerance update" in entry.text

    def test_engineering_result_sections_default_to_empty_lists(self):
        result = EngineeringDrawingResult()
        assert result.dimensions == []
        assert result.title_block == []
        assert result.notes == []
        assert result.gdt == []
        assert result.bom == []
        assert result.revisions == []

    def test_metadata_dict_coerced_to_extraction_metadata(self):
        result = EngineeringDrawingResult(metadata={"source": "drawing.pdf", "pages": 3})
        assert isinstance(result.metadata, ExtractionMetadata)
        assert result.metadata.source == "drawing.pdf"
        assert result.metadata.pages == 3


# ---------------------------------------------------------------------------
# Result completeness invariants
# ---------------------------------------------------------------------------

class TestResultInvariants:

    def test_all_elements_have_page_at_least_one(self, tmp_path):
        elements = [
            el("DWG NO. A-001", x=750.0, y=950.0),
            el("25.4 mm", x=200.0, y=300.0),
            el("GENERAL NOTES:", x=50.0, y=700.0),
            el("1. ALL DIMS IN MM", x=50.0, y=720.0),
            el("⊥ 0.05 A", x=400.0, y=500.0),
        ]
        pipeline = _pipeline_with_elements(elements)
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))

        all_items = (
            result.title_block + result.dimensions + result.notes
            + result.gdt + result.bom + result.revisions
        )
        for item in all_items:
            assert item.page >= 1, f"{type(item).__name__} has page={item.page}"

    def test_all_confidence_values_in_range(self, tmp_path):
        elements = [
            el("25.4 mm"), el("⊙ 0.1 A"), el("GENERAL NOTES:", x=50.0, y=100.0),
            el("1. note", x=50.0, y=120.0),
        ]
        pipeline = _pipeline_with_elements(elements)
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))

        all_items = (
            result.title_block + result.dimensions + result.notes
            + result.gdt + result.bom + result.revisions
        )
        for item in all_items:
            assert 0.0 <= item.confidence <= 1.0, \
                f"{type(item).__name__} confidence={item.confidence} out of range"

    def test_result_json_serialisable_with_unicode_gdt(self, tmp_path):
        import json
        elements = [
            el("⊥ 0.05 A"), el("⊙ 0.1 B"), el("⌀12.5"),
            el("∥ 0.02"), el("⌤ 0.03"),
        ]
        pipeline = _pipeline_with_elements(elements)
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))
        serialised = json.dumps(result.model_dump())
        assert isinstance(serialised, str)
        data = json.loads(serialised)
        assert "dimensions" in data
        assert "gdt" in data

    def test_extractor_version_in_metadata(self, tmp_path):
        pipeline = _pipeline_with_elements([])
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img))
        assert result.metadata.extractor_version
        assert isinstance(result.metadata.extractor_version, str)

    def test_selective_extraction_leaves_other_sections_empty(self, tmp_path):
        elements = [
            el("25.4 mm"), el("DWG NO. A-001", x=750.0, y=950.0),
            el("GENERAL NOTES:", x=50.0, y=700.0),
            el("1. ALL DIMS IN MM", x=50.0, y=720.0),
        ]
        pipeline = _pipeline_with_elements(elements)
        img = tmp_path / "drawing.png"
        img.write_bytes(b"fake")
        result = pipeline.extract_from_image(str(img), extractors=["gdt", "bom"])
        assert result.dimensions == []
        assert result.title_block == []
        assert result.notes == []
