from __future__ import annotations

import unittest

from app.models.schemas import AnalysisInput
from app.modules.data_collection.preprocessor import DataPreprocessingService
from app.modules.semantic_context.module import SemanticContextModule


class _FakeProvider:
    def complete_json(self, *, system_prompt: str, user_payload: dict):
        return type(
            "FakeResponse",
            (),
            {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "payload": {
                    "risk_score": 0.72,
                    "summary": "LLM 认为文本存在规避式表达和高风险断言。",
                    "tags": ["implicit-risk", "factuality"],
                    "evidence": [
                        {
                            "source": "comments",
                            "excerpt": "主页见，内部消息保真",
                            "reason": "包含规避式导流和待核验断言",
                        }
                    ],
                    "recommendations": ["对相关文本做外部检索和人工复核。"],
                },
            },
        )()


class SemanticContextLlmTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.preprocessor = DataPreprocessingService()

    def test_semantic_context_should_merge_llm_review(self):
        module = SemanticContextModule(llm_provider=_FakeProvider())
        content = self.preprocessor.preprocess(
            AnalysisInput(
                video_id="demo",
                title="内部消息今晚有安排",
                description="主页见，换个平台说",
                comments=["主页见", "内部消息保真"],
                metadata={"source_verified": False},
            )
        )

        finding = module.analyze(content)

        self.assertGreaterEqual(finding.risk_score, 0.72)
        self.assertIn("llm-semantic-review", finding.tags)
        self.assertTrue(any(item.source == "comments" for item in finding.evidence))
        self.assertTrue(any("人工复核" in item for item in finding.recommendations))


if __name__ == "__main__":
    unittest.main()
