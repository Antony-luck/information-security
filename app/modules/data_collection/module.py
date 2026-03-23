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
                    reason="采集模态较少，后续分析依据不足",
                )
            )

        if not segments.get("comments"):
            score += 0.08
            tags.append("comment-gap")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt="comments=0",
                    reason="评论区样本缺失，评论分析模块将只能给出保守结果",
                )
            )

        if not segments.get("speech_text") and not metadata.get("platform_caption"):
            score += 0.12
            tags.append("speech-gap")
            evidence.append(
                Evidence(
                    source="collection",
                    excerpt="speech_text=0",
                    reason="未获得可用语音文本，语义分析覆盖度下降",
                )
            )

        if not metadata.get("source_verified", False):
            score += 0.1
            tags.append("source-unverified")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata),
                    reason="来源未标记为可信信源，数据可信度需要人工复核",
                )
            )

        if int(metadata.get("account_age_days", 0)) < 30:
            score += 0.12
            tags.append("new-account")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata.get("account_age_days")),
                    reason="账号注册时间较短，传播可信度偏弱",
                )
            )

        if metadata.get("region_mismatch", False):
            score += 0.1
            tags.append("region-mismatch")
            evidence.append(
                Evidence(
                    source="metadata",
                    excerpt=str(metadata),
                    reason="内容地域描述与元数据疑似不一致",
                )
            )

        if evidence:
            summary = "采集链路已经完成，但当前样本在数据完整性或元数据可信度上仍存在不确定性，综合决策时应提高人工复核优先级。"
            recommendations = [
                "补齐评论、语音或 OCR 中缺失的模态数据，提升后续分析稳定性。",
                "对来源可信度偏低的样本保留原始链接、采集时间和快照，便于复核。",
            ]
        else:
            summary = "当前样本的采集字段较完整，元数据基础可信度正常，可作为后续各独立模块的稳定输入。"
            recommendations = [
                "继续保持采集链路的字段规范化和结构化输出，方便后续模块直接复用。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:5],
            recommendations=recommendations,
        )
