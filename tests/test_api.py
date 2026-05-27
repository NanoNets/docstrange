"""Tests for the DocStrange Engineering FastAPI service layer.

Uses FastAPI's TestClient (sync) so no real OCR models are needed — the pipeline
is monkey-patched with a mock before each test.
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("httpx", reason="httpx not installed (required by TestClient)")

from fastapi.testclient import TestClient

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
                                  dimension_type="linear", confidence=0.9, bbox=_BBOX)],
    notes=[NoteElement(text="ALL DIMENSIONS IN MM", is_general=True,
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


@pytest.fixture(scope="module")
def client():
    """Return a TestClient with the pipeline swapped for a mock."""
    import docstrange.api.routes as routes_module

    mock_pipeline = MagicMock()
    mock_pipeline.extract_from_image.return_value = _FULL_RESULT
    mock_pipeline.extract_from_pdf.return_value = _FULL_RESULT

    # Patch the lazy singleton so no real models are loaded
    routes_module._pipeline = mock_pipeline
    routes_module._overlay_gen = None  # let the real OverlayGenerator instantiate

    from docstrange.api.routes import create_app
    app = create_app()
    return TestClient(app)


def _png_bytes() -> bytes:
    """Return a minimal 1×1 white PNG — valid enough for extension detection."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    """Minimal valid PDF bytes (enough to pass extension check)."""
    return b"%PDF-1.4 fake"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "docstrange-engineering"


# ---------------------------------------------------------------------------
# Individual extraction endpoints
# ---------------------------------------------------------------------------

class TestExtractionEndpoints:

    def _upload(self, client, url: str, content: bytes, filename: str = "drawing.png"):
        return client.post(url, files={"file": (filename, content, "image/png")})

    def test_title_block_returns_list(self, client):
        resp = self._upload(client, "/extract/title-block", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "title_block"
        assert body[0]["field_name"] == "drawing_number"

    def test_dimensions_returns_list(self, client):
        resp = self._upload(client, "/extract/dimensions", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "dimension"
        assert body[0]["nominal"] == 25.4

    def test_notes_returns_list(self, client):
        resp = self._upload(client, "/extract/notes", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "note"

    def test_gdt_returns_list(self, client):
        resp = self._upload(client, "/extract/gdt", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "gdt"
        assert body[0]["symbol"] == "perpendicularity"

    def test_bom_returns_list(self, client):
        resp = self._upload(client, "/extract/bom", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "bom"
        assert "Bolt M6" in body[0]["text"]

    def test_revisions_returns_list(self, client):
        resp = self._upload(client, "/extract/revisions", _png_bytes())
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["type"] == "revision"
        assert body[0]["revision"] == "A"


# ---------------------------------------------------------------------------
# Full extraction
# ---------------------------------------------------------------------------

class TestFullExtraction:

    def test_full_returns_all_sections(self, client):
        resp = client.post(
            "/extract/full",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "title_block" in body
        assert "dimensions" in body
        assert "notes" in body
        assert "gdt" in body
        assert "bom" in body
        assert "revisions" in body

    def test_full_no_overlay_by_default(self, client):
        resp = client.post(
            "/extract/full",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        body = resp.json()
        assert "overlay_json" not in body or body.get("overlay_json") is None

    def test_full_with_overlays(self, client):
        resp = client.post(
            "/extract/full?include_overlays=true&image_width=1000&image_height=800",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "overlay_json" in body
        overlay = body["overlay_json"]
        assert "annotations" in overlay
        assert "total_annotations" in overlay

    def test_full_metadata_is_typed(self, client):
        resp = client.post(
            "/extract/full",
            files={"file": ("drawing.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "metadata" in body
        # ExtractionMetadata fields
        assert "source" in body["metadata"]
        assert "pages" in body["metadata"]
        assert "extractor_version" in body["metadata"]


# ---------------------------------------------------------------------------
# Overlay endpoint
# ---------------------------------------------------------------------------

class TestOverlayEndpoint:

    def test_overlay_structure(self, client):
        resp = client.post(
            "/generate/overlays?image_width=1000&image_height=800",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "annotations" in body
        assert "image_size" in body
        assert body["image_size"]["width"] == 1000
        assert body["total_annotations"] == len(body["annotations"])

    def test_overlay_annotations_have_page_field(self, client):
        resp = client.post(
            "/generate/overlays?image_width=1000&image_height=800",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        for ann in resp.json()["annotations"]:
            assert "page" in ann
            assert isinstance(ann["page"], int)

    def test_overlay_page_filter(self, client):
        resp = client.post(
            "/generate/overlays?image_width=1000&image_height=800&page=1",
            files={"file": ("drawing.png", _png_bytes(), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_filter"] == 1
        for ann in body["annotations"]:
            assert ann["page"] == 1


# ---------------------------------------------------------------------------
# Validation — file type and size
# ---------------------------------------------------------------------------

class TestValidation:

    def test_unsupported_extension_returns_415(self, client):
        resp = client.post(
            "/extract/dimensions",
            files={"file": ("drawing.docx", b"fake", "application/octet-stream")},
        )
        assert resp.status_code == 415

    def test_empty_file_returns_400(self, client):
        resp = client.post(
            "/extract/dimensions",
            files={"file": ("drawing.png", b"", "image/png")},
        )
        assert resp.status_code == 400

    def test_oversized_file_returns_413(self, client):
        big = b"X" * (51 * 1024 * 1024)  # 51 MB
        resp = client.post(
            "/extract/dimensions",
            files={"file": ("drawing.png", big, "image/png")},
        )
        assert resp.status_code == 413
