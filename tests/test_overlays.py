"""Tests for Phase 6 — Overlay JSON generation.

Covers change_id sequencing, bbox field naming, summary section,
page filtering, and cross-run stability of sequential IDs.
"""

import re

import pytest

from docstrange.overlays.generator import OverlayGenerator
from docstrange.schemas.engineering import (
    BBoxSchema,
    BOMRow,
    DimensionElement,
    EngineeringDrawingResult,
    GDTElement,
    NoteElement,
    RevisionEntry,
    TitleBlockField,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_BBOX = BBoxSchema(x=10.0, y=20.0, width=50.0, height=15.0)

_FULL_RESULT = EngineeringDrawingResult(
    title_block=[TitleBlockField(text="DWG-001", field_name="drawing_number",
                                 field_value="DWG-001", confidence=0.95, bbox=_BBOX)],
    dimensions=[DimensionElement(text="25.4 mm", nominal=25.4, unit="mm",
                                  dimension_type="linear", confidence=0.9, bbox=_BBOX),
                DimensionElement(text="12.7 mm", nominal=12.7, unit="mm",
                                  dimension_type="linear", confidence=0.85, bbox=_BBOX)],
    notes=[NoteElement(text="ALL DIMS IN MM", is_general=True,
                       confidence=0.85, bbox=_BBOX)],
    gdt=[GDTElement(text="⊥ 0.05 A", symbol="perpendicularity",
                    tolerance_value="0.05", datum_reference="A",
                    confidence=0.88, bbox=_BBOX)],
    bom=[BOMRow(item_number="1", quantity="2", description="Bolt M6",
                raw_cells=["1", "2", "Bolt M6"], confidence=0.9, bbox=_BBOX)],
    revisions=[RevisionEntry(revision="A", date="2024-01-15",
                             description="Initial release", confidence=0.8, bbox=_BBOX)],
    metadata={"source": "test.pdf", "pages": 1},
)


@pytest.fixture
def gen():
    return OverlayGenerator()


@pytest.fixture
def overlay(gen):
    return gen.generate(_FULL_RESULT, image_width=1000, image_height=800)


# ---------------------------------------------------------------------------
# change_id field
# ---------------------------------------------------------------------------

class TestChangeId:

    def test_every_annotation_has_change_id(self, overlay):
        for ann in overlay["annotations"]:
            assert "change_id" in ann

    def test_change_id_format(self, overlay):
        pattern = re.compile(r"^chg_\d{3}$")
        for ann in overlay["annotations"]:
            assert pattern.match(ann["change_id"]), \
                f"Bad change_id format: {ann['change_id']}"

    def test_change_ids_are_sequential(self, overlay):
        ids = [ann["change_id"] for ann in overlay["annotations"]]
        for i, cid in enumerate(ids, start=1):
            assert cid == f"chg_{i:03d}", \
                f"Expected chg_{i:03d}, got {cid}"

    def test_change_ids_are_unique(self, overlay):
        ids = [ann["change_id"] for ann in overlay["annotations"]]
        assert len(ids) == len(set(ids))

    def test_change_ids_stable_across_reruns(self, gen):
        """Same extraction → same change_id sequence every time."""
        overlay1 = gen.generate(_FULL_RESULT, image_width=1000, image_height=800)
        overlay2 = gen.generate(_FULL_RESULT, image_width=1000, image_height=800)
        ids1 = [a["change_id"] for a in overlay1["annotations"]]
        ids2 = [a["change_id"] for a in overlay2["annotations"]]
        assert ids1 == ids2

    def test_no_uuid_id_field(self, overlay):
        """Old random `id` field must not be present."""
        for ann in overlay["annotations"]:
            assert "id" not in ann


# ---------------------------------------------------------------------------
# bbox field (pixel-space, flat)
# ---------------------------------------------------------------------------

class TestBboxField:

    def test_bbox_present_on_every_annotation(self, overlay):
        for ann in overlay["annotations"]:
            assert "bbox" in ann

    def test_bbox_has_required_keys(self, overlay):
        for ann in overlay["annotations"]:
            bbox = ann["bbox"]
            for key in ("x", "y", "width", "height"):
                assert key in bbox, f"Missing bbox key: {key}"

    def test_bbox_values_match_source(self, overlay):
        for ann in overlay["annotations"]:
            assert ann["bbox"]["x"] == 10.0
            assert ann["bbox"]["y"] == 20.0
            assert ann["bbox"]["width"] == 50.0
            assert ann["bbox"]["height"] == 15.0

    def test_bbox_normalized_also_present(self, overlay):
        for ann in overlay["annotations"]:
            assert "bbox_normalized" in ann

    def test_no_bbox_pixels_field(self, overlay):
        """Old `bbox_pixels` key must not leak through."""
        for ann in overlay["annotations"]:
            assert "bbox_pixels" not in ann

    def test_bbox_normalized_values_in_range(self, overlay):
        for ann in overlay["annotations"]:
            nb = ann["bbox_normalized"]
            for key in ("x", "y", "width", "height"):
                assert 0.0 <= nb[key] <= 1.0, \
                    f"Normalized {key}={nb[key]} out of [0,1]"


# ---------------------------------------------------------------------------
# Summary section
# ---------------------------------------------------------------------------

class TestSummary:

    def test_summary_present(self, overlay):
        assert "summary" in overlay

    def test_summary_total_matches_annotations(self, overlay):
        assert overlay["summary"]["total"] == len(overlay["annotations"])

    def test_summary_by_type_keys(self, overlay):
        by_type = overlay["summary"]["by_type"]
        expected_types = {"dimension", "title_block", "note", "gdt", "bom", "revision"}
        assert expected_types == set(by_type.keys())

    def test_summary_by_type_counts(self, overlay):
        by_type = overlay["summary"]["by_type"]
        assert by_type["dimension"] == 2
        assert by_type["title_block"] == 1
        assert by_type["gdt"] == 1

    def test_summary_by_type_sum_equals_total(self, overlay):
        by_type = overlay["summary"]["by_type"]
        assert sum(by_type.values()) == overlay["summary"]["total"]


# ---------------------------------------------------------------------------
# Page filtering interacts correctly with change_id
# ---------------------------------------------------------------------------

class TestPageFilterWithChangeId:

    def test_page_filtered_ids_restart_at_chg_001(self, gen):
        """Page-filtered output renumbers from chg_001, not from the global index."""
        result = EngineeringDrawingResult(
            dimensions=[
                DimensionElement(text="10 mm", nominal=10.0, unit="mm",
                                  dimension_type="linear", confidence=0.9,
                                  bbox=_BBOX, page=1),
                DimensionElement(text="20 mm", nominal=20.0, unit="mm",
                                  dimension_type="linear", confidence=0.9,
                                  bbox=_BBOX, page=2),
            ],
        )
        overlay = gen.generate(result, image_width=500, image_height=400, page=2)
        assert len(overlay["annotations"]) == 1
        assert overlay["annotations"][0]["change_id"] == "chg_001"

    def test_page_filter_excludes_other_pages(self, gen):
        result = EngineeringDrawingResult(
            dimensions=[
                DimensionElement(text="10 mm", nominal=10.0, unit="mm",
                                  dimension_type="linear", confidence=0.9,
                                  bbox=_BBOX, page=1),
                DimensionElement(text="20 mm", nominal=20.0, unit="mm",
                                  dimension_type="linear", confidence=0.9,
                                  bbox=_BBOX, page=2),
            ],
        )
        overlay = gen.generate(result, image_width=500, image_height=400, page=1)
        assert all(ann["page"] == 1 for ann in overlay["annotations"])


# ---------------------------------------------------------------------------
# Overlay with zero image dimensions
# ---------------------------------------------------------------------------

class TestZeroDimensions:

    def test_no_crash_on_zero_dimensions(self, gen):
        overlay = gen.generate(_FULL_RESULT)
        assert overlay["total_annotations"] > 0

    def test_bbox_normalized_zero_when_no_dimensions(self, gen):
        overlay = gen.generate(_FULL_RESULT)
        for ann in overlay["annotations"]:
            nb = ann["bbox_normalized"]
            assert nb == {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
