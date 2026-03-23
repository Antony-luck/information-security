from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from app.models.schemas import AnalysisInput, PreprocessedContent


def _clean_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _clean_list(values: Iterable[str]) -> list[str]:
    return [_clean_text(value) for value in values if _clean_text(value)]


class DataPreprocessingService:
    def preprocess(
        self, payload: AnalysisInput, upload_path: str | None = None
    ) -> PreprocessedContent:
        comment_texts = payload.comments or [record.text for record in payload.comment_records]
        reply_texts = [
            reply.text
            for record in payload.comment_records
            for reply in record.replies
            if reply.text
        ]
        comment_tags = [
            tag
            for record in payload.comment_records
            for tag in record.keyword_tags
            if tag
        ]

        segments = {
            "title": _clean_list([payload.title]),
            "description": _clean_list([payload.description]),
            "speech_text": _clean_list([payload.speech_text]),
            "bullet_chats": _clean_list(payload.bullet_chats),
            "comments": _clean_list(comment_texts),
            "comment_replies": _clean_list(reply_texts),
            "comment_tags": _clean_list(comment_tags),
            "visual_descriptions": _clean_list(payload.visual_descriptions),
            "audio_cues": _clean_list(payload.audio_cues),
            "ocr_text": _clean_list(payload.ocr_text),
        }
        combined_text = "\n".join(
            item
            for section in (
                "title",
                "description",
                "speech_text",
                "bullet_chats",
                "visual_descriptions",
                "ocr_text",
            )
            for item in segments[section]
        )
        comment_corpus = "\n".join(
            [*segments["comments"], *segments["comment_replies"], *segments["comment_tags"]]
        )
        standardized_metadata = self._normalize_metadata(payload.metadata, payload)
        if upload_path:
            standardized_metadata["upload_path"] = upload_path

        return PreprocessedContent(
            request_id=f"{payload.video_id}-{uuid4().hex[:8]}",
            input_payload=payload,
            upload_path=upload_path,
            combined_text=combined_text,
            comment_corpus=comment_corpus,
            normalized_segments=segments,
            standardized_metadata=standardized_metadata,
        )

    def _normalize_metadata(
        self, metadata: dict[str, object], payload: AnalysisInput
    ) -> dict[str, object]:
        normalized = dict(metadata or {})
        normalized.setdefault("author_verified", False)
        normalized.setdefault("source_verified", False)
        normalized.setdefault("account_age_days", 0)
        normalized.setdefault("follower_count", 0)
        normalized.setdefault("engagement_spike_ratio", 1.0)
        normalized.setdefault("publish_hour", 12)
        normalized.setdefault("burst_comment_ratio", 0.0)
        normalized.setdefault("region_mismatch", False)
        normalized.setdefault("comment_count_scanned", len(payload.comment_records))
        normalized.setdefault("comment_count_selected", len(payload.comment_records))
        normalized.setdefault(
            "comment_reply_total",
            sum(record.reply_count for record in payload.comment_records),
        )
        normalized.setdefault(
            "comment_reply_preview_total",
            sum(record.reply_preview_count for record in payload.comment_records),
        )
        normalized.setdefault(
            "comment_like_total",
            sum(record.like_count for record in payload.comment_records),
        )
        normalized.setdefault(
            "structured_comment_count",
            len(payload.comment_records),
        )
        if payload.comment_records:
            speaker_ids = {
                record.speaker_id or record.speaker_nickname
                for record in payload.comment_records
                if record.speaker_id or record.speaker_nickname
            }
            normalized.setdefault("comment_unique_speaker_count", len(speaker_ids))
            normalized.setdefault(
                "important_comment_count",
                sum(
                    1 for record in payload.comment_records if record.importance_score >= 2.0
                ),
            )
        else:
            normalized.setdefault("comment_unique_speaker_count", 0)
            normalized.setdefault("important_comment_count", 0)
        return normalized
