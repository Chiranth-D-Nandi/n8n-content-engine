"""
Hugging Face ZeroGPU Space for CogVideoX-2B Video Generation
Deploy this code as a Gradio Space with ZeroGPU hardware on Hugging Face.
Free accounts get 48GB VRAM (half RTX Pro 6000 Blackwell) at zero cost with no credit card.
"""

import os
import tempfile
from pathlib import Path
import torch
import numpy as np
import imageio
import gradio as gr
from diffusers import CogVideoXPipeline

# Check if running in Hugging Face ZeroGPU environment
try:
    import spaces
    HAS_ZEROGPU = True
except ImportError:
    HAS_ZEROGPU = False
    print("[Warning] 'spaces' module not found. Running in standard CUDA mode.")

print("[ZeroGPU Space] Initializing CogVideoX-2B pipeline...")
# Model is loaded ONCE at module import into CUDA (CUDA-emulated outside @spaces.GPU)
pipe = CogVideoXPipeline.from_pretrained(
    "THUDM/CogVideoX-2b",
    torch_dtype=torch.float16
).to("cuda")

try:
    pipe.vae.enable_tiling()
    print("[ZeroGPU Space] VAE tiling enabled")
except AttributeError:
    pass

try:
    pipe.vae.enable_slicing()
    print("[ZeroGPU Space] VAE slicing enabled")
except AttributeError:
    pass

print("[ZeroGPU Space] CogVideoX-2B pipeline ready ✅")


def _generate_video_internal(prompt: str, num_frames: int = 49, num_inference_steps: int = 30) -> str:
    """Internal generation executed on GPU."""
    print(f"[ZeroGPU] Generating: '{prompt[:70]}' (frames={num_frames}, steps={num_inference_steps})")
    
    generator = torch.Generator("cpu").manual_seed(42)
    output = pipe(
        prompt=prompt,
        num_frames=num_frames,
        num_inference_steps=num_inference_steps,
        guidance_scale=6.0,
        generator=generator
    )
    
    frames = output.frames[0]
    
    # Save output to temporary MP4
    temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    output_path = temp_file.name
    temp_file.close()
    
    writer = imageio.get_writer(
        output_path,
        format="FFMPEG",
        mode="I",
        fps=8,
        codec="libx264",
        quality=8
    )
    for frame in frames:
        writer.append_data(np.array(frame))
    writer.close()
    
    print(f"[ZeroGPU] Encoded video to: {output_path}")
    return output_path


# Wrap with @spaces.GPU(duration=150) if in ZeroGPU environment
if HAS_ZEROGPU:
    @spaces.GPU(duration=150)
    def generate_reel_video(prompt: str, num_frames: int = 49, num_inference_steps: int = 30) -> str:
        return _generate_video_internal(prompt, num_frames, num_inference_steps)
else:
    def generate_reel_video(prompt: str, num_frames: int = 49, num_inference_steps: int = 30) -> str:
        return _generate_video_internal(prompt, num_frames, num_inference_steps)


# Build Gradio Interface exposing api_name="/generate"
demo = gr.Interface(
    fn=generate_reel_video,
    inputs=[
        gr.Textbox(label="Prompt", lines=3, placeholder="Describe visual scene for video reel..."),
        gr.Slider(minimum=9, maximum=49, value=49, step=8, label="Frames (49 ≈ 6s)"),
        gr.Slider(minimum=10, maximum=50, value=30, step=5, label="Inference Steps")
    ],
    outputs=gr.Video(label="Generated Video"),
    title="CogVideoX-2B ZeroGPU Inference Gateway",
    description="Zero-cost remote GPU video generation backend for n8n-content-engine."
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
