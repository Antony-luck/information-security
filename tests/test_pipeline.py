from __future__ import annotations

import unittest

from app.models.schemas import AnalysisInput, RiskLevel
from app.pipeline.orchestrator import AnalysisOrchestrator


class PipelineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = AnalysisOrchestrator()

    def test_high_risk_sample_should_trigger_multiple_modules(self):
        payload = AnalysisInput(
            video_id="risk-case",
            title="内部消息：官方证实今晚要狠狠干他们",
            description="画面里有人斗殴纵火，评论区已经吵起来了。",
            speech_text="现场有爆炸声和尖叫。",
            comments=[
                "私信我加V看完整版",
                "私信我加V看完整版",
                "滚出去，纯纯带节奏",
                "支持到底，狠狠干",
            ],
            visual_descriptions=["多人斗殴", "背景有敏感标语"],
            audio_cues=["尖叫", "爆炸声"],
            ocr_text=["紧急通知", "内部消息"],
            metadata={
                "account_age_days": 3,
                "follower_count": 5,
                "engagement_spike_ratio": 6.0,
                "publish_hour": 2,
                "burst_comment_ratio": 0.82,
                "region_mismatch": True,
            },
        )

        result = self.orchestrator.analyze(payload)

        self.assertIn(result.overall_risk_level, {RiskLevel.high, RiskLevel.critical})
        high_modules = {
            item.module_id for item in result.module_findings if item.risk_score >= 0.3
        }
        self.assertIn("semantic_context", high_modules)
        self.assertIn("comment_analysis", high_modules)
        self.assertIn("comprehensive_decision", high_modules)

    def test_low_risk_sample_should_stay_below_high(self):
        payload = AnalysisInput(
            video_id="safe-case",
            title="校园活动记录",
            description="分享今天的社团招新现场。",
            speech_text="欢迎大家参加本周活动。",
            comments=["氛围不错", "加油", "周末见"],
            metadata={
                "author_verified": True,
                "source_verified": True,
                "account_age_days": 365,
                "follower_count": 2200,
                "engagement_spike_ratio": 1.2,
                "publish_hour": 15,
                "burst_comment_ratio": 0.02,
            },
        )

        result = self.orchestrator.analyze(payload)

        self.assertIn(result.overall_risk_level, {RiskLevel.low, RiskLevel.medium})
        self.assertLess(result.overall_risk_score, 0.6)
        module_ids = {item.module_id for item in result.module_findings}
        self.assertEqual(
            module_ids,
            {
                "data_collection",
                "audiovisual_content",
                "semantic_context",
                "comment_analysis",
                "comprehensive_decision",
            },
        )


if __name__ == "__main__":
    unittest.main()
