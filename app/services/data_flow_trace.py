from __future__ import annotations

from typing import Any

from app.core.registry import MODULE_REGISTRY
from app.models.schemas import AnalysisInput, PreprocessedContent, SourceFetchSummary


MODULE_USAGE = {
    "data_collection": {
        "raw_fields": [
            "title",
            "description",
            "speech_text",
            "comments",
            "comment_records",
            "visual_descriptions",
            "audio_cues",
            "ocr_text",
            "metadata",
        ],
        "preprocessed_segments": [
            "title",
            "description",
            "speech_text",
            "bullet_chats",
            "comments",
            "comment_replies",
            "comment_tags",
            "visual_descriptions",
            "audio_cues",
            "ocr_text",
        ],
        "metadata_keys": [
            "source_verified",
            "author_verified",
            "account_age_days",
            "follower_count",
            "burst_comment_ratio",
            "region_mismatch",
            "comment_count_scanned",
            "comment_count_selected",
            "structured_comment_count",
            "important_comment_count",
        ],
        "notes": "负责完整性检查、结构化程度检查和元数据可信度评估。",
    },
    "audiovisual_content": {
        "raw_fields": [
            "title",
            "description",
            "speech_text",
            "visual_descriptions",
            "audio_cues",
            "ocr_text",
        ],
        "preprocessed_segments": [
            "title",
            "description",
            "speech_text",
            "visual_descriptions",
            "audio_cues",
            "ocr_text",
        ],
        "metadata_keys": [],
        "notes": "当前主要吃 OCR、ASR、抽帧摘要和音频事件形成的文本代理信号。",
    },
    "semantic_context": {
        "raw_fields": [
            "title",
            "description",
            "speech_text",
            "bullet_chats",
            "comments",
            "comment_records",
            "visual_descriptions",
            "audio_cues",
            "ocr_text",
            "metadata",
        ],
        "preprocessed_segments": [
            "title",
            "description",
            "speech_text",
            "bullet_chats",
            "comments",
        ],
        "metadata_keys": [
            "source_verified",
            "author_verified",
            "account_age_days",
            "burst_comment_ratio",
            "region_mismatch",
            "comment_count_scanned",
            "structured_comment_count",
        ],
        "notes": "规则层主要看文本，LLM 复判层还会补充 comment_records、OCR、音频线索和元数据。",
    },
    "comment_analysis": {
        "raw_fields": ["comments", "comment_records", "metadata"],
        "preprocessed_segments": ["comments"],
        "metadata_keys": [
            "burst_comment_ratio",
            "comment_count_scanned",
            "comment_count_selected",
            "comment_like_total",
            "comment_reply_total",
            "comment_unique_speaker_count",
            "important_comment_count",
        ],
        "notes": "优先使用结构化重要评论，不再依赖随机评论文本。",
    },
}


