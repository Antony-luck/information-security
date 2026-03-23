from __future__ import annotations

from app.modules.shared import BaseIndependentModule, scan_keyword_groups


class AudiovisualContentModule(BaseIndependentModule):
    module_id = "audiovisual_content"
    module_name = "音画内容分析模块"
    target = "画面风险 / 音频异常 / 音画协同线索"

    VISUAL_KEYWORDS = {
        "violence": ["斗殴", "砍人", "血腥", "纵火", "爆炸", "枪击", "持刀"],
        "sexual": ["裸露", "成人视频", "色情", "约炮", "裸聊", "擦边"],
        "sensitive_symbol": ["极端旗帜", "违禁标识", "煽动口号", "敏感标语"],
        "dangerous_behavior": ["制毒", "开锁教学", "炸药", "燃爆", "跳楼", "自残"],
    }
    AUDIO_KEYWORDS = {
        "violent_audio": ["枪声", "爆炸声", "尖叫", "哭喊", "求救", "警报"],
        "panic_audio": ["玻璃碎裂", "嘶吼", "火警", "追逃", "惨叫"],
    }

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
            "visual-content",
        )
        audio_tags, audio_evidence, audio_hits = scan_keyword_groups(
            audio_texts,
            self.AUDIO_KEYWORDS,
            "audio-content",
        )

        score = 0.12 * len(visual_evidence) + 0.14 * len(audio_evidence)
        if visual_hits.get("dangerous_behavior", 0) >= 2:
            score += 0.14
        if visual_hits.get("violence", 0) and audio_hits.get("violent_audio", 0):
            score += 0.18
        if visual_hits.get("sexual", 0) and visual_hits.get("sensitive_symbol", 0):
            score += 0.08

        evidence = [*visual_evidence[:4], *audio_evidence[:3]]
        tags = [*visual_tags, *audio_tags]

        if evidence:
            summary = "音画内容中存在明显风险线索，且画面与音频线索能够相互印证，建议优先进入人工复核或更强模型复判。"
            recommendations = [
                "继续补强关键帧视觉模型，对危险行为、敏感标识和暴力画面做二次识别。",
                "把音频事件识别与关键帧时间戳联动，输出更可解释的音画证据链。",
            ]
        else:
            summary = "当前样本的音画内容未出现明显高风险代理信号，但该模块仍依赖 OCR、ASR 与抽帧结果的间接表达。"
            recommendations = [
                "后续接入更强的视觉理解模型和音频分类器，降低代理文本带来的漏检风险。"
            ]

        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:6],
            recommendations=recommendations,
        )
