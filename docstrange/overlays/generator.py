"""Overlay JSON generator for UI rendering of engineering drawing extractions."""

from typing import Any, Dict, List, Optional


_COLOR_MAP: Dict[str, str] = {
    "dimension":   "#FF6B35",
    "title_block": "#2196F3",
    "note":        "#4CAF50",
    "gdt":         "#9C27B0",
    "bom":         "#FF9800",
    "revision":    "#607D8B",
    "unknown":     "#9E9E9E",
}


def _normalize_bbox(x: float, y: float, w: float, h: float, img_w: int, img_h: int) -> Dict:
    def _clamp(v: float) -> float:
        return max(0.0, min(1.0, v))

    if img_w and img_h:
        return {
            "x":      _clamp(round(x / img_w, 4)),
            "y":      _clamp(round(y / img_h, 4)),
            "width":  _clamp(round(w / img_w, 4)),
            "height": _clamp(round(h / img_h, 4)),
        }
    # Skip normalisation when dimensions are unknown
    return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}


def _annotation_from_element(el, img_w: int, img_h: int, seq: int) -> Dict[str, Any]:
    """Build one overlay annotation from any extracted element.

    Works with ExtractionElement subclasses (DimensionElement, TitleBlockField,
    NoteElement, GDTElement) and with BOMRow / RevisionEntry — all carry .text,
    .type, .confidence, .bbox, and .page after Phase 2.

    ``seq`` is the 1-based position in the final annotation list; it produces a
    stable ``change_id`` (``chg_001`` etc.) that is consistent across re-runs
    for the same extraction result ordering.
    """
    annotation_type = str(getattr(el, "type", "unknown"))
    bbox = el.bbox
    text = str(getattr(el, "text", ""))
    bbox_pixels = {
        "x":      float(bbox.x),
        "y":      float(bbox.y),
        "width":  float(bbox.width),
        "height": float(bbox.height),
    }
    return {
        "change_id":       f"chg_{seq:03d}",
        "type":            annotation_type,
        "text":            text,
        "page":            int(getattr(el, "page", 1)),
        "confidence":      round(float(el.confidence), 4),
        "bbox":            bbox_pixels,
        "bbox_normalized": _normalize_bbox(
            bbox.x, bbox.y, bbox.width, bbox.height, img_w, img_h
        ),
        "color":           _COLOR_MAP.get(annotation_type, _COLOR_MAP["unknown"]),
        "label":           text[:60],
    }


def _auto_image_size(image_path: str):
    """Return (width, height) from image file, or (0, 0) on failure."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.width, img.height
    except Exception:
        return 0, 0


class OverlayGenerator:
    """Converts EngineeringDrawingResult into a UI-renderable overlay JSON structure.

    Each annotation carries both pixel and normalised (0–1) bounding boxes so the
    consumer can render at any resolution.  Pass ``page`` to filter to a single PDF
    page; omit it to include all pages in one payload.
    """

    def generate(
        self,
        result,
        image_width: int = 0,
        image_height: int = 0,
        image_path: Optional[str] = None,
        page: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return the overlay dict.

        Args:
            result: :class:`EngineeringDrawingResult` instance.
            image_width: Pixel width of the source image. 0 → auto-detect or skip.
            image_height: Pixel height of the source image.
            image_path: Optional path used to auto-detect dimensions when
                ``image_width``/``image_height`` are both 0.
            page: If set, only annotations from this PDF page are included.
        """
        if image_width == 0 and image_height == 0 and image_path:
            image_width, image_height = _auto_image_size(image_path)

        all_elements = (
            list(result.title_block)
            + list(result.dimensions)
            + list(result.notes)
            + list(result.gdt)
            + list(result.bom)
            + list(result.revisions)
        )

        annotations: List[Dict] = []
        seq = 0
        for el in all_elements:
            if page is not None and int(getattr(el, "page", 1)) != page:
                continue
            seq += 1
            annotations.append(_annotation_from_element(el, image_width, image_height, seq))

        by_type: Dict[str, int] = {}
        for ann in annotations:
            by_type[ann["type"]] = by_type.get(ann["type"], 0) + 1

        return {
            "image_size":        {"width": image_width, "height": image_height},
            "page_filter":       page,
            "total_annotations": len(annotations),
            "summary":           {"by_type": by_type, "total": len(annotations)},
            "annotations":       annotations,
        }
