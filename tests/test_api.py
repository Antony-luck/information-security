from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import AnalysisInput, SourceFetchSummary


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_modules_endpoint_should_return_registry(self):
        response = self.client.get("/api/v1/modules")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["module_id"], "data_collection")
        self.assertEqual(data[-1]["module_id"], "comprehensive_decision")

    @patch("app.main.douyin_fetcher.fetch_source")
    def test_fetch_url_should_return_source_and_input_payload(self, mock_fetch_source):
        summary = SourceFetchSummary(
            platform="douyin",
            source_url="https://www.douyin.com/video/1234567890",
            aweme_id="1234567890",
            title="测试标题",
            author_nickname="测试作者",
            desc="测试描述",
            cover_url="https://example.com/cover.jpg",
            publish_time="2026-03-23T13:15:00+08:00",
            video_downloaded=False,
            video_path=None,
            video_play_url="https://example.com/video.mp4",
            comment_count_fetched=2,
            comment_total_reported=18,
        )
        payload = AnalysisInput(
            video_id="1234567890",
            title="测试标题",
            description="测试描述",
            comments=["第一条评论", "第二条评论"],
            ocr_text=["第一行OCR"],
            metadata={"platform": "douyin", "author_nickname": "测试作者"},
        )
        mock_fetch_source.return_value = (summary, payload, None)

        response = self.client.post(
            "/api/v1/fetch/url",
            json={
                "source_url": "https://www.douyin.com/video/1234567890",
                "max_comments": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"]["aweme_id"], "1234567890")
        self.assertEqual(data["source"]["author_nickname"], "测试作者")
        self.assertEqual(data["input_payload"]["comments"], ["第一条评论", "第二条评论"])
        self.assertEqual(data["input_payload"]["metadata"]["platform"], "douyin")
        mock_fetch_source.assert_called_once()


if __name__ == "__main__":
    unittest.main()
