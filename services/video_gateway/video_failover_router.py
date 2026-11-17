from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import requests
from gradio_client import Client
from gradio_client.exceptions import AppError

logger = logging.getLogger("video_failover")

# Empirically captured Hugging Face ZeroGPU scheduler error patterns (Nov 2026)
RE_QUOTA_PARTIAL = re.compile(
    r"exceeded your (?:free |Pro )?ZeroGPU quota\s*\((\d+)s requested vs\.\s*(\d+)s left\)"
    r"(?:\.\s*Try again in\s*(\d+):(\d+):(\d+))?",
    re.IGNORECASE,
)
RE_RUNS_LIMIT = re.compile(r"exceeded your ZeroGPU runs limit", re.IGNORECASE)
RE_ILLEGAL_DURATION = re.compile(
    r"requested GPU duration\s*\((\d+)s\)\s*is larger than the maximum allowed",
    re.IGNORECASE,
)


class FailureKind(Enum):
    ZEROGPU_PARTIAL_QUOTA = "zerogpu_partial_quota"
    ZEROGPU_EXHAUSTED = "zerogpu_exhausted"
    ZEROGPU_ILLEGAL_DUR = "zerogpu_illegal_duration"
    SPACE_UNAVAILABLE = "space_unavailable"
    QUEUE_TIMEOUT = "queue_timeout"
    UPSTREAM_ERROR = "upstream_error"


@dataclass
class ZeroGPUQuotaState:
    """Tracks global ZeroGPU quota shared across all *.hf.space apps for one identity."""
    remaining_seconds: int | None = None
    exhausted_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def can_fit(self, est_reserved_s: int) -> bool:
        with self.lock:
            if time.time() < self.exhausted_until:
                return False
            return self.remaining_seconds is None or est_reserved_s <= self.remaining_seconds

    def record_partial(self, left_s: int, hms: tuple[int, int, int] | None) -> None:
        with self.lock:
            self.remaining_seconds = left_s
            if left_s <= 0:
                ttl = hms[0] * 3600 + hms[1] * 60 + hms[2] if hms and any(hms) else 3600
                self.exhausted_until = time.time() + ttl

    def record_exhausted(self, cooldown_s: int = 3600) -> None:
        with self.lock:
            self.remaining_seconds = 0
            self.exhausted_until = time.time() + cooldown_s


@dataclass
class SpaceEndpoint:
    name: str
    space_id: str
    host_url: str
    api_name: str
    est_reserved_s: int
    timeout_s: float
    min_auth_required: bool
    build_kwargs: Callable[[str, float, int], dict[str, Any]]
    extract_video_path: Callable[[Any], str | None]
    cooldown_until: float = 0.0


