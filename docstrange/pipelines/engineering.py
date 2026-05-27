"""Engineering drawing extraction pipeline orchestrator."""

import logging
import os
import tempfile
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EngineeringDrawingPipeline:
    """Orchestrates full engineering drawing extraction from an image or PDF.

    Usage::

        pipeline = EngineeringDrawingPipeline()
        result = pipeline.extract_from_pdf("drawing.pdf")
        print(result.model_dump())
    """

    _ALL_EXTRACTORS = ["title_block", "dimensions", "notes", "gdt", "bom", "revisions"]

    def __init__(self, ocr_service=None):
        from ..pipeline.ocr_service import OCRServiceFactory
        from ..extractors import (
            TitleBlockExtractor, DimensionExtractor, NoteExtractor,
            GDTExtractor, BOMExtractor, RevisionExtractor,
        )
        self._ocr = ocr_service or OCRServiceFactory.create_service()
        self._extractors: Dict = {
            "title_block": TitleBlockExtractor(),
            "dimensions": DimensionExtractor(),
            "notes": NoteExtractor(),
            "gdt": GDTExtractor(),
            "bom": BOMExtractor(),
            "revisions": RevisionExtractor(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_from_image(
        self,
        image_path: str,
        extractors: Optional[List[str]] = None,
    ):
        """Run selected (or all) extractors on a single image file.

        Returns an :class:`EngineeringDrawingResult`.
        """
        from ..schemas.engineering import EngineeringDrawingResult

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        elements = self._get_layout_elements(image_path)
        return self._run_extractors(elements, extractors, metadata={"source": image_path, "pages": 1})

    def extract_from_pdf(
        self,
        pdf_path: str,
        extractors: Optional[List[str]] = None,
    ):
        """Convert each PDF page to an image and run extraction, merging results.

        Returns an :class:`EngineeringDrawingResult`.
        """
        from ..schemas.engineering import EngineeringDrawingResult

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        images = self._pdf_to_images(pdf_path)
        if not images:
            logger.warning(f"No pages extracted from PDF: {pdf_path}")
            return EngineeringDrawingResult(metadata={"source": pdf_path, "pages": 0})

        page_results = []
        for page_num, img_path in enumerate(images, start=1):
            try:
                elements = self._get_layout_elements(img_path)
                result = self._run_extractors(
                    elements, extractors,
                    metadata={"source": pdf_path, "page": page_num},
                )
                page_results.append(result)
            except Exception as e:
                logger.error(f"Failed to process page {page_num}: {e}")
            finally:
                try:
                    os.unlink(img_path)
                except OSError:
                    pass

        return self._merge_page_results(page_results, metadata={"source": pdf_path, "pages": len(images)})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_layout_elements(self, image_path: str) -> List:
        return self._ocr.extract_layout_elements(image_path)

    def _run_extractors(self, elements: List, extractors: Optional[List[str]], metadata: dict):
        from ..schemas.engineering import EngineeringDrawingResult

        names = extractors if extractors else self._ALL_EXTRACTORS
        page_num = metadata.get("page", 1)
        kwargs: Dict[str, list] = {}

        for name in names:
            extractor = self._extractors.get(name)
            if extractor is None:
                logger.warning(f"Unknown extractor: {name}")
                continue
            try:
                items = extractor.extract(elements)
            except Exception as e:
                logger.error(f"Extractor '{name}' failed: {e}")
                items = []
            # Stamp the source page on every element for multi-page traceability
            for item in items:
                item.page = page_num
            kwargs[name] = items  # type: ignore[assignment]

        return EngineeringDrawingResult(metadata=metadata, **kwargs)

    def _merge_page_results(self, pages: List, metadata: dict):
        from ..schemas.engineering import EngineeringDrawingResult

        if not pages:
            return EngineeringDrawingResult(metadata=metadata)

        merged = EngineeringDrawingResult(metadata=metadata)
        merged.title_block = [item for p in pages for item in p.title_block]
        merged.dimensions = [item for p in pages for item in p.dimensions]
        merged.notes = [item for p in pages for item in p.notes]
        merged.gdt = [item for p in pages for item in p.gdt]
        merged.bom = [item for p in pages for item in p.bom]
        merged.revisions = [item for p in pages for item in p.revisions]
        return merged

    def _pdf_to_images(self, pdf_path: str) -> List[str]:
        """Convert PDF pages to temporary image files. Returns list of image paths."""
        try:
            from pdf2image import convert_from_path
        except ImportError:
            raise ImportError("pdf2image is required for PDF processing: pip install pdf2image")

        images = convert_from_path(pdf_path, dpi=300)
        paths = []
        for img in images:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(tmp.name, "PNG")
            tmp.close()
            paths.append(tmp.name)
        return paths
