from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_HF_REPO = "Systran/faster-whisper-tiny"
DEFAULT_TARGET_DIR = ROOT_DIR / "models" / "asr" / "tiny"


def slugify_repo_id(repo_id: str) -> str:
    return repo_id.strip().rstrip("/").split("/")[-1].replace(":", "-")


def default_target_dir_for_repo(repo_id: str) -> Path:
    repo_name = slugify_repo_id(repo_id)
    if repo_name.startswith("faster-whisper-"):
        repo_name = repo_name.removeprefix("faster-whisper-")
    return ROOT_DIR / "models" / "asr" / repo_name


def is_faster_whisper_dir(path: Path) -> bool:
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


def ensure_empty_target(target_dir: Path, force: bool) -> None:
    if not target_dir.exists():
        return
    if is_faster_whisper_dir(target_dir):
        return
    if force:
        shutil.rmtree(target_dir)
        return
    raise SystemExit(
        "目标目录已存在，但不是有效的 faster-whisper 模型目录。"
        f"请先清理或使用 --force: {target_dir}"
    )


def clear_proxy_env() -> None:
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


def cleanup_download_metadata(target_dir: Path) -> None:
    for folder_name in (".cache", ".huggingface"):
        candidate = target_dir / folder_name
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)


def download_from_huggingface(repo_id: str, target_dir: Path, cache_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        cache_dir=str(cache_dir),
    )
    cleanup_download_metadata(target_dir)
    return target_dir


def download_from_modelscope(repo_id: str, target_dir: Path, cache_dir: Path) -> Path:
    try:
        from modelscope import snapshot_download
    except ImportError:
        try:
            from modelscope.hub.snapshot_download import snapshot_download
        except ImportError as exc:
            raise SystemExit(
                "使用 ModelScope 下载前，请先安装 modelscope：\n"
                r".\.venv\Scripts\python.exe -m pip install modelscope"
            ) from exc

    downloaded_dir = Path(snapshot_download(model_id=repo_id, cache_dir=str(cache_dir)))
    if target_dir.exists() and target_dir.resolve() != downloaded_dir.resolve():
        shutil.rmtree(target_dir)
    if downloaded_dir.resolve() != target_dir.resolve():
        shutil.copytree(downloaded_dir, target_dir, dirs_exist_ok=True)
    cleanup_download_metadata(target_dir)
    return target_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="下载或准备离线 faster-whisper ASR 模型目录。"
    )
    parser.add_argument(
        "--provider",
        choices=("huggingface", "modelscope"),
        default="huggingface",
        help="模型下载源，默认 huggingface。",
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_HF_REPO,
        help="模型仓库 ID。默认 Systran/faster-whisper-tiny。",
    )
    parser.add_argument(
        "--target-dir",
        default="",
        help="目标目录。默认下载到 models/asr/<size>，例如 models/asr/tiny。",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(ROOT_DIR / "data" / "cache" / "model-downloads"),
        help="下载缓存目录。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="若目标目录存在且不是有效模型目录，则强制覆盖。",
    )
    return parser


def resolve_target_dir(repo_id: str, target_dir_arg: str) -> Path:
    if target_dir_arg:
        target_dir = Path(target_dir_arg).expanduser()
        if not target_dir.is_absolute():
            target_dir = (ROOT_DIR / target_dir).resolve()
        return target_dir

    if repo_id == DEFAULT_HF_REPO:
        return DEFAULT_TARGET_DIR
    return default_target_dir_for_repo(repo_id)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_id = args.repo_id.strip()
    if not repo_id:
        raise SystemExit("repo-id 不能为空。")

    cache_dir = Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    clear_proxy_env()

    target_dir = resolve_target_dir(repo_id, args.target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    ensure_empty_target(target_dir, force=args.force)
    if is_faster_whisper_dir(target_dir):
        print(f"[skip] 已存在可用模型目录: {target_dir}")
        print(f"[hint] 页面中可直接填写: {target_dir}")
        return 0

    try:
        if args.provider == "huggingface":
            download_from_huggingface(repo_id, target_dir, cache_dir)
        else:
            download_from_modelscope(repo_id, target_dir, cache_dir)
    except Exception as exc:
        if args.provider == "huggingface":
            raise SystemExit(
                "从 Hugging Face 下载失败。\n"
                "如果当前网络无法直连，请改用 --provider modelscope，"
                "或手动将 faster-whisper 模型目录放到 models/asr 下。\n"
                f"原始错误: {exc}"
            ) from exc
        raise SystemExit(
            "从 ModelScope 下载失败，请检查模型 ID 是否正确，"
            "并确认当前环境可以访问 ModelScope。\n"
            f"原始错误: {exc}"
        ) from exc

    if not is_faster_whisper_dir(target_dir):
        raise SystemExit(
            "下载完成，但目标目录不是有效的 faster-whisper 模型目录。\n"
            "请确认仓库内容是 CTranslate2 / faster-whisper 格式。"
        )

    print(f"[ok] 离线 ASR 模型已准备完成: {target_dir}")
    print("[next] 你可以在页面输入框或 .env 中配置这个目录。")
    print(
        "[next] 推荐配置：\n"
        f"VIDEO_ASR_MODEL_DIR=models/asr\n"
        f"VIDEO_ASR_MODEL_NAME={target_dir.name}\n"
        f"# 或显式指定\n"
        f"VIDEO_ASR_MODEL_PATH={target_dir.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
