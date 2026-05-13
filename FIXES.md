# Matiks Codebase — Bug Report & Fix Summary

## Files changed
| File | Status |
|------|--------|
| `api.py` | Fixed |
| `genres.py` | Fixed |
| `pipeline/full_pipeline.py` | Fixed |
| `pipeline/editor.py` | Fixed |
| `dashboard/index.html` | Fixed |
| `requirements.txt` | Fixed |

---

## Bug 1 — "API not found" every time (dashboard always shows offline)

### Root cause A — `flask` and `flask-cors` missing from requirements.txt
`requirements.txt` had no `flask` or `flask-cors` entries. If you installed from
requirements.txt, `api.py` couldn't even start — `from flask import Flask` would
throw `ModuleNotFoundError`. The dashboard then shows "offline" because there's
nothing listening on port 5000.

**Fix:** Added `flask>=3.0.0` and `flask-cors>=4.0.0` to `requirements.txt`.

### Root cause B — `genres.py::list_genres()` returned trimmed data, causing silent JS crash
`/genres` endpoint called `list_genres()` which returned only `{id, name, niche, reel_style, duration}`.
The dashboard's `loadChannels()` merged these into the `channels` array, then
`onChannelChange()` tried to read `ch.search_keywords`, `ch.content_rules`,
`ch.voice_preset` — all `undefined`. This crashed the channel info panel silently and
in some browsers caused the entire `loadChannels()` call to fail, leaving the channel
dropdown empty, preventing any pipeline launch.

**Fix:** Added `list_genres_full()` to `genres.py` that returns complete genre objects.
Changed `/genres` endpoint in `api.py` to call `list_genres_full()`.
Also added `search_keywords` field to every genre in `GENRE_LIBRARY` (was only `keywords`
for most genres — the pipeline uses `channel['search_keywords']` specifically).

### Root cause C — `checkApi()` had no error handling on non-ok HTTP responses
The `api()` helper only caught network exceptions, not HTTP error status codes.
If Flask returned a 500 (e.g. during startup), `res.json()` would still return
something and `result` would be truthy — but it wouldn't have `result.status === 'ok'`.

**Fix:** `api()` now checks `res.ok` before parsing JSON. `checkApi()` now explicitly
checks `result.status === 'ok'` and also updates the sidebar dot colour.

### Root cause D — `api.py` ran with `debug=True`
Flask's debug mode with `use_reloader=False` is mostly fine, but `debug=True` changes
error response formats and can cause unexpected behaviour in threaded mode. Changed to
`debug=False` for production stability.

---

## Bug 2 — Video output doesn't appear after pipeline completes

### Root cause A — `_generate_video()` blocked the event loop (async bug)
In `full_pipeline.py`, `_generate_video()` was declared `async` but called
`self.cogvideo.generate_video()` (a synchronous, blocking function) directly — without
`asyncio.to_thread()`. This means:

1. The async event loop was completely blocked for the 15–25 minute CogVideoX generation.
2. `asyncio.gather(audio_task, video_task)` could not run them truly concurrently.
3. In some configurations, the blocking call inside an async function caused the
   coroutine to never yield, which could cause the gather to never resolve properly.

**Fix:** `_generate_video()` now uses `await asyncio.to_thread(self.cogvideo.generate_video, ...)`.
This runs the blocking CUDA call in a thread pool without blocking the event loop.

### Root cause B — Video errors were silently swallowed, triggering fallback
Even if `_generate_video()` raised an exception, `_stage_audio_and_video_parallel()`
caught it, logged "Will compose with black background", set `video_path = None`, and
continued. Then `_stage_compose()` detected `video_path is None` and called
`_compose_placeholder()` — producing a black background reel.

So the pipeline "completed" with an output file, but that output was the black
background fallback — not an AI video. The job appeared in the dashboard as "complete"
with outputs, but the video was wrong.

Additionally, if CogVideoX *did* work but `video_path` was `None` due to the async
blocking issue above, the fallback silently masked the underlying problem.

**Fix:** All fallback/placeholder code removed entirely (see Bug 3 below).

### Root cause C — FFmpeg ASS subtitle path broken on Windows
`editor.py::_compose_with_video()` used `job.subtitle_path.as_posix()` for the FFmpeg
`-vf ass=...` filter. On Windows, paths look like `C:\temp\1_subs.ass`. FFmpeg's filter
string parser treats `:` as an option separator, so `C:` breaks the filter. Result:
FFmpeg errors out, `_compose_with_video()` raises, `edit_job.final_path` is never set,
and `job.final_path` stays `None` — no output.

**Fix:** Added `_escape_ass_path_for_ffmpeg()` in `editor.py` that:
- Converts backslashes to forward slashes
- Escapes the Windows drive letter colon: `C:` → `C\:`
- Escapes spaces in paths

---

## Bug 3 — Fallback/placeholder reel used instead of AI video

### Root cause — Multiple fallback paths existed throughout the codebase
`full_pipeline.py::_stage_compose()` had an `else` branch that called
`_compose_placeholder()` when `video_path` was `None`. `editor.py` had
`_compose_placeholder()` which created a black background reel. `_stage_audio_and_video_parallel()`
printed "Will compose with black background" on video failure and continued without stopping.

**Fix:**
- `_compose_placeholder()` method **removed entirely** from `editor.py`.
- `_stage_compose()` in `full_pipeline.py` now hard-fails if `video_path` is `None`.
- `produce_reel()` in `full_pipeline.py` now returns early (incomplete reel) if either
  `video_path` or `audio_path` is `None` after the parallel generation stage.
- Dashboard Settings panel updated: "Background video generation" toggle changed to
  show "Always on — no fallback" and is permanently checked + disabled.

---

## Other fixes

### `requirements.txt` — Missing critical packages
Added: `flask`, `flask-cors`, `imageio[ffmpeg]` (used by `cogvideo.py` to save MP4),
`diffusers`, `transformers`, `accelerate` (all required by CogVideoX).
Updated `google-generativeai` minimum to `0.7.0` (the `0.3.0` pin is too old for the
`GenerativeModel` API used in `llm.py`).

### `dashboard/index.html` — `showPage()` used `event.currentTarget`
The original `showPage(name)` function used `event.currentTarget` to find the clicked
nav item. This relied on the global `event` object which is not reliable in all
browsers and was `undefined` in some call paths (e.g. `quickGenerate()` calling
`showPage()`). Changed signature to `showPage(name, btn)` and passed `this` explicitly
from each `onclick`.

### `dashboard/index.html` — XSS via unescaped user data
Channel names, topics, error messages etc. were inserted directly into `innerHTML`
without escaping. Added `escHtml()` utility and applied it throughout.

### `api.py` — Job marked `complete` even when no output files were produced
The original code set `status = "complete"` regardless of whether any output files
existed. Now: if `outputs` is empty, `status` is set to `"failed"` and the first
error is surfaced as `job.error` for the dashboard to display.

---

## Startup checklist

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify FFmpeg is installed
ffmpeg -version

# 3. Start the API (from project root)
python api.py

# 4. Open dashboard
# http://localhost:5000
# Sidebar should show "API connected" in green within a few seconds.
```

CogVideoX (~16GB) downloads on first run. Generation takes 15–25 min per reel on
an RTX 4060 8GB. The job will show as "running" in the dashboard during this time.
