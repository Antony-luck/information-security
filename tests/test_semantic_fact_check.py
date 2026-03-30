from __future__ import annotations

import unittest

from app.models.schemas import AnalysisInput
from app.modules.data_collection.preprocessor import DataPreprocessingService
from app.modules.semantic_context.module import SemanticContextModule
from app.services import LLMProviderError, SearchEvidence


class _NoLlmProvider:
    def complete_json(self, *, system_prompt: str, user_payload: dict):
        raise LLMProviderError("llm disabled for this test")


class _FakeSearchService:
    def search(self, query: str, max_results: int = 3):
        return [
            SearchEvidence(
                title="官方辟谣通报",
                snippet="该消息不实，系谣言，请勿传播。",
                url="https://example.com/fact-check",
                source="unit-test",
            )
        ][:max_results]


class SemanticFactCheckTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.preprocessor = DataPreprocessingService()

    def test_semantic_module_should_run_search_fact_check_step(self):
        module = SemanticContextModule(
            llm_provider=_NoLlmProvider(),
            search_service=_FakeSearchService(),
        )
        content = self.preprocessor.preprocess(
            AnalysisInput(
                video_id="fact-case",
                title="内部消息：今晚有重大通报",
                description="100%真实，请转发",
                comments=["刚刚官方证实，主页见"],
                metadata={"source_verified": False},
            )
        )

        finding = module.analyze(content)
        step_ids = [step.step_id for step in finding.workflow_steps]

        self.assertIn("sc-3", step_ids)
        self.assertGreaterEqual(finding.metrics.get("fact_check_claim_count", 0), 1)
        self.assertGreaterEqual(finding.metrics.get("fact_check_contradicted_count", 0), 1)
        self.assertTrue(any(tag.startswith("事实核查-") for tag in finding.tags))


if __name__ == "__main__":
    unittest.main()
