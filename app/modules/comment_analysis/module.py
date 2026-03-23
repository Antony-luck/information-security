from __future__ import annotations

from collections import Counter
from math import log1p

from app.models.schemas import CommentRecord, Evidence
from app.modules.shared import BaseIndependentModule, normalize_text


class CommentAnalysisModule(BaseIndependentModule):
    module_id = "comment_analysis"
    module_name = "评论区分析模块"
    target = "群体极化 / 异常引流 / 评论生态"

    POSITIVE_EXTREME = ["支持到底", "必须严惩", "全部封禁", "太解气了", "狠狠干"]
    NEGATIVE_EXTREME = ["恶心", "滚出去", "全是假的", "带节奏", "脑残"]
    CONFLICT_TERMS = ["吵起来", "对喷", "互骂", "站队", "冲他"]
    DRAINAGE_TERMS = [
        "私信",
        "加v",
        "vx",
        "微信",
        "主页链接",
        "点我主页",
        "带你赚钱",
        "关注领取",
    ]

    def analyze(self, content):
        records = content.input_payload.comment_records
        comments = [normalize_text(comment) for comment in content.normalized_segments["comments"]]
        comments = [comment for comment in comments if comment]
        if not comments:
            return self.build_finding(
                0.0,
                "当前没有可用评论样本，评论区模块只能给出保守结果。",
                recommendations=["补齐评论抓取后再启用评论区分析，以提升结论可信度。"],
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
                        source="comment",
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
                            source="comment",
                            excerpt=comment[:120],
                            reason=f"命中评论风险标签: {', '.join(risk_types)}",
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
            tags.append("polarization")
        score += min(0.24, conflict_hits * 0.08)
        score += min(0.24, drainage_hits * 0.12)
        score += min(0.12, high_engagement_risky * 0.06)

        if reply_thread_ratio >= 0.35:
            score += 0.08
            tags.append("reply-thread-active")
            evidence.append(
                Evidence(
                    source="comment-graph",
                    excerpt=f"reply_thread_ratio={reply_thread_ratio:.2f}",
                    reason="高互动评论占比较高，说明评论区已形成持续讨论链",
                )
            )

        if duplicate_ratio >= 0.3:
            score += 0.24
            tags.append("duplicate-comments")
            repeated_comment = max(duplicates, key=duplicates.get)
            evidence.append(
                Evidence(
                    source="comment",
                    excerpt=repeated_comment[:120],
                    reason=f"重复评论占比偏高: {duplicate_ratio:.2f}",
                )
            )
        if burst_ratio >= 0.5:
            score += 0.18
            tags.append("burst-comments")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(burst_ratio),
                    reason="评论短时突增，疑似存在异常控评或刷评",
                )
            )

        if records and unique_speakers and unique_speakers < max(3, len(records) // 3):
            score += 0.08
            tags.append("speaker-concentration")
            evidence.append(
                Evidence(
                    source="comment-profile",
                    excerpt=f"unique_speakers={unique_speakers}, selected_comments={len(records)}",
                    reason="重要评论的发言者过于集中，需要人工核查是否存在集中控评",
                )
            )

        if evidence:
            summary = (
                "评论区出现了极化、冲突、引流或重复评论迹象，且结构化评论显示部分"
                "高互动评论正在放大传播风险。"
            )
            recommendations = [
                "继续跟踪高点赞、高回复评论及其回复链，优先复核高互动风险评论。",
                "后续补入评论时间序列和账号画像，可以进一步识别刷评与控评。",
            ]
        else:
            summary = "评论区暂未出现明显的极化或异常引流模式，但仍建议持续跟踪互动链变化。"
            recommendations = [
                "保持结构化评论抓取，至少保留评论者、点赞数、回复数和回复预览。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:8],
            recommendations=recommendations,
        )

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
        speaker = record.speaker_nickname or record.speaker_id or "unknown"
        return (
            f"{speaker} | 赞 {record.like_count} | 回复 {record.reply_count} | "
            f"{record.text[:90]}"
        )

    def _format_reason(self, risk_types: list[str], record: CommentRecord) -> str:
        detail = ", ".join(risk_types)
        if record.reply_count or record.like_count:
            detail = f"{detail}; likes={record.like_count}, replies={record.reply_count}"
        return f"命中评论风险标签: {detail}"
