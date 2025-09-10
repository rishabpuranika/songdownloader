from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from yt_dlp import YoutubeDL
from flask_socketio import SocketIO
import logging
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
socketio = SocketIO(app)

# --- IMPORTANT CHANGE ---
# On Render, we can't reliably write to the user's home directory.
# We'll use a temporary directory within the project's instance storage.
# Render's filesystem is ephemeral, which is fine since we just need to
# store the file long enough for the user to download it.
OUTPUT_DIR = os.path.join(os.getcwd(), "temp_downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.info(f"Output directory set to: {OUTPUT_DIR}")


def progress_hook(d):
    if d['status'] == 'downloading':
        try:
            # This function is called from a different thread, so we use socketio.emit
            progress = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            socketio.emit('download_progress', {
                'progress': progress,
                'speed': speed,
                'eta': eta,
                'filename': d.get('filename', '')
            })
        except Exception as e:
            logging.error(f"Error in progress hook: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

# --- NEW ROUTE TO SERVE THE FILE ---
@app.route('/download_file/<path:filename>')
def download_file(filename):
    """
    This route serves the downloaded file to the user.
    """
    logging.info(f"Serving file: {filename} from directory: {OUTPUT_DIR}")
    try:
        return send_from_directory(
            OUTPUT_DIR,
            filename,
            as_attachment=True # This tells the browser to prompt a download
        )
    except FileNotFoundError:
        logging.error(f"File not found: {filename}")
        return "File not found.", 404


@app.route('/get_download_url', methods=['POST'])
def get_download_url():
    """Extract video info and always use server processing for consistent direct downloads"""
    video_url = request.json.get('url')
    format_type = request.json.get('format')
    quality = request.json.get('quality', 'best')
    
    if not video_url:
        return jsonify({'success': False, 'error': 'URL is required'})

    cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
    base_opts = {
        'nocheckcertificate': True,
        'quiet': True,  # Reduce noise for URL extraction
        # Use mweb client as recommended for current YouTube issues
        'extractor_args': {
            'youtube': {
                'client': ['mweb'],
                'lang': ['en'],
                'region': ['US']
            }
        },
        # Use a realistic user agent
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    if os.path.exists(cookies_path):
        logging.info("Using cookies.txt file for authentication.")
        base_opts['cookiefile'] = cookies_path

    try:
        # Extract video info to validate URL and get title
        ydl_opts = base_opts.copy()
        
        with YoutubeDL(ydl_opts) as ydl:
            logging.info(f"Extracting video info for: {video_url}")
            logging.info(f"Requested format: {format_type}, quality: {quality}")
            
            # Extract video info without downloading
            info = ydl.extract_info(video_url, download=False)
            
            title = info.get('title', 'Unknown')
            logging.info(f"Successfully extracted info for: {title}")
            
            # Always use server processing for consistent downloads
            # This ensures files are downloaded directly to user's device without redirects
            return jsonify({
                'success': True,
                'needs_processing': True,
                'title': title,
                'format': format_type,
                'message': f'{format_type.upper()} will be processed on server for direct download'
            })

    except Exception as e:
        logging.error(f"Error extracting video info: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download', methods=['POST'])
def download():
    """Fallback server-side download for audio formats that need processing"""
    video_url = request.json.get('url')
    format_type = request.json.get('format')
    quality = request.json.get('quality', 'best')
    
    if not video_url:
        return jsonify({'success': False, 'error': 'URL is required'})

    cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
    base_opts = {
        'outtmpl': os.path.join(OUTPUT_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'nocheckcertificate': True,
        # Use mweb client as recommended for current YouTube issues
        'extractor_args': {
            'youtube': {
                'client': ['mweb'],
                'lang': ['en'],
                'region': ['US']
            }
        },
        # Use a realistic user agent
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    if os.path.exists(cookies_path):
        logging.info("Using cookies.txt file for authentication.")
        base_opts['cookiefile'] = cookies_path

    try:
        # Determine format options
        if format_type == 'mp3':
            ydl_opts = {
                **base_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        elif format_type == 'mp4':
            # Use yt-dlp's native HLS/m3u8 handling - it can download and convert to MP4
            # More robust format selection that handles HLS streams
            quality_map = {
                '1080p': 'best[height<=1080]/bestvideo[height<=1080]+bestaudio/best',
                '720p': 'best[height<=720]/bestvideo[height<=720]+bestaudio/best', 
                '480p': 'best[height<=480]/bestvideo[height<=480]+bestaudio/best',
                '360p': 'best[height<=360]/bestvideo[height<=360]+bestaudio/best',
                'best': 'best/bestvideo+bestaudio/best',
            }
            ydl_opts = {
                **base_opts,
                'format': quality_map.get(quality, quality_map['best']),
                'merge_output_format': 'mp4',  # Force final output to be MP4
                'outtmpl': os.path.join(OUTPUT_DIR, '%(title)s.mp4'),  # Force MP4 extension in filename
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }
        elif format_type == 'wav':
            ydl_opts = {
                **base_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                }],
            }
        else:
            return jsonify({'success': False, 'error': 'Invalid format'})

        with YoutubeDL(ydl_opts) as ydl:
            # We run the download in a separate thread so the main request can finish.
            # The result is communicated back via Socket.IO.
            def do_download():
                try:
                    logging.info(f"Starting {format_type.upper()} download for URL: {video_url}")
                    if format_type == 'mp4':
                        logging.info("Using HLS/m3u8-compatible format selection with MP4 conversion")
                    info = ydl.extract_info(video_url, download=True)
                    logging.info(f"Download info extracted: {info.get('title', 'Unknown')}")
                    logging.info(f"Requested format: {format_type.upper()}, Quality: {quality}")
                    
                    # --- FILENAME LOGIC ---
                    # We need the final filename after post-processing
                    filename = ydl.prepare_filename(info)
                    logging.info(f"Initial filename: {filename}")
                    
                    if format_type in ['mp3', 'wav']:
                        # For audio formats, the extension changes.
                        filename = os.path.splitext(filename)[0] + '.' + format_type
                    elif format_type == 'mp4':
                        # For MP4, ensure the extension is .mp4 (especially for HLS/m3u8 conversions)
                        filename = os.path.splitext(filename)[0] + '.mp4'
                    
                    base_filename = os.path.basename(filename)
                    full_path = os.path.join(OUTPUT_DIR, base_filename)
                    
                    # Check if file actually exists
                    if os.path.exists(full_path):
                        logging.info(f"Download complete. Final filename: {base_filename}")
                        logging.info(f"File size: {os.path.getsize(full_path)} bytes")
                        
                        socketio.emit('download_complete', {
                            'success': True,
                            'filename': base_filename,
                        })
                    else:
                        # Try to find the actual file that was created
                        actual_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(os.path.splitext(base_filename)[0])]
                        if actual_files:
                            actual_filename = actual_files[0]
                            logging.info(f"Found actual file: {actual_filename}")
                            socketio.emit('download_complete', {
                                'success': True,
                                'filename': actual_filename,
                            })
                        else:
                            raise Exception(f"Downloaded file not found. Expected: {base_filename}")
                    
                except Exception as e:
                    logging.error(f"Error during download thread: {str(e)}")
                    import traceback
                    logging.error(f"Full traceback: {traceback.format_exc()}")
                    socketio.emit('download_error', {'error': str(e)})

            # Use socketio.start_background_task for proper handling
            logging.info("Starting background download task")
            socketio.start_background_task(do_download)

        # Immediately return success to the client, the actual result comes via socket
        return jsonify({'success': True, 'message': 'Download started...'})

    except Exception as e:
        logging.error(f"Error in /download route: {str(e)}")
        socketio.emit('download_error', {'error': str(e)})
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Use '0.0.0.0' to be accessible externally
    # Enable debug mode for local development
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode)
