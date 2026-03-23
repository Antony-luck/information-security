from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from app.models.schemas import CommentSelectionMode
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

    def test_build_comment_records_should_keep_speaker_likes_and_replies(self):
        detail = {
            "author": {
                "uid": "author-1",
                "nickname": "作者",
            }
        }
        comments = [
            {
                "cid": "comment-1",
                "text": "第一条评论",
                "digg_count": 18,
                "reply_comment_total": 2,
                "create_time": 1767690360,
                "ip_label": "江苏",
                "is_hot": True,
                "stick_position": 1,
                "label_text": "热评",
                "user": {
                    "uid": "user-1",
                    "sec_uid": "sec-1",
                    "nickname": "评论者A",
                    "unique_id": "abc001",
                    "region": "CN",
                },
                "reply_comment": [
                    {
                        "cid": "reply-1",
                        "text": "作者回复",
                        "digg_count": 3,
                        "create_time": 1767690390,
                        "ip_label": "河南",
                        "user": {
                            "uid": "author-1",
                            "nickname": "作者",
                            "unique_id": "author001",
                        },
                    }
                ],
            },
            {
                "cid": "comment-2",
                "text": "第二条评论",
                "digg_count": 2,
                "reply_comment_total": 0,
                "create_time": 1767690420,
                "user": {
                    "uid": "user-2",
                    "nickname": "评论者B",
                },
                "reply_comment": [],
            },
        ]

        records = self.fetcher._build_comment_records(comments, detail)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].speaker_id, "user-1")
        self.assertEqual(records[0].speaker_nickname, "评论者A")
        self.assertEqual(records[0].like_count, 18)
        self.assertEqual(records[0].reply_count, 2)
        self.assertEqual(records[0].reply_preview_count, 1)
        self.assertTrue(records[0].is_hot)
        self.assertTrue(records[0].is_pinned)
        self.assertEqual(records[0].replies[0].speaker_id, "author-1")
        self.assertTrue(records[0].replies[0].is_author)
        self.assertGreater(records[0].importance_score, records[1].importance_score)

    def test_build_analysis_input_from_detail_and_comments(self):
        detail = {
            "desc": "示例视频文案 #测试",
            "create_time": 1767690360,
            "caption": "平台字幕文本",
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
        raw_comments = [
            {
                "cid": "comment-1",
                "text": "第一条评论",
                "digg_count": 9,
                "reply_comment_total": 1,
                "create_time": 1767690360,
                "user": {"uid": "user-1", "nickname": "评论者A"},
                "reply_comment": [],
            },
            {
                "cid": "comment-2",
                "text": "第二条评论",
                "digg_count": 1,
                "reply_comment_total": 0,
                "create_time": 1767690420,
                "user": {"uid": "user-2", "nickname": "评论者B"},
                "reply_comment": [],
            },
        ]
        comment_records = self.fetcher._build_comment_records(raw_comments, detail)

        payload = self.fetcher._build_analysis_input(
            aweme_id="7589926461256027430",
            source_url="https://www.douyin.com/video/7589926461256027430",
            detail=detail,
            comment_records=comment_records,
            scanned_comment_count=6,
            comment_selection_mode=CommentSelectionMode.comprehensive,
        )

        self.assertEqual(payload.video_id, "7589926461256027430")
        self.assertEqual(payload.comments, ["第一条评论", "第二条评论"])
        self.assertEqual(payload.ocr_text, ["第一行OCR", "第二行OCR"])
        self.assertEqual(payload.metadata["author_nickname"], "测试作者")
        self.assertEqual(payload.metadata["comment_count"], 12)
        self.assertEqual(payload.metadata["comment_count_scanned"], 6)
        self.assertEqual(payload.metadata["comment_count_selected"], 2)
        self.assertEqual(payload.metadata["comment_selection_mode"], "comprehensive")
        self.assertEqual(
            payload.metadata["comment_selection_strategy"],
            self.fetcher.COMMENT_SELECTION_STRATEGIES[CommentSelectionMode.comprehensive],
        )
        self.assertEqual(len(payload.comment_records), 2)
        self.assertTrue(payload.metadata["author_verified"])

    def test_select_important_comments_should_prefer_high_value_records(self):
        detail = {"author": {"uid": "author-1"}}
        comments = [
            {
                "cid": "comment-1",
                "text": "普通评论",
                "digg_count": 0,
                "reply_comment_total": 0,
                "user": {"uid": "user-1", "nickname": "普通用户"},
                "reply_comment": [],
            },
            {
                "cid": "comment-2",
                "text": "私信我加V看完整版",
                "digg_count": 35,
                "reply_comment_total": 4,
                "is_hot": True,
                "user": {"uid": "user-2", "nickname": "高互动用户"},
                "reply_comment": [],
            },
        ]
        records = self.fetcher._build_comment_records(comments, detail)

        selected = self.fetcher._select_important_comments(records, max_comments=1)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].comment_id, "comment-2")
        self.assertIn("drainage", selected[0].keyword_tags)

    def test_select_important_comments_recent_mode_should_prefer_latest_comment(self):
        detail = {"author": {"uid": "author-1"}}
        comments = [
            {
                "cid": "comment-1",
                "text": "older comment",
                "digg_count": 20,
                "reply_comment_total": 3,
                "create_time": 1767690300,
                "user": {"uid": "user-1", "nickname": "older"},
                "reply_comment": [],
            },
            {
                "cid": "comment-2",
                "text": "latest comment",
                "digg_count": 1,
                "reply_comment_total": 0,
                "create_time": 1767690900,
                "user": {"uid": "user-2", "nickname": "latest"},
                "reply_comment": [],
            },
        ]
        records = self.fetcher._build_comment_records(comments, detail)

        selected = self.fetcher._select_important_comments(
            records,
            max_comments=1,
            mode=CommentSelectionMode.recent,
        )

        self.assertEqual(selected[0].comment_id, "comment-2")

    def test_select_important_comments_risk_mode_should_prefer_keyword_rich_comment(self):
        detail = {"author": {"uid": "author-1"}}
        comments = [
            {
                "cid": "comment-1",
                "text": "normal discussion",
                "digg_count": 12,
                "reply_comment_total": 2,
                "create_time": 1767690500,
                "user": {"uid": "user-1", "nickname": "normal"},
                "reply_comment": [],
            },
            {
                "cid": "comment-2",
                "text": "私信我加V看完整版 官方证实 独家爆料",
                "digg_count": 2,
                "reply_comment_total": 0,
                "create_time": 1767690400,
                "user": {"uid": "user-2", "nickname": "risk"},
                "reply_comment": [],
            },
        ]
        records = self.fetcher._build_comment_records(comments, detail)

        selected = self.fetcher._select_important_comments(
            records,
            max_comments=1,
            mode=CommentSelectionMode.risk,
        )

        self.assertEqual(selected[0].comment_id, "comment-2")
        self.assertTrue(
            {"drainage", "fact_claim"}.intersection(set(selected[0].keyword_tags))
        )

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
