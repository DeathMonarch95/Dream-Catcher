from flask import Flask, request, send_file, jsonify
from yt_dlp import YoutubeDL
import os
import tempfile
from flask_cors import CORS
import logging
import re # Import regex for more robust URL validation

# Configure logging to show debug messages in the terminal
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
# Enable CORS for all routes. This is crucial for your web page (index.html)
# to make requests to this server from a different "origin" (even if it's localhost)
CORS(app)

@app.route('/download', methods=['POST'])
def download_media():
    """
    Handles download requests from the frontend.
    Expects a JSON payload with 'url' and 'format' ('video' or 'audio').
    """
    try: # Outer try block for general unhandled exceptions in the route
        data = request.get_json() # Use get_json() to correctly parse incoming JSON data
        youtube_url = data.get('url')
        format_type = data.get('format') # 'video' or 'audio'

        logging.debug(f"Received download request for URL: {youtube_url}, format: {format_type}")

        # --- Basic Input Validation ---
        if not youtube_url:
            logging.error("YouTube URL is required.")
            return jsonify({"success": False, "error": "YouTube URL is required."}), 400
        if not format_type or format_type not in ['video', 'audio']:
            logging.error("Invalid format type. Must be 'video' or 'audio'.")
            return jsonify({"success": False, "error": "Invalid format type. Must be 'video' or 'audio'."}), 400

        # More robust YouTube URL validation using regex
        youtube_regex = re.compile(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+')
        if not youtube_regex.match(youtube_url):
            logging.error(f"Invalid YouTube URL format provided: {youtube_url}")
            return jsonify({"success": False, "error": "Invalid YouTube URL format. Please provide a valid YouTube link."}), 400

        # --- Download Logic using yt-dlp ---
        # Create a temporary directory to store the downloaded file
        # This ensures files are cleaned up automatically after they're sent
        with tempfile.TemporaryDirectory() as tmpdir:
            # yt-dlp will save the file inside this temporary directory.
            # We use %(title)s, %(id)s and %(ext)s to ensure a unique and correct filename.
            # This is critical for yt-dlp to output the file with its actual name and extension.
            # The 'title' ensures a human-readable name, 'id' ensures uniqueness, 'ext' ensures correct format.
            filepath_template = os.path.join(tmpdir, "%(title)s_%(id)s.%(ext)s")

            ydl_opts = {
                'outtmpl': filepath_template, # Output file template
                'noplaylist': True,  # Ensures only single video is downloaded, not a playlist
                'quiet': True,       # Suppress console output from yt-dlp
                'no_warnings': True, # Suppress warnings from yt-dlp
                'retries': 5,        # Number of retries for failed downloads
            }

            if format_type == 'video':
                # Download best quality video and audio, then merge them into MP4
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
                ydl_opts['merge_output_format'] = 'mp4'
            elif format_type == 'audio':
                # Download best audio and convert to MP3
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192', # 192kbps for audio
                }]

            downloaded_file = None # Initialize to None
            try: # Inner try block for yt-dlp specific errors
                logging.debug(f"Starting yt-dlp download for: {youtube_url} into {tmpdir}")
                with YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(youtube_url, download=True)
                    # Use prepare_filename to get the *expected* path of the downloaded file.
                    # This might be the .webm before conversion, or the .mp3 after.
                    downloaded_file = ydl.prepare_filename(info_dict)
                    logging.debug(f"yt-dlp completed. Expected downloaded file path (from prepare_filename): {downloaded_file}")

                # --- Verify the downloaded file exists ---
                # For audio, check for the .mp3 file.  yt-dlp downloads a .webm and then converts it.
                if format_type == 'audio':
                    # Check for the .mp3 file as yt-dlp's postprocessor changes the extension
                    mp3_file = os.path.splitext(downloaded_file)[0] + '.mp3'
                    if os.path.exists(mp3_file):
                        downloaded_file = mp3_file # Use the .mp3 file for sending
                        logging.debug(f"Found converted MP3 file: {downloaded_file}")
                    else:
                        logging.error(f"MP3 file not found after conversion. Original file also missing.")
                        return jsonify({"success": False, "error": "MP3 file not found after conversion."}, 500)

                # This check catches if for some reason the file doesn't exist even after the above logic
                if not os.path.exists(downloaded_file):
                    logging.error(f"Downloaded file NOT FOUND at final path: {downloaded_file}")
                    return jsonify({"success": False, "error": "Downloaded file not found. yt-dlp might have failed to save the file or saved it elsewhere."}, 500)

                # --- Determine MIME type for the browser ---
                # This helps the browser correctly identify the file type
                if format_type == 'video':
                    mime_type = 'video/mp4'
                elif format_type == 'audio':
                    mime_type = 'audio/mpeg' # For MP3
                else:
                    mime_type = 'application/octet-stream' # Generic binary data

                # --- Send the file back to the client ---
                logging.debug(f"Attempting to send file: {downloaded_file} with download name: {os.path.basename(downloaded_file)}")
                return send_file(
                    downloaded_file,
                    as_attachment=True,
                    download_name=os.path.basename(downloaded_file), # Ensures browser gets correct filename
                    mimetype=mime_type # Specify mimetype
                )

            except Exception as ydl_e:
                logging.exception(f"Error caught during yt-dlp execution for URL: {youtube_url}") # Log full traceback
                return jsonify({"success": False, "error": f"Failed to download media using yt-dlp: {str(ydl_e)}. Check server logs for details."}), 500

    except Exception as e: # Catch any other unexpected errors in the route
        logging.exception(f"Unexpected general error in /download route: {e}") # Log full traceback for unexpected errors
        return jsonify({"success": False, "error": f"An unexpected server error occurred: {str(e)}"}), 500

# --- Run the Flask Application ---
if __name__ == '__main__':
    # This runs the Flask server on your local machine, usually at http://127.00.1:5000/
    # debug=True allows for automatic reloading on code changes and provides more detailed errors
    # For a real application, you would set debug=False
    app.run(debug=True, port=5000)