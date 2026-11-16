import os
import time
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from app.core.config import settings
from app.core.logging import logger
from app.schemas.job import JobStatus, PipelineStage
from app.repositories.job_repository import JobRepository
from app.repositories.channel_repository import ChannelRepository
from services.whisper_service.client import WhisperClient
from services.video_gateway.gateway import VideoGenerationGateway
from database.db import MatiksDatabase
from research.aggregator import TrendAggregator
from pipeline.llm import GeminiClient
from pipeline.generator import ContentGenerator
from pipeline.editor import VideoEditor, EditJob
from pipeline.reel_styles import get_style
from observability.tracing import get_tracer
from observability.metrics import (
    STAGE_DURATION_SECONDS,
    JOB_DURATION_SECONDS,
    JOBS_COMPLETED_TOTAL,
    JOBS_FAILED_TOTAL,
    JOBS_RUNNING_GAUGE,
    JOBS_QUEUED_GAUGE,
    JOB_RETRIES_TOTAL,
)


class PipelineService:
    def __init__(
        self,
        job_repo: JobRepository = None,
        channel_repo: ChannelRepository = None,
    ):
        self.job_repo = job_repo or JobRepository()
        self.channel_repo = channel_repo or ChannelRepository()
        self.whisper_client = WhisperClient()
        self.video_gateway = VideoGenerationGateway()
        self.tracer = get_tracer()

    def execute_job(self, job_id: str, payload: dict, task_instance=None) -> Dict[str, Any]:
        """
        Executes complete asynchronous reel pipeline for job_id.
        """
        start_time = time.time()
        channel_id = payload.get("channel_id")
        JOBS_QUEUED_GAUGE.dec()
        JOBS_RUNNING_GAUGE.inc()
        
        self.job_repo.update_job_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
            stage=PipelineStage.INIT,
            progress=5,
            backend_used=settings.VIDEO_BACKEND
        )
        
        try:
            # 1. Resolve Channel
            channel = self.channel_repo.get_channel(channel_id)
            if not channel:
                raise ValueError(f"Channel '{channel_id}' not found in configuration or genres.")
                
            # Apply payload overrides
            if payload.get("reel_count"):
                channel["reels_per_day"] = int(payload["reel_count"])
                
            custom_style = payload.get("subtitle_style")
            if custom_style:
                style_name = f"custom_{job_id[:8]}"
                self.channel_repo.save_caption_style(style_name, custom_style)
                channel["caption_style"] = style_name

            topic_override = payload.get("topic_override", "").strip()

            # 2. Stage: Research & Script
            topic, script = self._stage_research_and_script(
                job_id=job_id,
                channel=channel,
                topic_override=topic_override
            )

            # 3. Stage: Audio (TTS)
            audio_path = self._stage_audio_generation(
                job_id=job_id,
                channel=channel,
                script=script
            )

            # 4. Stage: Video Generation (Pluggable Gateway)
            video_path, video_meta = self._stage_video_generation(
                job_id=job_id,
                channel=channel,
                script=script
            )

            # 5. Stage: Subtitles (Whisper BentoML Microservice)
            subtitles_path = self._stage_subtitles_generation(
                job_id=job_id,
                channel=channel,
                audio_path=audio_path
            )

            # 6. Stage: Video Composition (FFmpeg)
            final_path = self._stage_composition(
                job_id=job_id,
                channel=channel,
                audio_path=audio_path,
                video_path=video_path,
                subtitles_path=subtitles_path,
                topic=topic,
                script=script
            )

            total_duration = time.time() - start_time
            size_mb = round(final_path.stat().st_size / 1024 / 1024, 2) if final_path.exists() else 0.0

            outputs = [{
                "topic": topic,
                "file": str(final_path),
                "size_mb": size_mb,
                "errors": []
            }]

            self.job_repo.complete_job(
                job_id=job_id,
                outputs=outputs,
                failed_reels=[],
                duration_seconds=round(total_duration, 2),
                backend_used=video_meta.get("backend", settings.VIDEO_BACKEND)
            )

            JOBS_COMPLETED_TOTAL.labels(
                channel_id=channel_id,
                backend=video_meta.get("backend", settings.VIDEO_BACKEND)
            ).inc()
            JOB_DURATION_SECONDS.labels(
                channel_id=channel_id,
                backend=video_meta.get("backend", settings.VIDEO_BACKEND)
            ).observe(total_duration)

            logger.info(f"Job {job_id} successfully completed in {total_duration:.2f}s! Output: {final_path}")
            return self.job_repo.get_job(job_id)

        except Exception as e:
            total_duration = time.time() - start_time
            error_msg = str(e)
            error_type = type(e).__name__
            
            logger.error(f"Job {job_id} failed: {error_msg}", exc_info=True)
            self.job_repo.update_job_status(
                job_id=job_id,
                status=JobStatus.FAILED,
                stage=PipelineStage.FAILED,
                error=error_msg,
                error_type=error_type,
            )
            
            JOBS_FAILED_TOTAL.labels(channel_id=channel_id or "unknown", error_type=error_type).inc()
            
            # Check if retryable by Celery
            if task_instance and hasattr(task_instance, "request") and task_instance.request.retries < task_instance.max_retries:
                # Do not retry permanent validation errors
                if not isinstance(e, (ValueError, FileNotFoundError)):
                    JOB_RETRIES_TOTAL.labels(stage="pipeline_retry").inc()
                    raise task_instance.retry(exc=e)
                    
            return self.job_repo.get_job(job_id)

        finally:
            JOBS_RUNNING_GAUGE.dec()

    def _stage_research_and_script(self, job_id: str, channel: dict, topic_override: str) -> tuple[str, dict]:
        stage_start = time.time()
        self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.RESEARCH, progress=15)
        
        with self.tracer.start_as_current_span("stage.research_and_script") as span:
            span.set_attribute("stage", "research_and_script")
            try:
                apis = {
                    "gemini_api_key": settings.GEMINI_API_KEY,
                    "youtube_api_key": settings.YOUTUBE_API_KEY,
                }
                config = {"apis": apis, "channels": [channel], "caption_styles": self.channel_repo.list_caption_styles()}
                
                db = MatiksDatabase(settings.DATABASE_PATH)
                aggregator = TrendAggregator(config, db)
                llm = GeminiClient(api_key=settings.GEMINI_API_KEY or "dummy_key")
                generator = ContentGenerator(llm, db, aggregator)
                
                # Execute async topic & script generation
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    if topic_override:
                        topic = topic_override
                        topic_data = {
                            "topic": topic,
                            "angle": "Direct user requested topic",
                            "hook_type": "curiosity_gap",
                            "inspired_by": "User Input"
                        }
                    else:
                        topics = loop.run_until_complete(
                            generator.generate_topics_for_channel(channel, user_keyword="")
                        )
                        topic_data = topics[0] if topics else {
                            "topic": f"The hidden truth about {channel['niche']}",
                            "angle": "Insider perspective",
                            "hook_type": "curiosity_gap"
                        }
                        topic = topic_data["topic"]

                    self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.SCRIPT, progress=30)
                    script = loop.run_until_complete(
                        generator.generate_script(channel, topic_data, user_keyword=topic_override)
                    )
                finally:
                    loop.close()

                duration = time.time() - stage_start
                STAGE_DURATION_SECONDS.labels(stage="research_and_script").observe(duration)
                self.job_repo.record_stage(job_id, "research_and_script", "complete", duration)
                return topic, script

            except Exception as e:
                duration = time.time() - stage_start
                self.job_repo.record_stage(job_id, "research_and_script", "failed", duration, str(e))
                raise

    def _stage_audio_generation(self, job_id: str, channel: dict, script: dict) -> Path:
        stage_start = time.time()
        self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.AUDIO, progress=45)
        
        with self.tracer.start_as_current_span("stage.audio_generation") as span:
            span.set_attribute("stage", "audio_generation")
            try:
                import edge_tts
                voice = channel.get("voice_preset", "en-US-ChristopherNeural")
                full_text = script.get("full_script") or (
                    f"{script.get('hook', '')}. {script.get('body', '')}. {script.get('cta', '')}."
                )

                output_path = Path("temp") / f"{job_id}_audio.mp3"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    communicate = edge_tts.Communicate(full_text, voice)
                    loop.run_until_complete(communicate.save(str(output_path)))
                finally:
                    loop.close()

                duration = time.time() - stage_start
                STAGE_DURATION_SECONDS.labels(stage="audio_generation").observe(duration)
                self.job_repo.record_stage(job_id, "audio_generation", "complete", duration)
                return output_path

            except Exception as e:
                duration = time.time() - stage_start
                self.job_repo.record_stage(job_id, "audio_generation", "failed", duration, str(e))
                raise

    def _stage_video_generation(self, job_id: str, channel: dict, script: dict) -> tuple[Path, dict]:
        stage_start = time.time()
        self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.VIDEO, progress=60)
        
        with self.tracer.start_as_current_span("stage.video_generation") as span:
            span.set_attribute("stage", "video_generation")
            try:
                video_prompt = script.get("video_prompt") or f"Cinematic scene representing {channel.get('niche')}"
                output_path = Path("temp") / f"{job_id}_video.mp4"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                result = self.video_gateway.generate_video(
                    prompt=video_prompt,
                    output_path=output_path,
                    num_frames=49,
                    num_inference_steps=30
                )

                duration = time.time() - stage_start
                STAGE_DURATION_SECONDS.labels(stage="video_generation").observe(duration)
                self.job_repo.record_stage(job_id, "video_generation", "complete", duration)
                return Path(result.video_path), result.dict()

            except Exception as e:
                duration = time.time() - stage_start
                self.job_repo.record_stage(job_id, "video_generation", "failed", duration, str(e))
                raise

    def _stage_subtitles_generation(self, job_id: str, channel: dict, audio_path: Path) -> Path:
        stage_start = time.time()
        self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.SUBTITLES, progress=75)
        
        with self.tracer.start_as_current_span("stage.subtitles_generation") as span:
            span.set_attribute("stage", "subtitles_generation")
            try:
                # Transcribe via Whisper BentoML Microservice
                words = self.whisper_client.transcribe(audio_path=audio_path, language="en")
                
                subtitle_path = Path("temp") / f"{job_id}_subs.ass"
                subtitle_path.parent.mkdir(parents=True, exist_ok=True)

                styles = self.channel_repo.list_caption_styles()
                style_name = channel.get("caption_style", "bold_white")
                style = styles.get(style_name, {
                    "font": "Arial Black", "font_size": 80, "primary_color": "#FFFFFF",
                    "stroke_color": "#000000", "stroke_width": 4, "position": "center",
                    "bold": True, "italic": False
                })

                editor = VideoEditor({"caption_styles": styles})
                chunks = editor._build_chunks(words, chunk_size=3)
                editor._write_ass_file(chunks, subtitle_path, style)

                duration = time.time() - stage_start
                STAGE_DURATION_SECONDS.labels(stage="subtitles_generation").observe(duration)
                self.job_repo.record_stage(job_id, "subtitles_generation", "complete", duration)
                return subtitle_path

            except Exception as e:
                duration = time.time() - stage_start
                self.job_repo.record_stage(job_id, "subtitles_generation", "failed", duration, str(e))
                raise

    def _stage_composition(
        self,
        job_id: str,
        channel: dict,
        audio_path: Path,
        video_path: Path,
        subtitles_path: Path,
        topic: str,
        script: dict
    ) -> Path:
        stage_start = time.time()
        self.job_repo.update_job_status(job_id=job_id, status=JobStatus.RUNNING, stage=PipelineStage.COMPOSITION, progress=90)
        
        with self.tracer.start_as_current_span("stage.composition") as span:
            span.set_attribute("stage", "composition")
            try:
                output_dir = Path("outputs") / channel["id"]
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"reel_{job_id}.mp4"

                styles = self.channel_repo.list_caption_styles()
                editor = VideoEditor({"caption_styles": styles})

                edit_job = EditJob(
                    job_id=job_id,
                    channel_id=channel["id"],
                    topic=topic,
                    script=script,
                    audio_path=audio_path,
                    video_path=video_path,
                    subtitle_path=subtitles_path
                )

                # Execute FFmpeg composition safely
                edit_job = editor._compose_with_video(edit_job, output_path)

                duration = time.time() - stage_start
                STAGE_DURATION_SECONDS.labels(stage="composition").observe(duration)
                self.job_repo.record_stage(job_id, "composition", "complete", duration)
                return output_path

            except Exception as e:
                duration = time.time() - stage_start
                self.job_repo.record_stage(job_id, "composition", "failed", duration, str(e))
                raise
