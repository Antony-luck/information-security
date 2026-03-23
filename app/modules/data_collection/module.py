from __future__ import annotations

from app.models.schemas import Evidence, PreprocessedContent
from app.modules.shared import BaseIndependentModule


class DataCollectionModule(BaseIndependentModule):
    module_id = "data_collection"
    module_name = "数据处理与采集模块"
    target = "采集完整性 / 数据质量 / 元数据可信度"

    def analyze(self, content: PreprocessedContent):
        metadata = content.standardized_metadata
        segments = content.normalized_segments
        comment_records = content.input_payload.comment_records
        evidence: list[Evidence] = []
        tags: list[str] = []
        score = 0.0

        modality_count = sum(
            bool(segments.get(name))
            for name in (
                "title",
                "description",
                "speech_text",
                "comments",
                "visual_descriptions",
                "audio_cues",
                "ocr_text",
            )
        )
        if modality_count < 4:
            score += 0.16
            tags.append("low-coverage")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt=f"有效模态数: {modality_count}",
                    reason="当前可用模态较少，后续判断将更多依赖单一证据",
                )
            )

        if not segments.get("comments"):
            score += 0.08
            tags.append("comment-gap")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt="comments=0",
                    reason="没有可用评论样本，评论区分析会退化为保守判断",
                )
            )
        elif not comment_records:
            score += 0.1
            tags.append("comment-structure-missing")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt=f"plain_comments={len(segments.get('comments', []))}",
                    reason="只有纯文本评论，没有评论者、点赞、回复链等结构化字段",
                )
            )

        if comment_records:
            structured_ratio = sum(
                1
                for record in comment_records
                if record.speaker_id and (record.like_count >= 0) and record.publish_time
            ) / max(len(comment_records), 1)
            reply_rich_ratio = sum(
                1
                for record in comment_records
                if record.reply_count > 0 or record.reply_preview_count > 0
            ) / max(len(comment_records), 1)
            scanned_count = int(metadata.get("comment_count_scanned", len(comment_records)) or 0)

            if structured_ratio < 0.75:
                score += 0.08
                tags.append("comment-structure-thin")
                evidence.append(
                    Evidence(
                        source="collection",
                        excerpt=f"structured_ratio={structured_ratio:.2f}",
                        reason="结构化评论字段覆盖不足，评论者画像和互动链会不完整",
                    )
                )

            if reply_rich_ratio < 0.2:
                score += 0.05
                tags.append("reply-thread-thin")
                evidence.append(
                    Evidence(
                        source="collection",
                        excerpt=f"reply_rich_ratio={reply_rich_ratio:.2f}",
                        reason="高价值回复链过少，评论互动结构信息偏薄",
                    )
                )

            if scanned_count <= len(comment_records):
                score += 0.06
                tags.append("comment-ranking-shallow")
                evidence.append(
                    Evidence(
                        source="collection",
                        excerpt=f"scanned={scanned_count}, selected={len(comment_records)}",
                        reason="评论候选集和最终入选集几乎相同，说明重要评论筛选空间不足",
                    )
                )
            else:
                evidence.append(
                    Evidence(
                        source="collection",
                        excerpt=f"scanned={scanned_count}, selected={len(comment_records)}",
                        reason="评论不是随机截取，而是先扩大候选集再做重要性筛选",
                    )
                )

        if not segments.get("speech_text") and not metadata.get("platform_caption"):
            score += 0.12
            tags.append("speech-gap")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt="speech_text=0",
                    reason="缺少语音文本，语义分析会失去音频内容支撑",
                )
            )

        if not metadata.get("source_verified", False):
            score += 0.1
            tags.append("source-unverified")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(
                        {
                            "source_verified": metadata.get("source_verified", False),
                            "author_verified": metadata.get("author_verified", False),
                        }
                    ),
                    reason="来源未被平台标记为可信账号，元数据仍需人工复核",
                )
            )

        if int(metadata.get("account_age_days", 0)) < 30:
            score += 0.12
            tags.append("new-account")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata.get("account_age_days")),
                    reason="账号年龄较短，传播可信度需要结合更多外部证据判断",
                )
            )

        if metadata.get("region_mismatch", False):
            score += 0.1
            tags.append("region-mismatch")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata.get("region_mismatch")),
                    reason="内容叙述和元数据存在地域不一致的迹象",
                )
            )

        if evidence:
            summary = (
                "采集链路已完成，但样本在完整性、评论结构化程度或元数据可信度上"
                "仍存在需要复核的地方。"
            )
            recommendations = [
                "优先保留结构化评论字段，至少包含 speaker_id、点赞数、回复总数和回复预览。",
                "继续补齐语音、OCR 和视频快照，避免后续模块仅依赖单一模态判断。",
            ]
        else:
            summary = "当前样本的采集字段较完整，结构化评论和元数据质量可支撑后续模块稳定分析。"
            recommendations = [
                "维持结构化输出规范，确保评论者信息、互动强度和回复链在接口层持续可复用。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:6],
            recommendations=recommendations,
        )
