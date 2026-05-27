"""Notes extractor for engineering drawings."""

import re
from typing import List, Optional

from .base import BaseExtractor

_NOTE_HEADER = re.compile(r'\b(GENERAL\s*NOTES?|NOTES?:?)\b', re.I)
_NUMBERED = re.compile(r'^\s*(\d+)\.\s+(.+)', re.DOTALL)
_CONTINUATION = re.compile(r'^\s{2,}')


class NoteExtractor(BaseExtractor):
    """Extracts notes and annotations from engineering drawings."""

    def extract(self, elements: List) -> List:
        from ..schemas.engineering import NoteElement

        results = []
        in_notes_section = False
        sorted_els = sorted(
            (e for e in elements if e.text and e.text.strip()),
            key=lambda e: (e.y, e.x),
        )

        for el in sorted_els:
            text = el.text.strip()

            # Detect notes section header
            if _NOTE_HEADER.search(text):
                in_notes_section = True
                # Don't emit the header itself as a note
                continue

            if in_notes_section:
                m = _NUMBERED.match(text)
                if m:
                    results.append(NoteElement(
                        text=text,
                        note_number=int(m.group(1)),
                        is_general=False,
                        confidence=self._confidence(el, 1.0),
                        bbox=self._to_bbox(el),
                    ))
                elif _CONTINUATION.match(el.text):
                    # Indented continuation — attach to last note or emit as general
                    if results:
                        # Merge into the last note's text (keep bbox of last note)
                        last = results[-1]
                        results[-1] = NoteElement(
                            text=last.text + " " + text,
                            note_number=last.note_number,
                            is_general=last.is_general,
                            confidence=last.confidence,
                            bbox=last.bbox,
                        )
                    else:
                        results.append(NoteElement(
                            text=text,
                            is_general=True,
                            confidence=self._confidence(el, 0.85),
                            bbox=self._to_bbox(el),
                        ))
                else:
                    # Non-numbered, non-indented — possible general note line
                    results.append(NoteElement(
                        text=text,
                        is_general=True,
                        confidence=self._confidence(el, 0.8),
                        bbox=self._to_bbox(el),
                    ))
                    # A clearly unrelated heading or separator ends the section
                    if len(text) < 4 or text.isupper() and not any(c.isdigit() for c in text):
                        in_notes_section = False

        return results
