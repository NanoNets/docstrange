"""Neural Document Processor using docling's pre-trained models for superior document understanding."""

import logging
import os
import platform
import sys
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from PIL import Image
import numpy as np

# macOS-specific NumPy compatibility fix
if platform.system() == "Darwin":
    try:
        import numpy as np
        # Check if we're on NumPy 2.x
        if hasattr(np, '__version__') and np.__version__.startswith('2'):
            # Set environment variable to use NumPy 1.x compatibility mode
            os.environ['NUMPY_EXPERIMENTAL_ARRAY_FUNCTION'] = '0'
            # Also set this for PyTorch compatibility
            os.environ['PYTORCH_NUMPY_COMPATIBILITY'] = '1'
            logger = logging.getLogger(__name__)
            logger.warning(
                "NumPy 2.x detected on macOS. This may cause compatibility issues. "
                "Consider downgrading to NumPy 1.x: pip install 'numpy<2.0.0'"
            )
    except ImportError:
        pass

# Runtime NumPy version check
def _check_numpy_version():
    """Check NumPy version and warn about compatibility issues."""
    try:
        import numpy as np
        version = np.__version__
        if version.startswith('2'):
            logger = logging.getLogger(__name__)
            logger.error(
                f"NumPy {version} detected. This library requires NumPy 1.x for compatibility "
                "with docling models. Please downgrade NumPy:\n"
                "pip install 'numpy<2.0.0'\n"
                "or\n"
                "pip install --upgrade llm-data-extractor"
            )
            if platform.system() == "Darwin":
                logger.error(
                    "On macOS, NumPy 2.x is known to cause crashes with PyTorch. "
                    "Downgrading to NumPy 1.x is strongly recommended."
                )
            return False
        return True
    except ImportError:
        return True

from .model_downloader import ModelDownloader
from .layout_detector import LayoutDetector

logger = logging.getLogger(__name__)


