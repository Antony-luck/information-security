from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from f2.apps.douyin.api import DouyinAPIEndpoints as DouyinAPI
from f2.apps.douyin.utils import ABogusManager, TokenManager

from app.core.config import settings
from app.models.schemas import AnalysisInput, SourceFetchSummary


class DouyinFetchError(RuntimeError):
    pass


class DouyinFetcher:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    )

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.storage_dir = settings.upload_dir / "douyin"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def fetch_source(
        self, source_url: str, max_comments: int = 20, download_video: bool = False
    ) -> tuple[SourceFetchSummary, AnalysisInput, str | None]:
        aweme_id, bootstrap_url = self._extract_aweme_id(source_url)
        self.session.get(bootstrap_url, timeout=20)

        detail = self._fetch_detail(aweme_id)
        comments = self._fetch_comments(aweme_id, max_comments=max_comments)
        upload_path = None
        download_error: str | None = None
        if download_video:
            try:
                upload_path = self._download_video(detail, aweme_id)
            except requests.RequestException as exc:
                download_error = str(exc)
        payload = self._build_analysis_input(aweme_id, source_url, detail, comments)
        if download_error:
            payload.metadata["video_download_error"] = download_error
        summary = self._build_summary(
            source_url=source_url,
            aweme_id=aweme_id,
            detail=detail,
            comments=comments,
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
        comments: list[dict[str, Any]],
    ) -> AnalysisInput:
        desc = detail.get("desc") or ""
        author = detail.get("author") or {}
        statistics = detail.get("statistics") or {}
        seo_info = detail.get("seo_info") or {}

        create_time = int(detail.get("create_time") or 0)
        publish_dt = (
            datetime.fromtimestamp(
                create_time, tz=timezone(timedelta(hours=8))
            )
            if create_time
            else None
        )
        ocr_text = self._split_lines(seo_info.get("seo_ocr_content") or "")
        comment_texts = [
            str(item.get("text") or "").strip()
            for item in comments
            if str(item.get("text") or "").strip()
        ]

        metadata = {
            "platform": "douyin",
            "source_url": source_url,
            "aweme_id": aweme_id,
            "platform_caption": str(detail.get("caption") or "").strip(),
            "author_uid": author.get("uid"),
            "author_sec_uid": author.get("sec_uid"),
            "author_nickname": author.get("nickname"),
            "author_verified": bool(
                author.get("enterprise_verify_reason") or author.get("custom_verify")
            ),
            "source_verified": bool(
                author.get("enterprise_verify_reason") or author.get("custom_verify")
            ),
            "follower_count": int(author.get("follower_count") or 0),
            "account_age_days": 0,
            "engagement_spike_ratio": 1.0,
            "publish_hour": publish_dt.hour if publish_dt else 12,
            "burst_comment_ratio": 0.0,
            "region_mismatch": False,
            "comment_count": int(statistics.get("comment_count") or 0),
            "digg_count": int(statistics.get("digg_count") or 0),
            "share_count": int(statistics.get("share_count") or 0),
            "collect_count": int(statistics.get("collect_count") or 0),
            "duration_ms": int(
                (detail.get("video") or {}).get("duration")
                or detail.get("duration")
                or 0
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
        comments: list[dict[str, Any]],
        upload_path: str | None,
        download_error: str | None = None,
    ) -> SourceFetchSummary:
        author = detail.get("author") or {}
        statistics = detail.get("statistics") or {}
        create_time = int(detail.get("create_time") or 0)
        publish_time = (
            datetime.fromtimestamp(
                create_time, tz=timezone(timedelta(hours=8))
            ).isoformat()
            if create_time
            else None
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
            comment_count_fetched=len(comments),
            comment_total_reported=(
                int(statistics.get("comment_count"))
                if statistics.get("comment_count") is not None
                else None
            ),
        )

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
