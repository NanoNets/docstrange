// DocStrange Document Extraction - Frontend JavaScript

class DocStrangeApp {
    constructor() {
        this.selectedFile = null;
        this.extractionResults = null;
        // Get root path from global config, default to empty string
        this.rootPath = window.APP_ROOT_PATH || '';
        this.initializeApp();
    }

    async initializeApp() {
        await this.loadSystemInfo();
        this.initializeEventListeners();
    }

    async loadSystemInfo() {
        try {
            const response = await fetch(`${this.rootPath}/api/system-info`);
            if (response.ok) {
                const systemInfo = await response.json();
                this.updateProcessingModeOptions(systemInfo);
            }
        } catch (error) {
            console.warn('Could not load system info:', error);
        }
    }

    updateProcessingModeOptions(systemInfo) {
        // Processing mode is now handled automatically - cloud by default, GPU if available and selected
        // No UI changes needed as processing mode selection has been removed
    }

    initializeEventListeners() {
        // File input change
        document.getElementById('fileInput').addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files[0]);
        });

        // Drag and drop events
        const uploadArea = document.getElementById('fileUploadArea');
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.handleFileSelect(files[0]);
            }
        });

        // Click on upload area to trigger file input
        uploadArea.addEventListener('click', () => {
            document.getElementById('fileInput').click();
        });

        // Form submission
        document.getElementById('uploadForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleFormSubmission();
        });

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTab(e.target.dataset.tab);
            });
        });
    }

    handleFileSelect(file) {
        if (!file) return;

        // Validate file type
        const allowedTypes = [
            '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt',
            '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.ppt', '.pptx',
            '.html', '.htm'
        ];
        
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowedTypes.includes(fileExtension)) {
            this.showError(`Unsupported file type: ${fileExtension}`);
            return;
        }

        // Validate file size (100MB limit)
        const maxSize = 100 * 1024 * 1024; // 100MB
        if (file.size > maxSize) {
            this.showError('File too large. Maximum size is 100MB.');
            return;
        }

        this.selectedFile = file;
        this.displayFileInfo(file);
        this.enableSubmitButton();
    }

    displayFileInfo(file) {
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const uploadArea = document.getElementById('fileUploadArea');

        fileName.textContent = file.name;
        fileSize.textContent = this.formatFileSize(file.size);
        fileInfo.style.display = 'flex';
        
        // Hide the drag and drop area when file is selected
        uploadArea.style.display = 'none';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    removeFile() {
        this.selectedFile = null;
        const fileInfo = document.getElementById('fileInfo');
        const uploadArea = document.getElementById('fileUploadArea');
        
        fileInfo.style.display = 'none';
        // Show the drag and drop area again when file is removed
        uploadArea.style.display = 'block';
        
        document.getElementById('fileInput').value = '';
        this.disableSubmitButton();
        this.hideResults();
    }

    enableSubmitButton() {
        const submitBtn = document.getElementById('submitBtn');
        submitBtn.disabled = false;
    }

    disableSubmitButton() {
        const submitBtn = document.getElementById('submitBtn');
        submitBtn.disabled = true;
    }

    async handleFormSubmission() {
        if (!this.selectedFile) {
            this.showError('Please select a file first.');
            return;
        }

        this.showLoading();
        this.hideResults();

        try {
            const formData = new FormData();
            formData.append('file', this.selectedFile);
            
            // Get selected output format
            const outputFormat = document.querySelector('input[name="outputFormat"]:checked').value;
            formData.append('output_format', outputFormat);

            // Use cloud processing mode by default
            formData.append('processing_mode', 'cloud');

            const response = await fetch(`${this.rootPath}/api/extract`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.displayResults(result);
            } else {
                const errorMessage = result.error || 'Extraction failed';
                
                // Handle specific GPU errors
                if (errorMessage.includes('GPU') && errorMessage.includes('not available')) {
                    this.showError('GPU mode is not available. Please install PyTorch with CUDA support or use cloud processing.');
                } else {
                    this.showError(errorMessage);
                }
            }
        } catch (error) {
            console.error('Error during extraction:', error);
            this.showError('Network error. Please try again.');
        } finally {
            this.hideLoading();
        }
    }

    displayResults(result) {
        this.extractionResults = result;
        
        // Update metadata
        document.getElementById('fileType').textContent = result.metadata.file_type.toUpperCase();
        document.getElementById('pagesProcessed').textContent = `${result.metadata.pages_processed} pages`;
        document.getElementById('processingTime').textContent = `${result.metadata.processing_time.toFixed(2)}s`;

        // Add processing mode to metadata if available
        if (result.metadata.processing_mode) {
            const processingModeElement = document.getElementById('processingMode');
            if (processingModeElement) {
                processingModeElement.textContent = result.metadata.processing_mode.toUpperCase();
            }
        }

        // Display content
        this.updatePreviewContent(result.content);
        this.updateRawContent(result.content);
        
        // Show results section
        document.getElementById('resultsSection').style.display = 'block';
        
        // Scroll to results
        document.getElementById('resultsSection').scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }

    updatePreviewContent(content) {
        const previewContent = document.getElementById('previewContent');
        
        // Format content based on output type
        const outputFormat = document.querySelector('input[name="outputFormat"]:checked').value;
        
        if (outputFormat === 'json' || outputFormat === 'flat-json') {
            try {
                const formatted = JSON.stringify(JSON.parse(content), null, 2);
                previewContent.innerHTML = `<pre class="json-preview">${this.escapeHtml(formatted)}</pre>`;
            } catch (e) {
                previewContent.textContent = content;
            }
        } else if (outputFormat === 'html') {
            previewContent.innerHTML = content;
        } else {
            previewContent.textContent = content;
        }
    }

    updateRawContent(content) {
        const rawContent = document.getElementById('rawContent');
        rawContent.textContent = content;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update tab content
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        document.getElementById(tabName).classList.add('active');
    }

    showLoading() {
        const submitBtn = document.getElementById('submitBtn');
        const btnText = submitBtn.querySelector('.btn-text');
        const spinner = submitBtn.querySelector('.spinner');
        
        btnText.textContent = 'Processing...';
        spinner.style.display = 'block';
        submitBtn.disabled = true;
    }

    hideLoading() {
        const submitBtn = document.getElementById('submitBtn');
        const btnText = submitBtn.querySelector('.btn-text');
        const spinner = submitBtn.querySelector('.spinner');
        
        btnText.textContent = 'Extract Content';
        spinner.style.display = 'none';
        submitBtn.disabled = false;
    }

    showError(message) {
        // Create error notification
        const notification = document.createElement('div');
        notification.className = 'error-notification';
        notification.innerHTML = `
            <div class="error-content">
                <span class="error-icon">⚠️</span>
                <span class="error-message">${message}</span>
                <button class="error-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;
        
        // Add styles
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #D02B2B;
            color: white;
            padding: 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            max-width: 400px;
        `;
        
        notification.querySelector('.error-content').style.cssText = `
            display: flex;
            align-items: center;
            gap: 12px;
        `;
        
        notification.querySelector('.error-close').style.cssText = `
            background: none;
            border: none;
            color: white;
            font-size: 20px;
            cursor: pointer;
            margin-left: auto;
        `;
        
        document.body.appendChild(notification);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }

    hideResults() {
        document.getElementById('resultsSection').style.display = 'none';
    }
}

// Global functions for HTML onclick handlers
function removeFile() {
    if (window.docStrangeApp) {
        window.docStrangeApp.removeFile();
    }
}

function downloadAsText() {
    if (window.docStrangeApp && window.docStrangeApp.extractionResults) {
        const content = window.docStrangeApp.extractionResults.content;
        const fileName = window.docStrangeApp.selectedFile.name;
        const outputFormat = document.querySelector('input[name="outputFormat"]:checked').value;
        const extension = outputFormat === 'json' ? 'json' : outputFormat === 'html' ? 'html' : 'txt';
        
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName.split('.')[0]}_extracted.${extension}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

function downloadAsJson() {
    if (window.docStrangeApp && window.docStrangeApp.extractionResults) {
        const result = {
            content: window.docStrangeApp.extractionResults.content,
            metadata: window.docStrangeApp.extractionResults.metadata,
            original_file: window.docStrangeApp.selectedFile.name
        };
        
        const fileName = window.docStrangeApp.selectedFile.name;
        const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName.split('.')[0]}_extraction_result.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.docStrangeApp = new DocStrangeApp();
}); 