
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import asyncio
import json
import threading
import uuid
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# In-memory job store
jobs = {}


def load_config():
    with open("config.json") as f:
        config = json.load(f)
    
    # Inject API keys from environment
    config["apis"] = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "youtube_api_key": os.getenv("YOUTUBE_API_KEY")
    }
    
    return config


def save_config(config):
    with open("config.json", "w") as f:
        # Don't save API keys to config.json
        config_copy = config.copy()
        config_copy.pop("apis", None)
        json.dump(config_copy, f, indent=2)


# ─── JOB RUNNER ────────────────────────────────────────

def run_pipeline_job(job_id: str, payload: dict):
    """Runs in background thread."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = datetime.now().isoformat()

        config = load_config()

        # Find the channel
        channel_id = payload.get("channel_id")
        channel = None

        for ch in config["channels"]:
            if ch["id"] == channel_id:
                channel = ch.copy()
                break

        if not channel:
            # Try genre library
            from genres import get_genre
            try:
                channel = get_genre(channel_id)
            except ValueError:
                pass

        if not channel:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = f"Channel '{channel_id}' not found in config or genre library"
            return

        # Apply overrides from UI
        if payload.get("reel_count"):
            channel["reels_per_day"] = int(payload["reel_count"])

        # Apply custom subtitle style if provided
        if payload.get("subtitle_style"):
            style = payload["subtitle_style"]
            style_name = f"custom_{job_id[:8]}"
            config["caption_styles"][style_name] = style
            channel["caption_style"] = style_name
            save_config(config)

        # Ensure caption_styles are available in the config passed to pipeline
        config["channels"] = [channel]
        config["user_keyword"] = payload.get("topic_override", "")

        # Run pipeline
        from pipeline.full_pipeline import FullPipeline
        pipeline = FullPipeline(config)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(pipeline.run_all_channels())
        finally:
            loop.close()

        # Collect outputs - only count reels that actually have a final video file
        outputs = []
        errors = []
        for job in results:
            if job.final_path and job.final_path.exists():
                outputs.append({
                    "topic": job.topic,
                    "file": str(job.final_path),
                    "size_mb": round(
                        job.final_path.stat().st_size / 1024 / 1024, 2
                    ),
                    "errors": job.errors
                })
            else:
                # Job ran but produced no output - surface the errors
                errors.append({
                    "topic": job.topic,
                    "errors": job.errors
                })

        jobs[job_id]["status"] = "complete" if outputs else "failed"
        jobs[job_id]["outputs"] = outputs
        jobs[job_id]["failed_reels"] = errors
        jobs[job_id]["completed_at"] = datetime.now().isoformat()

        if not outputs and errors:
            # Summarise the first error for the UI
            first_errors = errors[0]["errors"] if errors else []
            jobs[job_id]["error"] = (
                first_errors[0] if first_errors
                else "Pipeline ran but produced no video output"
            )

    except Exception as e:
        import traceback
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
        jobs[job_id]["traceback"] = traceback.format_exc()
        print(f"[API] Job {job_id} failed: {e}")
        traceback.print_exc()


# ─── ROUTES ────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Health check - returns shape the dashboard expects."""
    return jsonify({
        "status": "ok",
        "jobs": len(jobs),          # total job count (int) - used by sidebar
        "running": sum(1 for j in jobs.values() if j["status"] == "running"),
        "complete": sum(1 for j in jobs.values() if j["status"] == "complete"),
    })


@app.route("/webhook/matiks-reel", methods=["POST"])
def webhook_generate():
    """Dashboard sends POST here to trigger generation."""
    payload = request.json or {}

    if not payload.get("channel_id"):
        return jsonify({"error": "channel_id is required"}), 400

    job_id = str(uuid.uuid4())[:12]

    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "payload": payload,
        "created_at": datetime.now().isoformat(),
        "outputs": [],
        "failed_reels": [],
        "error": None
    }

    thread = threading.Thread(
        target=run_pipeline_job,
        args=(job_id, payload),
        daemon=True
    )
    thread.start()

    return jsonify({
        "job_id": job_id,
        "status": "queued",
        "message": "Pipeline started",
        "poll_url": f"/jobs/{job_id}"
    })


@app.route("/jobs", methods=["GET"])
def list_jobs():
    return jsonify(list(jobs.values()))


@app.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(jobs[job_id])


@app.route("/channels", methods=["GET"])
def get_channels():
    config = load_config()
    return jsonify(config.get("channels", []))


@app.route("/channels", methods=["POST"])
def add_channel():
    config = load_config()
    new_channel = request.json

    required = ["id", "name", "niche"]
    for field in required:
        if field not in new_channel:
            return jsonify({"error": f"Missing field: {field}"}), 400

    for ch in config["channels"]:
        if ch["id"] == new_channel["id"]:
            return jsonify({"error": "Channel ID already exists"}), 409

    new_channel.setdefault("search_keywords", [new_channel["niche"]])
    new_channel.setdefault("target_audience", "general audience 18-35")
    new_channel.setdefault("tone", "engaging, informative")
    new_channel.setdefault("reels_per_day", 1)
    new_channel.setdefault("content_rules", [])
    new_channel.setdefault("duration_seconds", 60)
    new_channel.setdefault("voice_preset", "en-US-ChristopherNeural")
    new_channel.setdefault("caption_style", "bold_white")
    new_channel.setdefault("kling_duration", 5)
    new_channel.setdefault("kling_mode", "std")

    config["channels"].append(new_channel)
    save_config(config)
    return jsonify({"success": True, "channel": new_channel})


@app.route("/channels/<channel_id>", methods=["PUT"])
def update_channel(channel_id):
    config = load_config()
    updates = request.json

    for i, ch in enumerate(config["channels"]):
        if ch["id"] == channel_id:
            config["channels"][i].update(updates)
            save_config(config)
            return jsonify({
                "success": True,
                "channel": config["channels"][i]
            })

    return jsonify({"error": "Channel not found"}), 404


@app.route("/channels/<channel_id>", methods=["DELETE"])
def delete_channel(channel_id):
    config = load_config()
    before = len(config["channels"])
    config["channels"] = [
        ch for ch in config["channels"]
        if ch["id"] != channel_id
    ]

    if len(config["channels"]) == before:
        return jsonify({"error": "Channel not found"}), 404

    save_config(config)
    return jsonify({"success": True})


@app.route("/caption-styles", methods=["GET"])
def get_caption_styles():
    config = load_config()
    return jsonify(config.get("caption_styles", {}))


@app.route("/caption-styles", methods=["POST"])
def add_caption_style():
    config = load_config()
    data = request.json
    name = data.get("name")
    style = data.get("style")

    if not name or not style:
        return jsonify({"error": "Need name and style"}), 400

    config["caption_styles"][name] = style
    save_config(config)
    return jsonify({"success": True})


@app.route("/genres", methods=["GET"])
def get_genres():
    """
    FIX: Return FULL genre data, not the trimmed version.
    The dashboard merges genres with channels and tries to render
    fields like search_keywords, content_rules, voice_preset etc.
    Returning trimmed data caused silent JS errors.
    """
    from genres import list_genres_full
    return jsonify(list_genres_full())


@app.route("/")
def dashboard():
    return send_from_directory("dashboard", "index.html")


if __name__ == "__main__":
    print("=" * 50)
    print("  Matiks API starting on http://localhost:5000")
    print("  Dashboard: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, use_reloader=False, port=5000, threaded=True)
