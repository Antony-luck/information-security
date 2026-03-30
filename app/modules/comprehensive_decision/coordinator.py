from __future__ import annotations

from app.models.schemas import (
    AnalysisOutput,
    Evidence,
    ModuleFinding,
    PreprocessedContent,
    RiskLevel,
    WorkflowStep,
)
from app.modules.shared import BaseIndependentModule, clamp_score, score_to_level, unique_keep_order


class ComprehensiveDecisionModule(BaseIndependentModule):
    module_id = "comprehensive_decision"
    module_name = "综合决策模块"
    target = "整合协调独立模块输出总体风险结论"
    RISK_LEVEL_LABELS = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "严重",
    }

    def __init__(self) -> None:
        self.weights = {
            "data_collection": 0.55,
            "audiovisual_content": 1.15,
            "semantic_context": 1.2,
            "comment_analysis": 0.95,
        }

    def analyze(
        self,
        content: PreprocessedContent,
        module_findings: list[ModuleFinding],
    ) -> tuple[ModuleFinding, list[str], list[str]]:
        overall_score = self._aggregate_score(module_findings)
        overall_level = score_to_level(overall_score)
        recommendations = self._merge_recommendations(module_findings)
        next_actions = self._build_next_actions(module_findings, overall_level)
        summary = self._build_summary(module_findings, overall_level)
        evidence = self._build_evidence(module_findings)
        tags = self._build_tags(module_findings, overall_level)

        finding = self.build_finding(
            score=overall_score,
            summary=summary,
            tags=tags,
            evidence=evidence,
            recommendations=recommendations,
        )
        return finding, recommendations, next_actions

    def build_output(
        self,
        content: PreprocessedContent,
        independent_findings: list[ModuleFinding],
        execution_trace: list[str],
        pipeline_flow: list[WorkflowStep] | None = None,
    ) -> AnalysisOutput:
        decision_finding, recommendations, next_actions = self.analyze(
            content,
            independent_findings,
        )
        module_findings = [*independent_findings, decision_finding]
        return AnalysisOutput(
            request_id=content.request_id,
            created_at=content.created_at,
            overall_risk_level=decision_finding.risk_level,
            overall_risk_score=decision_finding.risk_score,
            summary=decision_finding.summary,
            module_findings=module_findings,
            recommendations=recommendations,
            next_actions=next_actions,
            execution_trace=execution_trace,
            pipeline_flow=pipeline_flow or [],
        )

    def _aggregate_score(self, findings: list[ModuleFinding]) -> float:
        total_weight = sum(self.weights.get(item.module_id, 1.0) for item in findings)
        weighted_score = sum(
            item.risk_score * self.weights.get(item.module_id, 1.0) for item in findings
        ) / max(total_weight, 1e-6)

        high_modules = sum(
            item.risk_level in {RiskLevel.high, RiskLevel.critical} for item in findings
        )
        if high_modules >= 2:
            weighted_score += 0.1
        if self._is_high("semantic_context", findings) and self._is_high(
            "comment_analysis", findings
        ):
            weighted_score += 0.08
        if self._is_high("audiovisual_content", findings) and self._is_high(
            "semantic_context", findings
        ):
            weighted_score += 0.1
        return clamp_score(weighted_score)

    def _merge_recommendations(self, findings: list[ModuleFinding]) -> list[str]:
        recommendations: list[str] = []
        for finding in findings:
            recommendations.extend(finding.recommendations)
        return unique_keep_order(recommendations)[:8]

    def _build_next_actions(
        self,
        findings: list[ModuleFinding],
        overall_level: RiskLevel,
    ) -> list[str]:
        actions: list[str] = []
        if overall_level in {RiskLevel.high, RiskLevel.critical}:
            actions.append("进入人工复核队列，并保留命中证据用于演示和答辩。")
        if self._risk_at_least("semantic_context", 0.35, findings):
            actions.append("对核心断言执行外部检索和可信源交叉验证。")
        if self._risk_at_least("comment_analysis", 0.3, findings):
            actions.append("导出评论极化、重复评论和引流线索，补充传播生态证据。")
        if self._risk_at_least("audiovisual_content", 0.35, findings):
            actions.append("对关键帧和音频时间窗做二次复判，确认音画风险是否相互印证。")
        if self._risk_at_least("data_collection", 0.2, findings):
            actions.append("补齐缺失模态或来源可信度字段，避免综合结论建立在低质量样本上。")
        if not actions:
            actions.append("当前样本可作为低风险基线样本保留，用于后续模型评测。")
        return actions

    def _build_summary(
        self,
        findings: list[ModuleFinding],
        overall_level: RiskLevel,
    ) -> str:
        top_findings = [item for item in findings if item.risk_score >= 0.25]
        if not top_findings:
            return "综合决策判断当前样本整体风险较低，独立模块均未发现强烈风险信号，可作为基线样本保存。"
        module_names = "、".join(item.module_name for item in top_findings[:3])
        level_label = self.RISK_LEVEL_LABELS.get(overall_level.value, overall_level.value)
        return (
            f"综合决策模块判定当前样本为{level_label}风险，"
            f"主要风险来源于 {module_names}。"
        )

    def _build_evidence(self, findings: list[ModuleFinding]) -> list[Evidence]:
        evidence: list[Evidence] = []
        for finding in sorted(findings, key=lambda item: item.risk_score, reverse=True)[:4]:
            evidence.append(
                Evidence(
                    source=finding.module_name,
                    excerpt=finding.summary[:120],
                    reason=f"模块风险分数: {finding.risk_score:.3f}",
                )
            )
        return evidence

    def _build_tags(
        self,
        findings: list[ModuleFinding],
        overall_level: RiskLevel,
    ) -> list[str]:
        level_label = self.RISK_LEVEL_LABELS.get(overall_level.value, overall_level.value)
        tags = [f"总体风险-{level_label}"]
        for finding in findings:
            tags.extend(finding.tags[:2])
        return unique_keep_order(tags)

    def _is_high(self, module_id: str, findings: list[ModuleFinding]) -> bool:
        return any(
            item.module_id == module_id
            and item.risk_level in {RiskLevel.high, RiskLevel.critical}
            for item in findings
        )

    def _risk_at_least(
        self,
        module_id: str,
        threshold: float,
        findings: list[ModuleFinding],
    ) -> bool:
        return any(
            item.module_id == module_id and item.risk_score >= threshold
            for item in findings
        )
