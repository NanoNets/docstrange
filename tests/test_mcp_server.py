"""Tests for the DocStrange Engineering MCP server layer.

The MCP server is exercised by calling _dispatch() and _extract() directly —
no real OCR models or stdio transport needed.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

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
def tmp_png(tmp_path):
    """Write a minimal PNG file and return its path string."""
    p = tmp_path / "drawing.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # minimal header
    return str(p)


@pytest.fixture
def server(tmp_png):
    """Return an EngineeringMCPServer with the pipeline swapped for a mock."""
    from docstrange.mcp_server.server import EngineeringMCPServer

    mock_pipeline = MagicMock()
    mock_pipeline.extract_from_image.return_value = _FULL_RESULT
    mock_pipeline.extract_from_pdf.return_value = _FULL_RESULT

    srv = EngineeringMCPServer.__new__(EngineeringMCPServer)
    # Bypass __init__ to avoid mcp.Server instantiation in tests
    from docstrange.mcp_server.cache import ExtractionCache
    srv._pipeline = mock_pipeline
    srv._overlay_gen = None
    srv._cache = ExtractionCache(maxsize=5)
    return srv


def _parse(content_list) -> dict | list:
    return json.loads(content_list[0].text)


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:

    def test_all_eight_tools_present(self):
        from docstrange.mcp_server.tools import TOOLS
        names = {t.name for t in TOOLS}
        expected = {
            "extract_dimensions", "extract_title_block", "extract_notes",
            "extract_gdt", "extract_bom", "extract_revisions",
            "extract_full", "generate_overlays",
        }
        assert expected == names

    def test_generate_overlays_has_page_param(self):
        from docstrange.mcp_server.tools import TOOLS
        t = next(t for t in TOOLS if t.name == "generate_overlays")
        assert "page" in t.inputSchema["properties"]

    def test_extract_full_has_page_param(self):
        from docstrange.mcp_server.tools import TOOLS
        t = next(t for t in TOOLS if t.name == "extract_full")
        assert "page" in t.inputSchema["properties"]

    def test_every_tool_requires_file_path(self):
        from docstrange.mcp_server.tools import TOOLS
        for t in TOOLS:
            assert "file_path" in t.inputSchema.get("required", []), \
                f"{t.name} missing file_path in required"


# ---------------------------------------------------------------------------
# Dispatch — happy paths
# ---------------------------------------------------------------------------

class TestDispatch:

    @pytest.mark.anyio
    async def test_extract_dimensions(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_dimensions", {"file_path": tmp_png}))
        assert isinstance(data, list)
        assert data[0]["type"] == "dimension"
        assert data[0]["nominal"] == 25.4

    @pytest.mark.anyio
    async def test_extract_title_block(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_title_block", {"file_path": tmp_png}))
        assert data[0]["field_name"] == "drawing_number"

    @pytest.mark.anyio
    async def test_extract_notes(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_notes", {"file_path": tmp_png}))
        assert data[0]["type"] == "note"

    @pytest.mark.anyio
    async def test_extract_gdt(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_gdt", {"file_path": tmp_png}))
        assert data[0]["symbol"] == "perpendicularity"

    @pytest.mark.anyio
    async def test_extract_bom(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_bom", {"file_path": tmp_png}))
        assert data[0]["type"] == "bom"
        assert "Bolt M6" in data[0]["text"]

    @pytest.mark.anyio
    async def test_extract_revisions(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_revisions", {"file_path": tmp_png}))
        assert data[0]["revision"] == "A"

    @pytest.mark.anyio
    async def test_extract_full(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_full", {"file_path": tmp_png}))
        assert "title_block" in data
        assert "dimensions" in data
        assert "metadata" in data
        assert "extractor_version" in data["metadata"]

    @pytest.mark.anyio
    async def test_extract_full_with_overlays(self, server, tmp_png):
        data = _parse(await server._dispatch("extract_full", {
            "file_path": tmp_png,
            "include_overlays": True,
            "image_width": 1000,
            "image_height": 800,
        }))
        assert "overlay_json" in data
        assert "annotations" in data["overlay_json"]

    @pytest.mark.anyio
    async def test_generate_overlays(self, server, tmp_png):
        data = _parse(await server._dispatch("generate_overlays", {
            "file_path": tmp_png,
            "image_width": 1000,
            "image_height": 800,
        }))
        assert "annotations" in data
        assert "total_annotations" in data

    @pytest.mark.anyio
    async def test_generate_overlays_page_filter(self, server, tmp_png):
        data = _parse(await server._dispatch("generate_overlays", {
            "file_path": tmp_png,
            "image_width": 1000,
            "image_height": 800,
            "page": 1,
        }))
        assert data["page_filter"] == 1

    @pytest.mark.anyio
    async def test_unknown_tool_returns_error(self, server, tmp_png):
        data = _parse(await server._dispatch("nonexistent_tool", {"file_path": tmp_png}))
        assert data["status"] == "error"
        assert "Unknown tool" in data["error"]


# ---------------------------------------------------------------------------
# Validation — file path checks
# ---------------------------------------------------------------------------

class TestValidation:

    def test_file_not_found_raises(self, server):
        with pytest.raises(FileNotFoundError):
            server._extract("/nonexistent/drawing.png")

    def test_unsupported_extension_raises(self, server, tmp_path):
        bad = tmp_path / "drawing.docx"
        bad.write_bytes(b"fake")
        with pytest.raises(ValueError, match="Unsupported file type"):
            server._extract(str(bad))

    def test_directory_path_raises(self, server, tmp_path):
        with pytest.raises(ValueError, match="not a regular file"):
            server._extract(str(tmp_path))

    @pytest.mark.anyio
    async def test_dispatch_wraps_file_not_found_as_error_json(self, server):
        data = _parse(await server._dispatch("extract_dimensions", {
            "file_path": "/no/such/file.png"
        }))
        assert data["status"] == "error"
        assert "not found" in data["error"].lower()


# ---------------------------------------------------------------------------
# LRU cache
# ---------------------------------------------------------------------------

class TestExtractionCache:

    def test_miss_returns_none(self, tmp_png):
        from docstrange.mcp_server.cache import ExtractionCache
        cache = ExtractionCache(maxsize=5)
        assert cache.get(tmp_png, None) is None

    def test_put_then_get(self, tmp_png):
        from docstrange.mcp_server.cache import ExtractionCache
        cache = ExtractionCache(maxsize=5)
        cache.put(tmp_png, None, _FULL_RESULT)
        assert cache.get(tmp_png, None) is _FULL_RESULT

    def test_lru_eviction(self, tmp_path):
        from docstrange.mcp_server.cache import ExtractionCache
        cache = ExtractionCache(maxsize=3)
        files = []
        for i in range(4):
            p = tmp_path / f"f{i}.png"
            p.write_bytes(b"\x89PNG" + bytes([i]) * 20)
            files.append(str(p))

        # Fill cache with f0, f1, f2
        for f in files[:3]:
            cache.put(f, None, f"result_{f}")
        assert len(cache) == 3

        # Access f0 to make f1 the LRU
        cache.get(files[0], None)

        # Insert f3 — f1 (LRU) should be evicted, not f0
        cache.put(files[3], None, "result_f3")
        assert len(cache) == 3
        assert cache.get(files[1], None) is None   # evicted
        assert cache.get(files[0], None) is not None  # still present

    def test_extractors_tuple_is_part_of_key(self, tmp_png):
        from docstrange.mcp_server.cache import ExtractionCache
        cache = ExtractionCache(maxsize=5)
        cache.put(tmp_png, ["dimensions"], "dims_result")
        cache.put(tmp_png, ["notes"], "notes_result")
        assert cache.get(tmp_png, ["dimensions"]) == "dims_result"
        assert cache.get(tmp_png, ["notes"]) == "notes_result"
        assert cache.get(tmp_png, None) is None

    def test_cache_hit_in_server(self, server, tmp_png):
        """Second call to _extract() should use cache, not re-invoke pipeline."""
        server._extract(tmp_png)
        server._extract(tmp_png)
        assert server._pipeline.extract_from_image.call_count == 1
