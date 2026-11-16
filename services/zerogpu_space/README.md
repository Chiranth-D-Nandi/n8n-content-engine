# CogVideoX-2B Hugging Face ZeroGPU Space

This directory contains the standalone Gradio Space app for remote GPU video inference.

## How to Deploy on Hugging Face ZeroGPU (100% Free, No Credit Card)

1. **Prerequisites:**
   - A free Hugging Face account (account must be 30+ days old per HF ZeroGPU terms).
   - Verified email address.
   - Zero cost, ₹0 expenditure, no credit card required.

2. **Create New Space:**
   - Go to [Hugging Face Spaces](https://huggingface.co/new-space).
   - Space Name: `cogvideox-2b-gateway`
   - License: `mit`
   - Space SDK: **Gradio**
   - Space Hardware: **ZeroGPU** (gives 48GB VRAM half RTX Pro 6000 Blackwell for free).

3. **Upload Files:**
   - Copy `app.py` and `requirements.txt` from this directory into your Space repository.
   - Hugging Face will automatically install dependencies and initialize the Space.

4. **Connect to n8n Content Engine:**
   - In your `.env` or deployment environment variables, set:
     ```env
     VIDEO_BACKEND=REAL_REMOTE
     HF_SPACE_URL=https://<your-username>-cogvideox-2b-gateway.hf.space
     HF_TOKEN=hf_your_read_token_here
     ```

## Free Tier Operating Rules
- **Quota:** 5 GPU-minutes per day on a free account.
- **Capacity:** At ~50-70 seconds per 49-frame reel, you can generate 2 to 3 real AI video reels per day for free!
- **Sleeping Behavior:** The Space sleeps after 48-72 hours of idle time. The client automatically handles waking up and reports queue rank.
