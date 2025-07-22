const API_BASE_URL = '/api';
let monitoringInterval = null;
let isMonitoring = false;

// Utility functions
function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    notification.textContent = message;
    notification.className = `notification ${type}`;
    notification.classList.add('show');
    
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}

function updateResults(message) {
    const results = document.getElementById('monitoring-results');
    const timestamp = new Date().toLocaleTimeString();
    results.textContent += `[${timestamp}] ${message}\n`;
    results.scrollTop = results.scrollHeight;
}

// URL Management
async function addUrl() {
    const urlInput = document.getElementById('url-input');
    const url = urlInput.value.trim();
    
    if (!url) {
        showNotification('Please enter a valid URL', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/urls`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        if (response.ok) {
            urlInput.value = '';
            showNotification('URL added successfully');
            loadUrls();
        } else {
            const error = await response.json();
            showNotification(error.message || 'Failed to add URL', 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}

async function loadUrls() {
    try {
        const response = await fetch(`${API_BASE_URL}/urls`);
        const urls = await response.json();
        
        const urlList = document.getElementById('url-list');
        urlList.innerHTML = '';
        
        if (urls.length === 0) {
            urlList.innerHTML = '<p style="color: #718096; font-style: italic;">No URLs added yet</p>';
            return;
        }

        urls.forEach(urlData => {
            const urlItem = document.createElement('div');
            urlItem.className = 'url-item';
            urlItem.innerHTML = `
                <div style="display: flex; align-items: center;">
                    <div class="status-indicator ${urlData.active ? 'status-active' : 'status-inactive'}"></div>
                    <div class="url-text">${urlData.url}</div>
                </div>
                <button class="btn btn-danger" onclick="removeUrl(${urlData.id})">Remove</button>
            `;
            urlList.appendChild(urlItem);
        });
    } catch (error) {
        showNotification('Failed to load URLs: ' + error.message, 'error');
    }
}

async function removeUrl(id) {
    try {
        const response = await fetch(`${API_BASE_URL}/urls/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showNotification('URL removed successfully');
            loadUrls();
        } else {
            showNotification('Failed to remove URL', 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}

// Monitoring Controls
async function startMonitoring() {
    if (isMonitoring) return;
    
    const interval = parseInt(document.getElementById('monitor-interval').value) || 5;
    console.log('DEBUG: Starting monitoring with interval:', interval);
    
    try {
        console.log('DEBUG: Calling /api/schedule/add...');
        const response = await fetch('/api/schedule/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                interval_minutes: interval,
                job_id: 'monitor_urls'
            })
        });
        
        console.log('DEBUG: Response status:', response.status);
        const data = await response.json();
        console.log('DEBUG: Response data:', data);
        
        if (response.ok) {
            // Backend monitoring started successfully
            isMonitoring = true;
            document.getElementById('monitor-btn-text').innerHTML = '<div class="loading"></div>Monitoring...';
            
            const startButton = document.querySelector('button[onclick="startMonitoring()"]');
            startButton.disabled = true;
            startButton.classList.remove('btn-success');
            startButton.classList.add('btn-secondary');
            
            updateResults(`Backend monitoring started - checking every ${interval} minutes`);
            showNotification(`Monitoring started! Checking every ${interval} minutes.`);
            
            // Save state to browser storage
            localStorage.setItem('monitoringActive', 'true');
            localStorage.setItem('monitoringInterval', interval.toString());
            localStorage.setItem('monitoringStartTime', Date.now().toString());
            
            // Also start frontend monitoring as backup
            monitoringInterval = setInterval(async () => {
                await checkNow();
            }, interval * 60000);
            
            // Initial check
            await checkNow();
            
        } else {
            // Backend failed, try frontend-only monitoring
            console.error('DEBUG: Backend monitoring failed, starting frontend monitoring:', data);
            
            isMonitoring = true;
            document.getElementById('monitor-btn-text').innerHTML = '<div class="loading"></div>Monitoring...';
            
            const startButton = document.querySelector('button[onclick="startMonitoring()"]');
            startButton.disabled = true;
            startButton.classList.remove('btn-success');
            startButton.classList.add('btn-secondary');
            
            updateResults(`Backend failed: ${data.message || 'Unknown error'}`);
            updateResults(`Starting frontend monitoring instead - checking every ${interval} minutes`);
            showNotification(`Backend failed, using frontend monitoring (${interval} min intervals)`, 'error');
            
            // Save frontend state to browser storage
            localStorage.setItem('monitoringActive', 'frontend');
            localStorage.setItem('monitoringInterval', interval.toString());
            localStorage.setItem('monitoringStartTime', Date.now().toString());
            
            // Start frontend monitoring
            monitoringInterval = setInterval(async () => {
                await checkNow();
            }, interval * 60000);
            
            // Initial check
            await checkNow();
        }
        
    } catch (error) {
        // Network error, fall back to frontend monitoring
        console.error('DEBUG: Network error, starting frontend monitoring:', error);
        
        isMonitoring = true;
        document.getElementById('monitor-btn-text').innerHTML = '<div class="loading"></div>Monitoring...';
        
        const startButton = document.querySelector('button[onclick="startMonitoring()"]');
        startButton.disabled = true;
        startButton.classList.remove('btn-success');
        startButton.classList.add('btn-secondary');
        
        updateResults(`Network error: ${error.message}`);
        updateResults(`Starting frontend monitoring - checking every ${interval} minutes`);
        showNotification(`Network error, using frontend monitoring (${interval} min intervals)`, 'error');
        
        // Save frontend state to browser storage
        localStorage.setItem('monitoringActive', 'frontend');
        localStorage.setItem('monitoringInterval', interval.toString());
        localStorage.setItem('monitoringStartTime', Date.now().toString());
        
        // Start frontend monitoring as fallback
        monitoringInterval = setInterval(async () => {
            await checkNow();
        }, interval * 60000);
        
        // Initial check
        await checkNow();
    }
}

