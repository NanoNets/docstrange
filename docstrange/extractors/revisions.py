"""Revision block extractor for engineering drawings."""

import re
from typing import Dict, List, Optional

from .base import BaseExtractor

_REV_HEADER = re.compile(
    r'\b(REV(?:ISION)?\s*(?:HISTORY|BLOCK|TABLE)?|CHANGE\s*LOG)\b', re.I
)
_REV_LETTER = re.compile(r'(?<!\w)([A-Z])(?!\w)')
_DATE_PATTERN = re.compile(
    r'\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{2}[/\-.]\d{2})\b'
)
_APPROVER_HINT = re.compile(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b')  # First Last format


def _row_key(el) -> float:
    return round(float(el.y) / 10) * 10


def _group_into_rows(elements: List) -> List[List]:
    from collections import defaultdict
    buckets: Dict[float, list] = defaultdict(list)
    for el in elements:
        buckets[_row_key(el)].append(el)
    rows = []
    for key in sorted(buckets):
        rows.append(sorted(buckets[key], key=lambda e: float(e.x)))
    return rows


def _parse_row(cells: List[str]) -> Dict[str, Optional[str]]:
    """Heuristically infer which cell is revision / date / description / approver."""
    result: Dict[str, Optional[str]] = {
        "revision": None, "date": None, "description": None, "approved_by": None,
    }
    for cell in cells:
        cell = cell.strip()
        if not cell:
            continue
        if result["date"] is None and _DATE_PATTERN.search(cell):
            result["date"] = cell
        elif result["revision"] is None and _REV_LETTER.fullmatch(cell):
            result["revision"] = cell
        elif result["approved_by"] is None and _APPROVER_HINT.search(cell) and len(cell) < 30:
            result["approved_by"] = cell
        elif result["description"] is None:
            result["description"] = cell
    return result


class RevisionExtractor(BaseExtractor):
    """Extracts revision block entries from engineering drawings."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import RevisionEntry

        if not elements:
            return []

        sorted_els = sorted(
            (e for e in elements if e.text and e.text.strip()),
            key=lambda e: (e.y, e.x),
        )

        # Find revision block header
        header_el = None
        header_idx = None
        for i, el in enumerate(sorted_els):
            if _REV_HEADER.search(el.text or ''):
                header_el = el
                header_idx = i
                break

        if header_el is None:
            return []

        # Collect elements below the header
        body_els = [
            el for el in sorted_els[header_idx + 1:]
            if float(el.y) > float(header_el.y)
        ]

        if not body_els:
            return []

        rows = _group_into_rows(body_els)
        avg_conf = sum(float(getattr(e, 'confidence', 0.8)) for e in body_els) / max(len(body_els), 1)
        results = []

        for row_els in rows:
            cells = [el.text.strip() for el in row_els]
            if not any(cells):
                continue
            parsed = _parse_row(cells)
            bbox = self._to_bbox(row_els[0]) if row_els else self._to_bbox(header_el)
            results.append(RevisionEntry(
                revision=parsed["revision"],
                date=parsed["date"],
                description=parsed["description"],
                approved_by=parsed["approved_by"],
                confidence=min(avg_conf, 1.0),
                bbox=bbox,
            ))

        return results
