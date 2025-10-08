"""Web application for docstrange document extraction."""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge

from .extractor import DocumentExtractor
from .exceptions import ConversionError, UnsupportedFormatError, FileNotFoundError

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

def check_gpu_availability():
    """Check if GPU is available for processing."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False

def download_models():
    """Download models synchronously before starting the app."""
    print("🔄 Starting model download...")
    
    # Check GPU availability
    gpu_available = check_gpu_availability()
    
    if gpu_available:
        print("🚀 GPU detected - downloading GPU models")
        # Download GPU models
        extractor = DocumentExtractor(gpu=True)
    else:
        print("💻 GPU not available - downloading CPU models only")
        # Download CPU models only
        extractor = DocumentExtractor(cpu=True)
    
    # Test extraction to trigger model downloads
    print("📥 Downloading models...")
    
    # Create a simple test file to trigger model downloads
    test_content = "Test document for model download."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_file:
        tmp_file.write(test_content)
        test_file_path = tmp_file.name
    
    try:
        # This will trigger model downloads
        result = extractor.extract(test_file_path)
        print("✅ Model download completed successfully")
    except Exception as e:
        print(f"⚠️ Model download warning: {e}")
        # Don't fail completely, just log the warning
    finally:
        # Clean up test file
        if os.path.exists(test_file_path):
            os.unlink(test_file_path)

def normalize_processing_mode(processing_mode: Optional[str]) -> str:
    """Map user-provided processing mode to an internal value."""
    if not processing_mode:
        return 'cpu'

    normalized = processing_mode.strip().lower()

    if normalized in {'cpu', 'gpu'}:
        return normalized

    # Treat any legacy labels (like "cloud" or "local") as CPU-only processing.
    return 'cpu'


def create_extractor_with_mode(processing_mode):
    """Create DocumentExtractor with proper error handling for processing mode."""
    normalized_mode = normalize_processing_mode(processing_mode)

    if normalized_mode == 'gpu':
        if not check_gpu_availability():
            raise ValueError("GPU mode selected but GPU is not available. Please install PyTorch with CUDA support or use CPU mode.")
        return DocumentExtractor(gpu=True)
    else:  # cpu mode (default)
        return DocumentExtractor(cpu=True)

# Initialize the document extractor
extractor = DocumentExtractor(cpu=True)

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('static', filename)

@app.route('/api/extract', methods=['POST'])
def extract_document():
    """API endpoint for document extraction."""
    try:
        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get parameters
        output_format = request.form.get('output_format', 'markdown')
        processing_mode = normalize_processing_mode(request.form.get('processing_mode', 'cpu'))
        
        # Create extractor based on processing mode
        try:
            extractor = create_extractor_with_mode(processing_mode)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            file.save(tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Extract content
            result = extractor.extract(tmp_path)
            
            # Convert to requested format
            if output_format == 'markdown':
                content = result.extract_markdown()
            elif output_format == 'html':
                content = result.extract_html()
            elif output_format == 'json':
                content = result.extract_data()
                content = json.dumps(content, indent=2)
            elif output_format == 'csv':
                content = result.extract_csv(include_all_tables=True)
            elif output_format == 'flat-json':
                content = result.extract_data()
                content = json.dumps(content, indent=2)
            elif output_format == 'text':
                content = result.extract_text()
            else:
                content = result.extract_markdown()  # Default to markdown
            
            # Get metadata
            metadata = {
                'file_type': Path(file.filename).suffix.lower(),
                'file_name': file.filename,
                'file_size': os.path.getsize(tmp_path),
                'pages_processed': getattr(result, 'pages_processed', 1),
                'processing_time': getattr(result, 'processing_time', 0),
                'output_format': output_format,
                'processing_mode': processing_mode
            }
            
            return jsonify({
                'success': True,
                'content': content,
                'metadata': metadata
            })
            
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except RequestEntityTooLarge:
        return jsonify({'error': 'File too large. Maximum size is 100MB.'}), 413
    except UnsupportedFormatError as e:
        return jsonify({'error': f'Unsupported file format: {str(e)}'}), 400
    except ConversionError as e:
        return jsonify({'error': f'Conversion error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/api/supported-formats')
def get_supported_formats():
    """Get list of supported file formats."""
    formats = extractor.get_supported_formats()
    return jsonify({'formats': formats})

@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'version': '1.0.0'})

@app.route('/api/system-info')
def get_system_info():
    """Get system information including GPU availability."""
    gpu_available = check_gpu_availability()
    
    # Get additional system info
    system_info = {
        'gpu_available': gpu_available,
        'processing_modes': {
            'cpu': {
                'available': True,
                'description': 'Process locally using CPU. Works offline, slower but private.'
            },
            'gpu': {
                'available': gpu_available,
                'description': 'Process locally using GPU. Fastest local processing, requires CUDA.' if gpu_available else 'GPU not available. Install PyTorch with CUDA support.'
            }
        }
    }
    
    return jsonify(system_info)

def run_web_app(host='0.0.0.0', port=8000, debug=False):
    """Run the web application."""
    print("🔄 Downloading models before starting the web interface...")
    download_models()
    print(f"✅ Starting docstrange web interface at http://{host}:{port}")
    print("Press Ctrl+C to stop the server")
    app.run(host=host, port=port, debug=debug)

if __name__ == '__main__':
    run_web_app(debug=True) 