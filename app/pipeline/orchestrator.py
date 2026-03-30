from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from app.models.schemas import AnalysisInput, WorkflowStep
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
        # 第一步：将采集数据预处理为标准化分段。
        pre_start = perf_counter()
        content = self.preprocessor.preprocess(payload, upload_path)
        pre_ms = int((perf_counter() - pre_start) * 1000)

        execution_trace = [
            "预处理完成：标准化分段与元数据已就绪。",
        ]
        pipeline_flow: list[WorkflowStep] = [
            WorkflowStep(
                step_id="S01",
                stage="预处理",
                title="标准化采集数据",
                detail=(
                    f"视频编号={payload.video_id or '未知'}，"
                    f"标准化处理耗时 {pre_ms} 毫秒。"
                ),
                module_id="data_collection",
                refs=["预处理分段", "标准化元数据", "评论语料"],
            )
        ]

        # 第二步：并行执行独立模块。
        module_start = perf_counter()
        with ThreadPoolExecutor(max_workers=len(self.independent_modules) + 1) as executor:
            futures = [
                executor.submit(self.data_collection_module.analyze, content),
                *[
                    executor.submit(module.analyze, content)
                    for module in self.independent_modules
                ],
            ]
            findings = [future.result() for future in futures]
        module_ms = int((perf_counter() - module_start) * 1000)
        execution_trace.append(
            "独立模块并行完成：数据采集、音画内容、语义上下文、评论区分析。"
        )

        risk_level_labels = {
            "low": "低风险",
            "medium": "中风险",
            "high": "高风险",
            "critical": "严重风险",
        }
        ordered_findings = sorted(findings, key=lambda item: item.risk_score, reverse=True)
        for index, finding in enumerate(ordered_findings, start=2):
            pipeline_flow.append(
                WorkflowStep(
                    step_id=f"S{index:02d}",
                    stage="模块分析",
                    title=f"{finding.module_name}完成",
                    detail=(
                        f"风险分数={finding.risk_score:.3f}，"
                        f"风险等级={risk_level_labels.get(finding.risk_level.value, finding.risk_level.value)}，"
                        f"证据数={len(finding.evidence)}"
                    ),
                    module_id=finding.module_id,
                    refs=finding.tags[:4],
                )
            )

        # 第三步：聚合模块结论形成综合决策。
        decision_start = perf_counter()
        output = self.decision_module.build_output(
            content,
            findings,
            execution_trace,
            pipeline_flow=pipeline_flow,
        )
        decision_ms = int((perf_counter() - decision_start) * 1000)
        output.module_findings.sort(key=lambda item: item.risk_score, reverse=True)

        output.execution_trace.append(
            "综合决策完成：已生成总体风险与下一步动作。"
        )
        output.pipeline_flow.extend(
            [
                WorkflowStep(
                    step_id="S90",
                    stage="综合决策",
                    title="聚合模块结论",
                    detail=f"综合聚合耗时 {decision_ms} 毫秒。",
                    module_id="comprehensive_decision",
                    refs=["综合风险分数", "下一步动作", "处置建议"],
                ),
                WorkflowStep(
                    step_id="S99",
                    stage="流程汇总",
                    title="全链路耗时汇总",
                    detail=(
                        f"预处理={pre_ms} 毫秒，模块分析={module_ms} 毫秒，"
                        f"综合决策={decision_ms} 毫秒，模块数={len(findings)}"
                    ),
                    refs=["执行轨迹", "模块结论"],
                ),
            ]
        )
        return output
