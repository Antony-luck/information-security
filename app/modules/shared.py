from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.models.schemas import (
    Evidence,
    ModuleFinding,
    PreprocessedContent,
    RiskLevel,
    WorkflowStep,
)


def clamp_score(score: float) -> float:
    return max(0.0, min(1.0, round(score, 3)))


def score_to_level(score: float) -> RiskLevel:
    if score >= 0.85:
        return RiskLevel.critical
    if score >= 0.6:
        return RiskLevel.high
    if score >= 0.3:
        return RiskLevel.medium
    return RiskLevel.low


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def scan_keyword_groups(
    texts: Iterable[str],
    keyword_groups: dict[str, list[str]],
    source_name: str,
) -> tuple[list[str], list[Evidence], Counter]:
    matched_tags: list[str] = []
    evidence: list[Evidence] = []
    hit_counter: Counter = Counter()

    normalized_texts = [normalize_text(text) for text in texts if normalize_text(text)]
    for text in normalized_texts:
        for tag, keywords in keyword_groups.items():
            for keyword in keywords:
                if keyword in text:
                    matched_tags.append(tag)
                    hit_counter[tag] += 1
                    evidence.append(
                        Evidence(
                            source=source_name,
                            excerpt=text[:120],
                            reason=f"命中关键词: {keyword}",
                        )
                    )
                    break

    return unique_keep_order(matched_tags), evidence, hit_counter


class BaseIndependentModule:
    module_id = ""
    module_name = ""
    target = ""

    def analyze(self, content: PreprocessedContent) -> ModuleFinding:
        raise NotImplementedError

    def build_finding(
        self,
        score: float,
        summary: str,
        tags: list[str] | None = None,
        evidence: list[Evidence] | None = None,
        recommendations: list[str] | None = None,
        metrics: dict[str, object] | None = None,
        workflow_steps: list[WorkflowStep] | None = None,
    ) -> ModuleFinding:
        final_score = clamp_score(score)
        return ModuleFinding(
            module_id=self.module_id,
            module_name=self.module_name,
            target=self.target,
            risk_level=score_to_level(final_score),
            risk_score=final_score,
            summary=summary,
            tags=unique_keep_order(tags or []),
            evidence=evidence or [],
            recommendations=unique_keep_order(recommendations or []),
            metrics=metrics or {},
            workflow_steps=workflow_steps or [],
        )