class NeuralDocumentProcessor:
    """Neural Document Processor using docling's pre-trained models."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the Neural Document Processor."""
        logger.info("Initializing Neural Document Processor...")
        
        # Check NumPy version compatibility
        if not _check_numpy_version():
            raise RuntimeError(
                "Incompatible NumPy version detected. Please downgrade to NumPy 1.x: "
                "pip install 'numpy<2.0.0'"
            )
        
        # Initialize model downloader
        self.model_downloader = ModelDownloader(cache_dir)
        
        # Initialize layout detector
        self.layout_detector = LayoutDetector()
        
        # Initialize models
        self._initialize_models()
        
        logger.info("Neural Document Processor initialized successfully")
    
    def _initialize_models(self):
        """Initialize all required models."""
        try:
            # Initialize model paths
            self._initialize_model_paths()
            
            # Initialize docling neural models
            self._initialize_docling_models()
            
        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            raise
    
    def _initialize_model_paths(self):
        """Initialize paths to downloaded models."""
        from .model_downloader import ModelDownloader
        
        downloader = ModelDownloader()
        
        # Check if models exist, if not download them
        layout_path = downloader.get_model_path('layout')
        table_path = downloader.get_model_path('table')
        
        # If any model is missing, download all models
        if not layout_path or not table_path:
            logger.info("Some models are missing. Downloading all required models...")
            logger.info(f"Models will be cached at: {downloader.cache_dir}")
            try:
                downloader.download_models(force=False, progress=True)
                # Get paths again after download
                layout_path = downloader.get_model_path('layout')
                table_path = downloader.get_model_path('table')
                
                # Check if download was successful
                if layout_path and table_path:
                    logger.info("Model download completed successfully!")
                else:
                    logger.warning("Some models may not have downloaded successfully due to authentication issues.")
                    logger.info("Falling back to basic document processing without advanced neural models.")
                    # Set flags to indicate fallback mode
                    self._use_fallback_mode = True
                    return
                    
            except Exception as e:
                logger.warning(f"Failed to download models: {e}")
                if "401" in str(e) or "Unauthorized" in str(e) or "Authentication" in str(e):
                    logger.info(
                        "Model download failed due to authentication. Using basic document processing.\n"
                        "For enhanced features, please set up Hugging Face authentication:\n"
                        "1. Create account at https://huggingface.co/\n"
                        "2. Generate token at https://huggingface.co/settings/tokens\n"
                        "3. Run: huggingface-cli login"
                    )
                    self._use_fallback_mode = True
                    return
                else:
                    raise ValueError(f"Failed to download required models: {e}")
        else:
            logger.info("All required models found in cache.")
            
        # Set fallback mode flag
        self._use_fallback_mode = False
        
        # Set model paths
        self.layout_model_path = layout_path
        self.table_model_path = table_path
        
        if not self.layout_model_path or not self.table_model_path:
            if hasattr(self, '_use_fallback_mode') and self._use_fallback_mode:
                logger.info("Running in fallback mode without advanced neural models")
                return
            else:
                raise ValueError("One or more required models not found")
        
        # The models are downloaded with the full repository structure
        # The entire repo is downloaded to each cache folder, so we need to navigate to the specific model paths
        # Layout model is in layout/model_artifacts/layout/
        # Table model is in tableformer/model_artifacts/tableformer/accurate/
        # Note: EasyOCR downloads its own models automatically
        
        # Check if the expected structure exists, if not use the cache folder directly
        layout_artifacts = self.layout_model_path / "model_artifacts" / "layout"
        table_artifacts = self.table_model_path / "model_artifacts" / "tableformer" / "accurate"
        
        if layout_artifacts.exists():
            self.layout_model_path = layout_artifacts
        else:
            # Fallback: use the cache folder directly
            logger.warning(f"Expected layout model structure not found, using cache folder directly")
        
        if table_artifacts.exists():
            self.table_model_path = table_artifacts
        else:
            # Fallback: use the cache folder directly
            logger.warning(f"Expected table model structure not found, using cache folder directly")
        
        logger.info(f"Layout model path: {self.layout_model_path}")
        logger.info(f"Table model path: {self.table_model_path}")
        logger.info("EasyOCR will download its own models automatically")
        
        # Verify model files exist (with more flexible checking)
        layout_model_file = self.layout_model_path / "model.safetensors"
        table_config_file = self.table_model_path / "tm_config.json"
        
        if not layout_model_file.exists():
            # Try alternative locations
            alt_layout_file = self.layout_model_path / "layout" / "model.safetensors"
            if alt_layout_file.exists():
                self.layout_model_path = self.layout_model_path / "layout"
                layout_model_file = alt_layout_file
            else:
                raise FileNotFoundError(f"Missing layout model file. Checked: {layout_model_file}, {alt_layout_file}")
        
        if not table_config_file.exists():
            # Try alternative locations
            alt_table_file = self.table_model_path / "tableformer" / "accurate" / "tm_config.json"
            if alt_table_file.exists():
                self.table_model_path = self.table_model_path / "tableformer" / "accurate"
                table_config_file = alt_table_file
            else:
                raise FileNotFoundError(f"Missing table config file. Checked: {table_config_file}, {alt_table_file}")
    
    def _initialize_docling_models(self):
        """Initialize docling's pre-trained models."""
        # Check if we're in fallback mode
        if hasattr(self, '_use_fallback_mode') and self._use_fallback_mode:
            logger.info("Skipping docling models initialization - running in fallback mode")
            self.use_advanced_models = False
            self.layout_predictor = None
            self.table_predictor = None
            self.ocr_reader = None
            return
            
        try:
            # Import docling models
            from docling_ibm_models.layoutmodel.layout_predictor import LayoutPredictor
            from docling_ibm_models.tableformer.common import read_config
            from docling_ibm_models.tableformer.data_management.tf_predictor import TFPredictor
            import easyocr
            
            # Initialize layout model
            self.layout_predictor = LayoutPredictor(
                artifact_path=str(self.layout_model_path),
                device='cpu',
                num_threads=4
            )
            
            # Initialize table structure model
            tm_config = read_config(str(self.table_model_path / "tm_config.json"))
            tm_config["model"]["save_dir"] = str(self.table_model_path)
            self.table_predictor = TFPredictor(tm_config, 'cpu', 4)
            
            # Initialize OCR model
            self.ocr_reader = easyocr.Reader(['en'])
            
            self.use_advanced_models = True
            logger.info("Docling neural models initialized successfully")
            
        except ImportError as e:
            logger.error(f"Docling models not available: {e}")
            raise
        except Exception as e:
            error_msg = str(e)
            if "NumPy" in error_msg or "numpy" in error_msg.lower():
                logger.error(
                    f"NumPy compatibility error: {error_msg}\n"
                    "This is likely due to NumPy 2.x incompatibility. Please downgrade:\n"
                    "pip install 'numpy<2.0.0'"
                )
                if platform.system() == "Darwin":
                    logger.error(
                        "On macOS, NumPy 2.x is known to cause crashes with PyTorch. "
                        "Downgrading to NumPy 1.x is required."
                    )
            else:
                logger.error(f"Failed to initialize docling models: {e}")
            raise
    
    def extract_text(self, image_path: str) -> str:
        """Extract text from image using neural OCR."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file does not exist: {image_path}")
                return ""
            
            return self._extract_text_advanced(image_path)
                
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ""
    
    def extract_text_with_layout(self, image_path: str) -> str:
        """Extract text with layout awareness using neural models."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file does not exist: {image_path}")
                return ""

            return self._extract_text_with_layout_advanced(image_path)

        except Exception as e:
            logger.error(f"Layout-aware OCR extraction failed: {e}")
            return ""

    def extract_layout_elements(self, image_path: str) -> List:
        """Return raw LayoutElement objects for engineering drawing extraction.

        Returns the list of positioned text elements before markdown conversion,
        enabling downstream extractors to apply domain-specific logic.
        """
        from .layout_detector import LayoutElement

        if not os.path.exists(image_path):
            logger.error(f"Image file does not exist: {image_path}")
            return []

        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Fallback mode: use EasyOCR directly (no layout predictor available)
                if getattr(self, '_use_fallback_mode', False) or not getattr(self, 'use_advanced_models', False):
                    return self._extract_layout_elements_easyocr(img)

                layout_results = list(self.layout_predictor.predict(img))
                text_blocks = []

                for pred in layout_results:
                    label = pred.get('label', '').lower().replace(' ', '_').replace('-', '_')

                    if all(k in pred for k in ['l', 't', 'r', 'b']):
                        bbox = [pred['l'], pred['t'], pred['r'], pred['b']]
                    else:
                        bbox = pred.get('bbox') or pred.get('box')
                        if not bbox:
                            continue

                    region_text = self._extract_text_from_region(img, bbox)
                    if not region_text or pred.get('confidence', 1.0) < 0.5:
                        continue

                    if label in ['title', 'section_header', 'subtitle_level_1']:
                        element_type = 'heading'
                    elif label == 'list_item':
                        element_type = 'list_item'
                    elif label in ['table', 'document_index']:
                        element_type = 'table'
                    else:
                        element_type = 'paragraph'

                    text_blocks.append(LayoutElement(
                        text=region_text,
                        x=bbox[0],
                        y=bbox[1],
                        width=bbox[2] - bbox[0],
                        height=bbox[3] - bbox[1],
                        element_type=element_type,
                        confidence=pred.get('confidence', 1.0),
                    ))

                text_blocks.sort(key=lambda el: (el.y, el.x))
                return text_blocks

        except Exception as e:
            logger.error(f"extract_layout_elements failed: {e}")
            return []

    def _extract_layout_elements_easyocr(self, img: "Image.Image") -> List:
        """Build LayoutElement list from EasyOCR (bbox_points, text, confidence) tuples."""
        from .layout_detector import LayoutElement

        try:
            results = self.ocr_reader.readtext(img)
        except Exception as e:
            logger.error(f"EasyOCR readtext failed: {e}")
            return []

        elements = []
        for (bbox_pts, text, confidence) in results:
            if confidence < 0.5 or not text.strip():
                continue
            # bbox_pts is [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            xs = [pt[0] for pt in bbox_pts]
            ys = [pt[1] for pt in bbox_pts]
            x, y = min(xs), min(ys)
            w, h = max(xs) - x, max(ys) - y
            elements.append(LayoutElement(
                text=text,
                x=x,
                y=y,
                width=w,
                height=h,
                element_type='paragraph',
                confidence=confidence,
            ))

        elements.sort(key=lambda el: (el.y, el.x))
        return elements
    
    def _extract_text_advanced(self, image_path: str) -> str:
        """Extract text using docling's advanced models."""
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.extract('RGB')
                
                results = self.ocr_reader.readtext(img)
                texts = []
                for (bbox, text, confidence) in results:
                    if confidence > 0.5:
                        texts.append(text)
                
                return ' '.join(texts)
                
        except Exception as e:
            logger.error(f"Advanced OCR extraction failed: {e}")
            return ""
    
    def _extract_text_with_layout_advanced(self, image_path: str) -> str:
        """Extract text with layout awareness using docling's neural models."""
        try:
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.extract('RGB')
                
                # Get layout predictions using neural model
                layout_results = list(self.layout_predictor.predict(img))
                
                # Process layout results and extract text
                text_blocks = []
                table_blocks = []
                
                for pred in layout_results:
                    label = pred.get('label', '').lower().replace(' ', '_').replace('-', '_')
                    
                    # Construct bbox from l, t, r, b
                    if all(k in pred for k in ['l', 't', 'r', 'b']):
                        bbox = [pred['l'], pred['t'], pred['r'], pred['b']]
                    else:
                        bbox = pred.get('bbox') or pred.get('box')
                        if not bbox:
                            continue
                    
                    # Extract text from this region using OCR
                    region_text = self._extract_text_from_region(img, bbox)
                    
                    if not region_text or pred.get('confidence', 1.0) < 0.5:
                        continue
                    
                    from .layout_detector import LayoutElement
                    
                    # Handle different element types
                    if label in ['table', 'document_index']:
                        # Process tables separately
                        table_blocks.append({
                            'text': region_text,
                            'bbox': bbox,
                            'label': label,
                            'confidence': pred.get('confidence', 1.0)
                        })
                    elif label in ['title', 'section_header', 'subtitle_level_1']:
                        # Headers
                        text_blocks.append(LayoutElement(
                            text=region_text,
                            x=bbox[0],
                            y=bbox[1],
                            width=bbox[2] - bbox[0],
                            height=bbox[3] - bbox[1],
                            element_type='heading',
                            confidence=pred.get('confidence', 1.0)
                        ))
                    elif label in ['list_item']:
                        # List items
                        text_blocks.append(LayoutElement(
                            text=region_text,
                            x=bbox[0],
                            y=bbox[1],
                            width=bbox[2] - bbox[0],
                            height=bbox[3] - bbox[1],
                            element_type='list_item',
                            confidence=pred.get('confidence', 1.0)
                        ))
                    else:
                        # Regular text/paragraphs
                        text_blocks.append(LayoutElement(
                            text=region_text,
                            x=bbox[0],
                            y=bbox[1],
                            width=bbox[2] - bbox[0],
                            height=bbox[3] - bbox[1],
                            element_type='paragraph',
                            confidence=pred.get('confidence', 1.0)
                        ))
                
                # Sort by position (top to bottom, left to right)
                text_blocks.sort(key=lambda x: (x.y, x.x))
                
                # Process tables using table structure model
                processed_tables = self._process_tables_with_structure_model(img, table_blocks)
                
                # Convert to markdown with proper structure
                return self._convert_to_structured_markdown_advanced(text_blocks, processed_tables, img.size)
                
        except Exception as e:
            logger.error(f"Advanced layout-aware OCR failed: {e}")
            return ""
    
    def _process_tables_with_structure_model(self, img: Image.Image, table_blocks: List[Dict]) -> List[Dict]:
        """Process tables using the table structure model."""
        processed_tables = []
        
        for table_block in table_blocks:
            try:
                # Extract table region
                bbox = table_block['bbox']
                x1, y1, x2, y2 = bbox
                table_region = img.crop((x1, y1, x2, y2))
                
                # Convert to numpy array
                table_np = np.array(table_region)
                
                # Create page input in the format expected by docling table structure model
                page_input = {
                    "width": table_np.shape[1],
                    "height": table_np.shape[0],
                    "image": table_np,
                    "tokens": []  # Empty tokens since we're not using cell matching
                }
                
                # The bbox coordinates should be relative to the table region
                table_bbox = [0, 0, x2-x1, y2-y1]
                
                # Predict table structure
                tf_output = self.table_predictor.multi_table_predict(page_input, [table_bbox], do_matching=False)
                table_out = tf_output[0] if isinstance(tf_output, list) else tf_output
                
                # Extract table data
                table_data = []
                tf_responses = table_out.get("tf_responses", []) if isinstance(table_out, dict) else []
                
                for element in tf_responses:
                    if isinstance(element, dict) and "bbox" in element:
                        cell_bbox = element["bbox"]
                        # Handle bbox as dict with keys l, t, r, b
                        if isinstance(cell_bbox, dict) and all(k in cell_bbox for k in ["l", "t", "r", "b"]):
                            cell_x1 = cell_bbox["l"]
                            cell_y1 = cell_bbox["t"]
                            cell_x2 = cell_bbox["r"]
                            cell_y2 = cell_bbox["b"]
                            cell_region = table_region.crop((cell_x1, cell_y1, cell_x2, cell_y2))
                            cell_np = np.array(cell_region)
                            cell_text = self._extract_text_from_region_numpy(cell_np)
                            table_data.append(cell_text)
                        elif isinstance(cell_bbox, list) and len(cell_bbox) == 4:
                            cell_x1, cell_y1, cell_x2, cell_y2 = cell_bbox
                            cell_region = table_region.crop((cell_x1, cell_y1, cell_x2, cell_y2))
                            cell_np = np.array(cell_region)
                            cell_text = self._extract_text_from_region_numpy(cell_np)
                            table_data.append(cell_text)
                        else:
                            pass
                    else:
                        pass
                
                # Organize table data into rows and columns
                processed_table = self._organize_table_data(table_data, table_out if isinstance(table_out, dict) else {})
                # Preserve the original bbox from the table block
                processed_table['bbox'] = table_block['bbox']
                processed_tables.append(processed_table)
                
            except Exception as e:
                logger.error(f"Failed to process table: {e}")
                # Fallback to simple table extraction
                processed_tables.append({
                    'type': 'simple_table',
                    'text': table_block['text'],
                    'bbox': table_block['bbox']
                })
        
        return processed_tables
    
    def _extract_text_from_region_numpy(self, region_np: np.ndarray) -> str:
        """Extract text from numpy array region."""
        try:
            results = self.ocr_reader.readtext(region_np)
            texts = []
            for (_, text, confidence) in results:
                if confidence > 0.5:
                    texts.append(text)
            return ' '.join(texts)
        except Exception as e:
            logger.error(f"Failed to extract text from numpy region: {e}")
            return ""
    
    def _organize_table_data(self, table_data: list, table_out: dict) -> dict:
        """Organize table data into proper structure using row/col indices from tf_responses."""
        try:
            tf_responses = table_out.get("tf_responses", []) if isinstance(table_out, dict) else []
            num_rows = table_out.get("predict_details", {}).get("num_rows", 0)
            num_cols = table_out.get("predict_details", {}).get("num_cols", 0)

            # Build empty grid
            grid = [["" for _ in range(num_cols)] for _ in range(num_rows)]

            # Place cell texts in the correct grid positions
            for idx, element in enumerate(tf_responses):
                row = element.get("start_row_offset_idx", 0)
                col = element.get("start_col_offset_idx", 0)
                # Use the extracted text if available, else fallback to element text
                text = table_data[idx] if idx < len(table_data) else element.get("text", "")
                grid[row][col] = text

            return {
                'type': 'structured_table',
                'grid': grid,
                'num_rows': num_rows,
                'num_cols': num_cols
            }
        except Exception as e:
            logger.error(f"Failed to organize table data: {e}")
            return {
                'type': 'simple_table',
                'data': table_data
            }
    
    def _convert_table_to_markdown(self, table: dict) -> str:
        """Convert structured table to markdown format."""
        if table['type'] != 'structured_table':
            return f"**Table:** {table.get('text', '')}"
        grid = table['grid']
        if not grid or not grid[0]:
            return ""
        
        # Find the first non-empty row to use as header
        header_row = None
        for row in grid:
            if any(cell.strip() for cell in row):
                header_row = row
                break
        
        if not header_row:
            return ""
        
        # Use the header row as is (preserve all columns)
        header_cells = [cell.strip() if cell else "" for cell in header_row]
        
        markdown_lines = []
        markdown_lines.append("| " + " | ".join(header_cells) + " |")
        markdown_lines.append("|" + "|".join(["---"] * len(header_cells)) + "|")
        
        # Add data rows (skip the header row)
        header_index = grid.index(header_row)
        for row in grid[header_index + 1:]:
            cells = [cell.strip() if cell else "" for cell in row]
            markdown_lines.append("| " + " | ".join(cells) + " |")
        
        return '\n'.join(markdown_lines)
    
    def _convert_to_structured_markdown_advanced(self, text_blocks: List, processed_tables: List[Dict], img_size: Tuple[int, int]) -> str:
        """Convert text blocks and tables to structured markdown."""
        markdown_parts = []
        
        # Sort all elements by position
        all_elements = []
        
        # Add text blocks
        for block in text_blocks:
            all_elements.append({
                'type': 'text',
                'element': block,
                'y': block.y,
                'x': block.x
            })
        
        # Add tables
        for table in processed_tables:
            if 'bbox' in table:
                all_elements.append({
                    'type': 'table',
                    'element': table,
                    'y': table['bbox'][1],
                    'x': table['bbox'][0]
                })
            else:
                logger.warning(f"Table has no bbox, skipping: {table}")
        
        # Sort by position
        all_elements.sort(key=lambda x: (x['y'], x['x']))
        
        # Convert to markdown
        for element in all_elements:
            if element['type'] == 'text':
                block = element['element']
                text = block.text.strip()
                if not text:
                    continue
                
                if block.element_type == 'heading':
                    # Determine heading level based on font size/position
                    level = self._determine_heading_level(block)
                    markdown_parts.append(f"{'#' * level} {text}")
                    markdown_parts.append("")
                elif block.element_type == 'list_item':
                    markdown_parts.append(f"- {text}")
                else:
                    markdown_parts.append(text)
                    markdown_parts.append("")
                    
            elif element['type'] == 'table':
                table = element['element']
                if table['type'] == 'structured_table':
                    # Convert structured table to markdown
                    table_md = self._convert_table_to_markdown(table)
                    markdown_parts.append(table_md)
                    markdown_parts.append("")
                else:
                    # Simple table
                    markdown_parts.append(f"**Table:** {table.get('text', '')}")
                    markdown_parts.append("")
        
        return '\n'.join(markdown_parts)
    
    def _determine_heading_level(self, block) -> int:
        """Determine heading level based on font size and position."""
        # Simple heuristic: larger text or positioned at top = higher level
        if block.y < 100:  # Near top of page
            return 1
        elif block.height > 30:  # Large text
            return 2
        else:
            return 3
    
    def _extract_text_from_region(self, img: Image.Image, bbox: List[float]) -> str:
        """Extract text from a specific region of the image."""
        try:
            # Crop the region
            x1, y1, x2, y2 = bbox
            region = img.crop((x1, y1, x2, y2))
            
            # Convert PIL image to numpy array for easyocr
            region_np = np.array(region)
            
            # Use OCR on the region
            results = self.ocr_reader.readtext(region_np)
            texts = []
            for (_, text, confidence) in results:
                if confidence > 0.5:
                    texts.append(text)
            
            return ' '.join(texts)
            
        except Exception as e:
            logger.error(f"Failed to extract text from region: {e}")
            return ""
    
    def __del__(self):
        """Cleanup resources."""
        pass 