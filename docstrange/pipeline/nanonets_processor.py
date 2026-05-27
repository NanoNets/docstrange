"""Neural Document Processor using Nanonets OCR for superior document understanding."""

import logging
import os
from typing import Optional
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)


class NanonetsDocumentProcessor:
    """Neural Document Processor using Nanonets OCR model."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the Neural Document Processor with Nanonets OCR."""
        logger.info("Initializing Neural Document Processor with Nanonets OCR...")
        
        # Initialize models
        self._initialize_models(cache_dir)
        
        logger.info("Neural Document Processor initialized successfully")
    
    def _initialize_models(self, cache_dir: Optional[Path] = None):
        """Initialize Nanonets OCR model from local cache."""
        try:
            from transformers import AutoTokenizer, AutoProcessor, AutoModelForImageTextToText
            from .model_downloader import ModelDownloader
            
            # Get model downloader instance
            model_downloader = ModelDownloader(cache_dir)
            
            # Get the path to the locally cached Nanonets model
            model_path = model_downloader.get_model_path('nanonets-ocr')
            
            if model_path is None:
                raise RuntimeError(
                        "Failed to download Nanonets OCR model. "
                        "Please ensure you have sufficient disk space and internet connection."
                    )
            
            # The actual model files are in a subdirectory with the same name
            actual_model_path = model_path / "Nanonets-OCR-ss"
            
            if not actual_model_path.exists():
                raise RuntimeError(
                    f"Model files not found at expected path: {actual_model_path}"
                )
            
            logger.info(f"Loading Nanonets OCR model from local cache: {actual_model_path}")
            
            # Load model from local path
            self.model = AutoModelForImageTextToText.from_pretrained(
                str(actual_model_path), 
                torch_dtype="auto", 
                device_map="auto", 
                local_files_only=True  # Use only local files
            )
            self.model.eval()
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(actual_model_path),
                local_files_only=True
            )
            self.processor = AutoProcessor.from_pretrained(
                str(actual_model_path),
                local_files_only=True
            )
            
            logger.info("Nanonets OCR model loaded successfully from local cache")
            
        except ImportError as e:
            logger.error(f"Transformers library not available: {e}")
            raise ImportError(
                "Transformers library is required for Nanonets OCR. "
                "Please install it: pip install transformers"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Nanonets OCR model: {e}")
            raise
    
    def extract_text(self, image_path: str) -> str:
        """Extract text from image using Nanonets OCR."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file does not exist: {image_path}")
                return ""
            
            return self._extract_text_with_nanonets(image_path)
                
        except Exception as e:
            logger.error(f"Nanonets OCR extraction failed: {e}")
            return ""
    
    def extract_text_with_layout(self, image_path: str) -> str:
        """Extract text with layout awareness using Nanonets OCR.
        
        Note: Nanonets OCR already provides layout-aware extraction,
        so this method returns the same result as extract_text().
        """
        return self.extract_text(image_path)
    
    def _extract_text_with_nanonets(self, image_path: str, max_new_tokens: int = 4096) -> str:
        """Extract text using Nanonets OCR model."""
        try:
            prompt = """Extract the text from the above document as if you were reading it naturally. Return the tables in html format. Return the equations in LaTeX representation. If there is an image in the document and image caption is not present, add a small description of the image inside the <img></img> tag; otherwise, add the image caption inside <img></img>. Watermarks should be wrapped in brackets. Ex: <watermark>OFFICIAL COPY</watermark>. Page numbers should be wrapped in brackets. Ex: <page_number>14</page_number> or <page_number>9/22</page_number>. Prefer using ☐ and ☑ for check boxes."""
            
            image = Image.open(image_path)
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": [
                    {"type": "image", "image": f"file://{image_path}"},
                    {"type": "text", "text": prompt},
                ]},
            ]
            
            text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.processor(text=[text], images=[image], padding=True, return_tensors="pt")
            inputs = inputs.to(self.model.device)
            
            output_ids = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
            generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, output_ids)]
            
            output_text = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True)
            return output_text[0]
            
        except Exception as e:
            logger.error(f"Nanonets OCR extraction failed: {e}")
            return ""
    
    def extract_layout_elements(self, image_path: str) -> List:
        """Return line-level LayoutElements derived from the Nanonets OCR text output.

        The Nanonets transformer returns structured text (not positional data), so
        we synthesise spatial coordinates by distributing lines across the image
        height.  This gives downstream extractors sequential order and approximate
        y-positions suitable for zone heuristics (title block region, notes section,
        etc.).
        """
        from .layout_detector import LayoutElement

        text = self.extract_text(image_path)
        if not text:
            return []

        try:
            with Image.open(image_path) as img:
                img_w, img_h = img.size
        except Exception:
            img_w, img_h = 1000, 1400  # A4-like fallback

        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            return []

        line_height = max(img_h / len(lines), 15)
        elements = []
        for idx, line in enumerate(lines):
            elements.append(LayoutElement(
                text=line,
                x=0,
                y=int(idx * line_height),
                width=img_w,
                height=int(line_height),
                element_type="paragraph",
                confidence=0.8,
            ))
        return elements

    def __del__(self):
        """Cleanup resources."""
        pass