async function stopMonitoring() {
    if (!isMonitoring) return;
    
    try {
        console.log('DEBUG: Stopping backend monitoring...');
        
        // Call backend API to remove the scheduled job
        const response = await fetch('/api/schedule/remove/monitor_urls', {
            method: 'DELETE'
        });
        
        console.log('DEBUG: Stop response status:', response.status);
        const data = await response.json();
        console.log('DEBUG: Stop response data:', data);
        
        // Update frontend state regardless of backend response
        isMonitoring = false;
        document.getElementById('monitor-btn-text').textContent = 'Start Monitoring';
        
        const startButton = document.querySelector('button[onclick="startMonitoring()"]');
        startButton.disabled = false;
        startButton.classList.remove('btn-secondary');
        startButton.classList.add('btn-success');
        
        // Stop frontend monitoring if running
        if (monitoringInterval) {
            clearInterval(monitoringInterval);
            monitoringInterval = null;
        }
        
        // Clear browser storage
        localStorage.removeItem('monitoringActive');
        localStorage.removeItem('monitoringInterval');
        localStorage.removeItem('monitoringStartTime');
        
        if (response.ok) {
            updateResults('✅ Backend monitoring stopped successfully');
            showNotification('Monitoring stopped successfully');
        } else {
            updateResults(`⚠️ Backend stop failed: ${data.message}`);
            updateResults('✅ Frontend monitoring stopped');
            showNotification('Backend stop failed, but frontend stopped', 'error');
        }
        
    } catch (error) {
        console.error('DEBUG: Error stopping monitoring:', error);
        
        // Still update frontend even if backend call fails
        isMonitoring = false;
        document.getElementById('monitor-btn-text').textContent = 'Start Monitoring';
        
        const startButton = document.querySelector('button[onclick="startMonitoring()"]');
        startButton.disabled = false;
        startButton.classList.remove('btn-secondary');
        startButton.classList.add('btn-success');
        
        if (monitoringInterval) {
            clearInterval(monitoringInterval);
            monitoringInterval = null;
        }
        
        updateResults(`❌ Error stopping backend: ${error.message}`);
        updateResults('✅ Frontend monitoring stopped');
        showNotification('Error stopping backend, but frontend stopped', 'error');
    }
}

