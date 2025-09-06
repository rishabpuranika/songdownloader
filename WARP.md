# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a Flask-based YouTube Downloader web application that allows users to download YouTube videos directly to their devices in various formats (MP3, MP4, WAV). The app uses yt-dlp for URL extraction and downloading, Flask-SocketIO for real-time communication, and is optimized for deployment on Render with minimal server storage usage.

## Development Commands

### Setup and Installation
```bash
# Install Python dependencies
pip install -r requirements.txt

# Alternative setup (Linux/Mac)
./requirements.bash

# Alternative setup (Windows)
requirements.bat
```

### Running the Application
```bash
# Development server with debug mode
python app.py

# Production server with Gunicorn (as configured for Render)
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
```

### Testing Downloads
```bash
# Test direct URL extraction functionality
python3 test_direct_download.py

# Test full application with browser
python3 app.py
# Then open http://localhost:5000 in browser
```

### Debugging
- Monitor console logs for detailed download information
- Check temp_downloads/ directory for server-processed files (audio formats only)
- Use browser developer tools to inspect direct download attempts

## Architecture Overview

### Core Components

**Flask Application (`app.py`)**
- Main Flask web server with SocketIO integration
- Download endpoint (`/download`) that accepts JSON requests
- File serving endpoint (`/download_file/<filename>`) for completed downloads
- Real-time progress reporting via WebSocket events

**Frontend (`templates/index.html`)**
- Single-page web interface with responsive design
- Socket.IO client for real-time progress updates
- Format selection (MP3, MP4, WAV) with quality options for video
- Real-time download progress bar and status updates

**Download Architecture**
- **Direct Downloads (MP4)**: Extracts direct download URLs using yt-dlp and triggers browser downloads
- **Server Processing (MP3/WAV)**: Uses server-side yt-dlp processing with FFmpeg for audio conversion
- **Dual-endpoint system**: `/get_download_url` for direct downloads, `/download` for server processing
- **Smart fallback**: Automatically falls back to server processing when direct URLs aren't available
- Background task processing via SocketIO for server-side downloads only

### Key Technical Details

**File Storage Strategy**
- **Direct downloads (MP4)**: No server storage - files download directly to user's device
- **Server processing (MP3/WAV)**: Temporary storage in `temp_downloads/` directory
- **Render-optimized**: Minimal server storage usage reduces deployment costs and storage constraints
- Files served via Flask's `send_from_directory` only for server-processed audio files

**Real-time Communication**
- Flask-SocketIO handles bidirectional communication
- Events: `download_progress`, `download_complete`, `download_error`
- Background task execution prevents request timeout issues

**Format Handling**
- **MP4**: Direct browser downloads using extracted YouTube URLs with quality selection (360p-1080p)
- **MP3/WAV**: Server-side processing with FFmpeg post-processing and `bestaudio/best` quality
- **Quality matching**: Direct URL extraction respects user quality preferences
- **Filename sanitization**: Safe filename generation for cross-platform compatibility

**Authentication Support**
- Optional cookies.txt file support for accessing restricted content
- Automatic detection and usage if present in project root

## Deployment Configuration

**Render Deployment (`render.yaml`)**
- Python 3.11.0 environment
- Gunicorn with eventlet worker class (required for SocketIO)
- Single worker configuration to avoid WebSocket connection issues
- Build command installs requirements, start command runs production server

**Environment Variables**
- `PORT`: Server port (defaults to 5000 for local development)
- `PYTHON_VERSION`: Set to 3.11.0 for Render deployment

## Dependencies

**Core Dependencies**
- `flask`: Web framework
- `yt_dlp`: YouTube video downloading and extraction
- `flask_socketio`: Real-time WebSocket communication
- `ffmpeg-python`: Audio format conversion
- `gunicorn`: Production WSGI server
- `eventlet`: Async support for SocketIO

**System Requirements**
- Python 3.11+
- FFmpeg (for audio conversion)
- Network access for YouTube downloads

## Development Notes

**Local Development**
- App runs on `http://localhost:5000` by default
- Debug mode controlled via `FLASK_DEBUG` environment variable (default: True)
- Enhanced logging provides detailed URL extraction and download information

**Download Flow**
1. **MP4 requests**: Try direct URL extraction first, fallback to server processing if needed
2. **MP3/WAV requests**: Always use server processing due to conversion requirements
3. **Error handling**: Comprehensive error reporting for both direct and server-processed downloads

**File Management**
- **Direct downloads**: No server files created - downloads go directly to user device
- **Server processing**: Files temporarily stored in `temp_downloads/` and cleaned up
- `.gitignore` excludes the `song/` directory (virtual environment)
- `temp_downloads/` directory created automatically if missing

**Error Handling**
- Download errors communicated via WebSocket events
- HTTP error responses for invalid requests
- File not found handling for download requests

**Frontend Architecture**
- Vanilla JavaScript with Socket.IO client library
- Responsive CSS Grid layout
- Progress tracking with percentage, speed, and ETA display
- Button state management during downloads
