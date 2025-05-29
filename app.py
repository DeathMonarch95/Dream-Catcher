import os
import tempfile
import uuid
import logging
import re

from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from yt_dlp import YoutubeDL

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Set yt-dlp's logger to WARNING to avoid excessive output from it unless it's a serious issue
logging.getLogger('yt_dlp').setLevel(logging.WARNING)

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Define the route for the main page (index.html)
@app.route('/')
def serve_index():
    logging.info("Serving index.html")
    return send_file('index.html')

@app.route('/download', methods=['POST'])
def download_media(): # This is the ONLY download function definition you should have
    """
    Handles download requests from the frontend.
    Expects a JSON payload with 'url' and 'format' ('video' or 'audio').
    """
    try:
        data = request.get_json()
        youtube_url = data.get('url')
        format_type = data.get('format')

        logging.info(f"Received download request for URL: {youtube_url}, format: {format_type}")

        # --- Input Validation ---
        if not youtube_url:
            logging.error("YouTube URL is required.")
            return jsonify({"success": False, "error": "YouTube URL is required."}), 400
        if not format_type or format_type not in ['video', 'audio']:
            logging.error("Invalid format type. Must be 'video' or 'audio'.")
            return jsonify({"success": False, "error": "Invalid format type. Must be 'video' or 'audio'."}), 400

        # Robust YouTube URL validation using regex
        youtube_regex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)\/.+')
        if not youtube_regex.match(youtube_url):
            logging.error(f"Invalid YouTube URL format provided: {youtube_url}")
            return jsonify({"success": False, "error": "Invalid YouTube URL format. Please provide a valid YouTube link."}), 400

        # --- Download Logic using yt-dlp ---
        # Create a temporary directory to store the downloaded file.
        # This is crucial for Render's environment, ensuring files are written to a writable, temporary location.
        # It also handles cleanup automatically when the 'with' block exits.
        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate a unique base filename to prevent clashes, but let yt-dlp add title/extension.
            # Using uuid helps avoid issues if titles contain characters that are problematic for filenames.
            base_filename = str(uuid.uuid4())
            # outtmpl tells yt-dlp where to save the file and what naming convention to use.
            # `%(title)s.%(ext)s` will use the video's title and its actual extension.
            # yt-dlp needs to determine the final filename itself, so we give it a template.
            output_template = os.path.join(tmpdir, f"{base_filename}_%(title)s.%(ext)s")

            ydl_opts = {
                'outtmpl': output_template, # Output file template
                'noplaylist': True,        # Ensures only single video is downloaded, not a playlist
                'quiet': True,             # Suppress most console output from yt-dlp
                'no_warnings': True,       # Suppress warnings from yt-dlp
                'retries': 5,              # Number of retries for failed downloads
                'external_downloader': 'ffmpeg', # Explicitly use ffmpeg if available
                'external_downloader_args': ['-loglevel', 'error'] # Suppress verbose ffmpeg output
            }

            if format_type == 'video':
                # Download best quality video and audio, then merge them into MP4
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
                ydl_opts['merge_output_format'] = 'mp4'
            elif format_type == 'audio':
                # Download best audio and convert to MP3
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192', # 192kbps for audio
                }]

            downloaded_filepath = None
            try:
                logging.info(f"Starting yt-dlp download for: {youtube_url} into {tmpdir}")
                with YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(youtube_url, download=True)

                    # yt-dlp provides the actual downloaded file path in 'requested_downloads' or sometimes 'filepath'
                    if 'requested_downloads' in info_dict and info_dict['requested_downloads']:
                        # This covers scenarios where multiple files are downloaded then merged/processed
                        # We assume the first in the list is the final one
                        downloaded_filepath = info_dict['requested_downloads'][0]['filepath']
                    elif 'filepath' in info_dict:
                        # For simpler downloads where yt-dlp directly provides the path
                        downloaded_filepath = info_dict['filepath']
                    else:
                        # Fallback: try to find the file using glob based on the base filename and potential extensions
                        import glob
                        # Be careful with glob patterns. A very broad one can pick up temporary files.
                        # This assumes the base_filename is unique and helps narrow down.
                        possible_files = glob.glob(os.path.join(tmpdir, f"{base_filename}_*"))
                        if possible_files:
                            # Prioritize mp4/mp3 if format_type matches
                            if format_type == 'video':
                                downloaded_filepath = next((f for f in possible_files if f.endswith('.mp4')), possible_files[0])
                            elif format_type == 'audio':
                                downloaded_filepath = next((f for f in possible_files if f.endswith('.mp3')), possible_files[0])
                            else:
                                downloaded_filepath = possible_files[0] # Just take the first if type doesn't matter
                        logging.warning(f"Could not find exact downloaded_filepath from info_dict. Falling back to glob search. Found: {downloaded_filepath}")

                if not downloaded_filepath or not os.path.exists(downloaded_filepath):
                    logging.error(f"Downloaded file NOT FOUND at final path: {downloaded_filepath}. Info: {info_dict}")
                    return jsonify({"success": False, "error": "Downloaded file not found. yt-dlp failed to save the file or saved it elsewhere. Check server logs for detailed yt-dlp output."}, 500)

                # --- Determine MIME type for the browser ---
                if format_type == 'video':
                    mime_type = 'video/mp4'
                elif format_type == 'audio':
                    mime_type = 'audio/mpeg' # For MP3
                else:
                    mime_type = 'application/octet-stream' # Generic binary data

                # --- Send the file back to the client ---
                logging.info(f"Sending file: {downloaded_filepath} with download name: {os.path.basename(downloaded_filepath)}")
                return send_file(
                    downloaded_filepath,
                    as_attachment=True,
                    download_name=os.path.basename(downloaded_filepath), # Ensures browser gets correct filename
                    mimetype=mime_type # Specify mimetype
                )

            except Exception as ydl_e:
                logging.exception(f"Error caught during yt-dlp execution for URL: {youtube_url}")
                # Provide a more specific error message if it's a known yt-dlp error type
                error_message = str(ydl_e)
                if isinstance(ydl_e, yt_dlp.utils.DownloadError):
                    if "Private video" in error_message:
                        error_message = "This video is private or unavailable."
                    elif "unavailable" in error_message:
                        error_message = "This video is unavailable or restricted."
                    else:
                        error_message = f"Failed to download media: {error_message.split('ERROR:')[-1].strip()}"
                return jsonify({"success": False, "error": f"Download failed: {error_message}. Check server logs for details."}), 500

    except Exception as e:
        logging.exception(f"An unexpected general error occurred in /download route: {e}")
        return jsonify({"success": False, "error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- Run the Flask Application ---
if __name__ == '__main__':
    # When deploying to Render, Gunicorn (or your chosen WSGI server) will run the app.
    # This 'app.run' block is primarily for local development.
    # Render's environment variables (like PORT) should be respected if you're using them.
    port = int(os.environ.get('PORT', 5000)) # Use PORT env var if available, else 5000
    app.run(debug=True, host='0.0.0.0', port=port) # Listen on all interfaces