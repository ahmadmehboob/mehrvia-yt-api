"""Mehrvia YouTube Downloader API.

Based on zararashraf/youtube-video-downloader-api (MIT), extended for the
Mehrvia Tech blog's Video Downloader page:
  - new /resolve endpoint: one POST call returns video info + direct stream
    URLs the browser page can offer as download buttons
  - CORS enabled so https://mehrviatech.blogspot.com can call it
  - original endpoints (/download/<resolution>, /video_info,
    /available_resolutions) kept as-is
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from pytubefix import YouTube
import re

app = Flask(__name__)
CORS(app)  # allow the Blogger page to call this API


def extract_video_id(url):
    m = re.search(r'(?:v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})', url or '')
    return m.group(1) if m else None


def download_video(url, resolution):
    try:
        yt = YouTube(url)
        stream = yt.streams.filter(progressive=True, file_extension='mp4',
                                   resolution=resolution).first()
        if stream:
            out_dir = f"./downloads/{url.split('v=')[1].split('&')[0]}"
            import os
            os.makedirs(out_dir, exist_ok=True)
            stream.download(output_path=out_dir)
            return True, None
        return False, "Video with the specified resolution not found."
    except Exception as e:
        return False, str(e)


def get_video_info(url):
    try:
        yt = YouTube(url)
        video_info = {
            "title": yt.title,
            "author": yt.author,
            "length": yt.length,
            "views": yt.views,
            "description": yt.description,
            "publish_date": str(yt.publish_date) if yt.publish_date else None,
            "thumbnail": yt.thumbnail_url,
        }
        return video_info, None
    except Exception as e:
        return None, str(e)


def is_valid_youtube_url(url):
    pattern = r"^(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+(&\S*)?$"
    return re.match(pattern, url) is not None


@app.route('/download/<resolution>', methods=['POST'])
def download_by_resolution(resolution):
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url')

    if not url:
        return jsonify({"error": "Missing 'url' parameter in the request body."}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL."}), 400

    success, error_message = download_video(url, resolution)
    if success:
        return jsonify({"message": f"Video with resolution {resolution} downloaded successfully."}), 200
    return jsonify({"error": error_message}), 500


@app.route('/video_info', methods=['POST'])
def video_info():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url')

    if not url:
        return jsonify({"error": "Missing 'url' parameter in the request body."}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL."}), 400

    info, error_message = get_video_info(url)
    if info:
        return jsonify(info), 200
    return jsonify({"error": error_message}), 500


@app.route('/available_resolutions', methods=['POST'])
def available_resolutions():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url')

    if not url:
        return jsonify({"error": "Missing 'url' parameter in the request body."}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL."}), 400

    try:
        yt = YouTube(url)
        progressive_resolutions = sorted(set(
            s.resolution for s in yt.streams.filter(progressive=True, file_extension='mp4')
            if s.resolution))
        all_resolutions = sorted(set(
            s.resolution for s in yt.streams.filter(file_extension='mp4')
            if s.resolution))
        return jsonify({"progressive": progressive_resolutions,
                        "all": all_resolutions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/resolve', methods=['POST'])
def resolve():
    """One-shot endpoint for the blog page.

    Request:  {"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
    Response: {"title","author","thumbnail","duration","views","video_id",
               "streams":[{"quality","url","audio","size_mb"}], "audio":{...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url', '')
    vid = extract_video_id(url)
    if not vid:
        return jsonify({"error": "Invalid YouTube URL."}), 400

    try:
        yt = YouTube(f'https://www.youtube.com/watch?v={vid}')

        streams, seen = [], set()
        # progressive (video+audio) first — best for one-tap downloads
        for s in yt.streams.filter(progressive=True, file_extension='mp4') \
                           .order_by('resolution').desc():
            if s.resolution and s.resolution not in seen and s.url:
                seen.add(s.resolution)
                streams.append({"quality": s.resolution, "url": s.url,
                                "audio": True,
                                "size_mb": round((s.filesize_approx or 0) / 1048576, 1)})
        # then video-only mp4 (no audio) as fallback qualities
        for s in yt.streams.filter(file_extension='mp4', progressive=False) \
                           .order_by('resolution').desc():
            if (s.resolution and s.resolution not in seen and s.url
                    and not s.includes_audio_track):
                seen.add(s.resolution)
                streams.append({"quality": s.resolution + " (no sound)", "url": s.url,
                                "audio": False,
                                "size_mb": round((s.filesize_approx or 0) / 1048576, 1)})

        audio = None
        a = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
        if a and a.url:
            audio = {"quality": (a.abr or "audio") + " audio",
                     "url": a.url,
                     "size_mb": round((a.filesize_approx or 0) / 1048576, 1)}

        if not streams and not audio:
            return jsonify({"error": "No downloadable streams found."}), 500

        return jsonify({
            "title": yt.title,
            "author": yt.author,
            "thumbnail": yt.thumbnail_url,
            "duration": yt.length,
            "views": yt.views,
            "video_id": vid,
            "streams": streams,
            "audio": audio,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
