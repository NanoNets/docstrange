"""Unit tests for engineering drawing extractors using synthetic LayoutElement fixtures."""

import pytest


def make_element(text, x=0.0, y=0.0, w=100.0, h=20.0, confidence=0.9, element_type="paragraph"):
    """Create a synthetic LayoutElement without invoking OCR."""
    from docstrange.pipeline.layout_detector import LayoutElement
    return LayoutElement(
        text=text,
        x=x, y=y, width=w, height=h,
        element_type=element_type,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# DimensionExtractor
# ---------------------------------------------------------------------------

class TestDimensionExtractor:

    def test_linear_dimension_nominal_only(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("25.4 mm")
        results = DimensionExtractor().extract([el])
        dims = [r for r in results if r.dimension_type == "linear"]
        assert len(dims) >= 1
        assert dims[0].nominal == 25.4
        assert dims[0].unit == "mm"

    def test_linear_with_symmetric_tolerance(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("25.4 ±0.1 mm")
        results = DimensionExtractor().extract([el])
        dims = [r for r in results if r.dimension_type == "linear"]
        assert len(dims) >= 1
        d = dims[0]
        assert d.nominal == 25.4
        assert d.upper_tolerance == 0.1
        assert d.lower_tolerance == -0.1
        assert d.confidence >= 0.9  # full strict match

    def test_diameter_unicode(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("⌀12.5")
        results = DimensionExtractor().extract([el])
        diam = [r for r in results if r.dimension_type == "diameter"]
        assert len(diam) >= 1
        assert diam[0].nominal == 12.5

    def test_angular(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("45°")
        results = DimensionExtractor().extract([el])
        ang = [r for r in results if r.dimension_type == "angular"]
        assert len(ang) >= 1
        assert ang[0].nominal == 45.0

    def test_radial(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("R12.5")
        results = DimensionExtractor().extract([el])
        rad = [r for r in results if r.dimension_type == "radial"]
        assert len(rad) >= 1
        assert rad[0].nominal == 12.5

    def test_no_false_positive_on_long_serial(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("PART NO. 1234567")
        results = DimensionExtractor().extract([el])
        # No valid dimension should be extracted for a long serial number
        assert all(r.nominal is None or r.nominal < 9999 for r in results)

    def test_picture_elements_skipped(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("25.4 mm", element_type="picture")
        results = DimensionExtractor().extract([el])
        assert results == []

    def test_bbox_populated(self):
        from docstrange.extractors.dimensions import DimensionExtractor
        el = make_element("10.0 mm", x=120.0, y=240.0, w=80.0, h=20.0)
        results = DimensionExtractor().extract([el])
        assert len(results) > 0
        bbox = results[0].bbox
        assert bbox.x == 120.0
        assert bbox.y == 240.0
        assert bbox.width == 80.0
        assert bbox.height == 20.0


# ---------------------------------------------------------------------------
# TitleBlockExtractor
# ---------------------------------------------------------------------------

class TestTitleBlockExtractor:

    def test_keyword_match_in_zone(self):
        from docstrange.extractors.title_block import TitleBlockExtractor
        # Place in title block zone (high x, high y)
        el = make_element("SCALE 1:2", x=700.0, y=900.0, w=80.0, h=15.0)
        results = TitleBlockExtractor().extract([el])
        scale_fields = [r for r in results if r.field_name == "scale"]
        assert len(scale_fields) >= 1

    def test_drawing_number_detection(self):
        from docstrange.extractors.title_block import TitleBlockExtractor
        el = make_element("DWG NO. A-1234", x=750.0, y=950.0)
        results = TitleBlockExtractor().extract([el])
        dn = [r for r in results if r.field_name == "drawing_number"]
        assert len(dn) >= 1

    def test_material_detection(self):
        from docstrange.extractors.title_block import TitleBlockExtractor
        el = make_element("MATERIAL: SS316", x=710.0, y=920.0)
        results = TitleBlockExtractor().extract([el])
        mat = [r for r in results if r.field_name == "material"]
        assert len(mat) >= 1

    def test_low_confidence_outside_zone_without_keyword(self):
        from docstrange.extractors.title_block import TitleBlockExtractor
        # Outside zone, no keyword
        el = make_element("Some random text", x=10.0, y=10.0, w=100.0, h=15.0)
        results = TitleBlockExtractor().extract([el])
        assert all(r.confidence < 0.8 for r in results)

    def test_empty_elements(self):
        from docstrange.extractors.title_block import TitleBlockExtractor
        assert TitleBlockExtractor().extract([]) == []


# ---------------------------------------------------------------------------
# NoteExtractor
# ---------------------------------------------------------------------------

class TestNoteExtractor:

    def test_numbered_note(self):
        from docstrange.extractors.notes import NoteExtractor
        header = make_element("GENERAL NOTES:", x=50.0, y=100.0)
        note1 = make_element("1. ALL DIMENSIONS IN MM", x=50.0, y=120.0)
        note2 = make_element("2. REMOVE ALL BURRS", x=50.0, y=140.0)
        results = NoteExtractor().extract([header, note1, note2])
        numbered = [r for r in results if r.note_number is not None]
        assert len(numbered) == 2
        assert numbered[0].note_number == 1
        assert numbered[1].note_number == 2

    def test_general_note(self):
        from docstrange.extractors.notes import NoteExtractor
        header = make_element("NOTES", x=50.0, y=100.0)
        note = make_element("FINISH ALL OVER", x=50.0, y=120.0)
        results = NoteExtractor().extract([header, note])
        general = [r for r in results if r.is_general]
        assert len(general) >= 1

    def test_no_notes_without_header(self):
        from docstrange.extractors.notes import NoteExtractor
        el = make_element("1. Some text without notes header", x=0.0, y=0.0)
        results = NoteExtractor().extract([el])
        assert results == []


# ---------------------------------------------------------------------------
# GDTExtractor
# ---------------------------------------------------------------------------

class TestGDTExtractor:

    def test_unicode_perpendicularity(self):
        from docstrange.extractors.gdt import GDTExtractor
        el = make_element("⊥ 0.05 A")
        results = GDTExtractor().extract([el])
        gdt = [r for r in results if r.symbol == "perpendicularity"]
        assert len(gdt) >= 1

    def test_text_abbreviation(self):
        from docstrange.extractors.gdt import GDTExtractor
        el = make_element("FLATNESS 0.02")
        results = GDTExtractor().extract([el])
        flat = [r for r in results if r.symbol == "flatness"]
        assert len(flat) >= 1
        assert flat[0].tolerance_value == "0.02"

    def test_feature_control_frame(self):
        from docstrange.extractors.gdt import GDTExtractor
        el = make_element("|⊥|0.05|A|")
        results = GDTExtractor().extract([el])
        assert len(results) >= 1

    def test_datum_reference_extracted(self):
        from docstrange.extractors.gdt import GDTExtractor
        el = make_element("⊥ 0.05 A")
        results = GDTExtractor().extract([el])
        assert any(r.datum_reference == "A" for r in results)


# ---------------------------------------------------------------------------
# BOMExtractor
# ---------------------------------------------------------------------------

class TestBOMExtractor:

    def test_bom_detected_from_header(self):
        from docstrange.extractors.bom import BOMExtractor
        header = make_element("BILL OF MATERIALS", x=50.0, y=100.0, w=200.0)
        col_header = make_element("ITEM  QTY  PART NO.  DESCRIPTION", x=50.0, y=125.0, w=400.0)
        row1 = make_element("1  2  M6-BOLT  HEX BOLT M6x20", x=50.0, y=145.0, w=400.0)
        results = BOMExtractor().extract([header, col_header, row1])
        assert len(results) >= 1

    def test_no_bom_without_header(self):
        from docstrange.extractors.bom import BOMExtractor
        el = make_element("1  2  M6-BOLT  HEX BOLT M6x20", x=50.0, y=145.0)
        results = BOMExtractor().extract([el])
        assert results == []

    def test_empty_elements(self):
        from docstrange.extractors.bom import BOMExtractor
        assert BOMExtractor().extract([]) == []


# ---------------------------------------------------------------------------
# RevisionExtractor
# ---------------------------------------------------------------------------

class TestRevisionExtractor:

    def test_revision_entry_detected(self):
        from docstrange.extractors.revisions import RevisionExtractor
        header = make_element("REVISION HISTORY", x=700.0, y=10.0)
        entry = make_element("B  2024-01-15  Updated tolerances  J.Smith", x=700.0, y=30.0)
        results = RevisionExtractor().extract([header, entry])
        assert len(results) >= 1

    def test_date_extracted(self):
        from docstrange.extractors.revisions import RevisionExtractor
        header = make_element("REV BLOCK", x=700.0, y=10.0)
        entry = make_element("A  01/15/2024  Initial release", x=700.0, y=30.0)
        results = RevisionExtractor().extract([header, entry])
        assert any(r.date is not None for r in results)

    def test_no_results_without_header(self):
        from docstrange.extractors.revisions import RevisionExtractor
        el = make_element("A  01/15/2024  Initial release")
        results = RevisionExtractor().extract([el])
        assert results == []
