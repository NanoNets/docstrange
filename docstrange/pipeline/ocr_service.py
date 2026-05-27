"""OCR Service abstraction for neural document processing."""

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class OCRService(ABC):
    """Abstract base class for OCR services."""

    @abstractmethod
    def extract_text(self, image_path: str) -> str:
        """Extract plain text from an image file."""
        pass

    @abstractmethod
    def extract_text_with_layout(self, image_path: str) -> str:
        """Extract text with layout-aware markdown from an image file."""
        pass

    @abstractmethod
    def extract_layout_elements(self, image_path: str) -> List:
        """Return LayoutElement objects (text + bbox + confidence) for an image.

        This is the primary entry point for engineering drawing extraction — every
        element must carry accurate positional data so extractors can apply zone
        heuristics (title block region, BOM table area, etc.).
        """
        pass

    # ------------------------------------------------------------------
    # Shared validation helper
    # ------------------------------------------------------------------

    def _validate_image(self, image_path: str) -> bool:
        if not os.path.exists(image_path):
            logger.error("Image not found: %s", image_path)
            return False
        return True


class NanonetsOCRService(OCRService):
    """OCR service backed by NanonetsDocumentProcessor (transformer model)."""

    def __init__(self):
        from .nanonets_processor import NanonetsDocumentProcessor
        self._processor = NanonetsDocumentProcessor()

    # Properties kept for callers that inspect the underlying model objects
    @property
    def model(self):
        return self._processor.model

    @property
    def processor(self):
        return self._processor.processor

    @property
    def tokenizer(self):
        return self._processor.tokenizer

    def extract_text(self, image_path: str) -> str:
        if not self._validate_image(image_path):
            return ""
        try:
            return self._processor.extract_text(image_path).strip()
        except Exception as e:
            logger.error("NanonetsOCRService.extract_text failed: %s", e)
            return ""

    def extract_text_with_layout(self, image_path: str) -> str:
        if not self._validate_image(image_path):
            return ""
        try:
            return self._processor.extract_text_with_layout(image_path).strip()
        except Exception as e:
            logger.error("NanonetsOCRService.extract_text_with_layout failed: %s", e)
            return ""

    def extract_layout_elements(self, image_path: str) -> List:
        if not self._validate_image(image_path):
            return []
        try:
            return self._processor.extract_layout_elements(image_path)
        except Exception as e:
            logger.error("NanonetsOCRService.extract_layout_elements failed: %s", e)
            return []


class NeuralOCRService(OCRService):
    """OCR service backed by NeuralDocumentProcessor (docling + EasyOCR)."""

    def __init__(self):
        from .neural_document_processor import NeuralDocumentProcessor
        self._processor = NeuralDocumentProcessor()

    def extract_text(self, image_path: str) -> str:
        if not self._validate_image(image_path):
            return ""
        try:
            return self._processor.extract_text(image_path).strip()
        except Exception as e:
            logger.error("NeuralOCRService.extract_text failed: %s", e)
            return ""

    def extract_text_with_layout(self, image_path: str) -> str:
        if not self._validate_image(image_path):
            return ""
        try:
            return self._processor.extract_text_with_layout(image_path).strip()
        except Exception as e:
            logger.error("NeuralOCRService.extract_text_with_layout failed: %s", e)
            return ""

    def extract_layout_elements(self, image_path: str) -> List:
        if not self._validate_image(image_path):
            return []
        try:
            return self._processor.extract_layout_elements(image_path)
        except Exception as e:
            logger.error("NeuralOCRService.extract_layout_elements failed: %s", e)
            return []


class OCRServiceFactory:
    """Creates OCR service instances with automatic provider fallback."""

    _PROVIDERS = {
        "nanonets": NanonetsOCRService,
        "neural":   NeuralOCRService,
    }

    @staticmethod
    def create_service(provider: Optional[str] = None) -> OCRService:
        """Instantiate the requested provider; fall back to the other if it fails.

        Args:
            provider: ``"nanonets"`` or ``"neural"``. Defaults to
                ``InternalConfig.ocr_provider`` (which defaults to ``"nanonets"``).
        """
        from docstrange.config import InternalConfig

        preferred = (provider or getattr(InternalConfig, "ocr_provider", "nanonets")).lower()
        # Build a try-order: preferred first, then the other option
        order = [preferred] + [p for p in ("nanonets", "neural") if p != preferred]

        last_error: Optional[Exception] = None
        for name in order:
            cls = OCRServiceFactory._PROVIDERS.get(name)
            if cls is None:
                logger.warning("Unknown OCR provider '%s', skipping.", name)
                continue
            try:
                service = cls()
                if name != preferred:
                    logger.info("OCR provider '%s' unavailable; using '%s' instead.", preferred, name)
                return service
            except Exception as exc:
                logger.warning("OCR provider '%s' failed to initialise: %s", name, exc)
                last_error = exc

        raise RuntimeError(
            f"All OCR providers failed to initialise. Last error: {last_error}"
        )

    @staticmethod
    def get_available_providers() -> List[str]:
        return list(OCRServiceFactory._PROVIDERS.keys())
