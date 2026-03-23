from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.registry import MODULE_REGISTRY
from app.models.schemas import AnalysisInput, UrlFetchRequest, UrlFetchResponse
from app.pipeline.orchestrator import AnalysisOrchestrator
from app.services.data_flow_trace import build_debug_trace
from app.services.douyin import DouyinFetchError, DouyinFetcher
from app.services.video_processing import VideoProcessingService

settings.ensure_dirs()
app = FastAPI(title=settings.app_name, version=settings.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

orchestrator = AnalysisOrchestrator()
douyin_fetcher = DouyinFetcher()
video_processor = VideoProcessingService()


@app.get("/")
def index():
    return FileResponse(settings.static_dir / "index.html")


@app.get("/debug/flow")
def debug_flow_page():
    return FileResponse(settings.static_dir / "trace.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "runtime": settings.runtime_summary(),
    }


@app.get("/api/v1/modules")
def list_modules():
    return MODULE_REGISTRY


def _fetch_and_enrich_url(payload: UrlFetchRequest) -> tuple[object, AnalysisInput]:
    whisper_model = (payload.whisper_model or settings.default_asr_model).strip()
    asr_model_path = payload.asr_model_path or settings.default_asr_model_path
    try:
        summary, input_payload, _ = douyin_fetcher.fetch_source(
            source_url=payload.source_url,
            max_comments=payload.max_comments,
            download_video=payload.download_video or payload.process_video,
            comment_selection_mode=payload.comment_selection_mode,
        )
    except DouyinFetchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"抓取抖音数据失败: {exc}") from exc

    if payload.process_video:
        enrichment = video_processor.enrich_payload(
            input_payload,
            summary.video_path,
            frame_interval_seconds=payload.frame_interval_seconds,
            max_frames=payload.max_frames,
            whisper_model=whisper_model,
            asr_model_path=asr_model_path,
        )
        input_payload = enrichment.payload
        summary.video_processing = enrichment.summary

    return summary, input_payload


@app.post("/api/v1/fetch/url")
def fetch_url(payload: UrlFetchRequest) -> UrlFetchResponse:
    summary, input_payload = _fetch_and_enrich_url(payload)
    return UrlFetchResponse(source=summary, input_payload=input_payload)


@app.post("/api/v1/debug/flow")
def debug_flow(payload: UrlFetchRequest):
    summary, input_payload = _fetch_and_enrich_url(payload)
    content = orchestrator.preprocessor.preprocess(
        input_payload,
        upload_path=summary.video_path,
    )
    return build_debug_trace(
        source=summary,
        payload=input_payload,
        content=content,
    )


@app.post("/api/v1/analyze")
def analyze(payload: AnalysisInput):
    return orchestrator.analyze(payload)
