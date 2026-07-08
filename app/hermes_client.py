from __future__ import annotations

import json

import httpx

from .config import Settings


class HermesClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.hermes_api_key.strip())

    def chat_json(self, system_prompt: str, user_prompt: str, timeout_s: float = 120.0) -> dict:
        if not self.is_configured():
            raise RuntimeError("HERMES_API_KEY is not configured")

        url = self.settings.hermes_api_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.hermes_model_name,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self.settings.hermes_api_key}"}
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return extract_json_object(content)


def extract_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise ValueError("Hermes response did not contain a JSON object")
    return json.loads(text[first : last + 1])