// Check monitoring status
async function checkMonitoringStatus() {
    try {
        const response = await fetch('/api/status/monitoring');
        const data = await response.json();
        
        const startButton = document.querySelector('button[onclick="startMonitoring()"]');
        const startButtonText = document.getElementById('monitor-btn-text');
        
        if (data.monitoring_active) {
            // Monitoring is active - update UI to show "Monitoring..."
            if (startButtonText) {
                startButtonText.innerHTML = '<div class="loading"></div>Monitoring...';
            } else {
                startButton.textContent = 'Monitoring...';
            }
            startButton.disabled = true;
            startButton.classList.remove('btn-success');
            startButton.classList.add('btn-secondary');
            isMonitoring = true;
            
            updateResults('✅ Monitoring is active - checking every few minutes...');
            
            // Optionally show next run time
            if (data.next_run_time) {
                const nextRun = new Date(data.next_run_time).toLocaleTimeString();
                updateResults(`📅 Next check scheduled at: ${nextRun}`);
            }
        } else {
            // Monitoring is not active - update UI to show "Start Monitoring"
            if (startButtonText) {
                startButtonText.textContent = 'Start Monitoring';
            } else {
                startButton.textContent = 'Start Monitoring';
            }
            startButton.disabled = false;
            startButton.classList.remove('btn-secondary');
            startButton.classList.add('btn-success');
            isMonitoring = false;
        }
    } catch (error) {
        console.error('Error checking monitoring status:', error);
        updateResults('⚠️ Could not check monitoring status: ' + error.message);
    }
}

async function checkNow() {
    try {
        updateResults('Checking for changes...');
        
        const response = await fetch(`${API_BASE_URL}/monitor/check`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            updateResults(`Check completed: ${result.message}`);
            if (result.changes_detected) {
                showNotification('Changes detected! Check the diffs section.');
                loadDiffs();
            }
        } else {
            updateResults(`Check failed: ${result.message}`);
            showNotification('Check failed: ' + result.message, 'error');
        }
    } catch (error) {
        updateResults(`Check error: ${error.message}`);
        showNotification('Check error: ' + error.message, 'error');
    }
}

// Diff Viewer
async function loadDiffs() {
    try {
        const response = await fetch(`${API_BASE_URL}/diffs`);
        const diffs = await response.json();
        
        const diffList = document.getElementById('diff-list');
        diffList.innerHTML = '';
        
        if (diffs.length === 0) {
            diffList.innerHTML = '<p style="color: #718096; font-style: italic;">No diffs available</p>';
            return;
        }

        diffs.forEach(diff => {
            const diffItem = document.createElement('div');
            diffItem.className = 'diff-item';
            diffItem.onclick = () => viewDiff(diff.id);
            
            diffItem.innerHTML = `
                <div class="diff-title">${diff.filename}</div>
                <div class="diff-date">${new Date(diff.created_at).toLocaleString()}</div>
                <div class="diff-preview">${diff.preview || 'Click to view full diff'}</div>
            `;
            diffList.appendChild(diffItem);
        });
    } catch (error) {
        showNotification('Failed to load diffs: ' + error.message, 'error');
    }
}

async function viewDiff(diffId) {
    try {
        const response = await fetch(`${API_BASE_URL}/diffs/${diffId}`);
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            window.open(url, '_blank');
        } else {
            showNotification('Failed to load diff', 'error');
        }
    } catch (error) {
        showNotification('Error loading diff: ' + error.message, 'error');
    }
}

async function clearDiffs() {
    if (!confirm('Are you sure you want to clear all diffs?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/diffs`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showNotification('All diffs cleared');
            loadDiffs();
        } else {
            showNotification('Failed to clear diffs', 'error');
        }
    } catch (error) {
        showNotification('Error clearing diffs: ' + error.message, 'error');
    }
}
// Add these functions to your existing script.js file

// Global variables for file handling
let uploadedFileContent = '';
let currentTab = 'single';

// Tab Management
function switchUrlTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Remove active class from all tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab content
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Add active class to clicked tab button
    event.target.classList.add('active');
    
    currentTab = tabName;
}

