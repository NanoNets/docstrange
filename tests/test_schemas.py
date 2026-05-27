"""Tests for engineering drawing Pydantic schemas."""

import pytest


def test_bbox_schema():
    from docstrange.schemas.engineering import BBoxSchema
    bbox = BBoxSchema(x=10, y=20, width=80, height=15)
    assert bbox.x == 10
    assert bbox.y == 20
    d = bbox.model_dump()
    assert set(d.keys()) == {"x", "y", "width", "height"}


def test_extraction_element_confidence_bounds():
    from pydantic import ValidationError
    from docstrange.schemas.engineering import BBoxSchema, ExtractionElement
    bbox = BBoxSchema(x=0, y=0, width=50, height=10)
    with pytest.raises(ValidationError):
        ExtractionElement(text="foo", type="test", confidence=1.5, bbox=bbox)
    with pytest.raises(ValidationError):
        ExtractionElement(text="foo", type="test", confidence=-0.1, bbox=bbox)
    el = ExtractionElement(text="foo", type="test", confidence=0.95, bbox=bbox)
    assert el.confidence == 0.95


def test_dimension_element_defaults():
    from docstrange.schemas.engineering import BBoxSchema, DimensionElement
    bbox = BBoxSchema(x=0, y=0, width=60, height=12)
    d = DimensionElement(text="25.4", confidence=0.9, bbox=bbox)
    assert d.type == "dimension"
    assert d.nominal is None
    assert d.unit is None


def test_title_block_field():
    from docstrange.schemas.engineering import BBoxSchema, TitleBlockField
    bbox = BBoxSchema(x=700, y=900, width=80, height=15)
    f = TitleBlockField(text="SCALE 1:2", field_name="scale", field_value="1:2",
                        confidence=0.95, bbox=bbox)
    assert f.type == "title_block"
    assert f.field_name == "scale"


def test_engineering_drawing_result_empty():
    from docstrange.schemas.engineering import EngineeringDrawingResult
    r = EngineeringDrawingResult()
    assert r.dimensions == []
    assert r.title_block == []
    d = r.model_dump()
    assert "dimensions" in d
    assert "metadata" in d


def test_bom_row_schema():
    from docstrange.schemas.engineering import BBoxSchema, BOMRow
    bbox = BBoxSchema(x=0, y=100, width=200, height=15)
    row = BOMRow(item_number="1", quantity="2", description="Bolt M6", confidence=0.85, bbox=bbox)
    assert row.item_number == "1"
    assert row.quantity == "2"


def test_revision_entry_schema():
    from docstrange.schemas.engineering import BBoxSchema, RevisionEntry
    bbox = BBoxSchema(x=700, y=50, width=150, height=15)
    entry = RevisionEntry(revision="B", date="2024-01-15", description="Updated tolerances",
                          confidence=0.9, bbox=bbox)
    assert entry.revision == "B"
    assert entry.date == "2024-01-15"
