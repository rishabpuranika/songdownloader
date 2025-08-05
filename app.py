from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from yt_dlp import YoutubeDL
from flask_socketio import SocketIO
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

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


@app.route('/download', methods=['POST'])
def download():
    video_url = request.json.get('url')
    format_type = request.json.get('format')
    quality = request.json.get('quality', 'best')
    
    if not video_url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400

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
            quality_map = {
                '1080p': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
                '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best',
                '360p': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best',
                'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            }
            ydl_opts = {
                **base_opts,
                'format': quality_map.get(quality, quality_map['best']),
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
                    info = ydl.extract_info(video_url, download=True)
                    # --- FILENAME LOGIC ---
                    # We need the final filename after post-processing
                    filename = ydl.prepare_filename(info)
                    if format_type in ['mp3', 'wav']:
                        # For audio formats, the extension changes.
                        filename = os.path.splitext(filename)[0] + '.' + format_type
                    
                    base_filename = os.path.basename(filename)
                    logging.info(f"Download complete. Final filename: {base_filename}")
                    
                    socketio.emit('download_complete', {
                        'success': True,
                        'filename': base_filename,
                    })
                except Exception as e:
                    logging.error(f"Error during download thread: {str(e)}")
                    socketio.emit('download_error', {'error': str(e)})

            # Use socketio.start_background_task for proper handling
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
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