// Bulk URL Management
function validateUrl(url) {
    const urlPattern = /^https?:\/\/.+\..+/i;
    return urlPattern.test(url.trim());
}

function extractUrlsFromText(text) {
    return text
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
        .filter(line => !line.startsWith('#')); // Allow comments with #
}

function previewBulkUrls() {
    const bulkText = document.getElementById('bulk-urls').value;
    const urls = extractUrlsFromText(bulkText);
    
    const preview = document.getElementById('bulk-preview');
    
    if (urls.length === 0) {
        preview.innerHTML = '<div class="validation-error">❌ No URLs found. Please enter one URL per line.</div>';
        preview.classList.add('show');
        return;
    }
    
    const validUrls = [];
    const invalidUrls = [];
    
    urls.forEach(url => {
        if (validateUrl(url)) {
            validUrls.push(url);
        } else {
            invalidUrls.push(url);
        }
    });
    
    let previewHtml = `
        <div class="bulk-stats">
            <div class="stat-item">
                <span class="stat-number">${urls.length}</span>
                <span>Total URLs</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" style="color: #38a169;">${validUrls.length}</span>
                <span>Valid</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" style="color: #e53e3e;">${invalidUrls.length}</span>
                <span>Invalid</span>
            </div>
        </div>
    `;
    
    if (validUrls.length > 0) {
        previewHtml += '<div class="validation-success">✅ Valid URLs:</div>';
        validUrls.slice(0, 5).forEach(url => {
            previewHtml += `<div style="margin: 5px 0; color: #38a169;">• ${url}</div>`;
        });
        if (validUrls.length > 5) {
            previewHtml += `<div style="color: #718096; font-style: italic;">... and ${validUrls.length - 5} more</div>`;
        }
    }
    
    if (invalidUrls.length > 0) {
        previewHtml += '<div class="validation-error">❌ Invalid URLs:</div>';
        invalidUrls.forEach(url => {
            previewHtml += `<div style="margin: 5px 0; color: #e53e3e;">• ${url}</div>`;
        });
    }
    
    preview.innerHTML = previewHtml;
    preview.classList.add('show');
}

async function addBulkUrls() {
    const bulkText = document.getElementById('bulk-urls').value;
    const urls = extractUrlsFromText(bulkText);
    
    if (urls.length === 0) {
        showNotification('No URLs to import', 'error');
        return;
    }
    
    const validUrls = urls.filter(url => validateUrl(url));
    
    if (validUrls.length === 0) {
        showNotification('No valid URLs found', 'error');
        return;
    }
    
    let successCount = 0;
    let errorCount = 0;
    const errors = [];
    
    updateResults(`Starting bulk import of ${validUrls.length} URLs...`);
    
    for (const url of validUrls) {
        try {
            const response = await fetch(`${API_BASE_URL}/urls`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim() })
            });
            
            if (response.ok) {
                successCount++;
                updateResults(`✅ Added: ${url}`);
            } else {
                const error = await response.json();
                errorCount++;
                errors.push(`${url}: ${error.message}`);
                updateResults(`❌ Failed: ${url} - ${error.message}`);
            }
        } catch (error) {
            errorCount++;
            errors.push(`${url}: Network error`);
            updateResults(`❌ Error: ${url} - Network error`);
        }
    }
    
    // Show summary
    const summary = `Bulk import completed: ${successCount} added, ${errorCount} failed`;
    updateResults(`📊 ${summary}`);
    
    if (successCount > 0) {
        showNotification(`Successfully imported ${successCount} URLs!`, 'success');
        document.getElementById('bulk-urls').value = '';
        document.getElementById('bulk-preview').classList.remove('show');
        loadUrls();
    }
    
    if (errorCount > 0) {
        showNotification(`${errorCount} URLs failed to import`, 'error');
    }
}

function clearBulkInput() {
    document.getElementById('bulk-urls').value = '';
    document.getElementById('bulk-preview').classList.remove('show');
}

// File Upload Management
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add('dragover');
}

function handleFileDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        processFile(files[0]);
    }
}

