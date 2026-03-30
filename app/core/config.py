from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(base_dir: Path) -> None:
    env_file = base_dir / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parents[2]
        _load_dotenv(self.base_dir)

        self.app_name = os.getenv(
            "APP_NAME",
            "面向短视频多模态融合的内容安全智能研判系统",
        )
        self.version = os.getenv("APP_VERSION", "0.1.0")
        self.model_dir = self._resolve_dir("MODEL_DIR", self.base_dir / "models")
        self.upload_dir = self._resolve_dir(
            "UPLOAD_DIR", self.base_dir / "data" / "uploads"
        )
        self.cache_dir = self._resolve_dir(
            "CACHE_DIR", self.base_dir / "data" / "cache"
        )
        self.static_dir = self._resolve_dir(
            "STATIC_DIR", self.base_dir / "app" / "static"
        )

        self.default_asr_model = os.getenv("VIDEO_ASR_MODEL_NAME", "tiny").strip() or "tiny"
        self.default_asr_model_path = os.getenv("VIDEO_ASR_MODEL_PATH", "").strip() or None
        self.asr_model_dir = self._resolve_dir(
            "VIDEO_ASR_MODEL_DIR", self.model_dir / "asr"
        )
        self.asr_offline_only = _to_bool(
            os.getenv("VIDEO_ASR_OFFLINE_ONLY"), default=False
        )

        self.llm_provider = os.getenv("LLM_PROVIDER", "").strip()
        self.llm_base_url = os.getenv("LLM_BASE_URL", "").strip()
        self.llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_model = os.getenv("LLM_MODEL", "").strip()
        self.llm_api_path = os.getenv("LLM_API_PATH", "/chat/completions").strip()
        self.llm_timeout_seconds = float(
            os.getenv("LLM_TIMEOUT_SECONDS", "60").strip() or "60"
        )

        self.fact_check_search_enabled = _to_bool(
            os.getenv("FACT_CHECK_SEARCH_ENABLED"), default=False
        )
        self.fact_check_max_queries = int(
            os.getenv("FACT_CHECK_MAX_QUERIES", "3").strip() or "3"
        )
        self.fact_check_timeout_seconds = float(
            os.getenv("FACT_CHECK_TIMEOUT_SECONDS", "10").strip() or "10"
        )

    def _resolve_dir(self, env_name: str, default: Path) -> Path:
        raw_value = os.getenv(env_name, "").strip()
        if not raw_value:
            return default
        candidate = Path(raw_value).expanduser()
        if not candidate.is_absolute():
            candidate = self.base_dir / candidate
        return candidate

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_provider and self.llm_model and self.llm_api_key)

    def ensure_dirs(self) -> None:
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.asr_model_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def upload_asset_url(self, path: str | Path | None) -> str | None:
        if not path:
            return None
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(self.upload_dir.resolve())
        except ValueError:
            return None
        return f"/uploads/{relative.as_posix()}"

    def runtime_summary(self) -> dict[str, object]:
        return {
            "default_asr_model": self.default_asr_model,
            "default_asr_model_path": self.default_asr_model_path,
            "asr_model_dir": str(self.asr_model_dir),
            "asr_offline_only": self.asr_offline_only,
            "llm_provider": self.llm_provider or "unset",
            "llm_model": self.llm_model or "unset",
            "llm_ready": self.llm_ready,
            "llm_api_path": self.llm_api_path,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "fact_check_search_enabled": self.fact_check_search_enabled,
            "fact_check_max_queries": self.fact_check_max_queries,
            "fact_check_timeout_seconds": self.fact_check_timeout_seconds,
        }


settings = Settings()