def _extract_tuple_first_path(result: Any) -> str | None:
    if isinstance(result, (tuple, list)) and result:
        first = result[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("video") or first.get("path")
    if isinstance(result, dict):
        return result.get("video") or result.get("path")
    return result if isinstance(result, str) else None


def build_default_spaces() -> list[SpaceEndpoint]:
    return [
        # Space A: Official Lightricks LTX-2.3 (22B Distilled, T2V + native AAC audio, ~28s)
        # Declared @spaces.GPU(duration=75) -> ~113s reserved; consumes only ~20-28s actual quota.
        SpaceEndpoint(
            name="Lightricks/LTX-2-3",
            space_id="Lightricks/LTX-2-3",
            host_url="https://lightricks-ltx-2-3.hf.space",
            api_name="/generate_video",
            est_reserved_s=113,
            timeout_s=85.0,
            min_auth_required=False,
            build_kwargs=lambda prompt, dur, seed: {
                "input_image": None,
                "prompt": prompt,
                "duration": min(max(dur, 1.0), 10.0),
                "enhance_prompt": False,
                "seed": seed,
                "randomize_seed": False,
                "height": 512,
                "width": 768,
            },
            extract_video_path=_extract_tuple_first_path,
        ),
        # Space B: Wan2.2-T2V-A14B 4-Step LightX2V + SM120 AOTI (pure T2V, ~46s)
        # Dynamic get_duration -> 50s declared (~75s reserved) at 832x480, 5.0s, steps=4, cfg=1.
        SpaceEndpoint(
            name="Upsampler/wan-2-2-14b-text-to-video",
            space_id="Upsampler/wan-2-2-14b-text-to-video",
            host_url="https://upsampler-wan-2-2-14b-text-to-video.hf.space",
            api_name="/generate_video",
            est_reserved_s=75,
            timeout_s=90.0,
            min_auth_required=False,
            build_kwargs=lambda prompt, dur, seed: {
                "prompt": prompt,
                "aspect_ratio": "16:9 (832x480)",
                "steps": 4,
                "negative_prompt": (
                    "overexposed, static, blurred details, subtitles, worst quality, "
                    "low quality, JPEG compression residue, ugly, deformed, watermark"
                ),
                "duration_seconds": min(max(dur, 0.5), 5.0),
                "guidance_scale": 1.0,
                "guidance_scale_2": 1.0,
                "seed": seed,
                "randomize_seed": False,
            },
            extract_video_path=_extract_tuple_first_path,
        ),
        # Space C: Upsampler LTX-2.3 (lowest reservation tail-packer! 41s declared / 62s reserved @ 5s)
        SpaceEndpoint(
            name="Upsampler/ltx-video",
            space_id="Upsampler/ltx-video",
            host_url="https://upsampler-ltx-video.hf.space",
            api_name="/generate_video",
            est_reserved_s=62,
            timeout_s=85.0,
            min_auth_required=False,
            build_kwargs=lambda prompt, dur, seed: {
                "input_image": None,
                "prompt": prompt,
                "duration": min(max(dur, 1.0), 5.0),
                "enhance_prompt": False,
                "seed": seed,
                "randomize_seed": False,
                "height": 512,
                "width": 768,
            },
            extract_video_path=_extract_tuple_first_path,
        ),
        # Space D: Official ByteDance AnimateDiff-Lightning (ultra-fast ~5-8s emergency clip)
        SpaceEndpoint(
            name="ByteDance/AnimateDiff-Lightning",
            space_id="ByteDance/AnimateDiff-Lightning",
            host_url="https://bytedance-animatediff-lightning.hf.space",
            api_name="/generate_image",
            est_reserved_s=90,
            timeout_s=45.0,
            min_auth_required=False,
            build_kwargs=lambda prompt, dur, seed: {
                "prompt": prompt,
                "base": "epiCRealism",
                "motion": "guoyww/animatediff-motion-lora-zoom-in",
                "step": "4",
            },
            extract_video_path=_extract_tuple_first_path,
        ),
        # Space E (Free HF_TOKEN only): Exact THUDM/CogVideoX-2b (49 frames @ 8fps = 6.1s)
        SpaceEndpoint(
            name="Krish1440/CogVideoX-2B-Space",
            space_id="Krish1440/CogVideoX-2B-Space",
            host_url="https://krish1440-cogvideox-2b-space.hf.space",
            api_name="/generate",
            est_reserved_s=210,
            timeout_s=160.0,
            min_auth_required=True,
            build_kwargs=lambda prompt, dur, seed: {
                "prompt": prompt,
                "num_inference_steps": 35,
                "guidance_scale": 6.0,
            },
            extract_video_path=_extract_tuple_first_path,
        ),
    ]


def classify_exception(exc: BaseException) -> tuple[FailureKind, int | None, tuple[int, int, int] | None]:
    msg = str(exc)
    m = RE_QUOTA_PARTIAL.search(msg)
    if m:
        left = int(m.group(2))
        hms = (int(m.group(3)), int(m.group(4)), int(m.group(5))) if m.group(3) else None
        return (FailureKind.ZEROGPU_EXHAUSTED if left <= 0 else FailureKind.ZEROGPU_PARTIAL_QUOTA), left, hms
    if RE_RUNS_LIMIT.search(msg):
        return FailureKind.ZEROGPU_EXHAUSTED, 0, None
    if RE_ILLEGAL_DURATION.search(msg):
        return FailureKind.ZEROGPU_ILLEGAL_DUR, None, None
    if isinstance(exc, TimeoutError):
        return FailureKind.QUEUE_TIMEOUT, None, None
    return (FailureKind.UPSTREAM_ERROR if isinstance(exc, AppError) else FailureKind.SPACE_UNAVAILABLE), None, None


def is_space_awake(space_id: str, timeout: float = 4.0) -> bool:
    try:
        r = requests.get(f"https://huggingface.co/api/spaces/{space_id}", timeout=timeout)
        return r.status_code == 200 and (r.json().get("runtime") or {}).get("stage") == "RUNNING"
    except requests.RequestException:
        return False


def _stream_download(url: str, dest: Path, timeout: float = 60.0, headers: dict | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
    if dest.stat().st_size < 10_000:
        raise RuntimeError(f"Truncated MP4 ({dest.stat().st_size} B)")
    return dest


class VideoFailoverOrchestrator:
    def __init__(
        self,
        hf_token: str | None = None,
        bigmodel_api_key: str | None = None,
        kaggle_worker_url: str | None = None,
        pexels_api_key: str | None = None,
        global_deadline_s: float = 240.0,
    ) -> None:
        self.hf_token = hf_token or os.getenv("HF_TOKEN") or None
        self.bigmodel_key = bigmodel_api_key or os.getenv("BIGMODEL_API_KEY") or None
        self.kaggle_url = (kaggle_worker_url or os.getenv("KAGGLE_WORKER_URL") or "").rstrip("/") or None
        self.pexels_key = pexels_api_key or os.getenv("PEXELS_API_KEY") or None
        self.global_deadline_s = global_deadline_s
        self.spaces = build_default_spaces()
        self.quota_authed = ZeroGPUQuotaState()
        self.quota_anon = ZeroGPUQuotaState()

    def generate(
        self, prompt: str, output_path: str | Path = "output.mp4", duration_s: float = 5.0, seed: int = 42
    ) -> dict[str, Any]:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.global_deadline_s
        attempts: list[dict[str, Any]] = []

        # TIER 1: Quota-Aware HF ZeroGPU Cascade
        identities = ([("hf_free_token", self.hf_token, self.quota_authed)] if self.hf_token else []) + [
            ("anonymous", None, self.quota_anon)
        ]
        for id_label, tok, quota in identities:
            for sp in self.spaces:
                budget = deadline - time.monotonic()
                if budget < 20.0:
                    break
                if (sp.min_auth_required and not tok) or time.time() < sp.cooldown_until:
                    continue
                if not quota.can_fit(sp.est_reserved_s):
                    continue
                if not is_space_awake(sp.space_id):
                    sp.cooldown_until = time.time() + 300
                    attempts.append({"provider": sp.name, "kind": "sleeping"})
                    continue
                try:
                    t0 = time.monotonic()
                    self._run_space(sp, tok, prompt, duration_s, seed, dest, min(sp.timeout_s, budget - 5.0))
                    return {
                        "status": "ok", "tier": "hf_zerogpu", "provider": sp.name,
                        "identity": id_label, "path": str(dest), "latency_s": round(time.monotonic() - t0, 2),
                    }
                except Exception as exc:
                    kind, left_s, hms = classify_exception(exc)
                    attempts.append({"provider": sp.name, "identity": id_label, "kind": kind.value, "err": str(exc)[:180]})
                    if kind == FailureKind.ZEROGPU_PARTIAL_QUOTA and left_s is not None:
                        quota.record_partial(left_s, hms)
                    elif kind == FailureKind.ZEROGPU_EXHAUSTED:
                        quota.record_exhausted(hms[0] * 3600 + hms[1] * 60 + hms[2] if hms and any(hms) else 3600)
                        break
                    else:
                        sp.cooldown_until = time.time() + (90 if kind == FailureKind.QUEUE_TIMEOUT else 180)

        # TIER 2: Zhipu BigModel cogvideox-flash Free Async REST API
        if self.bigmodel_key and (deadline - time.monotonic()) >= 35.0:
            try:
                self._run_bigmodel(prompt, dest, min(120.0, deadline - time.monotonic() - 5.0))
                return {"status": "ok", "tier": "bigmodel_free", "provider": "cogvideox-flash", "path": str(dest)}
            except Exception as exc:
                attempts.append({"provider": "cogvideox-flash", "err": str(exc)[:180]})

        # TIER 3: Ephemeral Kaggle T4 + Cloudflare Quick Tunnel Worker
        if self.kaggle_url and (deadline - time.monotonic()) >= 30.0:
            try:
                _stream_download(
                    f"{self.kaggle_url}/generate?prompt={requests.utils.quote(prompt)}&duration={duration_s}&seed={seed}",
                    dest, timeout=min(120.0, deadline - time.monotonic() - 5.0),
                    headers={"X-Worker-Secret": os.getenv("KAGGLE_WORKER_SECRET", "")},
                )
                return {"status": "ok", "tier": "kaggle_worker", "provider": self.kaggle_url, "path": str(dest)}
            except Exception as exc:
                attempts.append({"provider": "kaggle_worker", "err": str(exc)[:180]})

        # TIER 4: Pexels Free Stock B-Roll -> Client Canvas Fallback
        if self.pexels_key and (deadline - time.monotonic()) >= 8.0:
            try:
                kw = " ".join(re.findall(r"[a-zA-Z]{4,}", prompt)[:4]) or "cinematic landscape"
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": self.pexels_key},
                    params={"query": kw, "orientation": "landscape", "per_page": 1}, timeout=10.0,
                )
                r.raise_for_status()
                mp4s = [v for v in r.json()["videos"][0]["video_files"] if v.get("file_type") == "video/mp4"]
                mp4s.sort(key=lambda v: abs((v.get("height") or 0) - 720))
                _stream_download(mp4s[0]["link"], dest, timeout=25.0)
                return {"status": "fallback_broll", "tier": "pexels", "path": str(dest), "attempts": attempts}
            except Exception as exc:
                attempts.append({"provider": "pexels", "err": str(exc)[:160]})

        return {
            "status": "fallback_canvas", "tier": "canvas", "path": None,
            "broll_keywords": re.findall(r"[a-zA-Z]{4,}", prompt)[:5], "attempts": attempts,
        }

    def _run_space(
        self, sp: SpaceEndpoint, token: str | None, prompt: str, dur: float, seed: int, dest: Path, timeout_s: float
    ) -> None:
        client = Client(sp.host_url, token=token, max_workers=2, verbose=False, httpx_kwargs={"timeout": 30.0})
        job, tmp = None, None
        try:
            job = client.submit(**sp.build_kwargs(prompt, dur, seed), api_name=sp.api_name)
            tmp = sp.extract_video_path(job.result(timeout=timeout_s))
            if not tmp or not os.path.exists(tmp):
                raise RuntimeError("Empty video output")
            shutil.move(tmp, dest)
        except Exception:
            if job is not None:
                try:
                    job.cancel()
                except Exception:
                    pass
            raise
        finally:
            if tmp and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            client.close()

    def _run_bigmodel(self, prompt: str, dest: Path, timeout_s: float) -> None:
        hdrs = {"Authorization": f"Bearer {self.bigmodel_key}", "Content-Type": "application/json"}
        r = requests.post(
            "https://open.bigmodel.cn/api/paas/v4/videos/generations",
            headers=hdrs, json={"model": "cogvideox-flash", "prompt": prompt[:512], "size": "1280x960", "fps": 30},
            timeout=15.0,
        )
        r.raise_for_status()
        task_id = r.json()["id"]
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            time.sleep(5.0)
            st = requests.get(f"https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}", headers=hdrs, timeout=15.0).json()
            if st.get("task_status") == "SUCCESS":
                _stream_download(st["video_result"][0]["url"], dest, timeout=45.0)
                return
            if st.get("task_status") == "FAIL":
                raise RuntimeError(f"BigModel failed: {st}")
        raise TimeoutError("BigModel polling timed out")
