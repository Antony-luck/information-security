from __future__ import annotations

from collections import Counter

from app.models.schemas import Evidence
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
        comments = [normalize_text(comment) for comment in content.normalized_segments["comments"]]
        comments = [comment for comment in comments if comment]
        if not comments:
            return self.build_finding(
                0.0,
                "当前没有可用评论样本，评论区分析模块只能返回保守结论。",
                recommendations=["补齐评论抓取后再启用评论区分析，以提升结论可信度。"],
            )

        evidence: list[Evidence] = []
        tags: list[str] = []
        pos_hits = 0
        neg_hits = 0
        conflict_hits = 0
        drainage_hits = 0

        for comment in comments:
            if any(term in comment for term in self.POSITIVE_EXTREME):
                pos_hits += 1
                evidence.append(
                    Evidence(
                        source="comment",
                        excerpt=comment[:120],
                        reason="命中极端支持表达",
                    )
                )
            if any(term in comment for term in self.NEGATIVE_EXTREME):
                neg_hits += 1
                evidence.append(
                    Evidence(
                        source="comment",
                        excerpt=comment[:120],
                        reason="命中极端反对表达",
                    )
                )
            if any(term in comment for term in self.CONFLICT_TERMS):
                conflict_hits += 1
                evidence.append(
                    Evidence(
                        source="comment",
                        excerpt=comment[:120],
                        reason="命中评论冲突表达",
                    )
                )
            if any(term in comment for term in self.DRAINAGE_TERMS):
                drainage_hits += 1
                evidence.append(
                    Evidence(
                        source="comment",
                        excerpt=comment[:120],
                        reason="命中异常引流表达",
                    )
                )

        duplicates = Counter(comments)
        duplicate_count = sum(count for count in duplicates.values() if count > 1)
        duplicate_ratio = duplicate_count / max(len(comments), 1)
        burst_ratio = float(content.standardized_metadata.get("burst_comment_ratio", 0.0))

        score = 0.0
        if pos_hits and neg_hits:
            score += 0.28
            tags.append("polarization")
        score += min(0.24, conflict_hits * 0.08)
        score += min(0.24, drainage_hits * 0.12)

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
                    reason="评论短时突增，疑似异常控评或刷评",
                )
            )

        if evidence:
            summary = "评论区已经出现了极化、冲突、异常引流或刷评迹象，说明传播生态存在明显的风险放大效应。"
            recommendations = [
                "增加评论情绪分布、立场聚类和重复评论图谱，提升评论生态的可解释性。",
                "把异常引流账号、重复文本和突增时间窗落库，便于后续追溯。",
            ]
        else:
            summary = "评论区当前未出现明显的极化或异常引流模式，但仍建议持续跟踪评论时间序列和账号行为。"
            recommendations = [
                "后续接入评论时间分布与账号画像数据，提升异常评论识别准确度。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:7],
            recommendations=recommendations,
        )
