"""GD&T (Geometric Dimensioning and Tolerancing) extractor for engineering drawings."""

import re
from typing import Dict, List, Optional

from .base import BaseExtractor

# Unicode GD&T symbols mapped to their names
_GDT_SYMBOL_MAP: Dict[str, str] = {
    "⊙": "position",
    "⊕": "position",
    "○": "roundness",
    "⌭": "cylindricity",
    "⌒": "profile_surface",
    "⌓": "profile_line",
    "∥": "parallelism",
    "⊥": "perpendicularity",
    "∠": "angularity",
    "⌒": "circularity",
    "⌤": "flatness",
    "↗": "circular_runout",
    "⌀": "diameter",
    "Ⓜ": "maximum_material_condition",
    "Ⓛ": "least_material_condition",
    "Ⓕ": "free_state",
    "Ⓟ": "projected_tolerance_zone",
}

# Text abbreviation fallbacks when OCR misses the symbol
_GDT_TEXT = re.compile(
    r'\b(PERP(?:ENDICULARITY)?|PAR(?:ALLELISM)?|POS(?:ITION)?'
    r'|FLAT(?:NESS)?|CYL(?:INDRICITY)?|ROUND(?:NESS)?'
    r'|CONC(?:ENTRICITY)?|SYM(?:METRY)?|ANG(?:ULARITY)?'
    r'|PROF(?:ILE)?|RUN(?:OUT)?|STR(?:AIGHTNESS)?|CIRC(?:ULARITY)?)'
    r'\s+(\d+\.?\d*)',
    re.IGNORECASE,
)

# Feature control frame: |symbol|tolerance|datum(s)|
_FEATURE_CTRL = re.compile(r'\|([^|\n]{1,20})\|([^|\n]{1,20})(?:\|([^|\n]{1,20}))?\|?')

# Numeric tolerance adjacent to a symbol
_TOLERANCE_VALUE = re.compile(r'(\d+\.?\d*)')

# Datum reference: isolated single uppercase letter (A–Z) not part of a longer word
_DATUM_REF = re.compile(r'(?<!\w)([A-Z])(?!\w)')

_ABBREV_TO_NAME = {
    "PERP": "perpendicularity", "PERPENDICULARITY": "perpendicularity",
    "PAR": "parallelism", "PARALLELISM": "parallelism",
    "POS": "position", "POSITION": "position",
    "FLAT": "flatness", "FLATNESS": "flatness",
    "CYL": "cylindricity", "CYLINDRICITY": "cylindricity",
    "ROUND": "roundness", "ROUNDNESS": "roundness",
    "CONC": "concentricity", "CONCENTRICITY": "concentricity",
    "SYM": "symmetry", "SYMMETRY": "symmetry",
    "ANG": "angularity", "ANGULARITY": "angularity",
    "PROF": "profile", "PROFILE": "profile",
    "RUN": "runout", "RUNOUT": "runout",
    "STR": "straightness", "STRAIGHTNESS": "straightness",
    "CIRC": "circularity", "CIRCULARITY": "circularity",
}


class GDTExtractor(BaseExtractor):
    """Extracts GD&T symbols, tolerances, and datum references."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import GDTElement

        results = []
        for el in elements:
            text = (el.text or '').strip()
            if not text:
                continue

            # Check for feature control frame pattern
            for m in _FEATURE_CTRL.finditer(text):
                raw_sym = m.group(1).strip()
                tol = m.group(2).strip()
                datum = m.group(3).strip() if m.group(3) else None
                symbol = self._resolve_symbol(raw_sym)
                if symbol:
                    results.append(GDTElement(
                        text=m.group(0),
                        symbol=symbol,
                        tolerance_value=tol or None,
                        datum_reference=datum,
                        confidence=self._confidence(el, 1.0),
                        bbox=self._to_bbox(el),
                    ))

            # Check for Unicode symbols
            for char, sym_name in _GDT_SYMBOL_MAP.items():
                if char in text:
                    tol = self._extract_tolerance(text)
                    datum = self._extract_datum(text)
                    results.append(GDTElement(
                        text=text,
                        symbol=sym_name,
                        tolerance_value=tol,
                        datum_reference=datum,
                        confidence=self._confidence(el, 0.95),
                        bbox=self._to_bbox(el),
                    ))
                    break  # one entry per element for unicode match

            # Check for text abbreviations
            for m in _GDT_TEXT.finditer(text):
                abbrev = m.group(1).upper()
                sym_name = _ABBREV_TO_NAME.get(abbrev, abbrev.lower())
                tol = m.group(2)
                datum = self._extract_datum(text)
                results.append(GDTElement(
                    text=m.group(0),
                    symbol=sym_name,
                    tolerance_value=tol,
                    datum_reference=datum,
                    confidence=self._confidence(el, 0.9),
                    bbox=self._to_bbox(el),
                ))

        return results

    def _resolve_symbol(self, raw: str) -> Optional[str]:
        for char, name in _GDT_SYMBOL_MAP.items():
            if char in raw:
                return name
        abbrev = raw.upper().split()[0] if raw.split() else raw.upper()
        return _ABBREV_TO_NAME.get(abbrev)

    def _extract_tolerance(self, text: str) -> Optional[str]:
        m = _TOLERANCE_VALUE.search(text)
        return m.group(1) if m else None

    def _extract_datum(self, text: str) -> Optional[str]:
        datums = _DATUM_REF.findall(text)
        return datums[0] if datums else None
