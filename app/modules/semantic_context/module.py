from __future__ import annotations

from app.models.schemas import Evidence
from app.modules.shared import BaseIndependentModule, normalize_text, scan_keyword_groups


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

    def analyze(self, content):
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
