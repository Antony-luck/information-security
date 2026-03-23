from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from app.services.douyin import DouyinFetchError, DouyinFetcher


class DouyinFetcherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = DouyinFetcher()

    def test_extract_aweme_id_from_modal_id_url(self):
        aweme_id, resolved = self.fetcher._extract_aweme_id(
            "https://www.douyin.com/jingxuan?modal_id=7589926461256027430"
        )
        self.assertEqual(aweme_id, "7589926461256027430")
        self.assertEqual(
            resolved, "https://www.douyin.com/discover?modal_id=7589926461256027430"
        )

    def test_extract_aweme_id_from_search_modal_url_should_use_canonical_discover_url(self):
        aweme_id, resolved = self.fetcher._extract_aweme_id(
            "https://www.douyin.com/search/%E5%85%B1%E4%BA%A7%E4%B8%BB%E4%B9%89"
            "?aid=6098dd47-5c24-4b2f-9911-adde7284421c&modal_id=7515703888260746537&type=general"
        )
        self.assertEqual(aweme_id, "7515703888260746537")
        self.assertEqual(
            resolved, "https://www.douyin.com/discover?modal_id=7515703888260746537"
        )

    def test_extract_aweme_id_from_video_url(self):
        aweme_id, resolved = self.fetcher._extract_aweme_id(
            "https://www.douyin.com/video/7589926461256027430"
        )
        self.assertEqual(aweme_id, "7589926461256027430")
        self.assertIn("/video/7589926461256027430", resolved)

    def test_build_analysis_input_from_detail_and_comments(self):
        detail = {
            "desc": "示例视频文案 #测试",
            "create_time": 1767690360,
            "author": {
                "uid": "123456",
                "sec_uid": "sec-test",
                "nickname": "测试作者",
                "follower_count": 1000,
                "enterprise_verify_reason": "已认证",
                "custom_verify": "",
            },
            "statistics": {
                "comment_count": 12,
                "digg_count": 45,
                "share_count": 6,
                "collect_count": 8,
            },
            "seo_info": {"seo_ocr_content": "第一行OCR\n第二行OCR"},
            "video": {
                "duration": 15000,
                "play_addr": {"url_list": ["https://example.com/video.mp4"]},
                "origin_cover": {"url_list": ["https://example.com/cover.jpg"]},
            },
        }
        comments = [
            {"text": "第一条评论"},
            {"text": "第二条评论"},
            {"text": "  "},
        ]

        payload = self.fetcher._build_analysis_input(
            aweme_id="7589926461256027430",
            source_url="https://www.douyin.com/video/7589926461256027430",
            detail=detail,
            comments=comments,
        )

        self.assertEqual(payload.video_id, "7589926461256027430")
        self.assertEqual(payload.comments, ["第一条评论", "第二条评论"])
        self.assertEqual(payload.ocr_text, ["第一行OCR", "第二行OCR"])
        self.assertEqual(payload.metadata["author_nickname"], "测试作者")
        self.assertEqual(payload.metadata["comment_count"], 12)
        self.assertTrue(payload.metadata["author_verified"])

    def test_safe_json_should_raise_douyin_error_for_non_json_body(self):
        response = Mock(spec=requests.Response)
        response.status_code = 200
        response.text = ""
        response.headers = {"content-type": "text/plain; charset=utf-8"}
        response.json.side_effect = requests.JSONDecodeError("Expecting value", "", 0)

        with self.assertRaises(DouyinFetchError) as context:
            self.fetcher._safe_json(response, "详情")

        self.assertIn("非 JSON 响应", str(context.exception))


if __name__ == "__main__":
    unittest.main()
