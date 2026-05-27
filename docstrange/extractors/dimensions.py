"""Dimension extractor for engineering drawings."""

import re
from typing import List, Optional, Tuple

from .base import BaseExtractor


# Compiled at class level — do not duplicate inside methods
_LINEAR = re.compile(
    r'([+\-]?\d+\.?\d*)\s*'
    r'(?:±\s*(\d+\.?\d*)'         # ±tolerance
    r'|([+\-]\d+\.?\d*)/([+\-]\d+\.?\d*))?'  # bilateral +x/-y
    r'\s*(mm|in|")?',
    re.IGNORECASE,
)
_DIAMETER = re.compile(r'[⌀Ø]\s*(\d+\.?\d*)', re.IGNORECASE)
_DIAMETER_TEXT = re.compile(r'\bDIA\.?\s+(\d+\.?\d*)', re.IGNORECASE)
_ANGULAR = re.compile(r'(\d+\.?\d*)\s*(?:°|DEG\.?)', re.IGNORECASE)
_RADIAL = re.compile(r'\bR\s*(\d+\.?\d*)\b', re.IGNORECASE)
# Reject: pure part numbers, long digit strings without units
_PART_NUMBER = re.compile(r'^\s*[A-Z]{0,4}\d{6,}\s*$')
_DIMENSION_GUARD = re.compile(r'\d')


class DimensionExtractor(BaseExtractor):
    """Extracts dimension annotations from engineering drawing layout elements."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import DimensionElement
        results = []
        for el in elements:
            if getattr(el, 'element_type', '') == 'picture':
                continue
            text = (el.text or '').strip()
            if not text or not _DIMENSION_GUARD.search(text):
                continue
            if _PART_NUMBER.match(text):
                continue

            found = self._parse(text, el)
            results.extend(found)
        return results

    def _parse(self, text: str, el) -> List:
        from ..schemas.engineering import DimensionElement
        results = []

        # Diameter (⌀ prefix takes priority)
        for m in _DIAMETER.finditer(text):
            results.append(DimensionElement(
                text=m.group(0),
                nominal=float(m.group(1)),
                dimension_type="diameter",
                confidence=self._confidence(el, 1.0),
                bbox=self._to_bbox(el),
            ))

        for m in _DIAMETER_TEXT.finditer(text):
            results.append(DimensionElement(
                text=m.group(0),
                nominal=float(m.group(1)),
                dimension_type="diameter",
                confidence=self._confidence(el, 0.95),
                bbox=self._to_bbox(el),
            ))

        # Angular
        for m in _ANGULAR.finditer(text):
            results.append(DimensionElement(
                text=m.group(0),
                nominal=float(m.group(1)),
                dimension_type="angular",
                unit="deg",
                confidence=self._confidence(el, 1.0),
                bbox=self._to_bbox(el),
            ))

        # Radial
        for m in _RADIAL.finditer(text):
            results.append(DimensionElement(
                text=m.group(0),
                nominal=float(m.group(1)),
                dimension_type="radial",
                confidence=self._confidence(el, 1.0),
                bbox=self._to_bbox(el),
            ))

        # Linear (only if no specialised type already matched this token)
        matched_spans = {r.text for r in results}
        for m in _LINEAR.finditer(text):
            raw = m.group(0).strip()
            if not raw or raw in matched_spans:
                continue
            nominal_str = m.group(1)
            if not nominal_str:
                continue
            try:
                nominal = float(nominal_str)
            except ValueError:
                continue
            # Skip very large integers that look like dates/serial numbers
            if nominal > 9999 and not m.group(5):
                continue

            upper_tol = lower_tol = None
            multiplier = 0.8  # partial match default

            if m.group(2):  # ± symmetric tolerance
                try:
                    t = float(m.group(2))
                    upper_tol = t
                    lower_tol = -t
                    multiplier = 1.0
                except ValueError:
                    pass
            elif m.group(3) and m.group(4):  # bilateral
                try:
                    upper_tol = float(m.group(3))
                    lower_tol = float(m.group(4))
                    multiplier = 1.0
                except ValueError:
                    pass

            unit = m.group(5) or None
            if unit == '"':
                unit = 'in'

            results.append(DimensionElement(
                text=raw,
                nominal=nominal,
                upper_tolerance=upper_tol,
                lower_tolerance=lower_tol,
                unit=unit,
                dimension_type="linear",
                confidence=self._confidence(el, multiplier),
                bbox=self._to_bbox(el),
            ))

        return results