function handleFileUpload(e) {
    const file = e.target.files[0];
    if (file) {
        processFile(file);
    }
}

function processFile(file) {
    if (!file.name.endsWith('.txt') && !file.name.endsWith('.csv')) {
        showNotification('Please upload a .txt or .csv file', 'error');
        return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
        uploadedFileContent = e.target.result;
        showFilePreview(uploadedFileContent, file.name);
    };
    reader.readAsText(file);
}

function showFilePreview(content, filename) {
    const urls = extractUrlsFromText(content);
    const preview = document.getElementById('file-preview');
    
    if (urls.length === 0) {
        preview.innerHTML = `
            <div class="validation-error">
                ❌ No URLs found in "${filename}". 
                <br>Make sure each URL is on a separate line.
            </div>
        `;
        preview.classList.add('show');
        return;
    }
    
    const validUrls = urls.filter(url => validateUrl(url));
    const invalidUrls = urls.filter(url => !validateUrl(url));
    
    let previewHtml = `
        <div style="margin-bottom: 15px; font-weight: 600; color: #4a5568;">
            📁 File: ${filename}
        </div>
        <div class="bulk-stats">
            <div class="stat-item">
                <span class="stat-number">${urls.length}</span>
                <span>Total URLs</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" style="color: #38a169;">${validUrls.length}</span>
                <span>Valid</span>
            </div>
            <div class="stat-item">
                <span class="stat-number" style="color: #e53e3e;">${invalidUrls.length}</span>
                <span>Invalid</span>
            </div>
        </div>
    `;
    
    if (validUrls.length > 0) {
        previewHtml += '<div class="validation-success">✅ Preview (first 5 valid URLs):</div>';
        validUrls.slice(0, 5).forEach(url => {
            previewHtml += `<div style="margin: 5px 0; color: #38a169;">• ${url}</div>`;
        });
        if (validUrls.length > 5) {
            previewHtml += `<div style="color: #718096; font-style: italic;">... and ${validUrls.length - 5} more</div>`;
        }
    }
    
    preview.innerHTML = previewHtml;
    preview.classList.add('show');
}

async function processUploadedFile() {
    if (!uploadedFileContent) {
        showNotification('Please upload a file first', 'error');
        return;
    }
    
    const urls = extractUrlsFromText(uploadedFileContent);
    const validUrls = urls.filter(url => validateUrl(url));
    
    if (validUrls.length === 0) {
        showNotification('No valid URLs found in file', 'error');
        return;
    }
    
    let successCount = 0;
    let errorCount = 0;
    
    updateResults(`Starting file import of ${validUrls.length} URLs...`);
    
    for (const url of validUrls) {
        try {
            const response = await fetch(`${API_BASE_URL}/urls`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url.trim() })
            });
            
            if (response.ok) {
                successCount++;
                updateResults(`✅ Added: ${url}`);
            } else {
                const error = await response.json();
                errorCount++;
                updateResults(`❌ Failed: ${url} - ${error.message}`);
            }
        } catch (error) {
            errorCount++;
            updateResults(`❌ Error: ${url} - Network error`);
        }
    }
    
    const summary = `File import completed: ${successCount} added, ${errorCount} failed`;
    updateResults(`📊 ${summary}`);
    
    if (successCount > 0) {
        showNotification(`Successfully imported ${successCount} URLs from file!`, 'success');
        uploadedFileContent = '';
        document.getElementById('file-preview').classList.remove('show');
        document.getElementById('url-file').value = '';
        loadUrls();
    }
    
    if (errorCount > 0) {
        showNotification(`${errorCount} URLs failed to import`, 'error');
    }
}

