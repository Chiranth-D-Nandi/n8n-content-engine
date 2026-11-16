"""
pipeline/cogvideo.py - CogVideoX-2b generation for RTX 4060 8GB
"""

import os
import torch
import time
import numpy as np
from pathlib import Path
from typing import Optional

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '600'

# INT8 import
try:
    from torchao.quantization import quantize_, int8_dynamic_activation_int8_weight
    HAS_INT8 = True
except ImportError:
    HAS_INT8 = False
    int8_dynamic_activation_int8_weight = None


class CogVideoXGenerator:
    """
    Local AI video generation using CogVideoX-2b.
    """

    _instance = None
    _pipe = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self, use_int8: bool = False):  # INT8 OFF by default
        """
        Load CogVideoX-2b.
        
        use_int8=False by default:
            INT8 quantization with CogVideoX causes silent hangs
            on some GPU/driver combinations. Disable unless
            you've confirmed it works on your system.
        """
        if self._loaded:
            print("[CogVideo] Model already loaded")
            return

        print("[CogVideo] Loading CogVideoX-2b...")
        
        # Check CUDA availability first
        if not torch.cuda.is_available():
            print("[CogVideo] No CUDA GPU detected!")
            print("[CogVideo] CogVideoX requires a CUDA GPU")
            raise RuntimeError("CUDA GPU required for CogVideoX generation")
        
        # Show VRAM info
        props = torch.cuda.get_device_properties(0)
        free, total = torch.cuda.mem_get_info()
        print(f"[CogVideo] GPU: {props.name}")
        print(f"[CogVideo] VRAM total: {total/1024**3:.1f}GB")
        print(f"[CogVideo] VRAM free:  {free/1024**3:.2f}GB")

        from diffusers import CogVideoXPipeline

        # Load to CPU first, then offload handles GPU placement
        print("[CogVideo] Loading to CPU (offload will manage GPU)...")
        self._pipe = CogVideoXPipeline.from_pretrained(
            "THUDM/CogVideoX-2b",
            torch_dtype=torch.float16
        )
        print("[CogVideo] Pipeline loaded to CPU")

        # INT8 quantization - disabled by default
        if use_int8 and HAS_INT8:
            print("[CogVideo] Applying INT8 quantization...")
            try:
                quantize_(
                    self._pipe.transformer,
                    int8_dynamic_activation_int8_weight
                )
                print("[CogVideo] INT8 applied")
            except Exception as e:
                print(f"[CogVideo] INT8 failed: {e}")
        else:
            print("[CogVideo] Using float16 (stable, no INT8)")

        # Enable offload with fallback chain
        print("[CogVideo] Enabling CPU offload...")
        self._enable_offload_with_fallback()

        # VAE tiling: decode video in spatial tiles instead of all at once
        # Without this: VAE tries to decode all 49 frames × full resolution → OOM
        # With this: decodes small spatial chunks → fits in VRAM
        print("[CogVideo] Enabling VAE tiling...")
        try:
            self._pipe.vae.enable_tiling()
            print("[CogVideo] VAE tiling enabled")
            print("[CogVideo]    Decodes in spatial chunks → prevents VAE OOM")
        except AttributeError:
            print("[CogVideo] VAE tiling not available on this version")

        # VAE slicing: processes one frame at a time through VAE
        # Works together with tiling for maximum memory efficiency
        print("[CogVideo] Enabling VAE slicing...")
        try:
            self._pipe.vae.enable_slicing()
            print("[CogVideo] VAE slicing enabled")
            print("[CogVideo]    Processes one frame at a time through VAE")
        except AttributeError:
            print("[CogVideo] VAE slicing not available on this version")

        self._loaded = True

        free, total = torch.cuda.mem_get_info()
        print(f"[CogVideo] VRAM after load: {free/1024**3:.2f}GB free")
        print("[CogVideo] Ready for generation")

    def _enable_offload_with_fallback(self):
        """
        Try offload methods in order from best to worst.
        Different diffusers versions support different methods.
        
        Hierarchy:
        1. enable_sequential_cpu_offload() - best memory, needs accelerate
        2. enable_model_cpu_offload()      - less optimal, needs accelerate  
        3. .to("cuda")                     - no offload, needs full VRAM
        4. stay on CPU                     - slowest, no GPU
        """
        
        # Method 1: Sequential offload (best for 8GB VRAM)
        try:
            self._pipe.enable_sequential_cpu_offload()
            print("[CogVideo] Sequential CPU offload enabled (best)")
            print("[CogVideo]    One layer in VRAM at a time")
            print("[CogVideo]    Uses ~6GB VRAM + ~12GB RAM")
            return
        except RuntimeError as e:
            if "accelerate" in str(e).lower():
                print(f"[CogVideo] Sequential offload needs accelerate:")
                print(f"[CogVideo]    pip install accelerate")
            else:
                print(f"[CogVideo] Sequential offload failed: {e}")
        except Exception as e:
            print(f"[CogVideo] Sequential offload failed: {e}")

        # Method 2: Model offload (less granular than sequential)
        try:
            self._pipe.enable_model_cpu_offload()
            print("[CogVideo] Model CPU offload enabled (good)")
            print("[CogVideo]    Full model moves GPU↔CPU between stages")
            return
        except RuntimeError as e:
            if "accelerate" in str(e).lower():
                print(f"[CogVideo] Model offload also needs accelerate")
                print(f"[CogVideo]    Install: pip install accelerate")
                print(f"[CogVideo]    Then restart and try again")
            else:
                print(f"[CogVideo] Model offload failed: {e}")
        except Exception as e:
            print(f"[CogVideo] Model offload failed: {e}")

        # Method 3: Direct CUDA (no offload - needs full VRAM)
        try:
            if torch.cuda.is_available():
                free_vram = torch.cuda.mem_get_info()[0] / 1024**3
                print(f"[CogVideo] No offload available")
                print(f"[CogVideo]    Loading directly to GPU")
                print(f"[CogVideo]    Free VRAM: {free_vram:.1f}GB")
                print(f"[CogVideo]    Need ~12GB - may OOM on 8GB GPU")
                self._pipe = self._pipe.to("cuda")
                print(f"[CogVideo]    Loaded to GPU (may fail during generation)")
                return
        except torch.cuda.OutOfMemoryError:
            print(f"[CogVideo] OOM loading to GPU")
            print(f"[CogVideo]    MUST install accelerate for offload")
            print(f"[CogVideo]    pip install accelerate")
            raise RuntimeError(
                "Cannot load CogVideoX: GPU OOM and no offload available.\n"
                "Fix: pip install accelerate"
            )

        # Method 4: CPU only (extremely slow but works)
        print(f"[CogVideo] Falling back to CPU-only mode")
        print(f"[CogVideo]    Generation will take HOURS not minutes")
        print(f"[CogVideo]    Strongly recommended: pip install accelerate")

    def generate_video_sync(
        self,
        prompt: str,
        output_path: Path,
        num_frames: int = 49,
        num_inference_steps: int = 30,
        guidance_scale: float = 6.0
    ) -> Path:
        """
        Generate video - synchronous, blocks caller.
        
        RTX 4060 timing estimates:
            9 frames,  5 steps:  ~2-3 min  (test only)
            25 frames, 20 steps: ~8-12 min (fast draft)
            49 frames, 30 steps: ~15-25 min (standard)
            49 frames, 50 steps: ~30-45 min (high quality)
        
        The progress bar shows steps, not time.
        Step 1 takes longest (cold start).
        Steps 2+ are faster.
        """
        if not self._loaded:
            self.load_model()

        print(f"\n[CogVideo] === GENERATION START ===")
        print(f"[CogVideo] Prompt: '{prompt[:80]}'")
        print(f"[CogVideo] Frames: {num_frames} | Steps: {num_inference_steps}")
        print(f"[CogVideo] Output: {output_path}")
        
        if torch.cuda.is_available():
            free = torch.cuda.mem_get_info()[0] / 1024**3
            print(f"[CogVideo] VRAM free: {free:.2f}GB")
            torch.cuda.empty_cache()

        # Track timing per step to detect hangs
        step_times = []
        generation_start = time.time()

        def progress_callback(pipe, step, timestep, callback_kwargs):
            """
            Called after each denoising step.
            
            If you see NO output from this callback,
            the model is hanging before even step 1.
            Usually means: OOM, device mismatch, or
            quantization incompatibility.
            """
            now = time.time()
            elapsed = now - generation_start
            
            if step_times:
                step_duration = now - step_times[-1]
                # Estimate remaining time
                avg_step = elapsed / (step + 1)
                remaining_steps = num_inference_steps - step - 1
                eta_seconds = int(avg_step * remaining_steps)
                eta_str = f"{eta_seconds//60}m {eta_seconds%60}s remaining"
            else:
                step_duration = elapsed
                eta_str = "calculating..."
            
            step_times.append(now)
            
            # Progress bar: [====    ] 4/30
            bar_width = 20
            filled = int(bar_width * (step + 1) / num_inference_steps)
            bar = '=' * filled + ' ' * (bar_width - filled)
            
            print(
                f"\r[CogVideo] [{bar}] "
                f"{step+1}/{num_inference_steps} | "
                f"{elapsed:.0f}s elapsed | "
                f"{eta_str}",
                end='', flush=True
            )
            
            return callback_kwargs

        print("[CogVideo] Starting generation...")
        print()

        # Try with requested frames first, fall back to fewer if OOM
        frames_to_try = [num_frames, 25, 9]
        video_frames = None

        for attempt, frames in enumerate(frames_to_try):
            if attempt > 0:
                print(f"\n[CogVideo] Retrying with {frames} frames...")
                torch.cuda.empty_cache()
                time.sleep(2)

            try:
                # CRITICAL: Use CPU generator
                generator = torch.Generator("cpu").manual_seed(42)

                output = self._pipe(
                    prompt=prompt,
                    num_frames=frames,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                    callback_on_step_end=progress_callback,
                    callback_on_step_end_tensor_inputs=["latents"]
                )

                print()
                video_frames = output.frames[0]

                total_time = time.time() - generation_start
                print(f"[CogVideo] Generation complete in {total_time/60:.1f} min")
                print(f"[CogVideo] Frames: {len(video_frames)}")
                break  # success - exit retry loop

            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                print()
                error_str = str(e).lower()
                
                if "out of memory" in error_str or isinstance(e, torch.cuda.OutOfMemoryError):
                    print(f"[CogVideo] OOM with {frames} frames")
                    if frames == frames_to_try[-1]:
                        # Exhausted all options
                        raise RuntimeError(
                            f"OOM even with {frames} frames. "
                            f"Close other GPU applications and retry."
                        )
                    # Try next frame count
                    continue
                else:
                    raise

        if video_frames is None:
            raise RuntimeError("Failed to generate video after all retries")

        # Save video
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[CogVideo] Encoding {len(video_frames)} frames to MP4...")
        self._save_as_mp4(video_frames, output_path)
        print(f"[CogVideo] Saved: {output_path}")
        
        return output_path

    def _save_as_mp4(self, frames: list, output_path: Path, fps: int = 8):
        """Save PIL Image list as MP4."""
        import imageio

        writer = imageio.get_writer(
            str(output_path),
            format='FFMPEG',
            mode='I',
            fps=fps,
            codec='libx264',
            quality=8
        )

        for frame in frames:
            writer.append_data(np.array(frame))

        writer.close()

    def generate_video(
        self,
        prompt: str,
        output_path: Path,
        num_inference_steps: int = 30
    ) -> Path:
        """Public interface. Synchronous."""
        return self.generate_video_sync(
            prompt=prompt,
            output_path=output_path,
            num_frames=49,
            num_inference_steps=num_inference_steps
        )
