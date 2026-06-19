from __future__ import annotations

import os
from pathlib import Path


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


ROOT_DIR = Path(os.environ.get("KURAGEVP_ROOT", Path(__file__).resolve().parents[1]))
STORAGE_DIR = Path(os.environ.get("KURAGEVP_STORAGE", ROOT_DIR / "storage"))
JOBS_DIR = STORAGE_DIR / "jobs"
TMP_DIR = STORAGE_DIR / "tmp"
VOICE_PRO_DIR = Path(os.environ.get("VOICE_PRO_DIR", ROOT_DIR / "vendor" / "voice-pro"))

PORT = int(os.environ.get("KURAGEVP_PORT", "18302"))
DEFAULT_SOURCE_LANG = os.environ.get("KURAGEVP_SOURCE_LANG", "auto")
DEFAULT_TARGET_LANG = os.environ.get("KURAGEVP_TARGET_LANG", "ja")
DEFAULT_TTS_VOICE = os.environ.get("KURAGEVP_TTS_VOICE", "ja-JP-NanamiNeural")
DEFAULT_TTS_RATE = os.environ.get("KURAGEVP_TTS_RATE", "+22%")
TRANSLATED_AUDIO_VOLUME = max(0.1, min(env_float("KURAGEVP_TRANSLATED_AUDIO_VOLUME", 1.35), 3.0))


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# 吹替音量を「割れずに」一定の大きさへ底上げ (EBU R128 loudnorm)。
# I=-14 LUFS は YouTube のラウドネス基準。OFFにすると素のvolume倍率のみ。
TRANSLATED_AUDIO_LOUDNORM = env_bool("KURAGEVP_TRANSLATED_AUDIO_LOUDNORM", True)
TRANSLATED_AUDIO_LOUDNORM_I = env_float("KURAGEVP_TRANSLATED_AUDIO_LOUDNORM_I", -14.0)
TRANSLATED_AUDIO_LOUDNORM_TP = env_float("KURAGEVP_TRANSLATED_AUDIO_LOUDNORM_TP", -1.5)
TRANSLATED_AUDIO_LOUDNORM_LRA = env_float("KURAGEVP_TRANSLATED_AUDIO_LOUDNORM_LRA", 11.0)

# 翻訳エンジン: "claude" (翻訳→自己批正→自然化, 高品質) / "google" (deep-translator)。
# claude失敗時はgoogleへ自動フォールバック。
TRANSLATOR = os.environ.get("KURAGEVP_TRANSLATOR", "claude").strip().lower()
CLAUDE_MODEL = os.environ.get("KURAGEVP_CLAUDE_MODEL", "sonnet")
CLAUDE_BIN = os.environ.get("KURAGEVP_CLAUDE_BIN", "")
CLAUDE_TIMEOUT = env_int("KURAGEVP_CLAUDE_TIMEOUT", 240)
# 1回のClaude呼び出しに含める字幕行数 (整合性確保のためチャンク分割)。
CLAUDE_TRANSLATE_CHUNK = env_int("KURAGEVP_CLAUDE_TRANSLATE_CHUNK", 60)
WHISPER_MODEL = os.environ.get("KURAGEVP_WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("KURAGEVP_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get("KURAGEVP_WHISPER_COMPUTE_TYPE", "float16")
FFMPEG_BIN = os.environ.get("KURAGEVP_FFMPEG_BIN", "/usr/bin/ffmpeg")
SUBTITLE_STYLE = os.environ.get(
    "KURAGEVP_SUBTITLE_STYLE",
    "FontName=Noto Sans CJK JP,FontSize=34,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BackColour=&H70000000,BorderStyle=1,"
    "Bold=-1,Outline=4,Shadow=2,Alignment=2,MarginL=16,MarginR=16,MarginV=72",
)
SUBTITLE_FONT_SIZE = env_int("KURAGEVP_SUBTITLE_FONT_SIZE", 34)
SUBTITLE_MARGIN_L = env_int("KURAGEVP_SUBTITLE_MARGIN_L", 16)
SUBTITLE_MARGIN_R = env_int("KURAGEVP_SUBTITLE_MARGIN_R", 16)
SUBTITLE_MARGIN_V = env_int("KURAGEVP_SUBTITLE_MARGIN_V", 72)
SUBTITLE_CJK_LINE_CHARS = env_int("KURAGEVP_SUBTITLE_CJK_LINE_CHARS", 17)
SUBTITLE_CJK_MAX_CHARS = env_int("KURAGEVP_SUBTITLE_CJK_MAX_CHARS", 34)
SUBTITLE_LATIN_LINE_CHARS = env_int("KURAGEVP_SUBTITLE_LATIN_LINE_CHARS", 42)
SUBTITLE_LATIN_MAX_CHARS = env_int("KURAGEVP_SUBTITLE_LATIN_MAX_CHARS", 120)
SUBTITLE_MAX_LINES = env_int("KURAGEVP_SUBTITLE_MAX_LINES", 3)

KURAGE_JOBS_DIR = Path(os.environ.get("KURAGE_JOBS_DIR", "/home/kojima/work/kurage/storage/jobs"))
KURAGE_PUBLIC_BASE_URL = os.environ.get("KURAGE_PUBLIC_BASE_URL", "https://kurage.exbridge.jp").rstrip("/")

JOBS_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)
KURAGE_JOBS_DIR.mkdir(parents=True, exist_ok=True)
