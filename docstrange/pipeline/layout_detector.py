"""Layout detection and markdown generation for document processing."""

import re
import logging
from typing import List, Dict, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class LayoutElement:
    """Represents a layout element with position and content."""
    
    def __init__(self, text: str, x: int, y: int, width: int, height: int, 
                 element_type: str = "text", confidence: float = 0.0):
        self.text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.element_type = element_type
        self.confidence = confidence
        self.bbox = (x, y, x + width, y + height)
    
    def area(self) -> int:
        """Calculate area of the element."""
        return self.width * self.height
    
    def center_y(self) -> float:
        """Get center Y coordinate."""
        return self.y + self.height / 2
    
    def center_x(self) -> float:
        """Get center X coordinate."""
        return self.x + self.width / 2


class LayoutDetector:
    """Handles layout detection and markdown generation."""
    
    def __init__(self):
        """Initialize the layout detector."""
        # Layout detection parameters
        self._header_threshold = 0.15  # Top 15% of page considered header area
        self._footer_threshold = 0.85  # Bottom 15% of page considered footer area
        self._heading_height_threshold = 1.5  # Relative height for heading detection
        self._list_patterns = [
            r'^\d+\.',  # Numbered list
            r'^[•·▪▫◦‣⁃]',  # Bullet points
            r'^[-*+]',  # Markdown list markers
            r'^[a-zA-Z]\.',  # Lettered list
        ]
    
    def convert_to_structured_markdown(self, text_blocks: List[LayoutElement], image_size: Tuple[int, int]) -> str:
        """Convert text blocks to structured markdown with proper hierarchy."""
        if not text_blocks:
            return ""
        
        # Sort blocks by vertical position (top to bottom), then horizontal (left to right)
        text_blocks.sort(key=lambda x: (x.y, x.x))
        
        # Group blocks into paragraphs based on vertical spacing and text analysis
        paragraphs = self._group_into_paragraphs_advanced(text_blocks, image_size)
        
        # Convert paragraphs to markdown
        markdown_parts = []
        
        for paragraph in paragraphs:
            if paragraph:
                # Determine if this paragraph is a heading, list, or regular text
                paragraph_type = self._classify_paragraph(paragraph)
                
                if paragraph_type == "heading":
                    level = self._determine_heading_level_from_text(paragraph)
                    markdown_parts.append(f"{'#' * level} {paragraph}")
                elif paragraph_type == "list_item":
                    markdown_parts.append(f"- {paragraph}")
                elif paragraph_type == "table_row":
                    markdown_parts.append(self._format_table_row(paragraph))
                else:
                    markdown_parts.append(paragraph)
        
        return '\n\n'.join(markdown_parts)
    
    def _group_into_paragraphs_advanced(self, text_blocks: List[LayoutElement], image_size: Tuple[int, int]) -> List[str]:
        """Advanced paragraph grouping using multiple heuristics."""
        if not text_blocks:
            return []
        
        # Calculate average text height for relative sizing
        heights = [block.height for block in text_blocks]
        avg_height = np.mean(heights) if heights else 20
        
        # Group by proximity and text characteristics
        paragraphs = []
        current_paragraph = []
        current_y = text_blocks[0].y
        paragraph_threshold = 1.5 * avg_height  # Dynamic threshold based on text size
        
        for block in text_blocks:
            # Check if this block is part of the same paragraph
            if abs(block.y - current_y) <= paragraph_threshold:
                current_paragraph.append(block)
            else:
                # Start new paragraph
                if current_paragraph:
                    paragraph_text = self._join_paragraph_text_advanced(current_paragraph)
                    if paragraph_text:
                        paragraphs.append(paragraph_text)
                current_paragraph = [block]
                current_y = block.y
        
        # Add the last paragraph
        if current_paragraph:
            paragraph_text = self._join_paragraph_text_advanced(current_paragraph)
            if paragraph_text:
                paragraphs.append(paragraph_text)
        
        return paragraphs
    
    def _join_paragraph_text_advanced(self, text_blocks: List[LayoutElement]) -> str:
        """Join text blocks into a coherent paragraph with better text processing."""
        if not text_blocks:
            return ""
        
        # Sort blocks by reading order (left to right, top to bottom)
        text_blocks.sort(key=lambda x: (x.y, x.x))
        
        # Extract and clean text
        texts = []
        for block in text_blocks:
            text = block.text.strip()
            if text:
                texts.append(text)
        
        if not texts:
            return ""
        
        # Join with smart spacing
        result = ""
        for i, text in enumerate(texts):
            if i == 0:
                result = text
            else:
                # Check if we need a space before this text
                prev_char = result[-1] if result else ""
                curr_char = text[0] if text else ""
                
                # Don't add space before punctuation
                if curr_char in ',.!?;:':
                    result += text
                # Don't add space after opening parenthesis/bracket
                elif prev_char in '([{':
                    result += text
                # Don't add space before closing parenthesis/bracket
                elif curr_char in ')]}':
                    result += text
                # Don't add space before common punctuation
                elif curr_char in ';:':
                    result += text
                # Handle hyphenation
                elif prev_char == '-' and curr_char.isalpha():
                    result += text
                else:
                    result += " " + text
        
        # Post-process the text
        result = self._post_process_text(result)
        
        return result.strip()
    
    def _post_process_text(self, text: str) -> str:
        """Post-process text to improve readability.

        Engineering safety: do NOT substitute digits or pipe characters — they carry
        meaning in dimension values (0, 1) and GD&T feature control frames (|⊥|0.5|A|).
        """
        text = re.sub(r'\s+', ' ', text)                      # collapse multiple spaces
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # sentence spacing
        return text
    
    def _classify_paragraph(self, text: str) -> str:
        """Classify a paragraph as heading, list item, table row, or regular text."""
        text = text.strip()
        
        # Check if it's a list item
        if self._is_list_item(text):
            return "list_item"
        
        # Check if it's a table row
        if self._is_table_row(text):
            return "table_row"
        
        # Check if it's a heading (short text, ends with period, or all caps)
        if len(text.split()) <= 5 and (text.endswith('.') or text.isupper()):
            return "heading"
        
        return "text"
    
    def _determine_heading_level_from_text(self, text: str) -> int:
        """Determine heading level based on text characteristics."""
        text = text.strip()
        
        # Short text is likely a higher level heading
        if len(text.split()) <= 3:
            return 1
        elif len(text.split()) <= 5:
            return 2
        else:
            return 3
    
    def _is_list_item(self, text: str) -> bool:
        """Check if text is a list item."""
        text = text.strip()
        for pattern in self._list_patterns:
            if re.match(pattern, text):
                return True
        return False
    
    def _is_table_row(self, text: str) -> bool:
        """Check if text might be a table row."""
        # Simple heuristic: if text contains multiple tab-separated or pipe-separated parts
        if '|' in text or '\t' in text:
            return True
        
        # Check for regular spacing that might indicate table columns
        words = text.split()
        if len(words) >= 4:  # More words likely indicate table data
            # Check if there are multiple spaces between words (indicating columns)
            if '  ' in text:  # Double spaces often indicate column separation
                return True
        
        return False
    
    def _format_table_row(self, text: str) -> str:
        """Format text as a table row."""
        # Split by common table separators
        if '|' in text:
            cells = [cell.strip() for cell in text.split('|')]
        elif '\t' in text:
            cells = [cell.strip() for cell in text.split('\t')]
        else:
            # Try to split by multiple spaces
            cells = [cell.strip() for cell in re.split(r'\s{2,}', text)]
        
        # Format as markdown table row
        return '| ' + ' | '.join(cells) + ' |'
    
    def join_text_properly(self, texts: List[str]) -> str:
        """Join text words into proper sentences and paragraphs."""
        if not texts:
            return ""
        
        # Clean and join text
        cleaned_texts = []
        for text in texts:
            # Remove extra whitespace
            text = text.strip()
            if text:
                cleaned_texts.append(text)
        
        if not cleaned_texts:
            return ""
        
        # Join with spaces, but be smart about punctuation
        result = ""
        for i, text in enumerate(cleaned_texts):
            if i == 0:
                result = text
            else:
                # Check if we need a space before this word
                prev_char = result[-1] if result else ""
                curr_char = text[0] if text else ""
                
                # Don't add space before punctuation
                if curr_char in ',.!?;:':
                    result += text
                # Don't add space after opening parenthesis/bracket
                elif prev_char in '([{':
                    result += text
                # Don't add space before closing parenthesis/bracket
                elif curr_char in ')]}':
                    result += text
                else:
                    result += " " + text
        
        return result.strip()
    
    def create_layout_element_from_block(self, block_data: List[Dict]) -> LayoutElement:
        """Create a LayoutElement from a block of text data."""
        if not block_data:
            return LayoutElement("", 0, 0, 0, 0)
        
        # Sort by line_num and word_num to maintain reading order
        block_data.sort(key=lambda x: (x['line_num'], x['word_num']))
        
        # Extract text and position information
        texts = [item['text'] for item in block_data]
        x_coords = [item['x'] for item in block_data]
        y_coords = [item['y'] for item in block_data]
        widths = [item['width'] for item in block_data]
        heights = [item['height'] for item in block_data]
        confidences = [item['conf'] for item in block_data]
        
        # Calculate bounding box
        min_x = min(x_coords)
        min_y = min(y_coords)
        max_x = max(x + w for x, w in zip(x_coords, widths))
        max_y = max(y + h for y, h in zip(y_coords, heights))
        
        # Join text with proper spacing
        text = self.join_text_properly(texts)
        
        return LayoutElement(
            text=text,
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
            element_type="text",
            confidence=np.mean(confidences) if confidences else 0.0
        ) 