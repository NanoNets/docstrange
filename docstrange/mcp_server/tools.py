"""MCP tool definitions for the DocStrange Engineering Drawing server.

Keeping tool schemas in their own module means they can be read, tested, and
updated without touching server routing logic.
"""

from typing import List

from mcp.types import Tool

TOOLS: List[Tool] = [
    Tool(
        name="extract_dimensions",
        description=(
            "Extract dimension annotations (linear, angular, radial, diameter) "
            "from an engineering drawing PDF or image file. Returns structured JSON "
            "with text, type, confidence, bounding box, and page number for each entity."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file (PDF, PNG, JPG, TIFF, BMP).",
                },
                "page": {
                    "type": "integer",
                    "description": "1-based page number to extract from. 0 = all pages (default).",
                    "default": 0,
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_title_block",
        description=(
            "Extract title block fields (drawing number, title, scale, date, material, "
            "revision, drawn by, approved by, sheet, tolerance, company, part number) "
            "from an engineering drawing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_notes",
        description=(
            "Extract general notes and numbered annotations from an engineering drawing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_gdt",
        description=(
            "Extract GD&T (Geometric Dimensioning and Tolerancing) symbols, feature "
            "control frames, tolerance values, and datum references from an engineering drawing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_bom",
        description=(
            "Extract Bill of Materials (parts list) rows including item number, quantity, "
            "part number, description, and material columns."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_revisions",
        description=(
            "Extract revision history block entries including revision letter, date, "
            "description, and approver name."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="extract_full",
        description=(
            "Run all extractors and return the complete EngineeringDrawingResult containing "
            "title_block, dimensions, notes, gdt, bom, and revisions. Optionally include "
            "UI overlay JSON for frontend rendering."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
                "include_overlays": {
                    "type": "boolean",
                    "description": "Include overlay JSON for UI rendering.",
                    "default": False,
                },
                "image_width": {
                    "type": "integer",
                    "description": "Source image width in pixels for overlay normalisation. 0 = skip.",
                    "default": 0,
                },
                "image_height": {
                    "type": "integer",
                    "description": "Source image height in pixels for overlay normalisation. 0 = skip.",
                    "default": 0,
                },
                "page": {
                    "type": "integer",
                    "description": "Filter overlay annotations to this 1-based page number. 0 = all pages.",
                    "default": 0,
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="generate_overlays",
        description=(
            "Generate UI-ready overlay JSON from an engineering drawing. Each detected entity "
            "is annotated with normalised and pixel bounding boxes, colour-coded by type, "
            "and tagged with its source page number."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the drawing file.",
                },
                "image_width": {
                    "type": "integer",
                    "description": "Image width in pixels for coordinate normalisation. 0 = skip.",
                    "default": 0,
                },
                "image_height": {
                    "type": "integer",
                    "description": "Image height in pixels for coordinate normalisation. 0 = skip.",
                    "default": 0,
                },
                "page": {
                    "type": "integer",
                    "description": "Return annotations for this 1-based page number only. 0 = all pages.",
                    "default": 0,
                },
            },
            "required": ["file_path"],
        },
    ),
]
