# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language Preference

**IMPORTANT**: Always respond in Korean (한글) when working with this repository. This project is Korean-focused and all user interactions should be in Korean language.

## Development Commands

### Running the Application
```bash
./run.sh
```
This script automatically:
- Kills any existing process on port 5000
- Activates the Python virtual environment (`venv/`)
- Installs dependencies from `requirements.txt`
- Starts the Flask application on port 5000
- Opens a browser to http://localhost:5000

### Manual Setup (if needed)
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run application
python app.py
```

## Architecture Overview

This is a Flask-based web server that provides system monitoring and metrics collection capabilities for a Visionix device. The application serves both a web interface and API endpoints.

### Core Components

**Flask Application (`app.py:1-241`)**
- Main web server handling HTTP requests and metrics collection
- Prometheus metrics integration for monitoring system resources
- RESTful API endpoints for status and OCR time management

**Web Interface (`templates/index.html:1-365`)**
- Single-page web UI for interacting with the device
- Real-time status monitoring and OCR time management
- Built-in API examples and documentation

**Grafana Integration (`grafana_dashboard.json`)**
- Pre-configured dashboard for visualizing metrics
- System monitoring charts and alerts

### API Endpoints

**Status Management**
- `GET /status` - Retrieve current device status
- `POST /status` - Update device status (1=normal, 0=failed)

**OCR Time Management**
- `GET /ocr` - Retrieve current OCR timestamp
- `POST /ocr` - Update OCR time (accepts Unix timestamp or "HH:MM:SS" format)

**System Metrics**
- `GET /metrics` - Prometheus-formatted system metrics
- `GET /` - Web interface dashboard

### Metrics Collection

The application automatically collects and exposes these system metrics:

- **System Resources**: CPU usage, memory usage, disk usage
- **Network Statistics**: Bytes sent/received, packets sent/received  
- **Process Information**: Process count, thread count
- **Application Metrics**: HTTP request counters, response times
- **Custom Metrics**: Device status, OCR timestamp

Key metric functions:
- `collect_system_metrics()` (`app.py:64-103`) - Gathers all system metrics
- `parse_time_string()` (`app.py:45-62`) - Converts time strings to timestamps

### File Structure

```
visionix_device_webserver/
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── run.sh                   # Startup script
├── templates/
│   └── index.html           # Web interface
├── grafana_dashboard.json   # Grafana dashboard config
├── venv/                    # Python virtual environment
└── README.md               # Basic usage instructions
```

## Development Notes

**Dependencies** (`requirements.txt:1-3`):
- Flask: Web framework
- prometheus_client: Metrics collection and export
- psutil: System resource monitoring

**Port Configuration**: Application runs on port 5000 by default

**Browser Integration**: Application automatically opens browser on startup

**Metrics Format**: All metrics follow Prometheus format and naming conventions

## Testing the Application

Use the web interface at http://localhost:5000 to test functionality, or send HTTP requests directly to the API endpoints. The interface includes built-in Python code examples for API usage.