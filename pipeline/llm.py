
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from google.genai import Client


GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]


class GeminiClient:

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.is_configured = bool(self.api_key and self.api_key != "dummy_key")
        self.client = Client(api_key=self.api_key) if self.is_configured else None
        self.model_name = model or GEMINI_MODELS[0]
        self._last_call = 0
        self._min_delay = 2  # seconds between calls

    def _rate_limit(self):
        if not self.is_configured:
            return
        elapsed = time.time() - self._last_call
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_call = time.time()

    def generate(self, prompt: str) -> str:
        if not self.is_configured or not self.client:
            return ""
        self._rate_limit()
        models_to_try = [self.model_name] + [m for m in GEMINI_MODELS if m != self.model_name]
        for model in models_to_try:
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self.client.models.generate_content,
                        model=model,
                        contents=prompt
                    )
                    response = future.result(timeout=10.0)
                    return response.text
            except Exception as e:
                print(f"[Gemini] Error with model {model}: {e}")
                continue
        return ""

    def generate_json(
        self,
        prompt: str,
        retries: int = 1
    ) -> dict:
        """
        JSON generation with strict timeout and multi-model failover.
        """
        if not self.is_configured or not self.client:
            return {}

        json_prompt = (
            prompt
            + "\n\nCRITICAL: Output ONLY valid JSON. "
            + "No markdown. No code blocks. No explanation. "
            + "Just the raw JSON object starting with { "
            + "and ending with }"
        )

        models_to_try = [self.model_name] + [m for m in GEMINI_MODELS if m != self.model_name]
        start_t = time.time()

        for model in models_to_try:
            # If already spent > 15s total across models, abort to fast fallback
            if time.time() - start_t > 15:
                break

            for attempt in range(retries):
                self._rate_limit()

                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(
                            self.client.models.generate_content,
                            model=model,
                            contents=json_prompt
                        )
                        response = future.result(timeout=10.0)

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

                except FutureTimeoutError:
                    print(f"[Gemini] Timeout (10s) on {model} attempt {attempt + 1}")
                    break

                except json.JSONDecodeError as e:
                    print(f"[Gemini] JSON parse failed on {model} attempt {attempt + 1}: {e}")

                except Exception as e:
                    err_str = str(e).lower()
                    print(f"[Gemini] Error on {model} attempt {attempt + 1}: {e}")
                    # Skip retrying if quota exhausted or model unavailable
                    if any(k in err_str for k in ["429", "quota", "resource_exhausted", "503", "404", "unavailable"]):
                        break

        print("[Gemini] Returning empty dict for instant fallback script")
        return {}

    async def generate_json_async(self, prompt: str) -> dict:
        import asyncio
        return await asyncio.to_thread(self.generate_json, prompt)
