

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime

import torch

from pipeline.cogvideo import CogVideoXGenerator
from pipeline.editor import VideoEditor, EditJob
from pipeline.generator import ContentGenerator
from pipeline.llm import GeminiClient
from research.aggregator import TrendAggregator
from database.db import MatiksDatabase


@dataclass
class ReelJob:
    """
    The state object for one complete reel.
    Flows through the entire pipeline.
    """
    job_id: int
    channel_id: str
    channel_name: str
    topic: str
    niche: str
    script: Optional[dict] = None
    audio_path: Optional[Path] = None
    video_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    final_path: Optional[Path] = None
    errors: list = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        return f"{secs//60}m {secs%60}s"

    def is_complete(self) -> bool:
        return self.final_path is not None

    def log_error(self, stage: str, error: Exception):
        msg = f"[{stage}] {type(error).__name__}: {str(error)}"
        self.errors.append(msg)
        print(f"  ❌ {msg}")


class FullPipeline:
    """
    Orchestrates all stages to produce a complete reel.
    """

    def __init__(self, config: dict):
        self.config = config
        apis = config['apis']

        self.db = MatiksDatabase()
        self.aggregator = TrendAggregator(config, self.db)
        self.llm = GeminiClient(
            api_key=apis['gemini_api_key']
        )
        self.generator = ContentGenerator(
            self.llm, self.db, self.aggregator
        )

        # Video generation: CogVideoX local only - no fallback
        self.cogvideo = CogVideoXGenerator()
        self.editor = VideoEditor(config)

        for d in ['temp', 'outputs', 'inbox', 'assets/music']:
            Path(d).mkdir(exist_ok=True)

        # Pre-load CogVideoX model
        print("[Pipeline] Pre-loading CogVideoX model...")
        print("[Pipeline] First run downloads ~16GB from HuggingFace")
        self.cogvideo.load_model()
        print("[Pipeline] CogVideoX ready ✅")

    async def produce_reel(
        self,
        job: ReelJob,
        channel: dict,
        user_keyword: str = ""
    ) -> ReelJob:
        """Full pipeline for one reel."""
        print(f"\n{'='*55}")
        print(f"  🎬 JOB #{job.job_id}: {job.topic[:45]}")
        print(f"     Channel: {job.channel_name}")
        print(f"     Niche:   {job.niche}")
        print(f"{'='*55}")

        # ── STAGE 1: Research + Script ─────────────────────
        print("\n  📊 STAGE 1: Research + Script Generation")
        job = await self._stage_research_and_script(
            job, channel, user_keyword
        )
        if job.script is None:
            print("  ❌ Script generation failed. Stopping job.")
            return job
        print(f"  ✅ Script ready")

        # ── STAGE 2: Audio + Video in PARALLEL ─────────────
        print("\n  🎙 STAGE 2: Audio + Video Generation (parallel)")
        print("     Audio: edge-tts → voice.mp3")
        print("     Video: CogVideoX local → background.mp4")
        job = await self._stage_audio_and_video_parallel(job, channel)

        # Hard stop: if video failed, do not proceed
        if job.video_path is None:
            print("  ❌ Video generation failed. Cannot produce reel without AI video.")
            print("     Errors:", job.errors)
            return job

        # Hard stop: if audio failed, do not proceed
        if job.audio_path is None:
            print("  ❌ Audio generation failed. Cannot produce reel without voiceover.")
            return job

        # ── STAGE 3: Subtitles ──────────────────────────────
        print("\n  📝 STAGE 3: Subtitle Generation")
        edit_job = EditJob(
            job_id=job.job_id,
            channel_id=job.channel_id,
            topic=job.topic,
            script=job.script,
            audio_path=job.audio_path,
            video_path=job.video_path
        )
        edit_job = await self.editor._generate_subtitles(edit_job, channel)
        job.subtitle_path = edit_job.subtitle_path

        # ── STAGE 4: Final Composition ──────────────────────
        print("\n  🎞 STAGE 4: Video Composition")
        job = await self._stage_compose(job, channel)

        # ── DONE ────────────────────────────────────────────
        elapsed = job.elapsed()
        if job.is_complete():
            print(f"\n  ✅ REEL COMPLETE in {elapsed}")
            print(f"  📁 {job.final_path}")
        else:
            print(f"\n  ⚠️  REEL INCOMPLETE after {elapsed}")
            print(f"     Errors: {job.errors}")

        return job

    async def _stage_research_and_script(
        self,
        job: ReelJob,
        channel: dict,
        user_keyword: str = ""
    ) -> ReelJob:
        """Research trends and generate script."""
        try:
            research = await self.aggregator.research_niche(
                niche=job.niche,
                keywords=channel['search_keywords'],
                genre=channel,
                user_keyword=user_keyword
            )
            briefing = self.aggregator.build_llm_briefing(research)

            topic_data = {
                'topic': job.topic,
                'angle': 'From live trend research',
                'hook_type': 'curiosity_gap',
                'inspired_by': briefing[:100]
            }

            script = await self.generator.generate_script(
                channel, topic_data, user_keyword=user_keyword
            )
            job.script = script

        except Exception as e:
            job.log_error('ResearchAndScript', e)

        return job

    async def _stage_audio_and_video_parallel(
        self,
        job: ReelJob,
        channel: dict
    ) -> ReelJob:
        """
        Run audio and video generation at the same time.

        NOTE: asyncio.gather runs both coroutines concurrently.
        _generate_video uses asyncio.to_thread so CUDA stays in one thread.
        """
        audio_task = self._generate_audio(job, channel)
        video_task = self._generate_video(job, channel)

        results = await asyncio.gather(
            audio_task,
            video_task,
            return_exceptions=True
        )

        audio_result, video_result = results

        if isinstance(audio_result, Exception):
            job.log_error('Audio', audio_result)
        elif isinstance(audio_result, Path):
            job.audio_path = audio_result
            print(f"  ✅ Audio: {audio_result.name}")

        if isinstance(video_result, Exception):
            # Surface the error - no silent fallback
            job.log_error('Video', video_result)
            print(f"  ❌ CogVideoX generation failed: {video_result}")
            # video_path stays None → produce_reel will stop here
        elif isinstance(video_result, Path):
            job.video_path = video_result
            print(f"  ✅ Video: {video_result.name}")

        return job

    async def _generate_audio(
        self,
        job: ReelJob,
        channel: dict
    ) -> Path:
        """Generate voiceover using edge-tts."""
        import edge_tts

        voice = channel.get('voice_preset', 'en-US-ChristopherNeural')
        script = job.script

        full_text = script.get('full_script', '')
        if not full_text:
            full_text = (
                f"{script.get('hook', '')}. "
                f"{script.get('body', '')}. "
                f"{script.get('cta', '')}."
            )

        output_path = Path(f"temp/{job.job_id}_audio.mp3")
        communicate = edge_tts.Communicate(full_text, voice)
        await communicate.save(str(output_path))
        return output_path

    async def _generate_video(
        self,
        job: ReelJob,
        channel: dict
    ) -> Path:
        """
        Generate background video using CogVideoX locally.
        NO fallback. If this fails, the reel fails.

        FIX: Use asyncio.to_thread() so the synchronous CUDA call
        doesn't block the event loop. The CUDA context is kept in
        the same OS thread (to_thread uses a thread pool, and since
        CogVideoX is a singleton, the context follows the model).
        """
        video_prompt = job.script.get('video_prompt', '')
        if not video_prompt:
            raise ValueError(
                "Script has no video_prompt field. "
                "Check that Gemini returned a complete script JSON."
            )

        output_path = Path(f"temp/{job.job_id}_video.mp4")

        try:
            # FIX: asyncio.to_thread wraps the synchronous CogVideoX call
            # This prevents blocking the event loop during the 15-25 min generation
            result = await asyncio.to_thread(
                self.cogvideo.generate_video,
                video_prompt,
                output_path
            )
            return result

        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            raise RuntimeError(
                "GPU out of memory during CogVideoX generation. "
                "Close other GPU applications and retry. "
                "No fallback video will be used."
            )

    async def _stage_compose(
        self,
        job: ReelJob,
        channel: dict
    ) -> ReelJob:
        """
        Compose final reel using FFmpeg.

        FIX: Only _compose_with_video path exists now.
        If job.video_path is None (should not reach here due to
        early exit in produce_reel), log error and return incomplete.
        """
        if not job.video_path or not job.video_path.exists():
            job.log_error(
                'Compose',
                RuntimeError(
                    "No AI-generated video file available. "
                    "CogVideoX must succeed before composition. "
                    "No fallback background will be used."
                )
            )
            return job

        try:
            output_dir = Path(f"outputs/{job.channel_id}")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"reel_{job.job_id}.mp4"

            edit_job = EditJob(
                job_id=job.job_id,
                channel_id=job.channel_id,
                topic=job.topic,
                script=job.script,
                audio_path=job.audio_path,
                video_path=job.video_path,
                subtitle_path=job.subtitle_path
            )

            # Always compose with the AI-generated video
            edit_job = await asyncio.to_thread(
                self.editor._compose_with_video,
                edit_job,
                output_path
            )

            job.final_path = edit_job.final_path
            job.errors.extend(edit_job.errors)

        except Exception as e:
            job.log_error('Compose', e)

        return job

    async def run_all_channels(self) -> list:
        """Process all channels."""
        channels = self.config['channels']
        user_keyword = self.config.get('user_keyword', '')

        all_jobs = []
        job_counter = 1

        print(f"\n  🚀 Starting pipeline for {len(channels)} channel(s)")
        print(f"     Total reels to produce: "
              f"{sum(c['reels_per_day'] for c in channels)}")

        for channel in channels:
            print(f"\n\n{'#'*55}")
            print(f"# CHANNEL: {channel['name']}")
            print(f"# {channel['reels_per_day']} reels/day")
            if user_keyword:
                print(f"# Topic: {user_keyword}")
            print(f"{'#'*55}")

            Path(f"outputs/{channel['id']}").mkdir(
                parents=True, exist_ok=True
            )

            try:
                topics = await self.generator.generate_topics_for_channel(
                    channel,
                    user_keyword=user_keyword
                )
            except Exception as e:
                print(f"  ❌ Topic generation failed for {channel['name']}: {e}")
                continue

            for topic_data in topics:
                job = ReelJob(
                    job_id=job_counter,
                    channel_id=channel['id'],
                    channel_name=channel['name'],
                    topic=topic_data['topic'],
                    niche=channel['niche']
                )

                completed_job = await self.produce_reel(
                    job, channel, user_keyword=user_keyword
                )
                all_jobs.append(completed_job)
                job_counter += 1

        return all_jobs
