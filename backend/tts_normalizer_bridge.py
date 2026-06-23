"""Bridge to Kurage shared TTS normalizer.

Kurage Voice Pro keeps subtitles unchanged, but normalizes only the text sent to
TTS so product names and AI/OSS terms are read consistently.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_NORMALIZER_DIR = Path(os.environ.get("KURAGE_TTS_NORMALIZER_DIR", "/home/kojima/work/kurage/backend"))
if _NORMALIZER_DIR.exists() and str(_NORMALIZER_DIR) not in sys.path:
    sys.path.insert(0, str(_NORMALIZER_DIR))

try:
    from tts_normalizer import normalize_tts_text as _kurage_normalize_tts_text
except Exception:  # pragma: no cover - production fallback for standalone installs
    _kurage_normalize_tts_text = None

_FALLBACK_REPLACEMENTS = {
    "Kurage": "クラゲ",
    "VWork": "ブイワーク",
    "kdeck": "ケーデック",
    "kvtuber": "ケーブイチューバー",
    "AIxSNS": "エーアイエックス エスエヌエス",
    "VOICEVOX": "ボイスボックス",
    "VTuber": "ブイチューバー",
    "YouTube": "ユーチューブ",
    "Live2D": "ライブツーディー",
    "VRM": "ブイアールエム",
    "LLM": "エルエルエム",
    "TTS": "ティーティーエス",
    "API": "エーピーアイ",
}


def normalize_tts_text(text: str) -> str:
    if _kurage_normalize_tts_text is not None:
        return _kurage_normalize_tts_text(text)
    normalized = text or ""
    for src, dst in sorted(_FALLBACK_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(src, dst)
    return normalized