RAW_FIELD_SPECS = [
    {
        "field": "video_id",
        "label": "video_id",
        "display_name": "视频编号",
        "preprocessed_targets": [],
        "modules": [],
        "notes": "统一样本 ID，主要用于标识和追踪。",
    },
    {
        "field": "title",
        "label": "title",
        "display_name": "标题",
        "preprocessed_targets": ["normalized_segments.title"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自视频标题或详情页文案。",
    },
    {
        "field": "description",
        "label": "description",
        "display_name": "描述",
        "preprocessed_targets": ["normalized_segments.description"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自视频简介、详情描述或平台文案。",
    },
    {
        "field": "speech_text",
        "label": "speech_text",
        "display_name": "ASR 文本",
        "preprocessed_targets": ["normalized_segments.speech_text"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自本地 ASR，失败时可回退平台 caption。",
    },
    {
        "field": "bullet_chats",
        "label": "bullet_chats",
        "display_name": "弹幕",
        "preprocessed_targets": ["normalized_segments.bullet_chats"],
        "modules": ["data_collection", "semantic_context"],
        "notes": "当前主要参与语义和上下文分析。",
    },
    {
        "field": "comments",
        "label": "comments",
        "display_name": "重要评论文本",
        "preprocessed_targets": [
            "normalized_segments.comments",
            "comment_corpus",
        ],
        "modules": ["data_collection", "semantic_context", "comment_analysis"],
        "notes": "结构化评论的纯文本视图，保留兼容性。",
    },
    {
        "field": "comment_records",
        "label": "comment_records",
        "display_name": "结构化评论",
        "preprocessed_targets": [
            "input_payload.comment_records",
            "standardized_metadata.structured_comment_count",
        ],
        "modules": ["data_collection", "semantic_context", "comment_analysis"],
        "notes": "包含 speaker_id、点赞、回复链、标签和重要性分数。",
    },
    {
        "field": "visual_descriptions",
        "label": "visual_descriptions",
        "display_name": "抽帧摘要 / 视觉描述",
        "preprocessed_targets": ["normalized_segments.visual_descriptions"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自抽帧后 OCR 摘要和视觉线索描述。",
    },
    {
        "field": "audio_cues",
        "label": "audio_cues",
        "display_name": "音频线索",
        "preprocessed_targets": ["normalized_segments.audio_cues"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自音频事件识别和 ASR 分段提示。",
    },
    {
        "field": "ocr_text",
        "label": "ocr_text",
        "display_name": "OCR 文本",
        "preprocessed_targets": ["normalized_segments.ocr_text"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
        "notes": "来自视频抽帧 OCR。",
    },
    {
        "field": "metadata",
        "label": "metadata",
        "display_name": "元数据",
        "preprocessed_targets": ["standardized_metadata"],
        "modules": ["data_collection", "semantic_context", "comment_analysis"],
        "notes": "包含账号可信度、评论统计、视频信息等辅助判断字段。",
    },
]


SEGMENT_SPECS = [
    {
        "segment": "title",
        "label": "normalized_segments.title",
        "derived_from": ["title"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
    },
    {
        "segment": "description",
        "label": "normalized_segments.description",
        "derived_from": ["description"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
    },
    {
        "segment": "speech_text",
        "label": "normalized_segments.speech_text",
        "derived_from": ["speech_text"],
        "modules": ["data_collection", "audiovisual_content", "semantic_context"],
    },
    {
        "segment": "bullet_chats",
        "label": "normalized_segments.bullet_chats",
        "derived_from": ["bullet_chats"],
        "modules": ["data_collection", "semantic_context"],
    },
    {
        "segment": "comments",
        "label": "normalized_segments.comments",
        "derived_from": ["comments"],
        "modules": ["data_collection", "semantic_context", "comment_analysis"],
    },
    {
        "segment": "comment_replies",
        "label": "normalized_segments.comment_replies",
        "derived_from": ["comment_records.replies"],
        "modules": ["data_collection"],
    },
    {
        "segment": "comment_tags",
        "label": "normalized_segments.comment_tags",
        "derived_from": ["comment_records.keyword_tags"],
        "modules": ["data_collection"],
    },
    {
        "segment": "visual_descriptions",
        "label": "normalized_segments.visual_descriptions",
        "derived_from": ["visual_descriptions"],
        "modules": ["data_collection", "audiovisual_content"],
    },
    {
        "segment": "audio_cues",
        "label": "normalized_segments.audio_cues",
        "derived_from": ["audio_cues"],
        "modules": ["data_collection", "audiovisual_content"],
    },
    {
        "segment": "ocr_text",
        "label": "normalized_segments.ocr_text",
        "derived_from": ["ocr_text"],
        "modules": ["data_collection", "audiovisual_content"],
    },
]


def _model_to_dict(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        return to_dict()
    return value


def _preview_value(value: Any) -> Any:
    if isinstance(value, str):
        compact = " ".join(value.split())
        return compact[:240] + ("..." if len(compact) > 240 else "")
    if isinstance(value, list):
        if not value:
            return []
        if value and isinstance(value[0], dict):
            return value[:2]
        return value[:5]
    if isinstance(value, dict):
        preview_keys = list(value.keys())[:8]
        return {key: value[key] for key in preview_keys}
    return value


def build_debug_trace(
    *,
    source: SourceFetchSummary,
    payload: AnalysisInput,
    content: PreprocessedContent,
) -> dict[str, Any]:
    payload_dict = _model_to_dict(payload)
    content_dict = _model_to_dict(content)
    source_dict = _model_to_dict(source)

    raw_field_trace = []
    for spec in RAW_FIELD_SPECS:
        value = payload_dict.get(spec["field"])
        raw_field_trace.append(
            {
                **spec,
                "value_preview": _preview_value(value),
                "item_count": len(value) if isinstance(value, list) else None,
            }
        )

    preprocessed_trace = []
    for spec in SEGMENT_SPECS:
        value = content.normalized_segments.get(spec["segment"], [])
        preprocessed_trace.append(
            {
                **spec,
                "value_preview": _preview_value(value),
                "item_count": len(value) if isinstance(value, list) else None,
            }
        )

    module_lookup = {profile.module_id: _model_to_dict(profile) for profile in MODULE_REGISTRY}
    module_routes = []
    for module_id, usage in MODULE_USAGE.items():
        profile = module_lookup.get(module_id, {})
        module_routes.append(
            {
                "module_id": module_id,
                "module_name": profile.get("module_name", module_id),
                "module_group": profile.get("module_group", ""),
                "detection_goal": profile.get("detection_goal", ""),
                **usage,
            }
        )

    metadata_usage = []
    standardized_metadata = content.standardized_metadata
    referenced_metadata_keys = []
    for usage in MODULE_USAGE.values():
        referenced_metadata_keys.extend(usage["metadata_keys"])
    for key in dict.fromkeys(referenced_metadata_keys):
        modules = [
            module_id
            for module_id, usage in MODULE_USAGE.items()
            if key in usage["metadata_keys"]
        ]
        metadata_usage.append(
            {
                "key": key,
                "value": standardized_metadata.get(key),
                "modules": modules,
            }
        )

    return {
        "source": source_dict,
        "raw_collected": {
            "source_summary": source_dict,
            "input_payload": payload_dict,
            "field_trace": raw_field_trace,
        },
        "preprocessed": {
            "request_id": content.request_id,
            "created_at": content.created_at,
            "combined_text": content.combined_text,
            "comment_corpus": content.comment_corpus,
            "normalized_segments": content.normalized_segments,
            "standardized_metadata": content.standardized_metadata,
            "segment_trace": preprocessed_trace,
            "metadata_trace": metadata_usage,
            "full_content": content_dict,
        },
        "module_routes": module_routes,
    }
