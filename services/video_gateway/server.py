import os
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from services.video_gateway.gateway import VideoGenerationGateway
from app.core.config import settings

app = Flask(__name__)
gateway = VideoGenerationGateway()


@app.route("/health", methods=["GET"])
def health():
    return jsonify(gateway.get_status())


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt")
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    num_frames = int(data.get("num_frames", 49))
    num_inference_steps = int(data.get("num_inference_steps", 30))
    job_id = data.get("job_id", "gw_test")

    output_path = Path("temp") / f"{job_id}_gw_video.mp4"
    result = gateway.generate_video(
        prompt=prompt,
        output_path=output_path,
        num_frames=num_frames,
        num_inference_steps=num_inference_steps
    )

    if Path(result.video_path).exists():
        return send_file(result.video_path, mimetype="video/mp4")
    return jsonify(result.dict())


if __name__ == "__main__":
    port = int(os.getenv("VIDEO_GATEWAY_PORT", "8000"))
    print(f"[VideoGateway Server] Starting on port {port} (Backend: {settings.VIDEO_BACKEND})")
    app.run(host="0.0.0.0", port=port, debug=False)
