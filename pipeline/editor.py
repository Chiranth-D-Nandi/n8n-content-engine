import asyncio
import subprocess
import json
import os
import platform
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EditJob:
    #required components
    job_id: int
    channel_id: str
    topic: str
    script: dict
    audio_path: Optional[Path] = None
    video_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    final_path: Optional[Path] = None
    errors: list = field(default_factory=list)

    def is_complete(self) -> bool:
        return self.final_path is not None and len(self.errors) == 0


class VideoEditor:

    def __init__(self, config: dict):
        self.config = config
        self.styles = config.get('caption_styles', {})

        for dir_name in ['temp', 'outputs']:
            Path(dir_name).mkdir(exist_ok=True)

    async def produce_reel(
        self,
        job: EditJob,
        channel: dict
    ) -> EditJob:
        print(f"\n[Editor] Producing reel: {job.topic[:50]}")

        job = await self._generate_audio(job, channel)
        if job.audio_path is None:
            print(f"[Editor] Audio failed, skipping reel")
            return job

        job = await self._generate_subtitles(job, channel)
        job = await self._compose_video(job, channel)

        if job.final_path:
            print(f"[Editor] Final reel: {job.final_path}")
        else:
            print(f"[Editor] Composition failed")

        return job

    async def _generate_audio(
        self,
        job: EditJob,
        channel: dict
    ) -> EditJob:
        #voiceover using edge tts
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

        try:
            print(f"  [Audio] Voice: {voice}")
            print(f"  [Audio] Words: {len(full_text.split())}")
            communicate = edge_tts.Communicate(full_text, voice)
            await communicate.save(str(output_path))
            job.audio_path = output_path
            print(f"  [Audio] Saved: {output_path}")
        except Exception as e:
            job.errors.append(f"Audio generation: {e}")
            print(f"  [Audio] Failed: {e}")

        return job

    async def _generate_subtitles(
        self,
        job: EditJob,
        channel: dict
    ) -> EditJob:
       #whisper for subtitle generation w/ timestamps
        subtitle_path = Path(f"temp/{job.job_id}_subs.ass")

        try:
            words = await asyncio.to_thread(
                self._transcribe_with_whisper,
                job.audio_path
            )

            if not words:
                print("  [Subtitles] No words transcribed")
                return job

            style_name = channel.get('caption_style', 'bold_white')
            style = self.styles.get(style_name, self._default_style())

            chunks = self._build_chunks(words, chunk_size=3)
            self._write_ass_file(chunks, subtitle_path, style)

            job.subtitle_path = subtitle_path
            print(f"  [Subtitles] {len(chunks)} chunks")

        except Exception as e:
            job.errors.append(f"Subtitle generation: {e}")
            print(f"  [Subtitles] {e}")

        return job

    def _transcribe_with_whisper(
        self,
        audio_path: Path
    ) -> list:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(
                'base',
                device='cpu',
                compute_type='int8'
            )
            segments, info = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language='en'
            )
            words = []
            for segment in segments:
                if segment.words is None:
                    continue
                for word in segment.words:
                    words.append({
                        'text': word.word.strip(),
                        'start': round(word.start, 3),
                        'end': round(word.end, 3)
                    })
            print(f"  [Whisper] Transcribed {len(words)} words")
            return words

        except ImportError:
            print("  [Whisper] faster-whisper not installed")
            print("  Run: pip install faster-whisper")
            return []
        except Exception as e:
            print(f"  [Whisper] Error: {e}")
            return []

    def _build_chunks(
        self,
        words: list,
        chunk_size: int = 3
    ) -> list:
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            clean_words = [w for w in chunk_words if w['text'].strip()]
            if not clean_words:
                continue
            chunks.append({
                'text': ' '.join(w['text'] for w in clean_words),
                'start': clean_words[0]['start'],
                'end': clean_words[-1]['end']
            })
        return chunks

    def _write_ass_file(
        self,
        chunks: list,
        output_path: Path,
        style: dict
    ):
        
        def seconds_to_ass(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            cs = int((seconds % 1) * 100)
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        def hex_to_ass(hex_color: str) -> str:
            hex_clean = hex_color.lstrip('#')
            r, g, b = hex_clean[0:2], hex_clean[2:4], hex_clean[4:6]
            return f"&H00{b}{g}{r}"

        primary = hex_to_ass(style.get('primary_color', '#FFFFFF'))
        stroke = hex_to_ass(style.get('stroke_color', '#000000'))
        font_size = style.get('font_size', 80)
        font = style.get('font', 'Arial Black')
        stroke_width = style.get('stroke_width', 4)
        position = style.get('position', 'center')
        
        # Convert bold and italic to ASS format (-1=true, 0=false)
        bold = -1 if style.get('bold', True) else 0
        italic = -1 if style.get('italic', False) else 0

        # Handle all three positions
        if position == 'top':
            pos_tag = '\\an8\\pos(540,300)'
        elif position == 'center':
            pos_tag = '\\an5\\pos(540,960)'
        else:  # bottom
            pos_tag = '\\an2\\pos(540,1600)'

        ass_content = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: no
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary},&H000000FF,{stroke},&H00000000,{bold},{italic},0,0,100,100,0,0,1,{stroke_width},0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        for chunk in chunks:
            start = seconds_to_ass(chunk['start'])
            end = seconds_to_ass(chunk['end'])
            text = chunk['text'].replace('{', '').replace('}', '')
            text = text.upper()
            ass_content += (
                f"Dialogue: 0,{start},{end},Default,,"
                f"0,0,0,,{{{pos_tag}}}{text}\n"
            )

        output_path.write_text(ass_content, encoding='utf-8')

    async def _compose_video(
        self,
        job: EditJob,
        channel: dict
    ) -> EditJob:
        try:
            output_dir = Path(f"outputs/{job.channel_id}")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"reel_{job.job_id}.mp4"

            if job.video_path and job.video_path.exists():
                job = await asyncio.to_thread(
                    self._compose_with_video,
                    job, output_path
                )
            else:
                # No video available and no fallback allowed
                raise RuntimeError(
                    f"No AI-generated video file found at {job.video_path}. "
                    "CogVideoX must produce a video before composition. "
                )

        except Exception as e:
            job.errors.append(f"Composition: {e}")
            print(f"  [Compose] Error: {e}")

        return job

    def _compose_with_video(
        self,
        job: EditJob,
        output_path: Path
    ) -> EditJob:
        import shutil

        # Get audio duration
        audio_duration = self._get_duration(job.audio_path)
        
        # Get video duration
        video_duration = self._get_duration(job.video_path)
        
        print(f"  [Compose] Video: {video_duration:.2f}s, Audio: {audio_duration:.2f}s")

        if job.subtitle_path and job.subtitle_path.exists():
            # Copy subtitle to temp/ with simple name (no spaces/colons)
            simple_sub = Path("temp") / f"s{job.job_id}.ass"
            shutil.copy2(job.subtitle_path, simple_sub)
            vf_filter = (
                "scale=1080:1920:"
                "force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                f"subtitles=s{job.job_id}.ass"
            )
        else:
            vf_filter = (
                "scale=1080:1920:"
                "force_original_aspect_ratio=increase,"
                "crop=1080:1920"
            )

        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', '-1',  # loop video input infinitely
            '-i', str(job.video_path.resolve()),
            '-i', str(job.audio_path.resolve()),
            '-vf', vf_filter,
            '-map', '0:v',
            '-map', '1:a',
            '-c:v', 'libx264',
            '-crf', '23',
            '-preset', 'fast',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-t', str(audio_duration),  # stop when audio ends
            str(output_path.resolve())
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(Path("temp").resolve())
        )

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr[-500:]}")

        job.final_path = output_path
        print(f"  [Compose] ✅ Video: {output_path}")
        return job

    def _get_duration(self, file_path: Path) -> float:
        """Get duration of audio or video file in seconds."""
        try:
            import json
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'json',
                    str(file_path.resolve())
                ],
                capture_output=True,
                text=True
            )
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration
        except Exception as e:
            print(f"  [Duration] Error getting duration: {e}")
            return 0.0

    def _default_style(self) -> dict:
        return {
            'font': 'Arial Black',
            'font_size': 80,
            'primary_color': '#FFFFFF',
            'stroke_color': '#000000',
            'stroke_width': 4,
            'position': 'center'
        }
