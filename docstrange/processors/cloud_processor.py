"""Cloud processor for Nanonets API integration."""

import os
import requests
import json
import logging
from typing import Dict, Any, Optional

from .base import BaseProcessor
from ..result import ConversionResult
from ..exceptions import ConversionError

logger = logging.getLogger(__name__)


class CloudConversionResult(ConversionResult):
    """Enhanced ConversionResult for cloud mode with lazy API calls."""
    
    def __init__(self, file_path: str, cloud_processor: 'CloudProcessor', metadata: Optional[Dict[str, Any]] = None):
        # Initialize with empty content - we'll make API calls on demand
        super().__init__("", metadata)
        self.file_path = file_path
        self.cloud_processor = cloud_processor
        self._cached_outputs = {}  # Cache API responses by output type
    
    def _get_cloud_output(self, output_type: str, specified_fields: Optional[list] = None, json_schema: Optional[dict] = None) -> str:
        """Get output from cloud API for specific type, with caching."""
        # Validate output type
        valid_output_types = ["markdown", "flat-json", "html", "csv", "specified-fields", "specified-json"]
        if output_type not in valid_output_types:
            logger.warning(f"Invalid output type '{output_type}' for cloud API. Using 'markdown'.")
            output_type = "markdown"
        
        # Create cache key based on output type and parameters
        cache_key = output_type
        if specified_fields:
            cache_key += f"_fields_{','.join(specified_fields)}"
        if json_schema:
            cache_key += f"_schema_{hash(str(json_schema))}"
        
        if cache_key in self._cached_outputs:
            return self._cached_outputs[cache_key]
        
        try:
            # Prepare headers - API key is optional
            headers = {}
            if self.cloud_processor.api_key:
                headers['Authorization'] = f'Bearer {self.cloud_processor.api_key}'
            
            # Prepare file for upload
            with open(self.file_path, 'rb') as file:
                files = {
                    'file': (os.path.basename(self.file_path), file, self.cloud_processor._get_content_type(self.file_path))
                }
                
                # The /api/v1/extract/sync endpoint expects `output_format`
                # (markdown|html|json|csv). Map from the legacy `output_type`
                # vocabulary; `flat-json` and the specified-* variants map to
                # the `json` output format on the new API. `output_type` is kept
                # for backward compatibility with any older endpoint.
                _fmt_map = {
                    "markdown": "markdown",
                    "html": "html",
                    "csv": "csv",
                    "flat-json": "json",
                    "specified-fields": "json",
                    "specified-json": "json",
                }
                output_format = _fmt_map.get(output_type, "markdown")
                data = {
                    'output_type': output_type,
                    'output_format': output_format,
                }

                # Add model_type if specified
                if self.cloud_processor.model_type:
                    data['model_type'] = self.cloud_processor.model_type
                
                # Add field extraction parameters
                if output_type == "specified-fields" and specified_fields:
                    data['specified_fields'] = ','.join(specified_fields)
                elif output_type == "specified-json" and json_schema:
                    data['json_schema'] = json.dumps(json_schema)
                
                # Log the request
                if self.cloud_processor.api_key:
                    logger.info(f"Making cloud API call with authenticated access for {output_type} on {self.file_path}")
                else:
                    logger.info(f"Making cloud API call without authentication (free tier) for {output_type} on {self.file_path}")
                
                # Make API request
                response = requests.post(
                    self.cloud_processor.api_url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300
                )
                
                # Handle HTTP 429 responses. A 429 does NOT always mean the
                # rate limit was hit: a deprecated endpoint returns 429 with a
                # body like {"detail": "The /extract endpoint is deprecated.
                # Please migrate to /api/v1/extract."}. Inspect the body before
                # assuming a quota problem so we never surface a misleading
                # "Rate limit exceeded" error when the real cause is different.
                if response.status_code == 429:
                    detail = self.cloud_processor._parse_error_detail(response)

                    if detail and self.cloud_processor._is_deprecation_notice(detail):
                        error_msg = (
                            f"The cloud extraction endpoint returned a deprecation "
                            f"notice: {detail}. Please upgrade docstrange to a version "
                            f"that targets the current API endpoint."
                        )
                        logger.error(error_msg)
                        raise ConversionError(error_msg)

                    if not self.cloud_processor.api_key:
                        error_msg = (
                            "Rate limit exceeded for free tier (limited calls daily). "
                            "Run 'docstrange login' for 10,000 docs/month, or use an API key from https://app.nanonets.com/#/keys.\n"
                            "Examples:\n"
                            "  - CLI: docstrange login\n"
                            "  - Python: DocumentExtractor()  # after login (uses cached credentials)\n"
                            "  - Python: DocumentExtractor(api_key='YOUR_API_KEY')  # alternative"
                        )
                        if detail:
                            error_msg += f"\nServer said: {detail}"
                        logger.error(error_msg)
                        raise ConversionError(error_msg)
                    else:
                        error_msg = "Rate limit exceeded (10k/month). Please try again later."
                        if detail:
                            error_msg += f" Server said: {detail}"
                        logger.error(error_msg)
                        raise ConversionError(error_msg)

                response.raise_for_status()
                result_data = response.json()
                
                # Extract content from response
                content = self.cloud_processor._extract_content_from_response(result_data)
                
                # Cache the result
                self._cached_outputs[cache_key] = content
                return content
                
        except ConversionError:
            # Re-raise ConversionError (like rate limiting) without fallback
            raise
        except Exception as e:
            logger.error(f"Failed to get {output_type} from cloud API: {e}")
            # Try fallback to local conversion for other errors
            return self._convert_locally(output_type)
    
    def _convert_locally(self, output_type: str) -> str:
        """Fallback to local conversion methods."""
        if output_type == "html":
            return super().extract_html()
        elif output_type == "flat-json":
            return json.dumps(super().extract_data(), indent=2)
        elif output_type == "csv":
            return super().extract_csv(include_all_tables=True)
        else:
            return self.content
    
    def extract_markdown(self) -> str:
        """Export as markdown."""
        return self._get_cloud_output("markdown")
    
    def extract_html(self) -> str:
        """Export as HTML."""
        return self._get_cloud_output("html")
    
    def extract_data(self, specified_fields: Optional[list] = None, json_schema: Optional[dict] = None) -> Dict[str, Any]:
        """Export as structured JSON with optional field extraction.
        
        Args:
            specified_fields: Optional list of specific fields to extract
            json_schema: Optional JSON schema defining fields and types to extract
            
        Returns:
            Structured JSON with extracted data
        """
        try:
            if specified_fields:
                # Request specified fields extraction
                content = self._get_cloud_output("specified-fields", specified_fields=specified_fields)
                extracted_data = json.loads(content)
                return {
                    "extracted_fields": extracted_data,
                    "format": "specified_fields"
                }
            
            elif json_schema:
                # Request JSON schema extraction
                content = self._get_cloud_output("specified-json", json_schema=json_schema)
                extracted_data = json.loads(content)
                return {
                    "structured_data": extracted_data,
                    "format": "structured_json"
                }
            
            else:
                # Standard JSON extraction
                json_content = self._get_cloud_output("flat-json")
                parsed_content = json.loads(json_content)
                return {
                    "document": parsed_content,
                    "format": "cloud_flat_json"
                }
                
        except Exception as e:
            logger.error(f"Failed to parse JSON content: {e}")
            return {
                "document": {"raw_content": content if 'content' in locals() else ""},
                "format": "json_parse_error",
                "error": str(e)
            }
    

    
    def extract_text(self) -> str:
        """Export as plain text."""
        # For text output, we can try markdown first and then extract to text
        try:
            return self._get_cloud_output("markdown")
        except Exception as e:
            logger.error(f"Failed to get text output: {e}")
            return ""
    
    def extract_csv(self, table_index: int = 0, include_all_tables: bool = False) -> str:
        """Export tables as CSV format.
        
        Args:
            table_index: Which table to export (0-based index). Default is 0 (first table).
            include_all_tables: If True, export all tables with separators. Default is False.
        
        Returns:
            CSV formatted string of the table(s)
        
        Raises:
            ValueError: If no tables are found or table_index is out of range
        """
        return self._get_cloud_output("csv")


