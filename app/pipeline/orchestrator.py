from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.models.schemas import AnalysisInput
from app.modules import (
    AudiovisualContentModule,
    CommentAnalysisModule,
    ComprehensiveDecisionModule,
    DataCollectionModule,
    DataPreprocessingService,
    SemanticContextModule,
)


class AnalysisOrchestrator:
    def __init__(self) -> None:
        self.preprocessor = DataPreprocessingService()
        self.data_collection_module = DataCollectionModule()
        self.independent_modules = [
            AudiovisualContentModule(),
            SemanticContextModule(),
            CommentAnalysisModule(),
        ]
        self.decision_module = ComprehensiveDecisionModule()

    def analyze(
        self,
        payload: AnalysisInput,
        upload_path: str | None = None,
    ):
        content = self.preprocessor.preprocess(payload, upload_path)
        execution_trace = [
            "数据处理与采集模块完成输入清洗、字段规范化和元数据标准化。",
            "音画内容模块、语义与上下文模块、评论区模块以独立线程并行分析。",
        ]

        with ThreadPoolExecutor(max_workers=len(self.independent_modules) + 1) as executor:
            futures = [
                executor.submit(self.data_collection_module.analyze, content),
                *[
                    executor.submit(module.analyze, content)
                    for module in self.independent_modules
                ],
            ]
            findings = [future.result() for future in futures]

        execution_trace.append("综合决策模块开始汇总独立模块结果并生成总体结论、行动建议和证据摘要。")
        output = self.decision_module.build_output(content, findings, execution_trace)
        output.module_findings.sort(key=lambda item: item.risk_score, reverse=True)
        return output
