from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import settings


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider returns an invalid response."""


@dataclass
class LLMJsonResponse:
    payload: dict[str, Any]
    model: str
    provider: str


def _strip_code_fences(content: str) -> str:
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


class OpenAICompatibleProvider:
    """
    Generic provider for APIs compatible with /chat/completions.

    DeepSeek, OpenAI-compatible gateways, and most hosted model APIs
    share this payload format.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        provider_name: str,
        timeout_seconds: float = 60,
        api_path: str = "/chat/completions",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "").rstrip("/")
        self.provider_name = provider_name
        self.timeout_seconds = timeout_seconds
        self.api_path = api_path if api_path.startswith("/") else f"/{api_path}"

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResponse:
        if not self.base_url:
            raise LLMProviderError("LLM base_url is empty.")
        if not self.api_key:
            raise LLMProviderError("LLM api_key is empty.")
        if not self.model:
            raise LLMProviderError("LLM model is empty.")

        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{self.base_url}{self.api_path}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError(f"{self.provider_name} response does not contain choices.")
        message = choices[0].get("message") or {}
        content = _strip_code_fences(str(message.get("content") or "").strip())
        if not content:
            raise LLMProviderError(f"{self.provider_name} response content is empty.")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"{self.provider_name} returned non-json content: {content[:200]}"
            ) from exc

        return LLMJsonResponse(
            payload=payload,
            model=str(data.get("model") or self.model),
            provider=self.provider_name,
        )


class DeepSeekProvider(OpenAICompatibleProvider):
    """Backwards-compatible alias with DeepSeek defaults."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 60,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model or "deepseek-chat",
            base_url=base_url or "https://api.deepseek.com",
            provider_name="deepseek",
            timeout_seconds=timeout_seconds,
            api_path="/chat/completions",
        )


def build_llm_provider() -> OpenAICompatibleProvider | None:
    provider_name = (settings.llm_provider or "").strip().lower()
    if not provider_name or not settings.llm_ready:
        return None

    base_url = settings.llm_base_url
    model = settings.llm_model
    timeout_seconds = settings.llm_timeout_seconds
    api_path = settings.llm_api_path

    if provider_name == "deepseek":
        return DeepSeekProvider(
            api_key=settings.llm_api_key,
            model=model or "deepseek-chat",
            base_url=base_url or "https://api.deepseek.com",
            timeout_seconds=timeout_seconds,
        )

    if provider_name in {"openai", "openai_compatible", "qwen", "custom"}:
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key,
            model=model,
            base_url=base_url,
            provider_name=provider_name,
            timeout_seconds=timeout_seconds,
            api_path=api_path or "/chat/completions",
        )
    return None

