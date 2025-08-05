from flask import Flask, render_template, request, jsonify
import os
from yt_dlp import YoutubeDL
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)
# Save to user's Downloads folder (cross-platform)
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def progress_hook(d):
    if d['status'] == 'downloading':
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

@app.route('/download', methods=['POST'])
def download():
    video_url = request.json.get('url')
    format_type = request.json.get('format')
    quality = request.json.get('quality', 'best')

    # Add cookies.txt support if present
    cookies_path = os.path.join(os.path.dirname(__file__), 'cookies.txt')
    base_opts = {
        'outtmpl': os.path.join(OUTPUT_DIR, '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
    }
    if os.path.exists(cookies_path):
        base_opts['cookiefile'] = cookies_path

    try:

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
            # Map quality to yt-dlp format string
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
            info = ydl.extract_info(video_url, download=True)
            extension = 'mp3' if format_type == 'mp3' else ('mp4' if format_type == 'mp4' else 'wav')
            filename = f"{info['title']}.{extension}"
            full_path = os.path.join(OUTPUT_DIR, filename)

            socketio.emit('download_complete', {
                'success': True,
                'filename': filename,
                'file_path': full_path
            })
            return jsonify({'success': True})

    except Exception as e:
        socketio.emit('download_error', {'error': str(e)})
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)