from __future__ import annotations

import re
from typing import Any

from app.core.config import settings
from app.models.schemas import Evidence, ModuleFinding, WorkflowStep
from app.modules.shared import (
    BaseIndependentModule,
    clamp_score,
    normalize_text,
    scan_keyword_groups,
    unique_keep_order,
)
from app.services import (
    LLMProviderError,
    SearchEvidenceService,
    build_llm_provider,
)


class SemanticContextModule(BaseIndependentModule):
    module_id = "semantic_context"
    module_name = "语义与上下文分析模块"
    target = "显性违规 / 隐性规避 / 事实断言风险"

    EXPLICIT_KEYWORDS = {
        "abuse": ["傻逼", "去死", "废物", "脑残", "滚出去"],
        "porn": ["约炮", "裸聊", "成人视频", "看片", "黄网"],
        "violence_extremism": ["杀人", "爆炸", "报复社会", "恐袭", "炸学校"],
    }
    IMPLICIT_KEYWORDS = {
        "coded_words": ["上车", "资源", "安排一个", "发链接", "主页见", "小号联系"],
        "slang_abuse": ["nmsl", "sb", "tm", "bzd"],
        "evasion": ["谐音", "拼音缩写", "换个平台说", "你懂的"],
    }
    FACT_TERMS = ["内部消息", "独家爆料", "100%真实", "官方证实", "紧急通知", "保真"]
    FACT_HINT_TERMS = ["刚刚", "今天", "今晚", "明天", "权威", "通报", "公告", "爆料"]
    FACT_NUMBER_PATTERN = re.compile(r"\d{2,}")

    RUMOR_TERMS = ["谣言", "辟谣", "不实", "假消息", "虚假", "网传", "系误传"]
    OFFICIAL_TERMS = ["官方", "通报", "公告", "新华社", "人民网", "gov.cn", "政府网"]
    TAG_LABELS = {
        "abuse": "辱骂攻击",
        "porn": "色情导流",
        "violence_extremism": "暴力极端",
        "coded_words": "暗语规避",
        "slang_abuse": "缩写辱骂",
        "evasion": "规避表达",
        "factuality": "事实断言",
        "implicit-risk": "隐性风险",
        "explicit-risk": "显性风险",
        "LLM语义复核": "LLM语义复核",
        "fact-check": "事实核查",
    }

    def __init__(self, llm_provider=None, search_service=None) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else build_llm_provider()
        if search_service is not None:
            self.search_service = search_service
        elif llm_provider is None and settings.fact_check_search_enabled:
            self.search_service = SearchEvidenceService(
                timeout_seconds=settings.fact_check_timeout_seconds
            )
        else:
            self.search_service = None

    def analyze(self, content):
        fact_bundle = self._run_search_fact_check(content)
        heuristic_finding = self._run_heuristic(content, fact_bundle)
        llm_finding = self._run_llm(content, fact_bundle)
        if not llm_finding:
            return heuristic_finding
        return self._merge_findings(heuristic_finding, llm_finding)

    def _run_heuristic(self, content, fact_bundle: dict[str, Any]) -> ModuleFinding:
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
            "语义显性线索",
        )
        implicit_tags, implicit_evidence, implicit_hits = scan_keyword_groups(
            texts,
            self.IMPLICIT_KEYWORDS,
            "语义隐性线索",
        )

        fact_hits = 0
        fact_evidence: list[Evidence] = []
        for text in texts:
            normalized = normalize_text(text)
            for term in self.FACT_TERMS:
                if term in normalized:
                    fact_hits += 1
                    fact_evidence.append(
                        Evidence(
                            source="语义事实断言",
                            excerpt=text[:120],
                            reason=f"命中事实断言关键词：{term}",
                        )
                    )
                    break

        score = 0.14 * len(explicit_evidence) + 0.12 * len(implicit_evidence)
        score += min(0.24, fact_hits * 0.12)
        score += float(fact_bundle.get("risk_delta", 0.0) or 0.0)

        if explicit_hits.get("violence_extremism", 0):
            score += 0.18
        if implicit_hits.get("coded_words", 0) and implicit_hits.get("evasion", 0):
            score += 0.16
        if fact_hits and not metadata.get("source_verified", False):
            score += 0.16
            fact_evidence.append(
                Evidence(
                    source="元数据",
                    excerpt=str(
                        {
                            "source_verified": metadata.get("source_verified", False),
                            "author_verified": metadata.get("author_verified", False),
                        }
                    ),
                    reason="出现高强度事实断言，但来源可信度不足。",
                )
            )

        evidence = [
            *explicit_evidence[:3],
            *implicit_evidence[:3],
            *fact_evidence[:3],
            *(fact_bundle.get("evidence") or [])[:3],
        ]
        tags = [*explicit_tags, *implicit_tags, *(fact_bundle.get("tags") or [])]
        if fact_hits:
            tags.append("factuality")
        tags = [self.TAG_LABELS.get(tag, tag) for tag in tags]

        summary = "未发现明显语义高风险表达，建议保持多模块联动复核。"
        recommendations = [
            "持续积累隐性规避样本和事实断言样本，提升语义推理稳定性。",
        ]
        if evidence:
            summary = "文本语义出现显性违规、隐性规避或事实断言风险，需要结合证据链继续复核。"
            recommendations = [
                "对高风险断言执行外部检索和可信来源交叉验证。",
                "对规避表达补充 LLM API 复判，减少规则误判与漏判。",
            ]

        metrics = {
            "explicit_evidence_count": len(explicit_evidence),
            "implicit_evidence_count": len(implicit_evidence),
            "fact_claim_hits": fact_hits,
            "source_verified": bool(metadata.get("source_verified", False)),
            "fact_check_search_enabled": bool(fact_bundle.get("search_enabled")),
            "fact_check_claim_count": int(fact_bundle.get("claim_count", 0) or 0),
            "fact_check_evidence_count": int(fact_bundle.get("evidence_count", 0) or 0),
            "fact_check_contradicted_count": int(
                fact_bundle.get("contradicted_count", 0) or 0
            ),
        }
        workflow_steps = [
            WorkflowStep(
                step_id="sc-1",
                stage="文本聚合",
                title="聚合语义输入",
                detail=(
                    f"文本片段数={len(texts)}，评论数={len(content.normalized_segments['comments'])}"
                ),
                module_id=self.module_id,
                refs=["标题", "描述", "语音文本", "评论文本", "弹幕"],
            ),
            WorkflowStep(
                step_id="sc-2",
                stage="规则筛查",
                title="规则层语义筛查",
                detail=(
                    f"显性命中={len(explicit_evidence)}，隐性命中={len(implicit_evidence)}，"
                    f"事实断言命中={fact_hits}"
                ),
                module_id=self.module_id,
                refs=[
                    *[self.TAG_LABELS.get(tag, tag) for tag in explicit_tags[:2]],
                    *[self.TAG_LABELS.get(tag, tag) for tag in implicit_tags[:2]],
                ],
            ),
        ]
        if fact_bundle.get("claim_count", 0):
            workflow_steps.append(
                WorkflowStep(
                    step_id="sc-3",
                    stage="事实核查",
                    title="外部检索事实核查",
                    detail=(
                        f"候选断言={int(fact_bundle.get('claim_count', 0))}，"
                        f"证据条目={int(fact_bundle.get('evidence_count', 0))}，"
                        f"反证数量={int(fact_bundle.get('contradicted_count', 0))}"
                    ),
                    module_id=self.module_id,
                    refs=["事实核查", "外部检索证据"],
                )
            )
        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:8],
            recommendations=recommendations,
            metrics=metrics,
            workflow_steps=workflow_steps,
        )

    def _run_search_fact_check(self, content) -> dict[str, Any]:
        texts = (
            content.normalized_segments["title"]
            + content.normalized_segments["description"]
            + content.normalized_segments["speech_text"]
            + content.normalized_segments["comments"]
        )
        claims = self._extract_fact_claims(texts, max_items=settings.fact_check_max_queries)
        bundle: dict[str, Any] = {
            "search_enabled": bool(self.search_service),
            "claim_count": len(claims),
            "evidence_count": 0,
            "contradicted_count": 0,
            "risk_delta": 0.0,
            "evidence": [],
            "tags": [],
            "claim_checks": [],
        }
        if not claims:
            return bundle

        for claim in claims:
            query = claim[:64]
            evidence_items = (
                self.search_service.search(query, max_results=3)
                if self.search_service
                else []
            )
            verdict, reason, risk_delta = self._judge_claim_with_search(evidence_items)

            if verdict == "反证":
                bundle["contradicted_count"] += 1
                bundle["tags"].append("事实核查-反证")
            elif verdict in {"未核实", "不确定"}:
                bundle["tags"].append("事实核查-未核实")
            else:
                bundle["tags"].append("事实核查-支持")

            bundle["risk_delta"] = float(bundle["risk_delta"]) + risk_delta
            bundle["evidence_count"] = int(bundle["evidence_count"]) + len(evidence_items)
            bundle["claim_checks"].append(
                {
                    "claim": claim,
                    "query": query,
                    "verdict": verdict,
                    "reason": reason,
                    "risk_delta": round(risk_delta, 3),
                    "evidences": [
                        {
                            "title": item.title,
                            "snippet": item.snippet,
                            "url": item.url,
                            "source": item.source,
                        }
                        for item in evidence_items
                    ],
                }
            )
            if evidence_items:
                top = evidence_items[0]
                bundle["evidence"].append(
                    Evidence(
                        source=f"检索:{top.source}",
                        excerpt=f"{claim[:80]} | {top.title[:70]} | {top.snippet[:110]}",
                        reason=f"事实核查结果：{verdict}（{reason}）",
                    )
                )
            else:
                bundle["evidence"].append(
                    Evidence(
                        source="检索:无结果",
                        excerpt=claim[:120],
                        reason="事实核查检索未返回有效证据。",
                    )
                )

        bundle["risk_delta"] = round(max(0.0, min(0.35, float(bundle["risk_delta"]))), 3)
        bundle["tags"] = unique_keep_order(bundle["tags"])
        return bundle

    def _extract_fact_claims(self, texts: list[str], max_items: int = 3) -> list[str]:
        claims: list[str] = []
        for text in texts:
            cleaned = " ".join((text or "").split()).strip()
            if len(cleaned) < 10:
                continue
            normalized = normalize_text(cleaned)
            has_fact_term = any(term in normalized for term in self.FACT_TERMS)
            has_hint_term = any(term in cleaned for term in self.FACT_HINT_TERMS)
            has_number = bool(self.FACT_NUMBER_PATTERN.search(cleaned))
            if has_fact_term or (has_hint_term and has_number):
                claims.append(cleaned[:160])
        return unique_keep_order(claims)[: max(1, max_items)]

    def _judge_claim_with_search(self, evidence_items) -> tuple[str, str, float]:
        if not evidence_items:
            return "未核实", "未检索到可用外部证据", 0.08

        merged = " ".join(
            [
                f"{item.title} {item.snippet} {item.url}".lower()
                for item in evidence_items
            ]
        )
        if any(term in merged for term in self.RUMOR_TERMS):
            return "反证", "检索结果出现辟谣/不实迹象", 0.18
        if any(term in merged for term in self.OFFICIAL_TERMS):
            return "支持", "检索结果出现官方来源迹象", -0.03
        return "不确定", "检索结果未形成明确支持或反证", 0.05

    def _run_llm(self, content, fact_bundle: dict[str, Any]) -> ModuleFinding | None:
        if not self.llm_provider:
            return None

        payload = {
            "video_id": content.input_payload.video_id,
            "title": content.input_payload.title,
            "description": content.input_payload.description,
            "speech_text": content.input_payload.speech_text[:1500],
            "ocr_text": content.input_payload.ocr_text[:12],
            "visual_descriptions": content.input_payload.visual_descriptions[:8],
            "comments": content.input_payload.comments[:12],
            "comment_records": [
                {
                    "speaker_id": record.speaker_id,
                    "speaker_nickname": record.speaker_nickname,
                    "text": record.text,
                    "like_count": record.like_count,
                    "reply_count": record.reply_count,
                    "keyword_tags": record.keyword_tags,
                    "importance_score": record.importance_score,
                }
                for record in content.input_payload.comment_records[:8]
            ],
            "metadata": {
                "source_verified": content.standardized_metadata.get("source_verified", False),
                "author_verified": content.standardized_metadata.get("author_verified", False),
                "account_age_days": content.standardized_metadata.get("account_age_days", 0),
                "burst_comment_ratio": content.standardized_metadata.get("burst_comment_ratio", 0.0),
                "region_mismatch": content.standardized_metadata.get("region_mismatch", False),
            },
            "fact_check_bundle": {
                "search_enabled": bool(fact_bundle.get("search_enabled")),
                "claim_count": int(fact_bundle.get("claim_count", 0)),
                "evidence_count": int(fact_bundle.get("evidence_count", 0)),
                "claim_checks": (fact_bundle.get("claim_checks") or [])[:3],
            },
        }
        try:
            response = self.llm_provider.complete_json(
                system_prompt=(
                    "你是短视频内容安全研判专家。请结合文本语义、上下文规避迹象和事实核查信息输出严格 JSON。"
                    "只返回 JSON，键为：risk_score, summary, tags, evidence, recommendations, fact_checks。"
                    "risk_score范围[0,1]；evidence每项必须包含source/excerpt/reason；"
                    "fact_checks每项包含claim/verdict/confidence/reason/source_urls。"
                    "summary、tags、evidence.reason、recommendations、fact_checks.reason请仅使用简体中文，不得输出英文或繁体中文。"
                ),
                user_payload=payload,
            )
        except LLMProviderError:
            return None
        except Exception:
            return None

        llm_payload = response.payload
        try:
            score = clamp_score(float(llm_payload.get("risk_score", 0.0) or 0.0))
        except (TypeError, ValueError):
            score = 0.0
        summary = str(llm_payload.get("summary") or "").strip()
        if not summary:
            return None

        evidence = self._parse_llm_evidence(llm_payload.get("evidence"))
        recommendations = self._parse_string_list(llm_payload.get("recommendations"))
        tags = self._parse_string_list(llm_payload.get("tags"))
        tags = [self.TAG_LABELS.get(tag, tag) for tag in tags]
        tags.append("LLM语义复核")
        workflow_steps = [
            WorkflowStep(
                step_id="sc-4",
                stage="LLM复核",
                title="大模型语义与事实复核",
                detail=(
                    f"调用提供方={response.provider}，模型={response.model}，"
                    f"LLM分数={score:.3f}"
                ),
                module_id=self.module_id,
                refs=["LLM语义复核", "事实核查"],
            )
        ]
        return self.build_finding(
            score=score,
            summary=summary,
            tags=tags,
            evidence=evidence[:5],
            recommendations=recommendations[:5],
            metrics={
                "llm_provider": response.provider,
                "llm_model": response.model,
                "llm_score": score,
                "llm_fact_checks": llm_payload.get("fact_checks") or [],
            },
            workflow_steps=workflow_steps,
        )

    def _parse_llm_evidence(self, raw_value: Any) -> list[Evidence]:
        evidence: list[Evidence] = []
        for item in raw_value or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "LLM语义").strip()
            excerpt = str(item.get("excerpt") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if excerpt and reason:
                evidence.append(
                    Evidence(
                        source=source[:60],
                        excerpt=excerpt[:180],
                        reason=reason[:180],
                    )
                )
        return evidence

    def _parse_string_list(self, raw_value: Any) -> list[str]:
        items = raw_value if isinstance(raw_value, list) else []
        return [
            str(item).strip()
            for item in items
            if str(item).strip()
        ]

    def _merge_findings(
        self,
        heuristic_finding: ModuleFinding,
        llm_finding: ModuleFinding,
    ) -> ModuleFinding:
        merged_score = clamp_score(
            max(
                heuristic_finding.risk_score,
                (heuristic_finding.risk_score * 0.45) + (llm_finding.risk_score * 0.75),
            )
        )
        merged_summary = (
            llm_finding.summary
            if llm_finding.risk_score >= heuristic_finding.risk_score
            else f"{heuristic_finding.summary} LLM补充：{llm_finding.summary}"
        )
        merged_tags = unique_keep_order([*heuristic_finding.tags, *llm_finding.tags])
        merged_evidence = [*heuristic_finding.evidence, *llm_finding.evidence]
        merged_recommendations = unique_keep_order(
            [*heuristic_finding.recommendations, *llm_finding.recommendations]
        )
        merged_metrics = {
            **heuristic_finding.metrics,
            **llm_finding.metrics,
            "merge_strategy": "取最大值（规则分数，加权融合分数）",
        }
        merged_workflow = [*heuristic_finding.workflow_steps, *llm_finding.workflow_steps]

        return self.build_finding(
            score=merged_score,
            summary=merged_summary,
            tags=merged_tags,
            evidence=merged_evidence[:9],
            recommendations=merged_recommendations[:7],
            metrics=merged_metrics,
            workflow_steps=merged_workflow,
        )
