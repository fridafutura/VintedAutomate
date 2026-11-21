"""Thin wrapper around the Anthropic API for the two things the agent needs
an LLM for: turning photos+notes into structured listing fields, and
drafting buyer replies. Kept separate from the business-rule modules so
those stay pure and unit-testable without any network/API dependency.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re

from .config import ANTHROPIC_MODEL

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> dict:
    match = _JSON_FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    return json.loads(candidate.strip())


def _encode_image(path: str) -> dict:
    media_type, _ = mimetypes.guess_type(path)
    if media_type is None:
        media_type = "image/jpeg"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


class ClaudeClient:
    """Lazily imports the `anthropic` package so modules that don't need
    network access (pricing, discounts) never require it to be installed."""

    def __init__(self, api_key: str | None = None, model: str = ANTHROPIC_MODEL):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "The 'anthropic' package is required for listing generation / "
                "message drafting. Install it with: pip install anthropic"
            ) from e

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY or pass api_key=..."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

    def structured_request(self, system: str, user_text: str, photo_paths: list[str] | None = None) -> dict:
        """Send a prompt (optionally with images) and parse a JSON object
        out of the response."""

        content: list[dict] = []
        for path in photo_paths or []:
            content.append(_encode_image(path))
        content.append({"type": "text", "text": user_text})

        response = self._client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return _extract_json(text)

    def text_request(self, system: str, user_text: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": user_text}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()
