param(
    [switch]$DownloadAsrModel,
    [string]$AsrProvider = "huggingface",
    [string]$AsrRepoId = "Systran/faster-whisper-tiny"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if ($DownloadAsrModel) {
    & ".\.venv\Scripts\python.exe" ".\scripts\download_asr_model.py" `
        --provider $AsrProvider `
        --repo-id $AsrRepoId
}

& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
