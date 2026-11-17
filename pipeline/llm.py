
import json
import time
from google.genai import Client


GEMINI_MODEL = "gemini-2.5-flash"


class GeminiClient:

    def __init__(self, api_key: str = None, model: str = GEMINI_MODEL):
        self.api_key = (api_key or "").strip()
        self.is_configured = bool(self.api_key and self.api_key != "dummy_key")
        self.client = Client(api_key=self.api_key) if self.is_configured else None
        self.model_name = model
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

        try:
            response = self.client.models.generate_content(
                model=self.model_name, contents=prompt
            )
            return response.text

        except Exception as e:
            print(f"[Gemini] Error: {e}")
            return ""

    def generate_json(
        self,
        prompt: str,
        retries: int = 3
    ) -> dict:
        """
        JSON generation with retry.
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

        for attempt in range(retries):
            self._rate_limit()

            try:
                response = self.client.models.generate_content(
                    model=self.model_name, contents=json_prompt
                )
                raw = response.text.strip()

                # Strip markdown code blocks if present
                # ```json ... ``` or ``` ... ```
                if raw.startswith("```"):
                    lines = raw.split('\n')
                    # Remove first line (```json or ```)
                    # Remove last line (```)
                    raw = '\n'.join(lines[1:-1])

                # Sometimes it adds "json" prefix
                if raw.startswith("json"):
                    raw = raw[4:].strip()

                parsed = json.loads(raw)

                if parsed:
                    return parsed

                raise ValueError("Empty JSON response")

            except json.JSONDecodeError as e:
                print(
                    f"[Gemini] JSON parse failed "
                    f"attempt {attempt + 1}: {e}"
                )
                if attempt < retries - 1:
                    print(f"[Gemini] Retrying...")

            except Exception as e:
                print(f"[Gemini] Error attempt {attempt + 1}: {e}")
                if "quota" in str(e).lower():
                    print("[Gemini] Rate limit hit. Waiting 60s...")
                    time.sleep(60)

        print("[Gemini] All retries failed, returning empty dict")
        return {}

    async def generate_json_async(self, prompt: str) -> dict:
        import asyncio
        return await asyncio.to_thread(self.generate_json, prompt)
