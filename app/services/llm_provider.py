from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from app.core.config import settings


class LLMProviderError(RuntimeError):
    pass


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


class DeepSeekProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model or "deepseek-chat"
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> LLMJsonResponse:
        session = requests.Session()
        session.trust_env = False
        response = session.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
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
            raise LLMProviderError("DeepSeek 返回中缺少 choices。")
        message = choices[0].get("message") or {}
        content = _strip_code_fences(str(message.get("content") or "").strip())
        if not content:
            raise LLMProviderError("DeepSeek 返回内容为空。")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"DeepSeek 返回了非 JSON 内容: {content[:200]}") from exc

        return LLMJsonResponse(
            payload=payload,
            model=str(data.get("model") or self.model),
            provider="deepseek",
        )


def build_llm_provider() -> DeepSeekProvider | None:
    provider_name = (settings.llm_provider or "").strip().lower()
    if not provider_name or not settings.llm_ready:
        return None
    if provider_name != "deepseek":
        return None
    return DeepSeekProvider(
        api_key=settings.llm_api_key,
        model=settings.llm_model or "deepseek-chat",
        base_url=settings.llm_base_url or "https://api.deepseek.com",
        timeout_seconds=settings.llm_timeout_seconds,
    )
