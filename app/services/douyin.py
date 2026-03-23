from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from f2.apps.douyin.api import DouyinAPIEndpoints as DouyinAPI
from f2.apps.douyin.utils import ABogusManager, TokenManager

from app.core.config import settings
from app.models.schemas import (
    AnalysisInput,
    CommentSelectionMode,
    CommentRecord,
    CommentReply,
    SourceFetchSummary,
)


class DouyinFetchError(RuntimeError):
    pass


class DouyinFetcher:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    )
    COMMENT_SELECTION_STRATEGIES = {
        CommentSelectionMode.comprehensive: (
            "engagement + reply-thread + author-participation + keyword-signal + dedupe"
        ),
        CommentSelectionMode.engagement: (
            "reply-count + like-count + hot/pinned + author-participation + dedupe"
        ),
        CommentSelectionMode.recent: (
            "latest-publish-time + interaction-assist + dedupe"
        ),
        CommentSelectionMode.risk: (
            "risk-keywords + author-participation + interaction-assist + dedupe"
        ),
    }
    COMMENT_KEYWORD_GROUPS = {
        "polarized": ["支持到底", "必须严惩", "滚出去", "全是假的", "太解气了"],
        "conflict": ["对喷", "互骂", "站队", "冲他", "开撕"],
        "drainage": ["私信", "加v", "微信", "主页链接", "关注领取", "带你赚钱"],
        "fact_claim": ["内部消息", "100%真实", "官方证实", "保真", "独家爆料"],
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.storage_dir = settings.upload_dir / "douyin"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def fetch_source(
        self,
        source_url: str,
        max_comments: int = 20,
        download_video: bool = False,
        comment_selection_mode: CommentSelectionMode = CommentSelectionMode.comprehensive,
    ) -> tuple[SourceFetchSummary, AnalysisInput, str | None]:
        aweme_id, bootstrap_url = self._extract_aweme_id(source_url)
        self.session.get(bootstrap_url, timeout=20)

        detail = self._fetch_detail(aweme_id)
        scan_limit = self._determine_comment_scan_limit(max_comments)
        raw_comments = self._fetch_comments(aweme_id, max_comments=scan_limit)
        comment_records = self._select_important_comments(
            self._build_comment_records(raw_comments, detail),
            max_comments=max_comments,
            mode=comment_selection_mode,
        )

        upload_path = None
        download_error: str | None = None
        if download_video:
            try:
                upload_path = self._download_video(detail, aweme_id)
            except requests.RequestException as exc:
                download_error = str(exc)

        payload = self._build_analysis_input(
            aweme_id=aweme_id,
            source_url=source_url,
            detail=detail,
            comment_records=comment_records,
            scanned_comment_count=len(raw_comments),
            comment_selection_mode=comment_selection_mode,
        )
        if download_error:
            payload.metadata["video_download_error"] = download_error

        summary = self._build_summary(
            source_url=source_url,
            aweme_id=aweme_id,
            detail=detail,
            comment_records=comment_records,
            scanned_comment_count=len(raw_comments),
            comment_selection_mode=comment_selection_mode,
            upload_path=upload_path,
            download_error=download_error,
        )
        return summary, payload, upload_path

    def _extract_aweme_id(self, source_url: str) -> tuple[str, str]:
        parsed = urlparse(source_url)
        modal_id = parse_qs(parsed.query).get("modal_id")
        if modal_id and modal_id[0]:
            return modal_id[0], self._canonical_modal_url(modal_id[0])

        for pattern in (r"/video/(\d+)", r"/note/(\d+)"):
            match = re.search(pattern, source_url)
            if match:
                return match.group(1), source_url

        response = self.session.get(source_url, allow_redirects=True, timeout=20)
        final_url = str(response.url)

        parsed_final = urlparse(final_url)
        modal_id = parse_qs(parsed_final.query).get("modal_id")
        if modal_id and modal_id[0]:
            return modal_id[0], self._canonical_modal_url(modal_id[0])

        for pattern in (r"/video/(\d+)", r"/note/(\d+)"):
            match = re.search(pattern, final_url)
            if match:
                return match.group(1), final_url

        raise DouyinFetchError(f"无法从链接中解析 aweme_id: {source_url}")

    def _canonical_modal_url(self, aweme_id: str) -> str:
        return f"https://www.douyin.com/discover?modal_id={aweme_id}"

    def _base_params(self) -> dict[str, str]:
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "version_code": "290100",
            "version_name": "29.1.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Edge",
            "browser_version": "134.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "134.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "cpu_core_num": "20",
            "device_memory": "8",
            "platform": "PC",
            "downlink": "10",
            "effective_type": "4g",
            "round_trip_time": "100",
            "msToken": TokenManager.gen_false_msToken(),
        }

    def _fetch_detail(self, aweme_id: str) -> dict[str, Any]:
        params = self._base_params() | {"aweme_id": aweme_id}
        endpoint = ABogusManager.model_2_endpoint(
            self.USER_AGENT, DouyinAPI.POST_DETAIL, params
        )
        response = self.session.get(
            endpoint,
            headers={"Referer": "https://www.douyin.com/"},
            timeout=30,
        )
        response.raise_for_status()
        data = self._safe_json(response, "详情")
        detail = data.get("aweme_detail")
        if not isinstance(detail, dict):
            raise DouyinFetchError(f"抖音详情接口返回异常: {data}")
        return detail

    def _fetch_comments(self, aweme_id: str, max_comments: int) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        cursor = 0

        while len(comments) < max_comments:
            params = self._base_params() | {
                "aweme_id": aweme_id,
                "cursor": str(cursor),
                "count": str(min(20, max_comments - len(comments))),
                "item_type": "0",
                "insert_ids": "",
                "whale_cut_token": "",
                "cut_version": "1",
                "rcFT": "",
            }
            endpoint = ABogusManager.model_2_endpoint(
                self.USER_AGENT, DouyinAPI.POST_COMMENT, params
            )
            response = self.session.get(
                endpoint,
                headers={"Referer": "https://www.douyin.com/"},
                timeout=30,
            )
            response.raise_for_status()
            data = self._safe_json(response, "评论")
            if data.get("status_code") != 0:
                raise DouyinFetchError(f"抖音评论接口返回异常: {data}")

            batch = data.get("comments") or []
            if not batch:
                break

            comments.extend(batch)
            cursor = int(data.get("cursor") or 0)
            if not data.get("has_more"):
                break

        return comments[:max_comments]

    def _determine_comment_scan_limit(self, max_comments: int) -> int:
        return min(100, max(max_comments, max_comments * 3, 30))

    def _download_video(self, detail: dict[str, Any], aweme_id: str) -> str | None:
        play_url = self._extract_video_play_url(detail)
        if not play_url:
            return None

        target_path = self.storage_dir / f"{aweme_id}.mp4"
        if target_path.exists() and target_path.stat().st_size > 0:
            return str(target_path)

        with self.session.get(
            play_url,
            stream=True,
            timeout=60,
            headers={"Referer": "https://www.douyin.com/"},
        ) as response:
            response.raise_for_status()
            with target_path.open("wb") as file_obj:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file_obj.write(chunk)
        return str(target_path)

    def _build_analysis_input(
        self,
        aweme_id: str,
        source_url: str,
        detail: dict[str, Any],
        comment_records: list[CommentRecord],
        scanned_comment_count: int,
        comment_selection_mode: CommentSelectionMode,
    ) -> AnalysisInput:
        desc = str(detail.get("desc") or "").strip()
        author = detail.get("author") or {}
        statistics = detail.get("statistics") or {}
        seo_info = detail.get("seo_info") or {}

        create_time = self._safe_int(detail.get("create_time"))
        publish_dt = self._to_local_datetime(create_time)
        ocr_text = self._split_lines(seo_info.get("seo_ocr_content") or "")
        comment_texts = [record.text for record in comment_records if record.text]

        metadata = {
            "platform": "douyin",
            "source_url": source_url,
            "aweme_id": aweme_id,
            "platform_caption": str(detail.get("caption") or "").strip(),
            "author_uid": str(author.get("uid") or "").strip(),
            "author_sec_uid": str(author.get("sec_uid") or "").strip() or None,
            "author_nickname": str(author.get("nickname") or "").strip(),
            "author_verified": bool(
                author.get("enterprise_verify_reason") or author.get("custom_verify")
            ),
            "source_verified": bool(
                author.get("enterprise_verify_reason") or author.get("custom_verify")
            ),
            "follower_count": self._safe_int(author.get("follower_count")),
            "account_age_days": 0,
            "engagement_spike_ratio": 1.0,
            "publish_hour": publish_dt.hour if publish_dt else 12,
            "burst_comment_ratio": 0.0,
            "region_mismatch": False,
            "comment_count": self._safe_int(statistics.get("comment_count")),
            "comment_count_scanned": scanned_comment_count,
            "comment_count_selected": len(comment_records),
            "comment_like_total": sum(record.like_count for record in comment_records),
            "comment_reply_total": sum(record.reply_count for record in comment_records),
            "comment_reply_preview_total": sum(
                record.reply_preview_count for record in comment_records
            ),
            "comment_selection_mode": comment_selection_mode.value,
            "comment_selection_strategy": self.COMMENT_SELECTION_STRATEGIES[
                comment_selection_mode
            ],
            "comment_author_participation_count": sum(
                1
                for record in comment_records
                if record.is_author or any(reply.is_author for reply in record.replies)
            ),
            "comment_keyword_tags": self._unique_keep_order(
                tag for record in comment_records for tag in record.keyword_tags
            ),
            "digg_count": self._safe_int(statistics.get("digg_count")),
            "share_count": self._safe_int(statistics.get("share_count")),
            "collect_count": self._safe_int(statistics.get("collect_count")),
            "duration_ms": self._safe_int(
                (detail.get("video") or {}).get("duration") or detail.get("duration")
            ),
            "video_play_url": self._extract_video_play_url(detail),
            "cover_url": self._extract_cover_url(detail),
        }

        return AnalysisInput(
            video_id=aweme_id,
            title=desc[:80],
            description=desc,
            speech_text="",
            bullet_chats=[],
            comments=comment_texts,
            comment_records=comment_records,
            visual_descriptions=[],
            audio_cues=[],
            ocr_text=ocr_text,
            metadata=metadata,
        )

    def _build_summary(
        self,
        source_url: str,
        aweme_id: str,
        detail: dict[str, Any],
        comment_records: list[CommentRecord],
        scanned_comment_count: int,
        comment_selection_mode: CommentSelectionMode,
        upload_path: str | None,
        download_error: str | None = None,
    ) -> SourceFetchSummary:
        author = detail.get("author") or {}
        statistics = detail.get("statistics") or {}
        create_time = self._safe_int(detail.get("create_time"))
        publish_time = (
            self._to_local_datetime(create_time).isoformat() if create_time else None
        )
        return SourceFetchSummary(
            platform="douyin",
            source_url=source_url,
            aweme_id=aweme_id,
            title=str(detail.get("desc") or "")[:80],
            author_nickname=str(author.get("nickname") or ""),
            desc=str(detail.get("desc") or ""),
            cover_url=self._extract_cover_url(detail),
            publish_time=publish_time,
            video_downloaded=bool(upload_path),
            video_path=upload_path,
            video_asset_url=settings.upload_asset_url(upload_path),
            video_download_error=download_error,
            video_play_url=self._extract_video_play_url(detail),
            comment_count_fetched=len(comment_records),
            comment_count_scanned=scanned_comment_count,
            comment_total_reported=(
                self._safe_int(statistics.get("comment_count"))
                if statistics.get("comment_count") is not None
                else None
            ),
            comment_selection_mode=comment_selection_mode,
            comment_selection_strategy=self.COMMENT_SELECTION_STRATEGIES[
                comment_selection_mode
            ],
        )

    def _build_comment_records(
        self, comments: list[dict[str, Any]], detail: dict[str, Any]
    ) -> list[CommentRecord]:
        author_uid = str(((detail.get("author") or {}).get("uid")) or "").strip()
        records: list[CommentRecord] = []

        for comment in comments:
            text = str(comment.get("text") or "").strip()
            if not text:
                continue

            user = comment.get("user") or {}
            replies = self._build_comment_replies(comment.get("reply_comment") or [], author_uid)
            record = CommentRecord(
                comment_id=str(comment.get("cid") or "").strip(),
                speaker_id=str(user.get("uid") or "").strip(),
                speaker_sec_uid=str(user.get("sec_uid") or "").strip() or None,
                speaker_nickname=str(user.get("nickname") or "").strip(),
                speaker_unique_id=str(user.get("unique_id") or "").strip() or None,
                speaker_region=str(user.get("region") or "").strip() or None,
                text=text,
                like_count=self._safe_int(comment.get("digg_count")),
                reply_count=max(
                    self._safe_int(comment.get("reply_comment_total")),
                    len(replies),
                ),
                reply_preview_count=len(replies),
                publish_timestamp=self._safe_int(comment.get("create_time")),
                publish_time=self._comment_publish_time(comment.get("create_time")),
                ip_label=str(comment.get("ip_label") or "").strip() or None,
                is_author=bool(author_uid and str(user.get("uid") or "").strip() == author_uid),
                is_hot=bool(comment.get("is_hot")),
                is_pinned=self._safe_int(comment.get("stick_position")) > 0,
                is_verified=bool(
                    user.get("enterprise_verify_reason") or user.get("custom_verify")
                ),
                has_media=bool(comment.get("image_list") or comment.get("video_list")),
                label_text=str(comment.get("label_text") or "").strip(),
                replies=replies,
            )
            keyword_tags = self._extract_comment_keyword_tags(
                " ".join([record.text, *[reply.text for reply in replies]])
            )
            importance_score, importance_reasons = self._score_comment_record(
                record,
                keyword_tags=keyword_tags,
            )
            record.keyword_tags = keyword_tags
            record.importance_score = importance_score
            record.importance_reasons = importance_reasons
            records.append(record)

        return records

    def _build_comment_replies(
        self, replies: list[dict[str, Any]], author_uid: str
    ) -> list[CommentReply]:
        items: list[CommentReply] = []
        for reply in replies:
            text = str(reply.get("text") or "").strip()
            if not text:
                continue
            user = reply.get("user") or {}
            items.append(
                CommentReply(
                    reply_id=str(reply.get("cid") or reply.get("reply_id") or "").strip(),
                    speaker_id=str(user.get("uid") or "").strip(),
                    speaker_sec_uid=str(user.get("sec_uid") or "").strip() or None,
                    speaker_nickname=str(user.get("nickname") or "").strip(),
                    speaker_unique_id=str(user.get("unique_id") or "").strip() or None,
                    speaker_region=str(user.get("region") or "").strip() or None,
                    text=text,
                    like_count=self._safe_int(reply.get("digg_count")),
                    publish_timestamp=self._safe_int(reply.get("create_time")),
                    publish_time=self._comment_publish_time(reply.get("create_time")),
                    ip_label=str(reply.get("ip_label") or "").strip() or None,
                    is_author=bool(
                        author_uid and str(user.get("uid") or "").strip() == author_uid
                    ),
                    is_hot=bool(reply.get("is_hot")),
                    is_verified=bool(
                        user.get("enterprise_verify_reason") or user.get("custom_verify")
                    ),
                    has_media=bool(reply.get("image_list") or reply.get("video_list")),
                )
            )
        return items

    def _select_important_comments(
        self,
        records: list[CommentRecord],
        max_comments: int,
        mode: CommentSelectionMode = CommentSelectionMode.comprehensive,
    ) -> list[CommentRecord]:
        ranked = sorted(
            records,
            key=lambda record: self._selection_sort_key(record, mode),
            reverse=True,
        )

        selected: list[CommentRecord] = []
        seen_texts: set[str] = set()
        for record in ranked:
            normalized = self._normalize_text(record.text)
            if not normalized or normalized in seen_texts:
                continue
            seen_texts.add(normalized)
            selected.append(record)
            if len(selected) >= max_comments:
                break

        if len(selected) < min(max_comments, len(records)):
            seen_ids = {record.comment_id for record in selected if record.comment_id}
            for record in records:
                if record.comment_id and record.comment_id in seen_ids:
                    continue
                selected.append(record)
                if len(selected) >= max_comments:
                    break

        return selected[:max_comments]

    def _selection_sort_key(
        self, record: CommentRecord, mode: CommentSelectionMode
    ) -> tuple[float, ...]:
        if mode == CommentSelectionMode.engagement:
            return (
                round(self._interaction_strength(record), 6),
                float(record.reply_count),
                float(record.like_count),
                float(int(record.is_hot)),
                float(int(record.is_pinned)),
                float(int(record.is_author or any(reply.is_author for reply in record.replies))),
                float(record.publish_timestamp),
            )

        if mode == CommentSelectionMode.recent:
            return (
                float(record.publish_timestamp),
                round(self._interaction_strength(record), 6),
                float(record.reply_count),
                float(record.like_count),
                float(record.importance_score),
            )

        if mode == CommentSelectionMode.risk:
            return (
                round(self._risk_priority(record), 6),
                round(self._interaction_strength(record), 6),
                float(int(record.is_author or any(reply.is_author for reply in record.replies))),
                float(record.publish_timestamp),
                float(record.importance_score),
            )

        return (
            float(record.importance_score),
            round(self._interaction_strength(record), 6),
            float(record.reply_count),
            float(record.like_count),
            float(int(record.is_author)),
            float(int(record.is_hot)),
            float(int(record.is_pinned)),
            float(record.publish_timestamp),
        )

    def _interaction_strength(self, record: CommentRecord) -> float:
        score = 0.0
        score += math.log1p(max(record.reply_count, 0)) * 1.3
        score += math.log1p(max(record.like_count, 0)) * 0.9
        score += min(record.reply_preview_count * 0.12, 0.6)
        score += 0.4 if record.is_hot else 0.0
        score += 0.3 if record.is_pinned else 0.0
        score += 0.25 if record.is_author or any(reply.is_author for reply in record.replies) else 0.0
        return score

    def _risk_priority(self, record: CommentRecord) -> float:
        tag_weights = {
            "drainage": 1.5,
            "conflict": 1.1,
            "fact_claim": 1.0,
            "polarized": 0.9,
        }
        score = sum(tag_weights.get(tag, 0.35) for tag in record.keyword_tags)
        if record.is_author or any(reply.is_author for reply in record.replies):
            score += 0.8
        if record.label_text:
            score += 0.2
        if record.has_media:
            score += 0.15
        return score

    def _score_comment_record(
        self, record: CommentRecord, keyword_tags: list[str]
    ) -> tuple[float, list[str]]:
        score = 0.2
        reasons: list[str] = []

        if record.is_pinned:
            score += 1.3
            reasons.append("置顶评论")
        if record.is_hot:
            score += 1.0
            reasons.append("热门评论")
        if record.is_author:
            score += 1.1
            reasons.append("作者直接发言")
        if any(reply.is_author for reply in record.replies):
            score += 0.9
            reasons.append("作者参与回复")
        if record.is_verified:
            score += 0.35
            reasons.append("认证账号")
        if record.like_count > 0:
            score += min(1.4, math.log1p(record.like_count) * 0.42)
            reasons.append(f"点赞 {record.like_count}")
        if record.reply_count > 0:
            score += min(1.6, math.log1p(record.reply_count) * 0.6)
            reasons.append(f"回复 {record.reply_count}")
        if record.reply_preview_count > 0:
            score += min(0.8, record.reply_preview_count * 0.18)
            reasons.append(f"已抓到 {record.reply_preview_count} 条回复预览")
        if len(record.text) >= 18:
            score += min(0.6, len(record.text) / 80.0)
            reasons.append("观点较完整")
        if record.has_media:
            score += 0.25
            reasons.append("评论携带媒体")
        if record.label_text:
            score += 0.15
            reasons.append(f"标签: {record.label_text[:12]}")
        if keyword_tags:
            score += min(1.0, len(keyword_tags) * 0.28)
            reasons.append(f"命中标签: {', '.join(keyword_tags[:2])}")
        if record.ip_label:
            score += 0.08

        return round(score, 3), self._unique_keep_order(reasons)

    def _extract_comment_keyword_tags(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        tags: list[str] = []
        for tag, keywords in self.COMMENT_KEYWORD_GROUPS.items():
            if any(keyword in normalized for keyword in keywords):
                tags.append(tag)
        return self._unique_keep_order(tags)

    def _comment_publish_time(self, value: Any) -> str | None:
        timestamp = self._safe_int(value)
        if not timestamp:
            return None
        return self._to_local_datetime(timestamp).isoformat()

    def _to_local_datetime(self, timestamp: int) -> datetime:
        return datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=8)))

    def _extract_video_play_url(self, detail: dict[str, Any]) -> str | None:
        video = detail.get("video") or {}

        play_addr = video.get("play_addr") or {}
        if isinstance(play_addr, dict):
            urls = play_addr.get("url_list") or []
            if urls:
                return str(urls[0])

        bit_rates = video.get("bit_rate") or []
        for item in bit_rates:
            urls = ((item or {}).get("play_addr") or {}).get("url_list") or []
            if urls:
                return str(urls[0])

        return None

    def _extract_cover_url(self, detail: dict[str, Any]) -> str | None:
        video = detail.get("video") or {}
        for key in ("origin_cover", "dynamic_cover", "cover"):
            candidate = video.get(key) or {}
            urls = candidate.get("url_list") or []
            if urls:
                return str(urls[0])
        return None

    def _split_lines(self, value: str) -> list[str]:
        return [line.strip() for line in value.splitlines() if line.strip()]

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _normalize_text(self, value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def _unique_keep_order(self, items) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    def _safe_json(self, response: requests.Response, scene: str) -> dict[str, Any]:
        try:
            data = response.json()
        except requests.JSONDecodeError as exc:
            body_preview = (response.text or "").strip().replace("\n", " ")[:200]
            content_type = response.headers.get("content-type") or "unknown"
            raise DouyinFetchError(
                f"抖音{scene}接口返回非 JSON 响应: status={response.status_code}, "
                f"content-type={content_type}, body={body_preview or '<empty>'}"
            ) from exc
        if not isinstance(data, dict):
            raise DouyinFetchError(f"抖音{scene}接口返回格式异常: {type(data).__name__}")
        return data
