"""Bill of Materials (BOM) extractor for engineering drawings."""

import re
from typing import Dict, List, Optional, Tuple

from .base import BaseExtractor

_BOM_HEADER = re.compile(r'\b(BILL\s+OF\s+MATERIALS?|BOM|PARTS?\s+LIST)\b', re.I)

_COLUMN_MAP: Dict[str, re.Pattern] = {
    "item": re.compile(r'\b(ITEM|NO\.?|#)\b', re.I),
    "qty": re.compile(r'\b(QTY|QUANTITY|NO\.\s*REQ)\b', re.I),
    "part_number": re.compile(r'\b(PART\s*NO\.?|P/?N|PART\s*#)\b', re.I),
    "description": re.compile(r'\b(DESCRIPTION|DESC\.?|NAME)\b', re.I),
    "material": re.compile(r'\b(MATERIAL|MAT\.?)\b', re.I),
}


def _row_key(el) -> float:
    """Round y to nearest 10px bucket for row grouping."""
    return round(float(el.y) / 10) * 10


def _group_into_rows(elements: List) -> List[List]:
    """Cluster elements that share the same y-bucket into rows, sorted by x."""
    from collections import defaultdict
    buckets: Dict[float, list] = defaultdict(list)
    for el in elements:
        buckets[_row_key(el)].append(el)
    rows = []
    for key in sorted(buckets):
        row = sorted(buckets[key], key=lambda e: float(e.x))
        rows.append(row)
    return rows


def _infer_column_order(header_row: List) -> Dict[int, str]:
    """Map column index → field name from the header row."""
    mapping: Dict[int, str] = {}
    for idx, el in enumerate(header_row):
        text = (el.text or '').strip()
        for field, pattern in _COLUMN_MAP.items():
            if pattern.search(text):
                mapping[idx] = field
                break
    return mapping


class BOMExtractor(BaseExtractor):
    """Extracts Bill of Materials tables from engineering drawings."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import BOMRow

        if not elements:
            return []

        sorted_els = sorted(
            (e for e in elements if e.text and e.text.strip()),
            key=lambda e: (e.y, e.x),
        )

        # Find the BOM header element
        header_idx = None
        header_el = None
        for i, el in enumerate(sorted_els):
            if _BOM_HEADER.search(el.text or ''):
                header_idx = i
                header_el = el
                break

        if header_el is None:
            return []

        # Collect elements below the header with similar x-range
        hx1, hx2 = float(header_el.x), float(header_el.x) + float(header_el.width)
        x_margin = max(float(header_el.width) * 3, 200)  # generous margin
        body_els = [
            el for el in sorted_els[header_idx + 1:]
            if float(el.y) > float(header_el.y)
            and float(el.x) < hx2 + x_margin
        ]

        if not body_els:
            return []

        rows = _group_into_rows(body_els)
        if not rows:
            return []

        # First row is assumed to be column headers
        col_map = _infer_column_order(rows[0])
        has_mapping = bool(col_map)

        bom_rows = []
        data_rows = rows[1:] if has_mapping else rows
        avg_conf = sum(float(getattr(e, 'confidence', 0.8)) for e in body_els) / max(len(body_els), 1)
        mult = 1.0 if has_mapping else 0.75

        for row_els in data_rows:
            cells = [el.text.strip() for el in row_els]
            if not any(cells):
                continue

            kwargs: Dict = {"raw_cells": cells}
            for idx, field in col_map.items():
                if idx < len(cells):
                    kwargs[field] = cells[idx]

            # Use bbox of the leftmost cell in the row for position
            bbox = self._to_bbox(row_els[0]) if row_els else self._to_bbox(header_el)
            bom_rows.append(BOMRow(
                confidence=min(avg_conf * mult, 1.0),
                bbox=bbox,
                **{k: v for k, v in kwargs.items() if k in
                   {"item_number", "quantity", "part_number", "description", "material", "raw_cells"}},
            ))

        return bom_rows
