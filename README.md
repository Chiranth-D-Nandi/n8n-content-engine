# n8n-content-engine

> Automated short video / reel generation pipeline, end-to-end from trending topic research to script and subtitles generation to published reel.

A production-grade content automation system that researches trending topics, writes scripts, generates TTS voiceovers and video, adds in subtitles, and composes the final reel, all triggered from n8n and orchestrated through a Flask API with a browser-based dashboard.

---

## Demo

**Full walkthrough:** [Google Drive](https://drive.google.com/drive/folders/1fx1sv6j_TeXD5qotVLrLZ_rcugIg37Iq?usp=sharing)

Pipeline triggered via n8n, running through research, script generation, TTS, CogVideoX inference, subtitle burn-in, and FFmpeg composition:

![Pipeline walkthrough](matiks_walkthrough-ezgif_com-video-to-gif-converter.gif)

**n8n workflow (published, tested on localhost:5678):**

![n8n workflow](Screenshot_2026-05-13_125156.png)

Generated reel samples are available in the `outputs/` folder, organised by channel (`ai_tech`, `animals`, `health_fitness`).

---

## How it works

The pipeline is structured as a DAG (directed acyclic graph). Tasks with dependencies run sequentially; independent tasks run in parallel.

```
Ideation (channel/genre selection)
    └── Research               <- 3 concurrent threads: YouTube API, Google Trends, News RSS
         └── Script Generation (Gemini 2.5 Flash, stored to SQLite)
              ├── TTS (Edge TTS via WebSocket)           -+
              └── Video (CogVideoX-2B, semaphore=1)      -+  run in parallel
                        └── (both complete)
                              └── Subtitle Generation (Whisper, timestamp-aligned)
                                    └── Final Composition (FFmpeg)
```

TTS is I/O-bound and video generation is GPU-bound, so they have no dependency on each other and run concurrently. The semaphore (concurrency = 1) on the video worker prevents CUDA OOM on consumer hardware (tested on RTX 4060). Subtitle generation depends on the TTS audio being ready, since Whisper runs over the generated voiceover. FFmpeg composition is the final step once all assets are available.

---

## Features

- **Multi-source research:** YouTube Data API v3, Google Trends (pytrends), and RSS news feeds are queried concurrently across three threads. Trend signal is derived from view velocity and engagement (like counts), with rate-limiting to stay within YouTube's 10,000 req/day quota.
- **Script generation:** Gemini 2.5 Flash produces structured scripts (hook, body, CTA) as typed dataclass parameters and persists them to SQLite. Markdown-wrapped JSON responses from the model are stripped and safely parsed before storage.
- **Voiceover:** Edge TTS over WebSocket produces the audio track asynchronously.
- **Video generation:** CogVideoX-2B runs locally via the Hugging Face `diffusers` stack with sequential CPU offload and optional INT8 quantisation (torchao). A semaphore of 1 serialises GPU access.
- **Subtitles:** faster-whisper produces word-level timestamp-aligned `.srt` files from the TTS audio.
- **Composition:** FFmpeg overlays subtitles and audio onto the generated video. Windows path escaping conflicts (FFmpeg uses `:` as a filter-graph separator) are resolved by copying subtitle files to a relative path before referencing them.
- **Job queue:** The Flask API returns a `job_id` immediately on video generation requests. Clients poll `/status/<job_id>` to avoid HTTP timeout on 5–8 minute generation jobs. In production this queue is backed by Redis + Celery.
- **n8n integration:** Webhooks notify n8n workflows on job completion, tested on localhost:5678.
- **Dashboard:** Browser-based UI with polling for live job status, channel management, and subtitle style preview.

---

## Future scope

**Redis + Celery job queue**
The current in-memory job queue is sufficient for local use but does not survive server restarts. The intended production upgrade is to replace it with Redis as the message broker and Celery as the task executor. Each generation request becomes a Celery task; Redis holds the key-value queue. This gives the system persistent job state across restarts, horizontal worker scaling, and built-in retry logic on failure, without changing the API contract (`job_id` polling stays the same, the backing store just becomes durable).

```python
# Rough shape of the migration
from celery import Celery

celery = Celery("content_engine", broker="redis://localhost:6379/0")

@celery.task(bind=True, max_retries=2)
def generate_reel(self, job_id: str, channel_id: str, topic: str):
    ...
```

The dashboard and n8n webhook integration require no changes, as they interact only with `/status/<job_id>` and the completion webhook.

---

## Architecture

```
n8n (workflow trigger)
    |  webhook
    v
Flask API  ──────────────────────────────────────────────────────┐
    |                                                             │
    |  async pipeline                                             │
    +── Research worker (asyncio + 3 threads)                     │
    |       +── YouTube API (rate-limited)                        │
    |       +── Google Trends                                     │
    |       └── RSS / News feeds                                  │
    |                                                             │
    +── Script worker  ->  Gemini 2.5 Flash  ->  SQLite          │
    |                                                             │
    |        (runs concurrently)                                  │
    +── TTS worker     ->  Edge TTS (WebSocket)        -+        │
    +── Video worker   ->  CogVideoX-2B (semaphore=1)  -+        │
    |                                                             │
    +── Subtitle worker ->  faster-whisper  (after TTS)          │
    └── Compose worker  ->  FFmpeg  (after all assets ready)     │
                                                                  │
Dashboard (polling)  <────────────────────────────────────────────┘
```

**Database:** SQLite with per-operation connection creation. Connections are not shared across threads; a fresh connection is opened and closed for each operation to avoid the thread-safety limitations of SQLite's default mode.

---

## Tech stack

| Concern | Tool |
|---|---|
| Workflow automation | n8n |
| API server | Flask + Flask-CORS |
| Script generation | Gemini 2.5 Flash (`google-genai`) |
| Voiceover | Edge TTS (WebSocket) |
| Video generation | CogVideoX-2B via Hugging Face `diffusers` |
| Subtitles | faster-whisper (timestamp-aligned) |
| Video composition | FFmpeg |
| Research | YouTube Data API v3 · pytrends · feedparser |
| Database | SQLite |
| Production queue | Redis + Celery (replaces in-memory queue) |
| Quantisation (opt.) | torchao INT8 |

---

## Setup

### Prerequisites

- Python 3.10+
- FFmpeg on system PATH
- CUDA-capable GPU (tested on RTX 4060, 8 GB VRAM)
- n8n instance (local or cloud)

### Install

```bash
git clone https://github.com/Chiranth-D-Nandi/n8n-content-engine
cd n8n-content-engine
pip install -r requirements.txt
```

### Configure

```bash
cp config.example.json config.json
```

Fill in `config.json`:

```json
{
  "gemini_api_key": "...",
  "youtube_api_key": "...",
  "n8n_webhook_url": "http://localhost:5678/webhook/matiks-reel",
  "output_dir": "outputs/"
}
```

Set your environment variables in `.env`:

```
GEMINI_API_KEY=...
YOUTUBE_API_KEY=...
```

### Run

**CLI (local generation):**
```bash
python main.py
```

Select a genre, optionally enter a topic hint, and the pipeline runs end-to-end. Output reels land in `outputs/`.

**API server (for n8n / dashboard):**
```bash
python api.py
```

Dashboard available at `http://localhost:5000/dashboard`.

---

## API reference

### `POST /webhook/matiks-reel`
The primary entry point. This is the endpoint n8n calls after normalising the incoming payload.

Request body:

```json
{
  "channel_id": "ai_tech",
  "topic_override": "optional topic hint",
  "reel_count": 1,
  "subtitle_style": null
}
```

All fields are optional. Defaults applied by the n8n Code node if not provided:

| Field | Default | Description |
|---|---|---|
| `channel_id` | `"ai_tech"` | Target channel/genre for research and script tone |
| `topic_override` | `""` | Pin the script to a specific topic instead of trending results |
| `reel_count` | `1` | Number of reels to generate in this job |
| `subtitle_style` | `null` | Subtitle style preset; falls back to server default if null |

Returns:
```json
{ "job_id": "abc123" }
```

### `GET /status/<job_id>`
Poll for job status. The dashboard and n8n poll this every 5-10 seconds.

```json
{
  "job_id": "abc123",
  "status": "running",
  "stage": "video_generation",
  "output_path": null
}
```

Status values: `queued`, `running`, `complete`, `failed`

### `GET /jobs`
List all jobs with metadata.

### n8n workflow

The included workflow (`n8n_content_enginev1_0.json`) has four nodes:

| Node | Type | Role |
|---|---|---|
| Webhook | Trigger | Listens on `POST /webhook/matiks-reel` at `localhost:5678` |
| Code in JavaScript | Transform | Normalises payload, applies field defaults |
| HTTP Request | Action | Forwards cleaned payload to Flask at `localhost:5000/webhook/matiks-reel` |
| Respond to Webhook | Output | Returns the Flask response (including `job_id`) to the original caller |

To import: open n8n, go to Workflows, click Import, and select `n8n_content_enginev1_0.json`. Activate the workflow and ensure the Flask server is running on port 5000 before triggering.

---

## Production notes

**Job queue:** The in-memory job queue resets on server restart. For production, replace with Redis + Celery:

```bash
pip install redis celery
celery -A tasks worker --loglevel=info
```

**CUDA OOM:** The `asyncio.Semaphore(1)` on the video worker ensures only one CogVideoX inference runs at a time. On cards with >8 GB VRAM this limit can be raised, but doing so will likely cause out-of-memory errors during concurrent requests on an RTX 4060.

**YouTube quota:** The YouTube Data API grants 10,000 units/day. Each `search.list` costs 100 units; `videos.list` (for like/view counts) costs 1 unit per video. The research worker applies request-level rate limiting and caches results in SQLite to avoid redundant API calls.

**FFmpeg on Windows:** FFmpeg's `subtitles` filter uses `:` as a key-value separator in filter graphs, which conflicts with Windows drive-letter paths (`C:\...`). The subtitle worker copies the `.srt` file to a relative path (`./tmp_subtitles.srt`) and passes that to FFmpeg instead.

---

## Project structure

```
n8n-content-engine/
├── api.py                   # Flask API server
├── main.py                  # CLI entry point
├── config.json              # Runtime configuration
├── requirements.txt
├── pipeline/
│   ├── full_pipeline.py     # DAG orchestration
│   ├── research.py          # YouTube · Trends · RSS
│   ├── script.py            # Gemini script generation
│   ├── tts.py               # Edge TTS
│   ├── cogvideo.py          # CogVideoX-2B inference
│   ├── subtitles.py         # faster-whisper
│   └── compose.py           # FFmpeg composition
├── genres.py                # Genre/channel definitions
├── db.py                    # SQLite helpers (per-op connections)
├── dashboard/
│   └── index.html           # Browser dashboard
└── outputs/                 # Generated reels
```

---

## Known limitations

- CogVideoX-2B generation takes 8-10 minutes per reel on an RTX 4060. This is a model constraint, not a pipeline constraint.
- The in-process job queue does not survive server restarts. Use Redis + Celery in any environment where restarts are expected, in prod.
- YouTube API quota is shared across all research threads. Heavy usage (>50 reels/day with fresh topic research each time) may exhaust the daily quota.
- Instagram publishing and analytics are not implemented. The Instagram Graph API restricts programmatic media publishing and insights to accounts linked to a Facebook Business Manager, which requires a verified business account. Without that, the API access tier does not permit automated posting or engagement data retrieval. Publishing is therefore manual for now; the pipeline delivers the composed reel to `outputs/` and stops there.

---

## License

MIT