function downloadTemplate() {
    const template = `# JavaScript Monitor URL List Template
# Lines starting with # are comments and will be ignored
# Add one URL per line

https://example.com/script1.js
https://example.com/script2.js
https://example.com/script3.js

# You can organize URLs with comments:
# Social Media Scripts
https://platform.twitter.com/widgets.js
https://connect.facebook.net/en_US/sdk.js

# Analytics Scripts
https://www.google-analytics.com/analytics.js
https://cdn.example.com/tracking.js`;

    const blob = new Blob([template], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'url-template.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    showNotification('Template downloaded!', 'success');
}

// URL List Management
async function exportUrls() {
    try {
        const response = await fetch(`${API_BASE_URL}/urls`);
        const urls = await response.json();
        
        if (urls.length === 0) {
            showNotification('No URLs to export', 'error');
            return;
        }
        
        const exportText = urls.map(urlData => urlData.url).join('\n');
        const blob = new Blob([exportText], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `monitored-urls-${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showNotification(`Exported ${urls.length} URLs!`, 'success');
        updateResults(`📤 Exported ${urls.length} URLs to file`);
    } catch (error) {
        showNotification('Failed to export URLs: ' + error.message, 'error');
    }
}

async function clearAllUrls() {
    const confirmed = confirm('⚠️ Are you sure you want to remove ALL monitored URLs?\n\nThis action cannot be undone!');
    if (!confirmed) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/urls`);
        const urls = await response.json();
        
        if (urls.length === 0) {
            showNotification('No URLs to clear', 'error');
            return;
        }
        
        let deletedCount = 0;
        
        for (const urlData of urls) {
            try {
                const deleteResponse = await fetch(`${API_BASE_URL}/urls/${urlData.id}`, {
                    method: 'DELETE'
                });
                
                if (deleteResponse.ok) {
                    deletedCount++;
                    updateResults(`🗑️ Removed: ${urlData.url}`);
                }
            } catch (error) {
                updateResults(`❌ Failed to remove: ${urlData.url}`);
            }
        }
        
        showNotification(`Cleared ${deletedCount} URLs!`, 'success');
        updateResults(`🧹 Bulk deletion completed: ${deletedCount} URLs removed`);
        loadUrls();
        
    } catch (error) {
        showNotification('Failed to clear URLs: ' + error.message, 'error');
    }
}

// Enhanced URL list loading with counter
async function loadUrls() {
    try {
        const response = await fetch(`${API_BASE_URL}/urls`);
        const urls = await response.json();
        
        const urlList = document.getElementById('url-list');
        urlList.innerHTML = '';
        
        // Add URL counter
        const counterHtml = `
            <div class="url-counter">
                <span>📊</span>
                <span>${urls.length} URL${urls.length !== 1 ? 's' : ''} monitored</span>
            </div>
        `;
        
        if (urls.length === 0) {
            urlList.innerHTML = counterHtml + '<p style="color: #718096; font-style: italic; margin-top: 20px;">No URLs added yet. Use the tabs above to add single URLs, bulk import, or upload a file.</p>';
            return;
        }

        urlList.innerHTML = counterHtml;

        urls.forEach(urlData => {
            const urlItem = document.createElement('div');
            urlItem.className = 'url-item';
            urlItem.innerHTML = `
                <div style="display: flex; align-items: center; flex: 1;">
                    <div class="status-indicator ${urlData.active ? 'status-active' : 'status-inactive'}"></div>
                    <div class="url-text">${urlData.url}</div>
                </div>
                <div class="url-actions-mini">
                    <button class="btn btn-danger" onclick="removeUrl(${urlData.id})" title="Remove URL">
                        🗑️
                    </button>
                </div>
            `;
            urlList.appendChild(urlItem);
        });
    } catch (error) {
        showNotification('Failed to load URLs: ' + error.message, 'error');
    }
}

// Toggle URL active status
async function toggleUrl(id) {
    try {
        const response = await fetch(`${API_BASE_URL}/urls/${id}/toggle`, {
            method: 'PUT'
        });

        if (response.ok) {
            const urlData = await response.json();
            showNotification(`URL ${urlData.active ? 'activated' : 'paused'}`, 'success');
            loadUrls();
        } else {
            showNotification('Failed to toggle URL status', 'error');
        }
    } catch (error) {
        showNotification('Network error: ' + error.message, 'error');
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadUrls();
    loadDiffs();
    updateResults('Dashboard initialized');
    
    // Check monitoring status on page load
    checkMonitoringStatus();
    
    // Check status every 30 seconds to keep UI updated
    setInterval(checkMonitoringStatus, 30000);
});
