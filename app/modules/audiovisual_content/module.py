from __future__ import annotations

from typing import Any

from app.models.schemas import Evidence, WorkflowStep
from app.modules.shared import BaseIndependentModule, clamp_score, scan_keyword_groups, unique_keep_order
from app.services import LLMProviderError, build_llm_provider


class AudiovisualContentModule(BaseIndependentModule):
    module_id = "audiovisual_content"
    module_name = "音画内容分析模块"
    target = "画面风险 / 音频异常 / 音画协同线索"

    VISUAL_KEYWORDS = {
        "violence": ["斗殴", "砍人", "持刀", "爆炸", "纵火", "血腥", "枪击"],
        "sexual": ["裸露", "色情", "成人", "约炮", "擦边"],
        "sensitive_symbol": ["极端旗帜", "敏感标语", "煽动口号"],
        "dangerous_behavior": ["制毒", "炸药", "爆破", "跳楼", "自残"],
    }
    AUDIO_KEYWORDS = {
        "violent_audio": ["枪声", "爆炸声", "尖叫", "求救", "警报"],
        "panic_audio": ["玻璃碎裂", "火警", "惨叫", "追逐"],
    }
    TAG_LABELS = {
        "violence": "暴力画面",
        "sexual": "性相关画面",
        "sensitive_symbol": "敏感符号",
        "dangerous_behavior": "危险行为",
        "violent_audio": "暴力音频",
        "panic_audio": "恐慌音频",
        "llm-audiovisual-review": "LLM音画复核",
    }

    def __init__(self, llm_provider=None) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else build_llm_provider()

    def analyze(self, content):
        visual_texts = (
            content.normalized_segments["title"]
            + content.normalized_segments["description"]
            + content.normalized_segments["speech_text"]
            + content.normalized_segments["visual_descriptions"]
            + content.normalized_segments["ocr_text"]
        )
        audio_texts = (
            content.normalized_segments["audio_cues"]
            + content.normalized_segments["speech_text"]
            + content.normalized_segments["description"]
        )

        visual_tags, visual_evidence, visual_hits = scan_keyword_groups(
            visual_texts,
            self.VISUAL_KEYWORDS,
            "画面线索",
        )
        audio_tags, audio_evidence, audio_hits = scan_keyword_groups(
            audio_texts,
            self.AUDIO_KEYWORDS,
            "音频线索",
        )

        heuristic_score = 0.12 * len(visual_evidence) + 0.14 * len(audio_evidence)
        if visual_hits.get("dangerous_behavior", 0) >= 2:
            heuristic_score += 0.14
        if visual_hits.get("violence", 0) and audio_hits.get("violent_audio", 0):
            heuristic_score += 0.18
        if visual_hits.get("sexual", 0) and visual_hits.get("sensitive_symbol", 0):
            heuristic_score += 0.08

        evidence = [*visual_evidence[:4], *audio_evidence[:3]]
        tags = [*visual_tags, *audio_tags]
        tags = [self.TAG_LABELS.get(tag, tag) for tag in tags]

        summary = "未发现明显音画高风险线索，建议继续结合语义和评论模块做联动判定。"
        recommendations = [
            "补强视觉定位模型与音频事件模型，降低仅凭文本代理信号产生的误差。"
        ]
        if evidence:
            summary = "检测到音画层面的风险线索，存在画面和音频相互印证的迹象。"
            recommendations = [
                "对命中时段补做关键帧复核，确认风险类别和定位是否稳定。",
                "结合时间轴对齐音频事件与视觉线索，输出可追溯证据链。",
            ]

        llm_review = self._run_llm_review(content)
        if llm_review:
            heuristic_score = max(heuristic_score, heuristic_score * 0.5 + llm_review["risk_score"] * 0.7)
            summary = llm_review["summary"] or summary
            tags = unique_keep_order([*tags, *llm_review["tags"], "LLM音画复核"])
            evidence = [*evidence, *llm_review["evidence"]]
            recommendations = unique_keep_order([*recommendations, *llm_review["recommendations"]])

        metrics = {
            "visual_signal_count": len(visual_evidence),
            "audio_signal_count": len(audio_evidence),
            "visual_hits": dict(visual_hits),
            "audio_hits": dict(audio_hits),
            "llm_review_enabled": bool(self.llm_provider),
            "llm_review_used": bool(llm_review),
        }
        workflow_steps = [
            WorkflowStep(
                step_id="av-1",
                stage="信号提取",
                title="聚合音画代理信号",
                detail=(
                    f"画面文本片段={len(visual_texts)}，音频文本片段={len(audio_texts)}，"
                    f"OCR行数={len(content.normalized_segments['ocr_text'])}"
                ),
                module_id=self.module_id,
                refs=["视频摘要/抽帧描述", "音频线索", "OCR文本", "语音文本"],
            ),
            WorkflowStep(
                step_id="av-2",
                stage="规则筛查",
                title="规则层音画风险筛查",
                detail=(
                    f"画面命中={len(visual_evidence)}，音频命中={len(audio_evidence)}，"
                    f"规则分数={clamp_score(heuristic_score):.3f}"
                ),
                module_id=self.module_id,
                refs=[
                    *[self.TAG_LABELS.get(tag, tag) for tag in visual_tags[:2]],
                    *[self.TAG_LABELS.get(tag, tag) for tag in audio_tags[:2]],
                ],
            ),
            WorkflowStep(
                step_id="av-3",
                stage="LLM复核",
                title="大模型音画复核",
                detail=(
                    "已调用大模型进行细粒度音画复核。"
                    if llm_review
                    else "未调用大模型复核，当前仅使用规则结果。"
                ),
                module_id=self.module_id,
                refs=["LLM音画复核"] if llm_review else [],
            ),
        ]

        return self.build_finding(
            score=heuristic_score,
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
            "title": content.input_payload.title,
            "description": content.input_payload.description,
            "speech_text": content.input_payload.speech_text[:1600],
            "visual_descriptions": content.input_payload.visual_descriptions[:16],
            "ocr_text": content.input_payload.ocr_text[:16],
            "audio_cues": content.input_payload.audio_cues[:16],
            "video_metadata": {
                "platform": content.standardized_metadata.get("platform"),
                "publish_hour": content.standardized_metadata.get("publish_hour"),
                "source_verified": content.standardized_metadata.get("source_verified"),
            },
        }
        try:
            response = self.llm_provider.complete_json(
                system_prompt=(
                    "你是短视频音画安全研判专家。请只返回严格 JSON，键为："
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
                    source=str(item.get("source") or "LLM音画")[:60],
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
