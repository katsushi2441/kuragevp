from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(os.environ.get("KURAGEVP_ROOT", Path(__file__).resolve().parents[1]))
STORAGE_DIR = Path(os.environ.get("KURAGEVP_STORAGE", ROOT_DIR / "storage"))
JOBS_DIR = STORAGE_DIR / "jobs"
TMP_DIR = STORAGE_DIR / "tmp"
VOICE_PRO_DIR = Path(os.environ.get("VOICE_PRO_DIR", ROOT_DIR / "vendor" / "voice-pro"))

PORT = int(os.environ.get("KURAGEVP_PORT", "18302"))
DEFAULT_SOURCE_LANG = os.environ.get("KURAGEVP_SOURCE_LANG", "auto")
DEFAULT_TARGET_LANG = os.environ.get("KURAGEVP_TARGET_LANG", "ja")
DEFAULT_TTS_VOICE = os.environ.get("KURAGEVP_TTS_VOICE", "ja-JP-NanamiNeural")
WHISPER_MODEL = os.environ.get("KURAGEVP_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("KURAGEVP_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("KURAGEVP_WHISPER_COMPUTE_TYPE", "float16")
FFMPEG_BIN = os.environ.get("KURAGEVP_FFMPEG_BIN", "/usr/bin/ffmpeg")

KURAGE_JOBS_DIR = Path(os.environ.get("KURAGE_JOBS_DIR", "/home/kojima/work/kurage/storage/jobs"))
KURAGE_PUBLIC_BASE_URL = os.environ.get("KURAGE_PUBLIC_BASE_URL", "https://kurage.exbridge.jp").rstrip("/")

JOBS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)
KURAGE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
