#!/usr/bin/env python3
"""Engineering Drawing Extraction MCP Server powered by DocStrange."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .cache import ExtractionCache
from .tools import TOOLS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class EngineeringMCPServer:
    """MCP Server exposing DocStrange engineering drawing extraction tools.

    Architecture
    ------------
    - Tool definitions live in ``tools.py`` (schema registry)
    - Caching lives in ``cache.py`` (LRU, stat-based key)
    - This file owns server lifecycle, validation, and dispatch routing
    """

    def __init__(self) -> None:
        self.server = Server("docstrange-engineering")
        self._pipeline = None
        self._overlay_gen = None
        self._cache = ExtractionCache(maxsize=20)
        self._setup_handlers()

    # ------------------------------------------------------------------
    # Lazy singletons
    # ------------------------------------------------------------------

    def _get_pipeline(self):
        if self._pipeline is None:
            logger.info("Initialising EngineeringDrawingPipeline…")
            from ..pipelines.engineering import EngineeringDrawingPipeline
            self._pipeline = EngineeringDrawingPipeline()
        return self._pipeline

    def _get_overlay_generator(self):
        if self._overlay_gen is None:
            from ..overlays.generator import OverlayGenerator
            self._overlay_gen = OverlayGenerator()
        return self._overlay_gen

    # ------------------------------------------------------------------
    # Core extraction (validation + cache)
    # ------------------------------------------------------------------

    def _extract(self, file_path: str, extractors: Optional[List[str]] = None):
        """Validate, cache-check, and run extraction."""
        path = Path(file_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a regular file: {file_path}")

        ext = path.suffix.lower()
        if ext not in _ALLOWED_EXT:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXT)}"
            )

        cached = self._cache.get(str(path), extractors)
        if cached is not None:
            logger.debug("Cache hit: %s", path.name)
            return cached

        pipeline = self._get_pipeline()
        if ext == ".pdf":
            result = pipeline.extract_from_pdf(str(path), extractors=extractors)
        else:
            result = pipeline.extract_from_image(str(path), extractors=extractors)

        self._cache.put(str(path), extractors, result)
        return result

    # ------------------------------------------------------------------
    # MCP handler registration
    # ------------------------------------------------------------------

    def _setup_handlers(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return TOOLS

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            return await self._dispatch(name, arguments)

    # ------------------------------------------------------------------
    # Dispatch routing
    # ------------------------------------------------------------------

    async def _dispatch(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        file_path = arguments.get("file_path", "")

        # Helper: convert 0-sentinel to None for page filtering
        raw_page = arguments.get("page", 0)
        page: Optional[int] = int(raw_page) if raw_page else None

        try:
            return await self._dispatch_inner(name, arguments, file_path, page)
        except (FileNotFoundError, ValueError) as exc:
            return [TextContent(
                type="text",
                text=json.dumps({"status": "error", "error": str(exc)}, indent=2),
            )]
        except Exception as exc:
            logger.error("Tool '%s' failed: %s", name, exc, exc_info=True)
            return [TextContent(
                type="text",
                text=json.dumps({"status": "error", "error": "Internal error. Check server logs."}, indent=2),
            )]

    async def _dispatch_inner(
        self, name: str, arguments: Dict[str, Any], file_path: str, page: Optional[int]
    ) -> List[TextContent]:
        if name == "extract_dimensions":
            result = self._extract(file_path, extractors=["dimensions"])
            data = [el.model_dump() for el in result.dimensions]

        elif name == "extract_title_block":
            result = self._extract(file_path, extractors=["title_block"])
            data = [el.model_dump() for el in result.title_block]

        elif name == "extract_notes":
            result = self._extract(file_path, extractors=["notes"])
            data = [el.model_dump() for el in result.notes]

        elif name == "extract_gdt":
            result = self._extract(file_path, extractors=["gdt"])
            data = [el.model_dump() for el in result.gdt]

        elif name == "extract_bom":
            result = self._extract(file_path, extractors=["bom"])
            data = [row.model_dump() for row in result.bom]

        elif name == "extract_revisions":
            result = self._extract(file_path, extractors=["revisions"])
            data = [entry.model_dump() for entry in result.revisions]

        elif name == "extract_full":
            result = self._extract(file_path)
            data = result.model_dump()
            if arguments.get("include_overlays", False):
                gen = self._get_overlay_generator()
                data["overlay_json"] = gen.generate(
                    result,
                    image_width=arguments.get("image_width", 0),
                    image_height=arguments.get("image_height", 0),
                    image_path=file_path,
                    page=page,
                )

        elif name == "generate_overlays":
            result = self._extract(file_path)
            gen = self._get_overlay_generator()
            data = gen.generate(
                result,
                image_width=arguments.get("image_width", 0),
                image_height=arguments.get("image_height", 0),
                image_path=file_path,
                page=page,
            )

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"status": "error", "error": f"Unknown tool: {name}"}, indent=2),
            )]

        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                initialization_options=self.server.create_initialization_options(),
            )


async def main() -> None:
    server = EngineeringMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
