
import os
import json
import time
from google.genai import Client


GEMINI_MODELS = [
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-pro-latest",
]


class GeminiClient:

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.is_configured = bool(self.api_key and self.api_key != "dummy_key")
        self.client = Client(api_key=self.api_key) if self.is_configured else None
        self.model_name = model or GEMINI_MODELS[0]
        self._last_call = 0
        self._min_delay = 4  # seconds between calls (15 rpm = 4s apart)

    def _rate_limit(self):
        if not self.is_configured:
            return
        elapsed = time.time() - self._last_call
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_call = time.time()

    def generate(self, prompt: str) -> str:
        self._rate_limit()
        models_to_try = [self.model_name] + [m for m in GEMINI_MODELS if m != self.model_name]
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model, contents=prompt
                )
                return response.text
            except Exception as e:
                print(f"[Gemini] Error with model {model}: {e}")
                if "503" in str(e) or "404" in str(e) or "unavailable" in str(e).lower():
                    continue
        return ""

    def generate_json(
        self,
        prompt: str,
        retries: int = 2
    ) -> dict:
        """
        JSON generation with multi-model failover.
        """
        if not self.is_configured:
            return {}

        json_prompt = (
            prompt
            + "\n\nCRITICAL: Output ONLY valid JSON. "
            + "No markdown. No code blocks. No explanation. "
            + "Just the raw JSON object starting with { "
            + "and ending with }"
        )

        models_to_try = [self.model_name] + [m for m in GEMINI_MODELS if m != self.model_name]
        for model in models_to_try:
            for attempt in range(retries):
                self._rate_limit()

                try:
                    response = self.client.models.generate_content(
                        model=model, contents=json_prompt
                    )
                    raw = response.text.strip()

                    # Strip markdown code blocks if present
                    if raw.startswith("```"):
                        lines = raw.split('\n')
                        raw = '\n'.join(lines[1:-1])

                    if raw.startswith("json"):
                        raw = raw[4:].strip()

                    parsed = json.loads(raw)
                    if parsed:
                        return parsed

                except json.JSONDecodeError as e:
                    print(f"[Gemini] JSON parse failed on {model} attempt {attempt + 1}: {e}")

                except Exception as e:
                    print(f"[Gemini] Error on {model} attempt {attempt + 1}: {e}")
                    # If 503 or 404, switch to next model immediately without waiting
                    if "503" in str(e) or "404" in str(e) or "unavailable" in str(e).lower():
                        break

        print("[Gemini] All models/retries exhausted, returning empty dict")
        return {}

    async def generate_json_async(self, prompt: str) -> dict:
        import asyncio
        return await asyncio.to_thread(self.generate_json, prompt)
