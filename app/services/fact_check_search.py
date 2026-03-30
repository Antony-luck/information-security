from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class SearchEvidence:
    title: str
    snippet: str
    url: str
    source: str


class SearchEvidenceService:
    """
    轻量级检索服务，用于事实核查阶段补充外部证据片段。

    优先尝试 DuckDuckGo Instant Answer，其次回退到中文维基开放搜索。
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def search(self, query: str, max_results: int = 3) -> list[SearchEvidence]:
        normalized = " ".join((query or "").strip().split())
        if not normalized:
            return []

        results: list[SearchEvidence] = []
        results.extend(self._search_duckduckgo_instant(normalized, max_results=max_results))
        if len(results) < max_results:
            results.extend(
                self._search_zh_wikipedia(
                    normalized,
                    max_results=max_results - len(results),
                )
            )
        return self._dedupe(results)[:max_results]

    def _search_duckduckgo_instant(
        self, query: str, max_results: int
    ) -> list[SearchEvidence]:
        try:
            response = self.session.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                    "kl": "cn-zh",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        items: list[SearchEvidence] = []
        abstract_text = str(payload.get("AbstractText") or "").strip()
        abstract_url = str(payload.get("AbstractURL") or "").strip()
        heading = str(payload.get("Heading") or "").strip() or query
        if abstract_text and abstract_url:
            items.append(
                SearchEvidence(
                    title=heading[:120],
                    snippet=abstract_text[:280],
                    url=abstract_url[:300],
                    source="duckduckgo-instant",
                )
            )

        related = payload.get("RelatedTopics") or []
        for topic in self._flatten_related_topics(related):
            text = str(topic.get("Text") or "").strip()
            first_url = str(topic.get("FirstURL") or "").strip()
            if not text or not first_url:
                continue
            title = text.split(" - ", 1)[0].strip() or query
            items.append(
                SearchEvidence(
                    title=title[:120],
                    snippet=text[:280],
                    url=first_url[:300],
                    source="duckduckgo-related",
                )
            )
            if len(items) >= max_results:
                break

        return items[:max_results]

    def _search_zh_wikipedia(self, query: str, max_results: int) -> list[SearchEvidence]:
        try:
            response = self.session.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": str(max(1, min(10, max_results))),
                    "namespace": "0",
                    "format": "json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        if not isinstance(payload, list) or len(payload) < 4:
            return []

        titles = payload[1] if isinstance(payload[1], list) else []
        snippets = payload[2] if isinstance(payload[2], list) else []
        urls = payload[3] if isinstance(payload[3], list) else []
        result: list[SearchEvidence] = []

        for idx, title in enumerate(titles[:max_results]):
            snippet = str(snippets[idx] if idx < len(snippets) else "").strip()
            url = str(urls[idx] if idx < len(urls) else "").strip()
            if not url:
                continue
            result.append(
                SearchEvidence(
                    title=str(title).strip()[:120],
                    snippet=snippet[:280],
                    url=url[:300],
                    source="wikipedia-zh",
                )
            )
        return result

    def _flatten_related_topics(self, items: list[Any]) -> list[dict[str, Any]]:
        flattened: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            nested = item.get("Topics")
            if isinstance(nested, list):
                flattened.extend(self._flatten_related_topics(nested))
            else:
                flattened.append(item)
        return flattened

    def _dedupe(self, items: list[SearchEvidence]) -> list[SearchEvidence]:
        seen: set[str] = set()
        result: list[SearchEvidence] = []
        for item in items:
            key = f"{item.url}|{item.title}|{item.source}"
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
