# Mehrvia YouTube API — Deploy Guide

This folder runs the YouTube download engine behind the blog's Video Downloader page.
Based on [zararashraf/youtube-video-downloader-api](https://github.com/zararashraf/youtube-video-downloader-api) (MIT),
extended with a `/resolve` endpoint + CORS for the blog.

## Files
- `app.py` — the API (Flask + pytubefix). Endpoints: `/resolve`, `/video_info`,
  `/available_resolutions`, `/download/<resolution>`, `/health`
- `requirements.txt` — Python packages
- `Dockerfile` — for Hugging Face Spaces (Docker)

## Easiest free hosting: Hugging Face Spaces (no credit card)

1. Create a free account at https://huggingface.co/join (verify your email).
2. Click your profile → **New Space**.
   - Name: `mehrvia-yt-api` (or anything)
   - SDK: **Docker** ← important
   - Visibility: Public (free)
   - Create.
3. In the new Space: **Files** → **Add file** → **Upload files** — upload all 3 files
   (`app.py`, `requirements.txt`, `Dockerfile`).
4. Wait 2–5 minutes while it builds (the Space page shows the build log).
5. When it says **Running**, your API address is shown at the top, like:
   `https://YOURNAME-mehrvia-yt-api.hf.space`
6. Tell Muse that address — the blog's Video Downloader page will be updated to
   use it for YouTube links (with the old public servers as automatic fallback).

## Test it
Open in a browser: `https://YOUR-ADDRESS.hf.space/health` → should show `{"ok":true}`.

## Notes
- The free server sleeps when idle; the first download after a while can take ~30–60s to wake up. The page shows "Contacting the Mehrvia server…" meanwhile.
- If YouTube ever blocks the server, downloads fall back to the public servers automatically, and the Android app still works.
