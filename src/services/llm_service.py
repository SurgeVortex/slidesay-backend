import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Free model fallback chain
MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

SYSTEM_PROMPT = """You are a presentation structuring AI. Convert the user's speech transcript into a structured presentation.

Output ONLY valid JSON with this exact format:
{
  "title": "Presentation Title",
  "slides": [
    {
      "type": "title",
      "title": "Main Title",
      "subtitle": "Optional subtitle",
      "notes": "Speaker notes"
    },
    {
      "type": "content",
      "title": "Slide Title",
      "bullets": ["Point 1", "Point 2", "Point 3"],
      "notes": "Speaker notes for this slide"
    },
    {
      "type": "two-column",
      "title": "Comparison Slide",
      "left": {"heading": "Left", "bullets": ["A", "B"]},
      "right": {"heading": "Right", "bullets": ["C", "D"]},
      "notes": ""
    },
    {
      "type": "section",
      "title": "Section Break Title",
      "notes": ""
    }
  ]
}

Rules:
- First slide should be type "title"
- Use "content" for most slides (title + bullets)
- Use "two-column" only when comparing things
- Use "section" for topic transitions
- Keep bullets concise (max 8 words each)
- Max 5 bullets per slide
- Generate speaker notes from the original speech
- If the transcript mentions "next slide" or "new slide", treat that as a slide break
"""


class LLMService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

    async def structure_transcript(self, transcript: str, num_slides: int | None = None) -> dict[str, object]:
        """Convert raw transcript to structured slide JSON."""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        user_msg = "Convert this speech transcript into a presentation"
        if num_slides:
            user_msg += f" with approximately {num_slides} slides"
        user_msg += f":\n\n{transcript}"

        last_error = None
        for model in MODELS:
            try:
                result = await self._call_model(model, user_msg)
                return result
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                last_error = e
                continue

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    async def _call_model(self, model: str, user_message: str) -> dict[str, object]:
        """Call a specific model via OpenRouter."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://slidesay.com",
                    "X-Title": "SlideSay",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Parse JSON from response
        parsed: dict[str, object] = json.loads(content)

        # Validate structure
        if "title" not in parsed or "slides" not in parsed:
            raise ValueError("LLM response missing required fields (title, slides)")

        slides = parsed["slides"]
        if not isinstance(slides, list):
            raise ValueError("'slides' field must be a list")
        for slide in slides:
            if not isinstance(slide, dict):
                raise ValueError(f"Slide must be dict: {slide}")
            if "type" not in slide or "title" not in slide:
                raise ValueError(f"Slide missing required fields: {slide}")
        return parsed