class CloudProcessor(BaseProcessor):
    """Processor for cloud-based document conversion using Nanonets API."""
    
    def __init__(self, api_key: Optional[str] = None, output_type: str = None, model_type: Optional[str] = None, 
                 specified_fields: Optional[list] = None, json_schema: Optional[dict] = None, **kwargs):
        """Initialize the cloud processor.
        
        Args:
            api_key: API key for cloud processing (optional - uses rate-limited free tier without key)
            output_type: Output type for cloud processing (markdown, flat-json, html, csv, specified-fields, specified-json)
            model_type: Model type for cloud processing (gemini, openapi, nanonets)
            specified_fields: List of fields to extract (for specified-fields output type)
            json_schema: JSON schema defining fields and types to extract (for specified-json output type)
        """
        super().__init__(**kwargs)
        self.api_key = api_key
        self.output_type = output_type
        self.model_type = model_type
        self.specified_fields = specified_fields
        self.json_schema = json_schema
        # Nanonets deprecated the bare /extract endpoint: it now returns HTTP
        # 429 with body {"detail": "The /extract endpoint is deprecated. Please
        # migrate to /api/v1/extract."}. Target the current sync endpoint so a
        # deprecation notice is not misread as a rate-limit/quota error.
        self.api_url = "https://extraction-api.nanonets.com/api/v1/extract/sync"

        # Don't validate output_type during initialization - it will be validated during processing
        # This prevents warnings during DocumentExtractor initialization
    
    def can_process(self, file_path: str) -> bool:
        """Check if the processor can handle the file."""
        # Cloud processor supports most common document formats
        # API key is optional - without it, uses rate-limited free tier
        supported_extensions = {
            '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', 
            '.txt', '.html', '.htm', '.png', '.jpg', '.jpeg', '.gif', 
            '.bmp', '.tiff', '.tif'
        }
        
        _, ext = os.path.splitext(file_path.lower())
        return ext in supported_extensions
    
    def process(self, file_path: str) -> CloudConversionResult:
        """Create a lazy CloudConversionResult that will make API calls on demand.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            CloudConversionResult that makes API calls when output methods are called
            
        Raises:
            ConversionError: If file doesn't exist
        """
        if not os.path.exists(file_path):
            raise ConversionError(f"File not found: {file_path}")
        
        # Create metadata without making any API calls
        metadata = {
            'source_file': file_path,
            'processing_mode': 'cloud',
            'api_provider': 'nanonets',
            'file_size': os.path.getsize(file_path),
            'model_type': self.model_type,
            'has_api_key': bool(self.api_key)
        }
        
        if self.api_key:
            logger.info(f"Created cloud extractor for {file_path} with freeAPI key - increased limits")
        else:
            logger.info(f"Created cloud extractor for {file_path} without API key - rate-limited access")
        
        # Return lazy result that will make API calls when needed
        return CloudConversionResult(
            file_path=file_path,
            cloud_processor=self,
            metadata=metadata
        )
    
    @staticmethod
    def _parse_error_detail(response: requests.Response) -> str:
        """Best-effort extraction of a human-readable error message from a response.

        Nanonets error bodies use a JSON ``{"detail": "..."}`` shape; fall back
        to the raw (truncated) text for anything else.
        """
        try:
            body = response.json()
        except ValueError:
            return (response.text or "").strip()[:500]
        if isinstance(body, dict):
            for key in ("detail", "message", "error"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        return json.dumps(body)[:500]

    @staticmethod
    def _is_deprecation_notice(detail: str) -> bool:
        """Return True when an error message describes a deprecated endpoint."""
        lowered = detail.lower()
        return "deprecated" in lowered or "migrate to" in lowered

    def _extract_content_from_response(self, response_data: Dict[str, Any]) -> str:
        """Extract content from API response.

        Supports both the legacy flat shape (top-level ``content``) and the
        current /api/v1/extract/sync nested shape::

            {"success": true,
             "result": {"markdown": {"content": "..."}, "html": ..., ...},
             "output_format": "markdown"}
        """
        try:
            # Legacy shape: top-level 'content' field.
            if 'content' in response_data:
                return response_data['content']

            # Current /api/v1/extract/sync shape: content lives under
            # result.<format>.content (or result.<format> when it's a string).
            result = response_data.get('result')
            if isinstance(result, dict):
                requested_format = response_data.get('output_format')
                candidates = []
                # Prefer the block matching the requested output_format.
                if requested_format and requested_format in result:
                    candidates.append(result[requested_format])
                candidates.extend(
                    result[key]
                    for key in ("markdown", "html", "csv", "json")
                    if key in result and result[key] is not None
                )
                for block in candidates:
                    if isinstance(block, dict) and block.get('content') is not None:
                        return block['content']
                    if isinstance(block, str):
                        return block

            # Fallback: return whole response as JSON if no content field
            logger.warning("No 'content' field found in API response, returning full response")
            return json.dumps(response_data, indent=2)

        except Exception as e:
            logger.error(f"Failed to extract content from API response: {e}")
            return json.dumps(response_data, indent=2)
    
    def _get_content_type(self, file_path: str) -> str:
        """Get content type for file upload."""
        _, ext = os.path.splitext(file_path.lower())
        
        content_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff'
        }
        
        return content_types.get(ext, 'application/octet-stream') 