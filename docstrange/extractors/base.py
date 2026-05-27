"""Base extractor contract for all engineering drawing extractors."""

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipeline.layout_detector import LayoutElement
    from ..schemas.engineering import BBoxSchema, ExtractionElement


class BaseExtractor(ABC):
    """All domain extractors receive a flat List[LayoutElement] and return typed schema objects."""

    @abstractmethod
    def extract(self, elements: List["LayoutElement"]) -> list:
        pass

    def _to_bbox(self, el: "LayoutElement") -> "BBoxSchema":
        from ..schemas.engineering import BBoxSchema
        return BBoxSchema(x=float(el.x), y=float(el.y), width=float(el.width), height=float(el.height))

    def _confidence(self, el: "LayoutElement", multiplier: float = 1.0) -> float:
        return min(float(getattr(el, 'confidence', 0.8)) * multiplier, 1.0)
