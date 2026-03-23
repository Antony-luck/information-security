from __future__ import annotations

from typing import Any

from app.models.schemas import Evidence, ModuleFinding
from app.modules.shared import (
    BaseIndependentModule,
    clamp_score,
    normalize_text,
    scan_keyword_groups,
    unique_keep_order,
)
from app.services import LLMProviderError, build_llm_provider


class SemanticContextModule(BaseIndependentModule):
    module_id = "semantic_context"
    module_name = "语义与上下文分析模块"
    target = "显性违规 / 隐性规避 / 事实断言"

    EXPLICIT_KEYWORDS = {
        "abuse": ["傻逼", "滚", "去死", "废物", "杂种", "脑残"],
        "porn": ["约炮", "裸聊", "看黄", "成人视频", "做爱", "黄网站"],
        "violence_extremism": ["炸学校", "杀人", "爆炸", "恐袭", "报复社会", "砍死"],
    }
    IMPLICIT_KEYWORDS = {
        "coded_words": ["上车", "资源", "喝茶", "安排一个", "发链接", "接头"],
        "slang_abuse": ["sb", "tm", "nmsl", "bzd", "开团", "网暴"],
        "evasion": ["拼音缩写", "谐音", "小号联系", "换个平台说", "主页见"],
    }
    FACT_TERMS = ["震惊", "内部消息", "独家爆料", "100%真实", "官方证实", "紧急通知"]

    def __init__(self, llm_provider=None) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else build_llm_provider()

    def analyze(self, content):
        heuristic_finding = self._run_heuristic(content)
        llm_finding = self._run_llm(content)
        if not llm_finding:
            return heuristic_finding
        return self._merge_findings(heuristic_finding, llm_finding)

    def _run_heuristic(self, content) -> ModuleFinding:
        texts = (
            content.normalized_segments["title"]
            + content.normalized_segments["description"]
            + content.normalized_segments["speech_text"]
            + content.normalized_segments["bullet_chats"]
            + content.normalized_segments["comments"]
        )
        metadata = content.standardized_metadata

        explicit_tags, explicit_evidence, explicit_hits = scan_keyword_groups(
            texts,
            self.EXPLICIT_KEYWORDS,
            "semantic-explicit",
        )
        implicit_tags, implicit_evidence, implicit_hits = scan_keyword_groups(
            texts,
            self.IMPLICIT_KEYWORDS,
            "semantic-implicit",
        )

        fact_evidence: list[Evidence] = []
        fact_hits = 0
        for text in texts:
            normalized = normalize_text(text)
            for term in self.FACT_TERMS:
                if term in normalized:
                    fact_hits += 1
                    fact_evidence.append(
                        Evidence(
                            source="semantic-factuality",
                            excerpt=text[:120],
                            reason=f"出现待核验断言词: {term}",
                        )
                    )
                    break

        score = 0.14 * len(explicit_evidence) + 0.12 * len(implicit_evidence)
        score += min(0.24, fact_hits * 0.12)

        if explicit_hits.get("violence_extremism", 0):
            score += 0.18
        if implicit_hits.get("coded_words", 0) and implicit_hits.get("evasion", 0):
            score += 0.16
        if fact_hits and not metadata.get("source_verified", False):
            score += 0.16
            fact_evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata),
                    reason="来源未标记为可信信源，但文本存在高强度事实断言",
                )
            )

        evidence = [*explicit_evidence[:3], *implicit_evidence[:3], *fact_evidence[:3]]
        tags = [*explicit_tags, *implicit_tags]
        if fact_hits:
            tags.append("factuality")

        if evidence:
            summary = "语义层面出现了显性违规、隐性规避表达或待核验断言，说明文本上下文具有较强的不确定性与传播风险。"
            recommendations = [
                "优先给隐性违规识别和事实核验接入 LLM，补强上下文语义推理能力。",
                "对高风险断言增加外部检索与可信源交叉验证流程。",
            ]
        else:
            summary = "当前样本在文本语义与上下文层面未出现明显高风险表达，但该模块后续仍建议接入 LLM 做深层语义复判。"
            recommendations = [
                "继续沉淀黑话样本、缩写样本和事实断言样本，为后续 LLM 与训练数据做准备。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:7],
            recommendations=recommendations,
        )

    def _run_llm(self, content) -> ModuleFinding | None:
        if not self.llm_provider:
            return None

        payload = self._build_llm_payload(content)
        try:
            response = self.llm_provider.complete_json(
                system_prompt=self._system_prompt(),
                user_payload=payload,
            )
        except LLMProviderError:
            return None
        except Exception:
            return None

        llm_payload = response.payload
        score = clamp_score(float(llm_payload.get("risk_score", 0.0) or 0.0))
        summary = str(llm_payload.get("summary") or "").strip()
        if not summary:
            return None

        evidence = self._parse_llm_evidence(llm_payload.get("evidence"))
        recommendations = self._parse_string_list(llm_payload.get("recommendations"))
        tags = self._parse_string_list(llm_payload.get("tags"))
        tags.extend(["llm-semantic-review", response.provider, response.model])

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:4],
            recommendations=recommendations[:4],
        )

    def _build_llm_payload(self, content) -> dict[str, Any]:
        return {
            "video_id": content.input_payload.video_id,
            "title": content.input_payload.title,
            "description": content.input_payload.description,
            "speech_text": content.input_payload.speech_text[:1500],
            "ocr_text": content.input_payload.ocr_text[:12],
            "visual_descriptions": content.input_payload.visual_descriptions[:8],
            "comments": content.input_payload.comments[:12],
            "comment_records": [
                {
                    "speaker_id": record.speaker_id,
                    "speaker_nickname": record.speaker_nickname,
                    "text": record.text,
                    "like_count": record.like_count,
                    "reply_count": record.reply_count,
                    "ip_label": record.ip_label,
                    "keyword_tags": record.keyword_tags,
                    "importance_score": record.importance_score,
                    "replies": [
                        {
                            "speaker_nickname": reply.speaker_nickname,
                            "text": reply.text,
                            "like_count": reply.like_count,
                            "is_author": reply.is_author,
                        }
                        for reply in record.replies[:3]
                    ],
                }
                for record in content.input_payload.comment_records[:8]
            ],
            "audio_cues": content.input_payload.audio_cues[:8],
            "metadata": {
                "source_verified": content.standardized_metadata.get("source_verified", False),
                "author_verified": content.standardized_metadata.get("author_verified", False),
                "account_age_days": content.standardized_metadata.get("account_age_days", 0),
                "burst_comment_ratio": content.standardized_metadata.get("burst_comment_ratio", 0.0),
                "region_mismatch": content.standardized_metadata.get("region_mismatch", False),
                "comment_count_scanned": content.standardized_metadata.get("comment_count_scanned", 0),
                "structured_comment_count": content.standardized_metadata.get(
                    "structured_comment_count", 0
                ),
            },
        }

    def _system_prompt(self) -> str:
        return (
            "你是短视频内容安全研判系统中的语义与上下文分析模块。"
            "你只能根据输入内容判断显性违规、隐性规避表达、黑话缩写、事实断言风险。"
            "不要捏造输入中不存在的证据。"
            "请只输出 JSON 对象，不要输出 Markdown。"
            'JSON schema: {"risk_score":0.0,"summary":"","tags":[],"evidence":[{"source":"","excerpt":"","reason":""}],"recommendations":[]}.'
            "risk_score 范围必须是 0 到 1。evidence 最多 4 条，recommendations 最多 4 条。"
        )

    def _parse_llm_evidence(self, raw_value: Any) -> list[Evidence]:
        evidence: list[Evidence] = []
        for item in raw_value or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "llm-semantic").strip()
            excerpt = str(item.get("excerpt") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if excerpt and reason:
                evidence.append(
                    Evidence(
                        source=source[:60],
                        excerpt=excerpt[:160],
                        reason=reason[:160],
                    )
                )
        return evidence

    def _parse_string_list(self, raw_value: Any) -> list[str]:
        items = raw_value if isinstance(raw_value, list) else []
        return [
            str(item).strip()
            for item in items
            if str(item).strip()
        ]

    def _merge_findings(
        self,
        heuristic_finding: ModuleFinding,
        llm_finding: ModuleFinding,
    ) -> ModuleFinding:
        merged_score = clamp_score(
            max(
                heuristic_finding.risk_score,
                (heuristic_finding.risk_score * 0.45) + (llm_finding.risk_score * 0.75),
            )
        )
        merged_summary = (
            llm_finding.summary
            if llm_finding.risk_score >= heuristic_finding.risk_score
            else f"{heuristic_finding.summary} LLM 复判补充认为：{llm_finding.summary}"
        )
        merged_tags = unique_keep_order([*heuristic_finding.tags, *llm_finding.tags])
        merged_evidence = [*heuristic_finding.evidence, *llm_finding.evidence]
        merged_recommendations = unique_keep_order(
            [*heuristic_finding.recommendations, *llm_finding.recommendations]
        )

        return self.build_finding(
            score=merged_score,
            summary=merged_summary,
            tags=merged_tags,
            evidence=merged_evidence[:8],
            recommendations=merged_recommendations[:6],
        )
