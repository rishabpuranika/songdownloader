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
    """Extract direct download URL without downloading to server"""
    video_url = request.json.get('url')
    format_type = request.json.get('format')
    quality = request.json.get('quality', 'best')
    
    if not video_url:
        return jsonify({'success': False, 'error': 'URL is required'})

    cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
    base_opts = {
        'nocheckcertificate': True,
        'quiet': True,  # Reduce noise for URL extraction
    }
    if os.path.exists(cookies_path):
        logging.info("Using cookies.txt file for authentication.")
        base_opts['cookiefile'] = cookies_path

    try:
        # For URL extraction, don't specify format - get all available formats
        # This prevents format availability errors
        ydl_opts = base_opts.copy()  # Don't specify format selector
        
        # Store the requested format for later filtering
        requested_format = format_type
        requested_quality = quality

        with YoutubeDL(ydl_opts) as ydl:
            logging.info(f"Extracting download URL for: {video_url}")
            logging.info(f"Requested format: {requested_format}, quality: {requested_quality}")
            
            # Extract all available formats
            info = ydl.extract_info(video_url, download=False)  # Don't download, just extract info
            
            title = info.get('title', 'Unknown')
            logging.info(f"Successfully extracted info for: {title}")
            
            # For MP4, we can provide direct URL
            if requested_format == 'mp4':
                direct_url = None
                found_format = None
                
                # Try different ways to get the direct URL
                if 'url' in info:
                    direct_url = info['url']
                    found_format = {'note': 'Direct URL from info'}
                    logging.info("Found direct URL in main info")
                elif 'entries' in info and info['entries']:
                    # Handle playlists - take first entry
                    logging.info("Processing playlist - taking first entry")
                    first_entry = info['entries'][0]
                    if 'url' in first_entry:
                        direct_url = first_entry['url']
                        found_format = {'note': 'Direct URL from playlist entry'}
                    elif 'formats' in first_entry:
                        formats = first_entry['formats']
                        for fmt in formats:
                            if fmt.get('ext') == 'mp4' and fmt.get('url'):
                                direct_url = fmt['url']
                                found_format = fmt
                                break
                elif 'formats' in info and info['formats']:
                    formats = info['formats']
                    logging.info(f"Found {len(formats)} formats to analyze")
                    
                    # Filter formats - prefer progressive downloads but allow HLS as fallback
                    def is_progressive_format(fmt):
                        # Progressive formats are preferred (direct downloads)
                        if fmt.get('protocol') in ['https', 'http']:
                            url = fmt.get('url', '')
                            if not any(indicator in url.lower() for indicator in ['.m3u8', '/hls/', 'manifest', '.mpd']):
                                vcodec = fmt.get('vcodec', 'none')
                                acodec = fmt.get('acodec', 'none') 
                                # Skip audio-only formats
                                if vcodec == 'none' and acodec != 'none':
                                    return False
                                return fmt.get('url') is not None and vcodec != 'none'
                        return False
                    
                    def is_hls_format(fmt):
                        # HLS formats as fallback (m3u8 streams)
                        if fmt.get('protocol') in ['m3u8', 'm3u8_native']:
                            vcodec = fmt.get('vcodec', 'none')
                            acodec = fmt.get('acodec', 'none')
                            # Skip audio-only formats
                            if vcodec == 'none' and acodec != 'none':
                                return False
                            return fmt.get('url') is not None and vcodec != 'none'
                        return False
                    
                    # Try progressive formats first
                    progressive_formats = [fmt for fmt in formats if is_progressive_format(fmt)]
                    # Fallback to HLS formats if no progressive available
                    hls_formats = [fmt for fmt in formats if is_hls_format(fmt)]
                    
                    # Use progressive if available, otherwise HLS
                    valid_formats = progressive_formats if progressive_formats else hls_formats
                    format_type_desc = "progressive" if progressive_formats else "HLS streaming"
                    
                    logging.info(f"Found {len(progressive_formats)} progressive and {len(hls_formats)} HLS formats")
                    logging.info(f"Using {len(valid_formats)} {format_type_desc} formats")
                    
                    # Strategy 1: Find exact quality match with mp4
                    if requested_quality != 'best':
                        target_height = int(requested_quality.replace('p', '')) if requested_quality.endswith('p') else None
                        if target_height:
                            for fmt in valid_formats:
                                if (fmt.get('ext') == 'mp4' and 
                                    fmt.get('url') and 
                                    fmt.get('height') == target_height):
                                    direct_url = fmt['url']
                                    found_format = fmt
                                    logging.info(f"Found exact quality match: {requested_quality}")
                                    break
                    
                    # Strategy 2: Any mp4 format from valid formats
                    if not direct_url:
                        mp4_formats = [fmt for fmt in valid_formats if fmt.get('ext') == 'mp4' and fmt.get('url')]
                        if mp4_formats:
                            # Prefer formats with higher height
                            mp4_formats.sort(key=lambda x: x.get('height', 0), reverse=True)
                            direct_url = mp4_formats[0]['url']
                            found_format = mp4_formats[0]
                            logging.info(f"Found MP4 format: {found_format.get('format_note', 'Unknown')}")
                    
                    # Strategy 3: Any valid format with URL (last resort)
                    if not direct_url:
                        if valid_formats:
                            # Prefer mp4-like formats, then by file size/quality
                            valid_formats.sort(key=lambda x: (
                                x.get('ext') == 'mp4',
                                x.get('height', 0),
                                x.get('filesize', 0) or x.get('filesize_approx', 0) or 0
                            ), reverse=True)
                            direct_url = valid_formats[0]['url']
                            found_format = valid_formats[0]
                            logging.info(f"Using fallback format: {found_format.get('ext', 'unknown')} - {found_format.get('format_note', 'Unknown')}")
                        else:
                            logging.warning("No valid non-streaming formats found")
                
                if direct_url and found_format:
                    # Check if this is an HLS/streaming format - browsers can't download these directly
                    is_streaming = (found_format.get('protocol') in ['m3u8', 'm3u8_native', 'mpd'] or 
                                  any(indicator in direct_url.lower() for indicator in ['.m3u8', '/hls/', 'manifest', '.mpd']))
                    
                    if is_streaming:
                        logging.info(f"Found streaming format, requires server processing: {found_format.get('protocol', 'unknown')}")
                        # Force server processing for streaming formats
                        return jsonify({
                            'success': True,
                            'needs_processing': True,
                            'title': title,
                            'format': requested_format,
                            'message': f'Streaming format detected - will process on server and convert to {requested_format.upper()}'
                        })
                    else:
                        # Progressive download - browser can handle this directly
                        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        file_ext = found_format.get('ext', 'mp4') if found_format else 'mp4'
                        filename = f"{safe_title}.{file_ext}"
                        
                        logging.info(f"Direct download ready: {filename}")
                        
                        return jsonify({
                            'success': True,
                            'direct_url': direct_url,
                            'filename': filename,
                            'title': title,
                            'format': requested_format,
                            'actual_format': found_format.get('format_note', 'Unknown') if found_format else 'Unknown',
                            'resolution': f"{found_format.get('height', 'Unknown')}p" if found_format and found_format.get('height') else 'Unknown'
                        })
                else:
                    logging.warning(f"No direct URL found for {video_url}, falling back to server processing")
                    # Fallback to server-side download
                    return jsonify({
                        'success': True,
                        'needs_processing': True,
                        'title': title,
                        'format': requested_format,
                        'message': 'Direct download not available - will process on server'
                    })
            
            # For MP3/WAV, we need server-side processing
            else:
                return jsonify({
                    'success': True,
                    'needs_processing': True,
                    'title': title,
                    'format': requested_format,
                    'message': 'Audio conversion required - will process on server'
                })

    except Exception as e:
        logging.error(f"Error extracting download URL: {str(e)}")
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
