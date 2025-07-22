# JS Sentinel

**A beautiful, modern JavaScript file monitoring system with real-time change detection and intelligent diff analysis.**

[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org/)
[![Flask](https://img.shields.io/badge/flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **Monitor JavaScript files across the web, detect changes instantly, and visualize differences with stunning clarity.**

## Features

### **Smart Monitoring**
- **Real-time JavaScript change detection** with multiple algorithms
- **AST-based analysis** with intelligent fallback strategies
- **Deobfuscation support** for minified/obfuscated code
- **Configurable check intervals** (1 minute to 24 hours)
- **Background scheduling** with APScheduler

### **Powerful URL Management**
- **Single URL addition** with instant validation
- **Bulk import** from textarea (supports comments)
- **File upload** with drag & drop (.txt/.csv files)
- **Export/import** URL lists for backup
- **Pause/resume** individual URLs
- **URL status indicators** with real-time updates

### **Advanced Change Detection**
- **Multiple detection methods**: AST parsing, semantic analysis, content hashing
- **Smart normalization** removes timestamps, cache-busters, version strings
- **Confidence scoring** for change reliability
- **False positive reduction** with enhanced algorithms
- **Large file support** with intelligent chunking

### **Rich Diff Visualization**
- **Beautiful HTML diffs** with syntax highlighting
- **Line-by-line comparisons** with change indicators
- **Navigation between changes** with jump links
- **Statistics and metrics** (additions, deletions, modifications)
- **Obfuscation analysis** integrated into reports

### **Notifications & Integrations**
- **Discord webhook** support for instant alerts
- **Detailed logging** with structured data
- **Performance metrics** and monitoring stats
- **Content version history** with automatic cleanup

### **Modern UI/UX**
- **Glassmorphism design** with smooth animations
- **Responsive layout** for desktop and mobile
- **Dark mode support** with system preference detection
- **Real-time status updates** without page refreshes
- **Intuitive tab-based interface** for bulk operations

## Quick Start

### **Docker (Recommended)**

```bash
# Clone the repository
git clone https://github.com/yourusername/js-sentinel.git
cd js-sentinel

# Create environment file
echo "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL" > .env

# Build and run with Docker Compose
docker-compose up -d --build

# Access the dashboard
open http://localhost:5001
```

### **Manual Installation**

```bash
# Clone and setup
git clone https://github.com/yourusername/js-sentinel.git
cd js-sentinel

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# Run the application
python3 run_server.py
```

## Usage Guide

### Adding URLs to Monitor

#### **Single URL**
1. Navigate to the **Single URL** tab
2. Enter the JavaScript file URL
3. Click **Add URL**

#### **Bulk Import**
1. Switch to the **Bulk Import** tab
2. Paste multiple URLs (one per line)
3. Use `#` for comments
4. Click **Preview** to validate
5. Click **Import URLs**

```text
# Analytics Scripts
https://www.google-analytics.com/analytics.js
https://cdn.segment.com/analytics.js/v1/segment.min.js

# Application Scripts  
https://example.com/app.js
https://cdn.example.com/main.js
```

#### **File Upload**
1. Go to the **File Upload** tab
2. Drag & drop a .txt or .csv file
3. Preview the imported URLs
4. Click **Import from File**

### Starting Monitoring

1. Set your desired **check interval** (default: 5 minutes)
2. Click **Start Monitoring**
3. Monitor real-time status in the results area
4. View detected changes in the **Recent Changes** section

### Viewing Diffs

1. Changes appear automatically in the **Recent Changes** grid
2. Click any diff card to open the detailed comparison
3. Navigate between changes using the jump links
4. View statistics and obfuscation analysis

## Configuration

### Environment Variables

```bash
# Required
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL

# Optional
FLASK_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./database/monitor.db
```

### Application Settings

- **Check Interval**: 1-1440 minutes (configurable per monitoring session)
- **Content Retention**: Keeps last 5 versions per URL (configurable)
- **Diff Retention**: 90 days (configurable)
- **File Size Limits**: Automatically chunks large files (50KB chunks)

## Architecture

```
js-sentinel/
├── src/
│   ├── main.py              # Flask application factory
│   ├── models/              # Database models
│   ├── routes/              # API endpoints
│   ├── services/            # Business logic
│   │   ├── monitor_service.py      # Core monitoring
│   │   ├── scheduler_service.py    # Background jobs
│   │   ├── deobfuscator.py        # Code deobfuscation
│   │   ├── content_storage.py     # Version management
│   │   └── notification_service.py # Discord alerts
│   └── tasks.py             # Background task definitions
├── static/                  # Frontend assets
├── database/               # SQLite databases
├── logs/                   # Application logs
├── content_versions/       # Stored file versions
└── docker-compose.yml      # Container orchestration
```

## API Reference

### URLs Management
```http
GET    /api/urls                    # List all monitored URLs
POST   /api/urls                    # Add new URL
DELETE /api/urls/{id}               # Remove URL
PUT    /api/urls/{id}/toggle        # Toggle URL active status
```

### Monitoring Control
```http
GET    /api/status/monitoring       # Get monitoring status
POST   /api/schedule/add            # Start monitoring
DELETE /api/schedule/remove/{job_id} # Stop monitoring
POST   /api/monitor/check           # Manual check trigger
```

### Diffs & Changes
```http
GET    /api/diffs                   # List all diffs
GET    /api/diffs/{id}              # Download specific diff
DELETE /api/diffs                   # Clear all diffs
DELETE /api/diffs/{id}              # Delete specific diff
```

### System Status
```http
GET    /api/status                  # System statistics
GET    /api/schedule/list           # List scheduled jobs
```

## Development

### Running Tests
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Run with coverage
python -m pytest --cov=src tests/
```

### Local Development
```bash
# Enable debug mode
export FLASK_ENV=development

# Run with auto-reload
python3 run_server.py

# Access development server
open http://localhost:5001
```

## Performance & Scaling

- **Memory Usage**: ~50-100MB base, +10MB per 1000 monitored URLs
- **Storage**: ~1MB per URL per month (with 5 version retention)
- **Concurrent Monitoring**: Supports 100+ URLs simultaneously
- **Check Frequency**: Optimized for 1-60 minute intervals
- **Database**: SQLite for single-instance, easily upgradeable to PostgreSQL

## Security Features

- **Input validation** on all API endpoints
- **URL sanitization** and validation
- **Rate limiting** on check frequencies
- **Safe file handling** for uploads
- **No external code execution** (AST parsing only)
- **Configurable webhook validation**


### Development Setup
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Commit with conventional commits (`git commit -m 'feat: add amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Troubleshooting

### Common Issues

**Q: Monitoring shows "AST parsing failed"**
A: This is normal for non-JavaScript content. The system automatically falls back to content-based detection.

**Q: Too many false positives**
A: Adjust the normalization settings or check if the URLs contain dynamic timestamps.

**Q: Docker container won't start**
A: Ensure ports 5001 is available and check Docker logs with `docker-compose logs`.

**Q: Discord notifications not working**
A: Verify your webhook URL is correct and the Discord server allows webhook messages.
