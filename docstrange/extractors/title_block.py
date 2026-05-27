"""Title block extractor for engineering drawings."""

import re
from typing import List, Dict

from .base import BaseExtractor

_FIELD_KEYWORDS: Dict[str, re.Pattern] = {
    "drawing_number": re.compile(r'\b(DWG\.?\s*NO\.?|DRAWING\s*NO\.?|DOC\s*NO\.?)\b', re.I),
    "title": re.compile(r'\b(TITLE|PART\s*NAME)\b', re.I),
    "scale": re.compile(r'\bSCALE\b', re.I),
    "date": re.compile(r'\b(DATE|DRAWN)\b', re.I),
    "revision": re.compile(r'\b(REV\.?|REVISION)\b', re.I),
    "material": re.compile(r'\b(MATERIAL|MAT\.?)\b', re.I),
    "drawn_by": re.compile(r'\b(DRAWN\s*BY|DRN\.?\s*BY)\b', re.I),
    "approved_by": re.compile(r'\b(APPR\.?|APPROVED\s*BY)\b', re.I),
    "sheet": re.compile(r'\bSHEET\b', re.I),
    "tolerance": re.compile(r'\b(TOLERANCE|TOL\.?|UNLESS\s*OTHERWISE)\b', re.I),
    "company": re.compile(r'\b(COMPANY|ORGANIZATION|ORG)\b', re.I),
    "part_number": re.compile(r'\b(PART\s*NO\.?|P/N|PART\s*#)\b', re.I),
    "surface_finish": re.compile(r'\b(SURFACE\s*FINISH|FINISH)\b', re.I),
    "weight": re.compile(r'\bWEIGHT\b', re.I),
}


def _image_bounds(elements: List) -> tuple:
    """Return (max_x, max_y) across all elements to estimate image dimensions."""
    max_x = max_y = 1.0
    for el in elements:
        max_x = max(max_x, float(el.x) + float(el.width))
        max_y = max(max_y, float(el.y) + float(el.height))
    return max_x, max_y


def _in_title_block_zone(el, max_x: float, max_y: float) -> bool:
    """Title block heuristic: lower-right 35% × lower 20% of image."""
    return float(el.x) > 0.65 * max_x or float(el.y) > 0.80 * max_y


def _match_field(text: str):
    """Return (field_name, confidence_multiplier) or (None, 0)."""
    for field_name, pattern in _FIELD_KEYWORDS.items():
        if pattern.search(text):
            return field_name, 1.0
    return None, 0.0


def _avg_line_height(elements: List) -> float:
    heights = [float(el.height) for el in elements if float(el.height) > 0]
    return (sum(heights) / len(heights)) if heights else 20.0


class TitleBlockExtractor(BaseExtractor):
    """Extracts title block fields using zone heuristics and keyword matching."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import TitleBlockField

        if not elements:
            return []

        max_x, max_y = _image_bounds(elements)
        avg_h = _avg_line_height(elements)
        threshold = 1.5 * avg_h

        results = []
        # Filter to probable title block elements
        candidates = [el for el in elements if el.text and el.text.strip()]

        # Sort by position for stable pairing
        candidates_sorted = sorted(candidates, key=lambda e: (e.y, e.x))

        for i, el in enumerate(candidates_sorted):
            text = el.text.strip()
            in_zone = _in_title_block_zone(el, max_x, max_y)
            field_name, kw_mult = _match_field(text)

            if field_name:
                mult = 1.0 if in_zone else 0.6
                # Try to find a nearby value element (same row, slightly to the right)
                value_el = self._find_value_element(el, candidates_sorted, threshold)
                field_value = value_el.text.strip() if value_el else text

                results.append(TitleBlockField(
                    text=text,
                    field_name=field_name,
                    field_value=field_value,
                    confidence=self._confidence(el, mult),
                    bbox=self._to_bbox(el),
                ))
            elif in_zone and text:
                # Zone match without keyword — emit as "unknown" field
                results.append(TitleBlockField(
                    text=text,
                    field_name="unknown",
                    field_value=text,
                    confidence=self._confidence(el, 0.5),
                    bbox=self._to_bbox(el),
                ))

        return results

    def _find_value_element(self, label_el, candidates: List, threshold: float):
        """Find the element spatially adjacent to label_el (same row, to the right)."""
        lx, ly, lw, lh = float(label_el.x), float(label_el.y), float(label_el.width), float(label_el.height)
        for el in candidates:
            if el is label_el:
                continue
            ex, ey = float(el.x), float(el.y)
            # Same row: y-centers within threshold, to the right
            if abs(ey - ly) < threshold and ex > lx + lw * 0.5:
                return el
        return None
