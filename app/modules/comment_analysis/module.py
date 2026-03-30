from __future__ import annotations

from collections import Counter
from math import log1p
from typing import Any

from app.models.schemas import CommentRecord, Evidence, WorkflowStep
from app.modules.shared import BaseIndependentModule, clamp_score, normalize_text, unique_keep_order
from app.services import LLMProviderError, build_llm_provider


class CommentAnalysisModule(BaseIndependentModule):
    module_id = "comment_analysis"
    module_name = "评论区分析模块"
    target = "群体极化 / 异常引流 / 评论生态"

    POSITIVE_EXTREME = ["支持到底", "必须严惩", "全部封禁", "太解气了", "狠狠干"]
    NEGATIVE_EXTREME = ["恶心", "滚出去", "全是假的", "带节奏", "脑残"]
    CONFLICT_TERMS = ["吵起来", "对喷", "互骂", "站队", "冲他"]
    DRAINAGE_TERMS = ["私信", "加v", "vx", "微信", "主页链接", "点我主页", "带你赚钱", "关注领取"]
    TAG_LABELS = {
        "polarization": "群体极化",
        "reply-thread-active": "回复链活跃",
        "duplicate-comments": "重复评论",
        "burst-comments": "突发评论",
        "speaker-concentration": "账号集中",
        "llm-comment-review": "LLM评论复核",
        "geopolitical_bias_accusation": "地缘偏见指控",
        "nationality_ambush": "国籍质疑",
        "military_capability_denial": "军事能力否定",
        "linguistic_distortion": "语义扭曲",
        "coordinated_skepticism": "协同质疑",
        "media_bias_accusation": "媒体偏见指控",
    }
    RISK_TYPE_LABELS = {
        "positive": "极端正向表态",
        "negative": "极端负向表态",
        "conflict": "冲突对喷",
        "drainage": "引流导流",
    }

    def __init__(self, llm_provider=None) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else build_llm_provider()

    def analyze(self, content):
        records = content.input_payload.comment_records
        comments = [normalize_text(comment) for comment in content.normalized_segments["comments"]]
        comments = [comment for comment in comments if comment]
        if not comments:
            return self.build_finding(
                0.0,
                "当前没有可用评论样本，评论区模块只能给出保守结果。",
                recommendations=["补齐评论抓取后再执行评论生态分析。"],
                metrics={"comment_count": 0},
                workflow_steps=[
                    WorkflowStep(
                        step_id="cm-1",
                        stage="输入检查",
                        title="评论输入可用性检查",
                        detail="预处理后的评论分段中没有可用评论文本。",
                        module_id=self.module_id,
                        refs=["评论文本"],
                    )
                ],
            )

        evidence: list[Evidence] = []
        tags: list[str] = []
        pos_hits = 0
        neg_hits = 0
        conflict_hits = 0
        drainage_hits = 0
        high_engagement_risky = 0

        if records:
            for record in records:
                normalized = normalize_text(record.text)
                if not normalized:
                    continue
                risk_types = self._match_risk_types(normalized)
                if not risk_types:
                    continue

                if "positive" in risk_types:
                    pos_hits += 1
                if "negative" in risk_types:
                    neg_hits += 1
                if "conflict" in risk_types:
                    conflict_hits += 1
                if "drainage" in risk_types:
                    drainage_hits += 1

                amplification = log1p(max(record.like_count, 0)) + log1p(max(record.reply_count, 0))
                if amplification >= 2.4:
                    high_engagement_risky += 1

                evidence.append(
                    Evidence(
                        source="评论",
                        excerpt=self._format_record_excerpt(record),
                        reason=self._format_reason(risk_types, record),
                    )
                )
        else:
            for comment in comments:
                risk_types = self._match_risk_types(comment)
                if "positive" in risk_types:
                    pos_hits += 1
                if "negative" in risk_types:
                    neg_hits += 1
                if "conflict" in risk_types:
                    conflict_hits += 1
                if "drainage" in risk_types:
                    drainage_hits += 1
                if risk_types:
                    evidence.append(
                        Evidence(
                            source="评论",
                            excerpt=comment[:120],
                            reason=f"命中评论风险类型：{', '.join(self.RISK_TYPE_LABELS.get(item, item) for item in risk_types)}",
                        )
                    )

        duplicates = Counter(comments)
        duplicate_count = sum(count for count in duplicates.values() if count > 1)
        duplicate_ratio = duplicate_count / max(len(comments), 1)
        burst_ratio = float(content.standardized_metadata.get("burst_comment_ratio", 0.0))
        reply_thread_ratio = (
            sum(1 for record in records if record.reply_count > 0) / max(len(records), 1)
            if records
            else 0.0
        )
        unique_speakers = (
            len(
                {
                    record.speaker_id or record.speaker_nickname
                    for record in records
                    if record.speaker_id or record.speaker_nickname
                }
            )
            if records
            else 0
        )

        score = 0.0
        if pos_hits and neg_hits:
            score += 0.28
            tags.append("群体极化")
        score += min(0.24, conflict_hits * 0.08)
        score += min(0.24, drainage_hits * 0.12)
        score += min(0.12, high_engagement_risky * 0.06)

        if reply_thread_ratio >= 0.35:
            score += 0.08
            tags.append("回复链活跃")
            evidence.append(
                Evidence(
                    source="评论图谱",
                    excerpt=f"回复链占比={reply_thread_ratio:.2f}",
                    reason="回复链占比高，说明讨论具备持续扩散动量。",
                )
            )
        if duplicate_ratio >= 0.3:
            score += 0.24
            tags.append("重复评论")
            repeated_comment = max(duplicates, key=duplicates.get)
            evidence.append(
                Evidence(
                    source="评论",
                    excerpt=repeated_comment[:120],
                    reason=f"重复评论比例偏高：{duplicate_ratio:.2f}",
                )
            )
        if burst_ratio >= 0.5:
            score += 0.18
            tags.append("突发评论")
            evidence.append(
                Evidence(
                    source="元数据",
                    excerpt=str(burst_ratio),
                    reason="评论突发比例偏高，存在协同行为可能。",
                )
            )
        if records and unique_speakers and unique_speakers < max(3, len(records) // 3):
            score += 0.08
            tags.append("账号集中")
            evidence.append(
                Evidence(
                    source="评论画像",
                    excerpt=f"去重账号数={unique_speakers}，入选评论={len(records)}",
                    reason="入选评论的账号集中度偏高。",
                )
            )

        summary = "评论区未见明显极化或引流扩散模式。"
        recommendations = ["保持结构化评论采集，继续追踪评论随时间的变化。"]
        if evidence:
            summary = "评论区存在极化、冲突、引流或异常扩散迹象，且高互动评论放大了传播风险。"
            recommendations = [
                "优先复核高点赞/高回复评论及其回复链。",
                "补充账号画像和时间序列特征，提升控评与刷评识别能力。",
            ]

        llm_review = self._run_llm_review(content)
        if llm_review:
            score = max(score, score * 0.5 + llm_review["risk_score"] * 0.7)
            summary = llm_review["summary"] or summary
            tags = unique_keep_order([*tags, *llm_review["tags"], "LLM评论复核"])
            evidence = [*evidence, *llm_review["evidence"]]
            recommendations = unique_keep_order([*recommendations, *llm_review["recommendations"]])

        metrics = {
            "comment_count": len(comments),
            "structured_comment_count": len(records),
            "positive_hits": pos_hits,
            "negative_hits": neg_hits,
            "conflict_hits": conflict_hits,
            "drainage_hits": drainage_hits,
            "duplicate_ratio": round(duplicate_ratio, 3),
            "reply_thread_ratio": round(reply_thread_ratio, 3),
            "burst_comment_ratio": round(burst_ratio, 3),
            "llm_review_used": bool(llm_review),
        }
        workflow_steps = [
            WorkflowStep(
                step_id="cm-1",
                stage="特征提取",
                title="提取评论互动特征",
                detail=(
                    f"评论条数={len(comments)}，结构化评论数={len(records)}，"
                    f"去重账号数={unique_speakers}"
                ),
                module_id=self.module_id,
                refs=["评论文本", "结构化评论", "评论扫描数量"],
            ),
            WorkflowStep(
                step_id="cm-2",
                stage="风险筛查",
                title="规则层极化与引流筛查",
                detail=(
                    f"极端正向={pos_hits}，极端负向={neg_hits}，冲突对喷={conflict_hits}，"
                    f"引流导流={drainage_hits}，重复比例={duplicate_ratio:.2f}"
                ),
                module_id=self.module_id,
                refs=[*tags[:3]],
            ),
            WorkflowStep(
                step_id="cm-3",
                stage="LLM复核",
                title="大模型评论生态复核",
                detail=(
                    "已调用大模型执行评论生态交叉信号复核。"
                    if llm_review
                    else "未调用大模型复核，当前仅使用规则结果。"
                ),
                module_id=self.module_id,
                refs=["LLM评论复核"] if llm_review else [],
            ),
        ]
        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:8],
            recommendations=recommendations[:6],
            metrics=metrics,
            workflow_steps=workflow_steps,
        )

    def _run_llm_review(self, content) -> dict[str, Any] | None:
        if not self.llm_provider:
            return None

        payload = {
            "comments": content.input_payload.comments[:20],
            "comment_records": [
                {
                    "speaker_id": record.speaker_id,
                    "speaker_nickname": record.speaker_nickname,
                    "text": record.text,
                    "like_count": record.like_count,
                    "reply_count": record.reply_count,
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
                for record in content.input_payload.comment_records[:12]
            ],
            "metadata": {
                "comment_count_scanned": content.standardized_metadata.get("comment_count_scanned"),
                "structured_comment_count": content.standardized_metadata.get("structured_comment_count"),
                "burst_comment_ratio": content.standardized_metadata.get("burst_comment_ratio"),
                "comment_unique_speaker_count": content.standardized_metadata.get(
                    "comment_unique_speaker_count"
                ),
            },
        }
        try:
            response = self.llm_provider.complete_json(
                system_prompt=(
                    "你是短视频评论生态安全研判专家。请只返回严格 JSON，键为："
                    "risk_score, summary, tags, evidence, recommendations。"
                    "risk_score范围[0,1]；evidence每项包含source/excerpt/reason。"
                    "summary、tags、evidence.reason、recommendations必须使用简体中文，不得输出英文或繁体中文。"
                ),
                user_payload=payload,
            )
        except LLMProviderError:
            return None
        except Exception:
            return None

        raw = response.payload
        try:
            score = clamp_score(float(raw.get("risk_score", 0.0) or 0.0))
        except (TypeError, ValueError):
            score = 0.0
        summary = str(raw.get("summary") or "").strip()
        if not summary:
            return None

        evidence: list[Evidence] = []
        for item in raw.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            excerpt = str(item.get("excerpt") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if not excerpt or not reason:
                continue
            evidence.append(
                Evidence(
                    source=str(item.get("source") or "LLM评论")[:60],
                    excerpt=excerpt[:160],
                    reason=reason[:160],
                )
            )
        tags = [
            str(item).strip()
            for item in (raw.get("tags") or [])
            if str(item).strip()
        ]
        tags = [self.TAG_LABELS.get(tag, tag) for tag in tags]
        recommendations = [
            str(item).strip()
            for item in (raw.get("recommendations") or [])
            if str(item).strip()
        ]
        return {
            "risk_score": score,
            "summary": summary[:220],
            "tags": tags[:8],
            "evidence": evidence[:4],
            "recommendations": recommendations[:4],
        }

    def _match_risk_types(self, comment: str) -> list[str]:
        risk_types: list[str] = []
        if any(term in comment for term in self.POSITIVE_EXTREME):
            risk_types.append("positive")
        if any(term in comment for term in self.NEGATIVE_EXTREME):
            risk_types.append("negative")
        if any(term in comment for term in self.CONFLICT_TERMS):
            risk_types.append("conflict")
        if any(term in comment for term in self.DRAINAGE_TERMS):
            risk_types.append("drainage")
        return risk_types

    def _format_record_excerpt(self, record: CommentRecord) -> str:
        speaker = record.speaker_nickname or record.speaker_id or "未知用户"
        return (
            f"{speaker} | 点赞={record.like_count} | 回复={record.reply_count} | "
            f"{record.text[:90]}"
        )

    def _format_reason(self, risk_types: list[str], record: CommentRecord) -> str:
        detail = ", ".join(self.RISK_TYPE_LABELS.get(item, item) for item in risk_types)
        if record.reply_count or record.like_count:
            detail = f"{detail}；点赞={record.like_count}，回复={record.reply_count}"
        return f"命中评论风险类型：{detail}"
