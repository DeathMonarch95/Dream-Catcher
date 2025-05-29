import os
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import yt_dlp
import uuid # For unique filenames

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Define the route for the main page (index.html)
@app.route('/')
def serve_index():
    return send_file('index.html')

@app.route('/download', methods=['POST'])
def download_video_audio():
    # ... (rest of your existing /download route code)
    data = request.json
    url = data.get('url')
    format_type = data.get('format', 'video')

    if not url:
        return jsonify({"error": "URL is required.", "success": False}), 400

    # Create a unique filename
    unique_filename = str(uuid.uuid4())
    output_path = f"/tmp/{unique_filename}.%(ext)s" # Use /tmp for temporary storage on Render

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]' if format_type == 'video' else 'bestaudio/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4' if format_type == 'video' else None,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }] if format_type == 'audio' else [],
        'external_downloader': 'ffmpeg', # Explicitly use ffmpeg if available
        'external_downloader_args': ['-loglevel', 'error'] # Suppress verbose ffmpeg output
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            
            # Determine the actual downloaded file path
            # yt-dlp 2024.x.x changed how info_dict returns file paths
            # It's better to check for 'requested_downloads' or use glob if possible
            downloaded_filepath = None
            if 'requested_downloads' in info_dict and info_dict['requested_downloads']:
                downloaded_filepath = info_dict['requested_downloads'][0]['filepath']
            elif '_format_sort_fields' in info_dict: # Sometimes for single file
                downloaded_filepath = ydl.prepare_filename(info_dict) # Fallback, might not be exact after post-processing
            elif 'filepath' in info_dict: # For simple downloads
                 downloaded_filepath = info_dict['filepath']

            if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                # Fallback if specific path isn't found in info_dict
                # Look for files matching the unique_filename pattern in /tmp
                import glob
                matching_files = glob.glob(f'/tmp/{unique_filename}.*')
                if matching_files:
                    downloaded_filepath = matching_files[0]

            if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                print(f"DEBUG: yt-dlp output path: {output_path}") # Debugging
                print(f"DEBUG: info_dict: {info_dict}") # Debugging
                return jsonify({"error": "Downloaded file not found. yt-dlp might have failed to save the file or saved it elsewhere. Check server logs for yt-dlp output.", "success": False}), 500

            return send_file(downloaded_filepath, as_attachment=True, download_name=os.path.basename(downloaded_filepath))

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == '__main__':
    app.run(debug=True)