
import json
import time
from google.genai import Client


GEMINI_MODEL = "gemini-2.5-flash"


class GeminiClient:

    def __init__(self, api_key: str, model: str = GEMINI_MODEL):
        self.client = Client(api_key=api_key)
        self.model_name = model
        self._last_call = 0
        self._min_delay = 4  # seconds between calls (15 rpm = 4s apart)

    def _rate_limit(self):
        
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
        
        Gemini doesn't have a native JSON mode unlike Ollama.
        So we:
        1. Tell it explicitly to output JSON in the prompt
        2. Strip markdown code blocks if it adds them
        3. Parse the JSON
        4. Retry if parsing fails
        
        Why strip markdown?
        Gemini sometimes wraps JSON in:
        ```json
        { ... }
        ```
        json.loads() can't parse that.
        We strip the backticks first.
        """
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
