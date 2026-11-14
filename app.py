"""Mehrvia YouTube Downloader API.

Based on zararashraf/youtube-video-downloader-api (MIT), extended for the
Mehrvia Tech blog's Video Downloader page:
  - new /resolve endpoint: one POST call returns video info + direct stream
    URLs the browser page can offer as download buttons
  - CORS enabled so https://mehrviatech.blogspot.com can call it
  - original endpoints (/download/<resolution>, /video_info,
    /available_resolutions) kept as-is
  - tools-backend endpoint GET /api/rates: live exchange rates for the
    blog's Currency Converter tool (frankfurter.app first, open.er-api.com
    fallback; cached 1 hour; no API key)
"""
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from pytubefix import YouTube
import json
import re
import time
import urllib.error
import urllib.request

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


# ---------------------------------------------------------------------------
# Exchange rates (tools backend): GET /api/rates?base=USD
# Live rates for the blog's Currency Converter tool. Upstream is the free
# frankfurter.app API first, with open.er-api.com as fallback; no API key.
# Results are cached in memory for 1 hour so repeated calls are fast and
# don't hammer the upstream services.
# ---------------------------------------------------------------------------

RATES_TTL_SECONDS = 3600
_RATES_CACHE = {}  # base -> {"fetched_at": float, "payload": dict}

# Currencies the Currency Converter tool needs. frankfurter.app (ECB rates)
# does not cover all of these (e.g. PKR, AED, SAR), so any currency missing
# from its response is filled in from the fallback source.
RATES_CURRENCIES = [
    "USD", "PKR", "EUR", "GBP", "AED", "SAR", "INR", "CNY", "JPY", "AUD",
    "CAD", "TRY", "CHF", "KWD", "QAR", "BHD", "OMR", "MYR", "IDR", "BDT",
    "NPR", "LKR",
]


def _fetch_json(url, timeout=10):
    req = urllib.request.Request(url,
                                 headers={"User-Agent": "mehrvia-yt-api/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _rates_from_frankfurter(base):
    """Returns (date, rates dict) or None on any failure."""
    try:
        data = _fetch_json(
            "https://api.frankfurter.app/latest?from=" + base)
        rates = data.get("rates") or {}
        if not rates:
            return None
        return data.get("date"), {k: float(v) for k, v in rates.items()}
    except Exception:
        return None


def _rates_from_er_api(base):
    """Returns (date, rates dict) or None on any failure."""
    try:
        data = _fetch_json(
            "https://open.er-api.com/v6/latest/" + base)
        if data.get("result") != "success":
            return None
        rates = data.get("rates") or {}
        if not rates:
            return None
        ts = data.get("time_last_update_unix")
        date = None
        if ts:
            date = datetime.fromtimestamp(
                ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return date, {k: float(v) for k, v in rates.items()}
    except Exception:
        return None


def _get_rates(base):
    cached = _RATES_CACHE.get(base)
    now = time.time()
    if cached and now - cached["fetched_at"] < RATES_TTL_SECONDS:
        return cached["payload"]

    date, rates = None, {}
    primary = _rates_from_frankfurter(base)
    if primary:
        date, rates = primary
    # Fill in any currencies frankfurter does not cover (e.g. PKR, AED, SAR).
    missing = [c for c in RATES_CURRENCIES if c not in rates and c != base]
    if missing:
        fallback = _rates_from_er_api(base)
        if fallback:
            f_date, f_rates = fallback
            if date is None:
                date = f_date
            for code in missing:
                if code in f_rates:
                    rates[code] = f_rates[code]

    if not rates:
        return None
    if date is None:
        date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    rates[base] = 1.0
    payload = {"base": base, "date": date, "rates": rates,
               "source": "frankfurter.app + open.er-api.com"}
    _RATES_CACHE[base] = {"fetched_at": now, "payload": payload}
    return payload


@app.route('/api/rates', methods=['GET'])
def rates():
    base = (request.args.get("base") or "USD").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", base):
        return jsonify({"error": "Invalid base currency code."}), 400
    payload = _get_rates(base)
    if payload is None:
        return jsonify({"error": "Exchange rates are unavailable right now."}), 502
    return jsonify(payload)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"ok": True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
