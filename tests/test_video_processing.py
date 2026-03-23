from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.models.schemas import AnalysisInput, VideoFrameSample
from app.services.video_processing import VideoProcessingService, _AsrResult


class VideoProcessingServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VideoProcessingService()

    def test_build_sample_timestamps_should_respect_max_frames(self):
        timestamps = self.service._build_sample_timestamps(
            duration_seconds=42.0,
            frame_interval_seconds=4.0,
            max_frames=6,
        )
        self.assertEqual(len(timestamps), 6)
        self.assertGreater(timestamps[0], 0.0)
        self.assertLess(timestamps[-1], 42.0)
        self.assertEqual(timestamps, sorted(timestamps))

    def test_find_local_asr_model_should_accept_explicit_model_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / "tiny"
            model_dir.mkdir()
            for filename in ("model.bin", "config.json", "tokenizer.json"):
                (model_dir / filename).write_text("demo", encoding="utf-8")

            resolved = self.service._find_local_asr_model(str(model_dir), "tiny")

            self.assertEqual(resolved, model_dir.resolve())

    def test_detect_audio_events_should_flag_alarm_like_signal(self):
        sample_rate = 16000
        duration_seconds = 2.0
        timeline = np.linspace(
            0,
            duration_seconds,
            int(sample_rate * duration_seconds),
            endpoint=False,
        )
        signal = 0.14 * np.sin(2 * np.pi * 1800 * timeline)

        events = self.service._detect_audio_events(signal.astype(np.float32), sample_rate)

        self.assertTrue(any("警报" in item or "蜂鸣" in item for item in events))

    @patch.object(VideoProcessingService, "_run_asr")
    @patch.object(VideoProcessingService, "_run_ocr")
    @patch.object(VideoProcessingService, "_extract_frames")
    def test_enrich_payload_should_merge_auto_outputs(
        self,
        mock_extract_frames,
        mock_run_ocr,
        mock_run_asr,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(b"demo")

            mock_extract_frames.return_value = (
                [{"timestamp_seconds": 0.0, "path": str(video_path), "frame": object()}],
                {
                    "video_path": str(video_path),
                    "video_asset_url": "/uploads/sample.mp4",
                    "video_duration_seconds": 12.5,
                    "video_frame_count": 250,
                    "video_fps": 20.0,
                },
                [],
            )
            mock_run_ocr.return_value = (
                ["第一行OCR", "第二行OCR"],
                ["00:00.0 抽取关键帧，OCR识别：第一行OCR"],
                [
                    VideoFrameSample(
                        timestamp_seconds=0.0,
                        image_path=str(video_path),
                        image_url="/uploads/sample-frame.jpg",
                        ocr_text=["第一行OCR"],
                    )
                ],
            )
            mock_run_asr.return_value = _AsrResult(
                speech_text="这里是自动语音转写",
                audio_cues=["00:00.0-00:02.0 | 这里是自动语音转写"],
                asr_language="zh",
                segment_count=1,
                completed=True,
                backend="faster-whisper-local",
                speech_source="local_asr_model",
            )

            payload = AnalysisInput(
                video_id="demo-video",
                title="测试标题",
                metadata={"platform": "douyin"},
            )
            result = self.service.enrich_payload(
                payload,
                str(video_path),
                frame_interval_seconds=4.0,
                max_frames=6,
                whisper_model="tiny",
            )

        self.assertEqual(result.payload.speech_text, "这里是自动语音转写")
        self.assertIn("第一行OCR", result.payload.ocr_text)
        self.assertIn(
            "00:00.0 抽取关键帧，OCR识别：第一行OCR",
            result.payload.visual_descriptions,
        )
        self.assertIn("00:00.0-00:02.0 | 这里是自动语音转写", result.payload.audio_cues)
        self.assertTrue(result.summary.completed)
        self.assertTrue(result.summary.asr_completed)
        self.assertTrue(result.summary.ocr_completed)
        self.assertEqual(result.summary.extracted_frame_count, 1)
        self.assertEqual(result.summary.asr_backend, "faster-whisper-local")
        self.assertEqual(result.summary.speech_source, "local_asr_model")
        self.assertEqual(result.payload.metadata["video_processing"]["asr_language"], "zh")


if __name__ == "__main__":
    unittest.main()
