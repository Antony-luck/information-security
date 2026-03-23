from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import subprocess
from typing import Any
import wave

import cv2
import imageio_ffmpeg
import numpy as np

from app.core.config import settings
from app.models.schemas import AnalysisInput, VideoFrameSample, VideoProcessingSummary


@dataclass
class VideoEnrichmentResult:
    payload: AnalysisInput
    summary: VideoProcessingSummary


@dataclass
class _AsrResult:
    speech_text: str = ""
    audio_cues: list[str] = field(default_factory=list)
    asr_language: str | None = None
    segment_count: int = 0
    completed: bool = False
    backend: str | None = None
    speech_source: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class _AudioAnalysisResult:
    audio_cues: list[str] = field(default_factory=list)
    event_count: int = 0
    backend: str | None = None
    audio_path: str | None = None
    audio_asset_url: str | None = None
    notes: list[str] = field(default_factory=list)


class VideoProcessingService:
    _ocr_engine = None
    _whisper_models: dict[str, Any] = {}

    def __init__(self) -> None:
        self.frame_root = settings.upload_dir / "processed" / "frames"
        self.audio_root = settings.upload_dir / "processed" / "audio"
        self.whisper_cache_dir = settings.cache_dir / "whisper"
        self.local_asr_root = settings.model_dir / "asr"
        self.frame_root.mkdir(parents=True, exist_ok=True)
        self.audio_root.mkdir(parents=True, exist_ok=True)
        self.whisper_cache_dir.mkdir(parents=True, exist_ok=True)
        self.local_asr_root.mkdir(parents=True, exist_ok=True)

    def enrich_payload(
        self,
        payload: AnalysisInput,
        video_path: str | None,
        *,
        frame_interval_seconds: float = 4.0,
        max_frames: int = 6,
        whisper_model: str = "tiny",
        asr_model_path: str | None = None,
    ) -> VideoEnrichmentResult:
        summary = VideoProcessingSummary(
            enabled=True,
            whisper_model=whisper_model,
            frame_interval_seconds=frame_interval_seconds,
            frame_strategy="center-window-sharpest + histogram-dedupe",
            audio_event_backend="signal-heuristic",
        )
        if not video_path:
            download_error = str(payload.metadata.get("video_download_error") or "").strip()
            if download_error:
                summary.notes.append(f"视频下载失败，跳过抽帧、OCR 和 ASR: {download_error}")
            else:
                summary.notes.append("未提供本地视频文件，跳过抽帧、OCR 和 ASR。")
            return VideoEnrichmentResult(payload=payload, summary=summary)

        video_file = Path(video_path)
        if not video_file.exists():
            summary.notes.append(f"本地视频文件不存在: {video_path}")
            return VideoEnrichmentResult(payload=payload, summary=summary)

        frame_dir = self.frame_root / payload.video_id
        frame_dir.mkdir(parents=True, exist_ok=True)
        audio_path = self.audio_root / f"{payload.video_id}.wav"

        frame_data, video_metadata, frame_notes = self._extract_frames(
            video_file,
            frame_dir,
            frame_interval_seconds=frame_interval_seconds,
            max_frames=max_frames,
        )
        summary.notes.extend(frame_notes)

        audio_analysis = self._prepare_audio_analysis(video_file, audio_path)
        summary.notes.extend(audio_analysis.notes)
        summary.audio_path = audio_analysis.audio_path
        summary.audio_asset_url = audio_analysis.audio_asset_url
        summary.audio_event_count = audio_analysis.event_count

        ocr_lines: list[str] = []
        visual_descriptions: list[str] = []
        frame_samples: list[VideoFrameSample] = []
        if frame_data:
            try:
                ocr_lines, visual_descriptions, frame_samples = self._run_ocr(frame_data)
                summary.ocr_completed = True
                summary.extracted_frame_count = len(frame_samples)
                summary.ocr_line_count = len(ocr_lines)
                summary.frames = frame_samples
            except Exception as exc:
                summary.notes.append(f"OCR 执行失败: {exc}")
        else:
            summary.notes.append("未成功抽取关键帧，OCR 跳过。")

        asr_result = self._run_asr(
            media_path=Path(audio_analysis.audio_path) if audio_analysis.audio_path else video_file,
            whisper_model=whisper_model,
            asr_model_path=asr_model_path,
        )
        summary.notes.extend(asr_result.notes)
        summary.asr_completed = asr_result.completed
        summary.asr_language = asr_result.asr_language
        summary.asr_segment_count = asr_result.segment_count
        summary.asr_backend = asr_result.backend
        summary.speech_source = asr_result.speech_source
        summary.completed = (
            summary.ocr_completed
            or summary.asr_completed
            or bool(audio_analysis.audio_cues)
            or bool(audio_analysis.audio_path)
        )

        updated_payload = self._copy_payload(payload)
        updated_payload.speech_text = self._merge_text(
            updated_payload.speech_text, asr_result.speech_text
        )
        if not asr_result.completed and not updated_payload.speech_text.strip():
            platform_caption = str(updated_payload.metadata.get("platform_caption") or "").strip()
            if platform_caption:
                updated_payload.speech_text = platform_caption
                summary.speech_source = "platform_caption"
                summary.notes.append("ASR 未完成，已使用平台 caption 文本兜底回填。")

        updated_payload.visual_descriptions = self._merge_lines(
            updated_payload.visual_descriptions,
            visual_descriptions,
        )
        updated_payload.audio_cues = self._merge_lines(
            updated_payload.audio_cues,
            [*audio_analysis.audio_cues, *asr_result.audio_cues],
        )
        updated_payload.ocr_text = self._merge_lines(updated_payload.ocr_text, ocr_lines)
        summary.speech_text_length = len(updated_payload.speech_text)

        updated_payload.metadata = {
            **updated_payload.metadata,
            **video_metadata,
            "video_processing": {
                "completed": summary.completed,
                "asr_completed": summary.asr_completed,
                "ocr_completed": summary.ocr_completed,
                "frame_interval_seconds": frame_interval_seconds,
                "frame_strategy": summary.frame_strategy,
                "extracted_frame_count": summary.extracted_frame_count,
                "ocr_line_count": summary.ocr_line_count,
                "speech_text_length": summary.speech_text_length,
                "asr_segment_count": summary.asr_segment_count,
                "asr_language": summary.asr_language,
                "asr_backend": summary.asr_backend,
                "speech_source": summary.speech_source,
                "audio_event_backend": summary.audio_event_backend,
                "audio_event_count": summary.audio_event_count,
                "whisper_model": whisper_model,
                "audio_path": summary.audio_path,
                "audio_asset_url": summary.audio_asset_url,
                "frame_urls": [
                    sample.image_url for sample in frame_samples if sample.image_url
                ],
                "notes": summary.notes,
            },
        }

        return VideoEnrichmentResult(payload=updated_payload, summary=summary)

    def _extract_frames(
        self,
        video_path: Path,
        frame_dir: Path,
        *,
        frame_interval_seconds: float,
        max_frames: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        notes: list[str] = []
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return [], {}, [f"无法打开视频文件: {video_path}"]

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_seconds = frame_count / fps if fps and frame_count else 0.0
        timestamps = self._build_sample_timestamps(
            duration_seconds=duration_seconds,
            frame_interval_seconds=frame_interval_seconds,
            max_frames=max_frames,
        )

        frames: list[dict[str, Any]] = []
        selected_hists: list[np.ndarray] = []
        search_radius = min(max(frame_interval_seconds / 2.0, 0.5), 2.0)
        candidate_offsets = self._build_candidate_offsets(search_radius)

        for index, timestamp in enumerate(timestamps, start=1):
            candidates: list[dict[str, Any]] = []
            for offset in candidate_offsets:
                target = self._clamp_timestamp(timestamp + offset, duration_seconds)
                frame = self._read_frame(capture, target)
                if frame is None:
                    continue
                quality = self._frame_quality(frame)
                hist = self._frame_histogram(frame)
                candidates.append(
                    {
                        "timestamp_seconds": target,
                        "frame": frame,
                        "quality": quality,
                        "hist": hist,
                    }
                )

            if not candidates:
                notes.append(f"{self._format_timestamp(timestamp)} 关键帧抽取失败。")
                continue

            candidates.sort(key=lambda item: item["quality"], reverse=True)
            selected = candidates[0]
            for candidate in candidates:
                if self._is_distinct_frame(candidate["hist"], selected_hists):
                    selected = candidate
                    break

            if selected["timestamp_seconds"] != timestamp:
                notes.append(
                    f"{self._format_timestamp(timestamp)} 已自动偏移到 "
                    f"{self._format_timestamp(selected['timestamp_seconds'])} 以避开模糊/重复帧。"
                )

            frame_path = frame_dir / (
                f"frame-{index:02d}-{int(selected['timestamp_seconds'] * 1000):06d}ms.jpg"
            )
            cv2.imwrite(str(frame_path), selected["frame"])
            selected_hists.append(selected["hist"])
            frames.append(
                {
                    "timestamp_seconds": selected["timestamp_seconds"],
                    "path": str(frame_path),
                    "frame": selected["frame"],
                    "quality": round(float(selected["quality"]), 3),
                }
            )

        capture.release()
        metadata = {
            "video_path": str(video_path),
            "video_asset_url": settings.upload_asset_url(video_path),
            "video_duration_seconds": round(duration_seconds, 3),
            "video_frame_count": frame_count,
            "video_fps": round(fps, 3) if fps else 0.0,
            "frame_strategy": "center-window-sharpest + histogram-dedupe",
        }
        return frames, metadata, notes

    def _prepare_audio_analysis(
        self, video_path: Path, audio_path: Path
    ) -> _AudioAnalysisResult:
        extracted_path, notes = self._extract_audio_track(video_path, audio_path)
        if not extracted_path:
            return _AudioAnalysisResult(
                backend="signal-heuristic",
                notes=notes or ["音频抽取失败，跳过音频事件识别。"],
            )

        try:
            signal, sample_rate = self._load_wav_signal(extracted_path)
            cues = self._detect_audio_events(signal, sample_rate)
            return _AudioAnalysisResult(
                audio_cues=cues,
                event_count=len(cues),
                backend="signal-heuristic",
                audio_path=str(extracted_path),
                audio_asset_url=settings.upload_asset_url(extracted_path),
                notes=notes,
            )
        except Exception as exc:
            return _AudioAnalysisResult(
                backend="signal-heuristic",
                audio_path=str(extracted_path),
                audio_asset_url=settings.upload_asset_url(extracted_path),
                notes=[*notes, f"音频事件识别失败: {exc}"],
            )

    def _run_ocr(
        self, frame_data: list[dict[str, Any]]
    ) -> tuple[list[str], list[str], list[VideoFrameSample]]:
        ocr_engine = self._get_ocr_engine()
        ocr_lines: list[str] = []
        visual_descriptions: list[str] = []
        frame_samples: list[VideoFrameSample] = []

        for item in frame_data:
            result, _ = ocr_engine(item["frame"])
            texts = self._extract_ocr_texts(result)
            ocr_lines.extend(texts)
            timestamp = float(item["timestamp_seconds"])
            if texts:
                visual_descriptions.append(
                    f"{self._format_timestamp(timestamp)} 抽取关键帧，OCR识别：{'；'.join(texts[:3])}"
                )
            else:
                visual_descriptions.append(
                    f"{self._format_timestamp(timestamp)} 抽取关键帧，未识别到明显文字。"
                )
            frame_samples.append(
                VideoFrameSample(
                    timestamp_seconds=timestamp,
                    image_path=str(item["path"]),
                    image_url=settings.upload_asset_url(item["path"]),
                    ocr_text=texts,
                )
            )

        return (
            self._merge_lines([], ocr_lines),
            visual_descriptions,
            frame_samples,
        )

    def _run_asr(
        self,
        *,
        media_path: Path,
        whisper_model: str,
        asr_model_path: str | None = None,
    ) -> _AsrResult:
        resolved_model, backend, local_only, resolve_notes = self._resolve_asr_model(
            whisper_model=whisper_model,
            asr_model_path=asr_model_path,
        )
        if not resolved_model:
            return _AsrResult(
                backend=backend,
                speech_source="none",
                notes=resolve_notes,
            )

        try:
            whisper = self._get_whisper_model(
                resolved_model,
                backend=backend,
                local_only=local_only,
            )
        except Exception as exc:
            return _AsrResult(
                backend=backend,
                speech_source="none",
                notes=[*resolve_notes, f"ASR 模型加载失败: {exc}"],
            )

        try:
            segments, info = whisper.transcribe(
                str(media_path),
                beam_size=3,
                language="zh",
                vad_filter=True,
                condition_on_previous_text=False,
            )
            segment_texts: list[str] = []
            audio_cues: list[str] = []
            segment_count = 0
            for segment in segments:
                text = " ".join((segment.text or "").split()).strip()
                if not text:
                    continue
                segment_count += 1
                segment_texts.append(text)
                audio_cues.append(
                    f"{self._format_timestamp(segment.start)}-{self._format_timestamp(segment.end)} | 语音片段：{text}"
                )
            return _AsrResult(
                speech_text="\n".join(segment_texts),
                audio_cues=audio_cues[:12],
                asr_language=getattr(info, "language", None),
                segment_count=segment_count,
                completed=bool(segment_texts),
                backend=backend,
                speech_source="local_asr_model" if local_only else "online_whisper_model",
                notes=resolve_notes if segment_texts else [*resolve_notes, "ASR 未识别到有效语音文本。"],
            )
        except Exception as exc:
            return _AsrResult(
                backend=backend,
                speech_source="none",
                notes=[*resolve_notes, f"ASR 转写失败: {exc}"],
            )

    def _resolve_asr_model(
        self,
        *,
        whisper_model: str,
        asr_model_path: str | None,
    ) -> tuple[str | Path | None, str, bool, list[str]]:
        notes: list[str] = []

        if asr_model_path:
            resolved = self._find_local_asr_model(asr_model_path, whisper_model)
            if resolved:
                return resolved, "faster-whisper-local", True, [
                    f"已使用指定的离线 ASR 模型目录: {resolved}"
                ]
            return None, "faster-whisper-local", True, [
                f"指定的离线 ASR 模型目录不可用: {asr_model_path}"
            ]

        resolved = self._find_local_asr_model(whisper_model, whisper_model)
        if resolved:
            return resolved, "faster-whisper-local", True, [
                f"已命中本地离线 ASR 模型目录: {resolved}"
            ]

        offline_only = os.getenv("VIDEO_ASR_OFFLINE_ONLY", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if offline_only:
            return None, "faster-whisper-local", True, [
                "当前启用了离线 ASR 限制，但未找到可用的本地模型目录。"
            ]

        notes.append("未发现本地离线 ASR 模型目录，尝试在线加载 Whisper 模型。")
        return whisper_model, "faster-whisper-remote", False, notes

    def _find_local_asr_model(
        self, path_or_name: str | None, whisper_model: str
    ) -> Path | None:
        if not path_or_name:
            return None

        raw = Path(path_or_name)
        candidate_paths: list[Path] = []
        if raw.is_absolute() or path_or_name.startswith(".") or "/" in path_or_name or "\\" in path_or_name:
            candidate_paths.append(raw)

        env_root = os.getenv("VIDEO_ASR_MODEL_DIR", "").strip()
        roots = [
            Path(env_root) if env_root else None,
            self.local_asr_root,
            settings.cache_dir / "whisper",
        ]
        for root in roots:
            if not root:
                continue
            candidate_paths.append(root / path_or_name)
            if whisper_model and path_or_name != whisper_model:
                candidate_paths.append(root / whisper_model)

        for candidate in candidate_paths:
            resolved = candidate.expanduser().resolve()
            if self._is_local_whisper_model_dir(resolved):
                return resolved
        return None

    def _get_ocr_engine(self):
        if self.__class__._ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self.__class__._ocr_engine = RapidOCR()
        return self.__class__._ocr_engine

    def _get_whisper_model(
        self,
        resolved_model: str | Path,
        *,
        backend: str,
        local_only: bool,
    ):
        cache_key = f"{backend}:{resolved_model}"
        if cache_key not in self.__class__._whisper_models:
            from faster_whisper import WhisperModel

            if not local_only:
                self._disable_proxy_env()
            self.__class__._whisper_models[cache_key] = WhisperModel(
                str(resolved_model),
                device="cpu",
                compute_type="int8",
                download_root=str(self.whisper_cache_dir),
                local_files_only=local_only,
            )
        return self.__class__._whisper_models[cache_key]

    def _extract_audio_track(
        self, video_path: Path, audio_path: Path
    ) -> tuple[Path | None, list[str]]:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-loglevel",
            "error",
            str(audio_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not audio_path.exists():
            detail = (completed.stderr or completed.stdout or "").strip()
            return None, [f"音频抽取失败: {detail or 'ffmpeg 未生成输出文件。'}"]
        return audio_path, []

    def _load_wav_signal(self, audio_path: Path) -> tuple[np.ndarray, int]:
        with wave.open(str(audio_path), "rb") as audio_file:
            sample_rate = int(audio_file.getframerate())
            sample_width = int(audio_file.getsampwidth())
            channels = int(audio_file.getnchannels())
            raw = audio_file.readframes(audio_file.getnframes())

        if sample_width == 2:
            signal = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            signal = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"不支持的音频采样宽度: {sample_width}")

        if channels > 1:
            signal = signal.reshape(-1, channels).mean(axis=1)
        return signal, sample_rate

    def _detect_audio_events(self, signal: np.ndarray, sample_rate: int) -> list[str]:
        if signal.size == 0 or sample_rate <= 0:
            return []

        window_size = max(int(sample_rate * 0.75), 1)
        hop_size = max(int(sample_rate * 0.5), 1)
        detected: list[dict[str, Any]] = []

        for start in range(0, max(signal.size - window_size + 1, 1), hop_size):
            window = signal[start : start + window_size]
            if window.size < window_size // 2:
                continue

            features = self._compute_audio_features(window, sample_rate)
            label = self._classify_audio_event(features)
            if not label:
                continue
            detected.append(
                {
                    "label": label,
                    "start": start / sample_rate,
                    "end": min((start + window.size) / sample_rate, signal.size / sample_rate),
                    "score": round(float(features["rms"]), 3),
                }
            )

        merged = self._merge_audio_events(detected)
        return [
            f"{self._format_timestamp(item['start'])}-{self._format_timestamp(item['end'])} | {item['label']}"
            for item in merged[:8]
        ]

    def _compute_audio_features(
        self, window: np.ndarray, sample_rate: int
    ) -> dict[str, float]:
        eps = 1e-8
        spectrum = np.abs(np.fft.rfft(window))
        freqs = np.fft.rfftfreq(window.size, d=1.0 / sample_rate)
        power = spectrum**2 + eps

        rms = float(np.sqrt(np.mean(window**2) + eps))
        peak = float(np.max(np.abs(window)))
        zcr = float(np.mean(np.abs(np.diff(np.signbit(window)).astype(np.float32))))
        centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + eps))
        dominant_freq = float(freqs[int(np.argmax(spectrum))]) if spectrum.size else 0.0

        low_mask = freqs < 250
        high_mask = freqs >= 1800
        low_ratio = float(np.sum(power[low_mask]) / np.sum(power))
        high_ratio = float(np.sum(power[high_mask]) / np.sum(power))
        flatness = float(np.exp(np.mean(np.log(power))) / np.mean(power))

        return {
            "rms": rms,
            "peak": peak,
            "zcr": zcr,
            "centroid": centroid,
            "dominant_freq": dominant_freq,
            "low_ratio": low_ratio,
            "high_ratio": high_ratio,
            "flatness": flatness,
        }

    def _classify_audio_event(self, features: dict[str, float]) -> str | None:
        if features["peak"] >= 0.82 and features["low_ratio"] >= 0.28:
            return "疑似爆炸/冲击高能音"
        if (
            features["rms"] >= 0.06
            and features["high_ratio"] >= 0.35
            and 700 <= features["dominant_freq"] <= 3500
            and features["flatness"] <= 0.35
        ):
            return "疑似警报/蜂鸣"
        if (
            features["rms"] >= 0.05
            and features["zcr"] >= 0.18
            and features["centroid"] >= 1600
            and features["flatness"] >= 0.32
        ):
            return "疑似尖叫/高频喊叫"
        return None

    def _merge_audio_events(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for item in items:
            if (
                merged
                and merged[-1]["label"] == item["label"]
                and item["start"] - merged[-1]["end"] <= 0.35
            ):
                merged[-1]["end"] = item["end"]
                continue
            merged.append(dict(item))
        return merged

    def _build_sample_timestamps(
        self,
        *,
        duration_seconds: float,
        frame_interval_seconds: float,
        max_frames: int,
    ) -> list[float]:
        if duration_seconds <= 0:
            return [0.0]

        if duration_seconds <= frame_interval_seconds * max_frames:
            bucket_count = max(1, min(max_frames, math.ceil(duration_seconds / frame_interval_seconds)))
            timestamps = []
            for index in range(bucket_count):
                start = index * frame_interval_seconds
                end = min(duration_seconds, start + frame_interval_seconds)
                timestamps.append(round((start + end) / 2.0, 3))
            return timestamps

        bucket_size = duration_seconds / max_frames
        return [
            round((index * bucket_size) + bucket_size / 2.0, 3)
            for index in range(max_frames)
        ]

    def _build_candidate_offsets(self, search_radius: float) -> list[float]:
        offsets = [0.0]
        step = 0.5
        current = step
        while current <= search_radius + 1e-6:
            offsets.extend([-current, current])
            current += step
        return offsets

    def _read_frame(self, capture: cv2.VideoCapture, timestamp_seconds: float):
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp_seconds * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        return frame

    def _frame_quality(self, frame: np.ndarray) -> float:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(np.mean(gray))
        exposure_penalty = 1.0 - min(abs(brightness - 127.5) / 127.5, 1.0) * 0.4
        return sharpness * exposure_penalty

    def _frame_histogram(self, frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist

    def _is_distinct_frame(
        self, hist: np.ndarray, selected_hists: list[np.ndarray]
    ) -> bool:
        if not selected_hists:
            return True
        correlations = [
            cv2.compareHist(hist, previous, cv2.HISTCMP_CORREL)
            for previous in selected_hists
        ]
        return max(correlations, default=0.0) < 0.985

    def _clamp_timestamp(self, value: float, duration_seconds: float) -> float:
        if duration_seconds <= 0:
            return 0.0
        return max(0.0, min(value, max(duration_seconds - 0.05, 0.0)))

    def _extract_ocr_texts(self, result: list | None) -> list[str]:
        lines: list[str] = []
        for item in result or []:
            if len(item) < 3:
                continue
            text = str(item[1] or "").strip()
            score = float(item[2] or 0.0)
            if text and score >= 0.5:
                lines.append(text)
        return self._merge_lines([], lines)

    def _is_local_whisper_model_dir(self, path: Path) -> bool:
        if not path.exists() or not path.is_dir():
            return False
        existing = {item.name for item in path.iterdir() if item.is_file()}
        has_config = "config.json" in existing
        has_weights = "model.bin" in existing
        has_tokenizer = bool(
            {"tokenizer.json", "tokenizer_config.json", "vocabulary.json", "vocabulary.txt"}
            & existing
        )
        return has_config and has_weights and has_tokenizer

    def _merge_text(self, existing: str, addition: str) -> str:
        existing = (existing or "").strip()
        addition = (addition or "").strip()
        if not existing:
            return addition
        if not addition:
            return existing
        if addition in existing:
            return existing
        return f"{existing}\n{addition}"

    def _merge_lines(self, existing: list[str], addition: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in [*(existing or []), *(addition or [])]:
            cleaned = " ".join(str(item or "").split()).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    def _format_timestamp(self, value: float) -> str:
        total_seconds = max(float(value), 0.0)
        minutes = int(total_seconds // 60)
        seconds = total_seconds - minutes * 60
        return f"{minutes:02d}:{seconds:04.1f}"

    def _disable_proxy_env(self) -> None:
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ[key] = ""
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"

    def _copy_payload(self, payload: AnalysisInput) -> AnalysisInput:
        model_copy = getattr(payload, "model_copy", None)
        if callable(model_copy):
            return model_copy(deep=True)
        return payload.copy(deep=True)
