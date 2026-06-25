from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import traceback
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

try:
    from .config import (
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        DEFAULT_TTS_RATE,
        DEFAULT_TTS_VOICE,
        FFMPEG_BIN,
        JOBS_DIR,
        KURAGE_JOBS_DIR,
        KURAGE_PUBLIC_BASE_URL,
        SUBTITLE_CJK_LINE_CHARS,
        SUBTITLE_CJK_MAX_CHARS,
        SUBTITLE_FONT_SIZE,
        SUBTITLE_LATIN_LINE_CHARS,
        SUBTITLE_LATIN_MAX_CHARS,
        SUBTITLE_MARGIN_L,
        SUBTITLE_MARGIN_R,
        SUBTITLE_MARGIN_V,
        SUBTITLE_MAX_LINES,
        SUBTITLE_SHIFT_RIGHT_CHARS,
        SUBTITLE_SHIFT_UP_LINES,
        TMP_DIR,
        DEFAULT_VTUBER_MODE,
        TRANSLATED_AUDIO_VOLUME,
        TRANSLATED_AUDIO_LOUDNORM,
        TRANSLATED_AUDIO_LOUDNORM_I,
        TRANSLATED_AUDIO_LOUDNORM_TP,
        TRANSLATED_AUDIO_LOUDNORM_LRA,
        VTUBER_AVATAR_IDLE,
        VTUBER_AVATAR_MARGIN_X,
        VTUBER_AVATAR_MARGIN_Y,
        VTUBER_AVATAR_SHIFT_RIGHT_CHARS,
        VTUBER_AVATAR_TALK,
        VTUBER_AVATAR_WIDTH,
        VTUBER_SUBTITLE_CJK_LINE_CHARS,
        VTUBER_SUBTITLE_LATIN_LINE_CHARS,
        VTUBER_SUBTITLE_MARGIN_L,
        VTUBER_SUBTITLE_MARGIN_R,
        TRANSLATOR,
        CLAUDE_MODEL,
        CLAUDE_BIN,
        CLAUDE_TIMEOUT,
        CLAUDE_TRANSLATE_CHUNK,
        VOICE_PRO_DIR,
        WHISPER_COMPUTE_TYPE,
        WHISPER_DEVICE,
        WHISPER_MODEL,
    )
    from .tts_normalizer_bridge import normalize_tts_text
except ImportError:
    from config import (
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        DEFAULT_TTS_RATE,
        DEFAULT_TTS_VOICE,
        FFMPEG_BIN,
        JOBS_DIR,
        KURAGE_JOBS_DIR,
        KURAGE_PUBLIC_BASE_URL,
        SUBTITLE_CJK_LINE_CHARS,
        SUBTITLE_CJK_MAX_CHARS,
        SUBTITLE_FONT_SIZE,
        SUBTITLE_LATIN_LINE_CHARS,
        SUBTITLE_LATIN_MAX_CHARS,
        SUBTITLE_MARGIN_L,
        SUBTITLE_MARGIN_R,
        SUBTITLE_MARGIN_V,
        SUBTITLE_MAX_LINES,
        SUBTITLE_SHIFT_RIGHT_CHARS,
        SUBTITLE_SHIFT_UP_LINES,
        TMP_DIR,
        DEFAULT_VTUBER_MODE,
        TRANSLATED_AUDIO_VOLUME,
        TRANSLATED_AUDIO_LOUDNORM,
        TRANSLATED_AUDIO_LOUDNORM_I,
        TRANSLATED_AUDIO_LOUDNORM_TP,
        TRANSLATED_AUDIO_LOUDNORM_LRA,
        VTUBER_AVATAR_IDLE,
        VTUBER_AVATAR_MARGIN_X,
        VTUBER_AVATAR_MARGIN_Y,
        VTUBER_AVATAR_SHIFT_RIGHT_CHARS,
        VTUBER_AVATAR_TALK,
        VTUBER_AVATAR_WIDTH,
        VTUBER_SUBTITLE_CJK_LINE_CHARS,
        VTUBER_SUBTITLE_LATIN_LINE_CHARS,
        VTUBER_SUBTITLE_MARGIN_L,
        VTUBER_SUBTITLE_MARGIN_R,
        TRANSLATOR,
        CLAUDE_MODEL,
        CLAUDE_BIN,
        CLAUDE_TIMEOUT,
        CLAUDE_TRANSLATE_CHUNK,
        VOICE_PRO_DIR,
        WHISPER_COMPUTE_TYPE,
        WHISPER_DEVICE,
        WHISPER_MODEL,
    )
    from tts_normalizer_bridge import normalize_tts_text


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_job_id() -> str:
    return uuid.uuid4().hex[:16]


def job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def load_job(job_id: str) -> dict[str, Any] | None:
    path = job_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_job(job_id: str, data: dict[str, Any]) -> None:
    path = job_path(job_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_job(job_id: str, **kwargs: Any) -> None:
    data = load_job(job_id) or {}
    data.update(kwargs)
    data["updated_at"] = now()
    save_job(job_id, data)


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout[-4000:]}")
    return proc.stdout


def safe_name(text: str) -> str:
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text)
    return text[:80] or "video"


def extract_tweet_id(url: str) -> str:
    m = re.search(r"(\d{15,20})", url)
    return m.group(1) if m else ""


def fetch_fxtwitter(tweet_id: str) -> dict[str, Any]:
    api_url = f"https://api.fxtwitter.com/i/status/{re.sub(r'[^0-9]', '', tweet_id)}"
    raw = run_cmd(["curl", "-s", "--max-time", "10", api_url], timeout=20)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"FxTwitter JSON parse failed: {raw[:500]}") from exc
    if not isinstance(data, dict) or not data.get("tweet"):
        raise RuntimeError("FxTwitter tweet data not found")
    return data


def source_platform_label(source_url: str, source_platform: str = "") -> str:
    platform = (source_platform or "").strip().lower()
    host = urllib.parse.urlparse(source_url).netloc.lower()
    if platform in {"youtube", "youtu.be"} or "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    if platform in {"x", "twitter"} or "x.com" in host or "twitter.com" in host:
        return "X"
    if host:
        return host.replace("www.", "")
    return "元動画"


def source_metadata(source_url: str, source_title: str = "", source_platform: str = "") -> dict[str, str]:
    clean_source_title = "" if is_generic_source_title(source_title) else (source_title or "").strip()
    tweet_id = extract_tweet_id(source_url)
    if not tweet_id or ("x.com/" not in source_url and "twitter.com/" not in source_url):
        title = clean_source_title or "翻訳元動画"
        platform_label = source_platform_label(source_url, source_platform)
        return {
            "source_url": source_url,
            "source_title": title,
            "source_platform": platform_label,
            "tweet_text": title,
            "tweet_author": platform_label,
            "tweet_author_name": platform_label,
        }
    try:
        data = fetch_fxtwitter(tweet_id)
        tweet = data.get("tweet") if isinstance(data.get("tweet"), dict) else {}
        author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
        screen_name = str(author.get("screen_name") or author.get("username") or "Kurage Voice Pro")
        author_name = str(author.get("name") or screen_name)
        text = str(tweet.get("text") or "").strip()
        if is_generic_source_title(text):
            text = ""
        text = text or clean_source_title
        return {
            "source_url": source_url,
            "source_title": (clean_source_title or text).strip(),
            "source_platform": "X",
            "tweet_text": text,
            "tweet_author": "@" + screen_name if screen_name and not screen_name.startswith("@") else screen_name,
            "tweet_author_name": author_name,
        }
    except Exception:
        title = clean_source_title
        return {
            "source_url": source_url,
            "source_title": title,
            "source_platform": "X",
            "tweet_text": title,
            "tweet_author": "X",
            "tweet_author_name": "X",
        }


def extract_best_video_url(fx_data: dict[str, Any]) -> str:
    tweet = fx_data.get("tweet") if isinstance(fx_data.get("tweet"), dict) else {}
    media = tweet.get("media") if isinstance(tweet.get("media"), dict) else {}
    candidates: list[tuple[int, str]] = []

    for key in ("videos", "gifs"):
        items = media.get(key) if isinstance(media.get(key), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                candidates.append((0, str(item["url"])))
            variants = item.get("variants") if isinstance(item.get("variants"), list) else []
            for variant in variants:
                if not isinstance(variant, dict) or not variant.get("url"):
                    continue
                bitrate = int(variant.get("bitrate") or 0)
                candidates.append((bitrate, str(variant["url"])))

    candidates = [(bitrate, url) for bitrate, url in candidates if url]
    if not candidates:
        raise RuntimeError("動画URLを取得できませんでした")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def curl_download(url: str, out_file: Path, timeout: int = 1800) -> Path:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    run_cmd([
        "curl",
        "-s",
        "-L",
        "--max-time",
        str(timeout),
        "-A",
        "Mozilla/5.0",
        "-o",
        str(out_file),
        url,
    ], timeout=timeout + 30)
    if not out_file.exists() or out_file.stat().st_size <= 0:
        raise RuntimeError("動画ダウンロードに失敗しました")
    return out_file


def download_video(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if re.match(r"^https?://", url):
        tweet_id = extract_tweet_id(url)
        if tweet_id and ("x.com/" in url or "twitter.com/" in url):
            fx_data = fetch_fxtwitter(tweet_id)
            media_url = extract_best_video_url(fx_data)
            return curl_download(media_url, out_dir / f"x_{tweet_id}.mp4")

        clean = url.split("?", 1)[0]
        ext = "mp4"
        m = re.search(r"\.([a-zA-Z0-9]{2,5})$", clean)
        if m and m.group(1).lower() in {"mp4", "mov", "m4v", "webm"}:
            ext = m.group(1).lower()
        return curl_download(url, out_dir / f"{safe_name(clean)}.{ext}")

    src = Path(url)
    if src.exists():
        dst = out_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst
    raise RuntimeError(f"unsupported url/path: {url}")


def extract_audio(video: Path, out_dir: Path) -> Path:
    audio = out_dir / "source.wav"
    run_cmd([FFMPEG_BIN, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(audio)], timeout=1800)
    return audio


def transcribe_audio(audio: Path, out_dir: Path, source_lang: str) -> tuple[Path, Path]:
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    lang = None if source_lang == "auto" else source_lang
    segments, info = model.transcribe(str(audio), language=lang, vad_filter=True)
    srt = out_dir / "source.srt"
    txt = out_dir / "source.txt"
    lines: list[str] = []
    text_lines: list[str] = []
    for idx, seg in enumerate(segments, 1):
        text = seg.text.strip()
        lines.append(f"{idx}\n{fmt_srt(seg.start)} --> {fmt_srt(seg.end)}\n{text}\n")
        text_lines.append(text)
    srt.write_text("\n".join(lines), encoding="utf-8")
    txt.write_text("\n".join(text_lines), encoding="utf-8")
    return srt, txt


def fmt_srt(sec: float) -> str:
    ms = int(round((sec - int(sec)) * 1000))
    total = int(sec)
    s = total % 60
    m = (total // 60) % 60
    h = total // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _resolve_claude_bin() -> str:
    candidates: list[str] = []
    if CLAUDE_BIN:
        candidates.append(CLAUDE_BIN)
    found = shutil.which("claude")
    if found:
        candidates.append(found)
    import glob

    versioned = sorted(
        glob.glob(
            "/home/kojima/.vscode-server/extensions/"
            "anthropic.claude-code-*/resources/native-binary/claude"
        )
    )
    # 新しいバージョンを優先 (末尾が最新)。
    candidates.extend(reversed(versioned))
    for path in candidates:
        if path and Path(path).exists() and os.access(path, os.X_OK):
            return path
    return ""


def claude_request(prompt: str) -> str:
    claude_bin = _resolve_claude_bin()
    if not claude_bin:
        return ""
    cmd = [
        claude_bin,
        "-p",
        "--output-format", "text",
        "--permission-mode", "dontAsk",
        "--model", CLAUDE_MODEL,
        prompt,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT, check=False)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _target_lang_label(target_lang: str) -> str:
    lang = (target_lang or "").lower()
    return {
        "ja": "日本語", "en": "英語", "ko": "韓国語", "zh": "中国語",
    }.get(lang[:2], target_lang.upper() or "the target language")


_NUM_LINE_RE = re.compile(r"^\s*(\d+)[\.\)、:：]\s*(.*)$")


def _translate_chunk_claude(lines: list[str], target_lang: str) -> list[str] | None:
    """字幕チャンクをClaudeで「翻訳→自己批正→自然化」して返す。行数が一致しなければNone。"""
    target = _target_lang_label(target_lang)
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(lines, 1))
    prompt = (
        f"あなたはNetflix品質の字幕翻訳者です。次の字幕を{target}に翻訳してください。\n\n"
        "手順（内部で実行し、最終結果だけ出力）:\n"
        "1. まず直訳する\n"
        "2. 直訳の不自然さ・誤訳・文脈ずれを自己点検する\n"
        f"3. 話し言葉として自然で簡潔な{target}字幕に仕上げる\n\n"
        "厳守ルール:\n"
        f"- 出力は番号付きの{target}訳のみ。説明・前置き・原文は一切書かない\n"
        "- 入力と同じ行数・同じ番号を維持する（1行＝1字幕、増減禁止）\n"
        "- 各訳は1行に収める（改行を入れない）\n"
        "- 固有名詞・数字・専門用語は文脈に合わせて正確に\n"
        "- 機械翻訳調の硬い表現を避け、映像の語りとして自然にする\n\n"
        f"字幕:\n{numbered}\n"
    )
    raw = claude_request(prompt)
    if not raw:
        return None
    result: dict[int, str] = {}
    for line in raw.splitlines():
        m = _NUM_LINE_RE.match(line)
        if m:
            result[int(m.group(1))] = m.group(2).strip()
    out: list[str] = []
    for i, original in enumerate(lines, 1):
        out.append(result.get(i) or original)
    # 半数以上が訳せていなければ失敗扱い。
    translated_count = sum(1 for i in range(1, len(lines) + 1) if result.get(i))
    if translated_count < max(1, len(lines) // 2):
        return None
    return out


def translate_srt_claude(source_srt: Path, out_dir: Path, target_lang: str) -> Path | None:
    import pysubs2

    subs = pysubs2.load(str(source_srt), encoding="utf-8")
    events = [event for event in subs if event.plaintext.strip()]
    if not events:
        return None
    texts = [event.plaintext.strip() for event in events]
    translated: list[str] = []
    chunk = max(1, CLAUDE_TRANSLATE_CHUNK)
    for start in range(0, len(texts), chunk):
        part = texts[start:start + chunk]
        out_part = _translate_chunk_claude(part, target_lang)
        if out_part is None:
            return None
        translated.extend(out_part)
    if len(translated) != len(events):
        return None
    for event, text in zip(events, translated):
        event.text = text
    out = out_dir / f"translated.{target_lang}.srt"
    subs.save(str(out))
    return out


def translate_srt(source_srt: Path, out_dir: Path, source_lang: str, target_lang: str) -> Path:
    if TRANSLATOR == "claude":
        try:
            claude_out = translate_srt_claude(source_srt, out_dir, target_lang)
            if claude_out is not None:
                return claude_out
        except Exception:
            pass  # Google翻訳へフォールバック

    import pysubs2
    from deep_translator import GoogleTranslator

    src = "auto" if source_lang == "auto" else source_lang
    translator = GoogleTranslator(source=src, target=target_lang)
    subs = pysubs2.load(str(source_srt), encoding="utf-8")
    for event in subs:
        plain = event.plaintext.strip()
        if plain:
            event.text = translator.translate(plain) or plain
    out = out_dir / f"translated.{target_lang}.srt"
    subs.save(str(out))
    return out


async def _edge_tts(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts

    tts_text = normalize_tts_text(text)
    communicate = edge_tts.Communicate(tts_text, voice, rate=rate)
    await communicate.save(str(out))


def _fit_audio_to_slot(src: Path, dst: Path, slot_seconds: float) -> tuple[Path, float, float]:
    """Speed up a TTS segment when it would overlap the next subtitle slot."""
    original_duration = media_duration(src)
    slot_seconds = max(0.25, slot_seconds)
    if original_duration <= 0:
        return src, original_duration, 1.0
    if original_duration <= slot_seconds:
        return src, original_duration, 1.0

    speed = max(1.0, original_duration / slot_seconds)
    remaining = speed
    filters: list[str] = []
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.5f}")
    filters.append(f"atrim=0:{slot_seconds:.3f}")
    filters.append("asetpts=N/SR/TB")
    run_cmd([
        FFMPEG_BIN,
        "-y",
        "-i",
        str(src),
        "-af",
        ",".join(filters),
        "-c:a",
        "aac",
        str(dst),
    ], timeout=300)
    return dst, media_duration(dst), speed


def tts_from_srt(
    translated_srt: Path,
    out_dir: Path,
    voice: str,
    rate: str = DEFAULT_TTS_RATE,
    target_duration: float | None = None,
) -> Path:
    import pysubs2

    subs = pysubs2.load(str(translated_srt), encoding="utf-8")
    segments_dir = out_dir / "tts_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    adjusted_dir = out_dir / "tts_timeline_segments"
    adjusted_dir.mkdir(parents=True, exist_ok=True)
    timeline_file = out_dir / "tts_timeline.json"
    segment_items: list[dict[str, Any]] = []
    events = [event for event in subs if event.plaintext.strip()]
    for i, event in enumerate(events, 1):
        text = event.plaintext.strip()
        mp3 = segments_dir / f"{i:05d}.mp3"
        asyncio.run(_edge_tts(text, mp3, voice, rate))
        start = max(0.0, int(event.start) / 1000.0)
        if i < len(events):
            next_start = max(start + 0.25, int(events[i].start) / 1000.0)
            slot = max(0.25, next_start - start - 0.05)
        else:
            end = max(start + 0.25, int(event.end) / 1000.0)
            if target_duration:
                end = min(max(end, start + 0.25), target_duration)
            slot = max(0.25, end - start)
        fitted, fitted_duration, speed = _fit_audio_to_slot(mp3, adjusted_dir / f"{i:05d}.m4a", slot)
        segment_items.append({
            "index": i,
            "start": start,
            "slot": slot,
            "source_duration": media_duration(mp3),
            "duration": fitted_duration,
            "speed": speed,
            "text": text,
            "file": str(fitted),
        })

    out = out_dir / "translated_voice.m4a"
    timeline_duration = max(
        target_duration or 0.0,
        max((int(event.end) for event in subs), default=0) / 1000.0,
        max((item["start"] + item["duration"] for item in segment_items), default=0.0),
        1.0,
    )
    timeline_file.write_text(
        json.dumps({
            "target_duration": target_duration,
            "timeline_duration": timeline_duration,
            "segments": segment_items,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not segment_items:
        run_cmd([
            FFMPEG_BIN,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={timeline_duration:.3f}",
            "-t",
            f"{timeline_duration:.3f}",
            str(out),
        ], timeout=60)
        return out

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=44100:cl=stereo:d={timeline_duration:.3f}",
    ]
    for item in segment_items:
        cmd.extend(["-i", item["file"]])
    delayed_labels: list[str] = []
    filters: list[str] = []
    for idx, item in enumerate(segment_items, 1):
        delay_ms = int(round(item["start"] * 1000))
        label = f"a{idx}"
        filters.append(f"[{idx}:a]adelay={delay_ms}:all=1[{label}]")
        delayed_labels.append(f"[{label}]")
    filters.append(
        f"[0:a]{''.join(delayed_labels)}amix=inputs={len(segment_items) + 1}:"
        f"duration=first:dropout_transition=0,atrim=0:{timeline_duration:.3f},asetpts=N/SR/TB[aout]"
    )
    cmd.extend([
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[aout]",
        "-c:a",
        "aac",
        "-t",
        f"{timeline_duration:.3f}",
        str(out),
    ])
    run_cmd(cmd, timeout=1800)
    return out


def media_duration(path: Path) -> float:
    output = run_cmd([
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ], timeout=60).strip()
    try:
        return max(0.0, float(output))
    except ValueError:
        return 0.0


def video_stream_count(path: Path) -> int:
    output = run_cmd([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(path),
    ], timeout=60).strip()
    return len([line for line in output.splitlines() if line.strip()])


def ensure_rendered_video(path: Path, label: str) -> None:
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError(f"{label} video is empty or broken: {path}")
    if video_stream_count(path) <= 0:
        raise RuntimeError(f"{label} video has no video stream: {path}")
    if media_duration(path) <= 0:
        raise RuntimeError(f"{label} video has no duration: {path}")


def srt_plain_text(srt_path: Path) -> str:
    import pysubs2

    subs = pysubs2.load(str(srt_path), encoding="utf-8")
    return "\n".join(event.plaintext.strip() for event in subs if event.plaintext.strip())


def first_content_line(text: str) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def translate_plain_text(text: str, target_lang: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    try:
        from deep_translator import GoogleTranslator

        return (GoogleTranslator(source="auto", target=target_lang).translate(text) or text).strip()
    except Exception:
        return text


def smart_truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    sentence_cut = max(cut.rfind(mark) for mark in ("。", "！", "？", "!", "?", "."))
    if sentence_cut >= max(12, limit // 3):
        return cut[: sentence_cut + 1].strip()
    clause_cut = cut.rfind("、")
    if clause_cut >= max(12, limit // 2):
        return cut[: clause_cut + 1].strip()
    if re.search(r"[A-Za-z0-9]$", cut):
        word_cut = re.sub(r"\s+\S*$", "", cut).strip()
        if len(word_cut) >= max(12, limit // 2):
            return word_cut
    return cut


def compact_description(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return ""
    sentences = [p.strip() for p in re.split(r"(?<=[。！？!?.,])\s*", text) if p.strip()]
    if not sentences:
        return smart_truncate(text, limit)
    out = ""
    for sentence in sentences:
        candidate = (out + " " + sentence).strip() if out else sentence
        if len(candidate) > limit:
            break
        out = candidate
        if len(sentences) > 1 and len(out) >= min(90, limit):
            break
    return out or smart_truncate(text, limit)


def mode_label(target_lang: str, audio_mode: str) -> str:
    lang = (target_lang or "").lower()
    subtitle_only = audio_mode == "subtitle_only"
    if lang.startswith("en"):
        return "English Subtitles" if subtitle_only else "English Dub/Subtitles"
    if lang.startswith("ja"):
        return "日本語字幕" if subtitle_only else "日本語吹替・日本語字幕"
    if lang.startswith("ko"):
        return "한국어 자막" if subtitle_only else "한국어 더빙/자막"
    if lang.startswith("zh"):
        return "中文字幕" if subtitle_only else "中文配音/字幕"
    label = target_lang.upper() if target_lang else "Translated"
    return f"{label} Subtitles" if subtitle_only else f"{label} Dub/Subtitles"


def title_suffix(target_lang: str, audio_mode: str) -> str:
    lang = (target_lang or "").lower()
    label = mode_label(target_lang, audio_mode)
    if lang.startswith(("ja", "zh")):
        return f"【{label}】"
    return f"[{label}]"


def target_language_name(target_lang: str) -> str:
    lang = (target_lang or "").lower()
    if lang.startswith("en"):
        return "English"
    if lang.startswith("ja"):
        return "日本語"
    if lang.startswith("ko"):
        return "한국어"
    if lang.startswith("zh"):
        return "中文"
    return target_lang.upper() if target_lang else "Translation"


def is_generic_source_title(text: str) -> bool:
    normalized = re.sub(r"\s+", "", (text or "").strip()).lower()
    return normalized in {"", "x投稿", "twitter投稿", "tweet", "xpost", "twitterpost"}


def should_translate_title_to_ja(text: str) -> bool:
    text = text or ""
    if not text.strip():
        return False
    if re.search(r"[A-Za-z\uac00-\ud7af]", text):
        return True
    # Chinese Han text has no kana; Japanese usually contains kana in these captions.
    return bool(re.search(r"[\u3400-\u9fff]", text)) and not re.search(r"[\u3040-\u30ff]", text)


def is_latin_heavy_text(text: str) -> bool:
    text = text or ""
    latin = len(re.findall(r"[A-Za-z]", text))
    non_latin = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", text))
    return latin >= 12 and latin >= non_latin


def secondary_language_name(target_lang: str) -> str:
    lang = (target_lang or "").lower()
    if lang.startswith("en"):
        return "日本語"
    if lang.startswith("ja"):
        return "English"
    if lang.startswith("ko"):
        return "日本語"
    if lang.startswith("zh"):
        return "日本語"
    return "Original"


def public_title_from_source(
    source: dict[str, str],
    target_lang: str,
    audio_mode: str = "dubbed",
    fallback_text: str = "",
    title_source_text: str = "",
) -> str:
    text = (title_source_text or source.get("source_title") or source.get("tweet_text") or "").strip()
    if is_generic_source_title(text):
        text = ""
    first_line = first_content_line(text)
    if not first_line:
        first_line = first_content_line(compact_description(fallback_text, limit=160))
    if not first_line:
        platform = (source.get("source_platform") or "元動画").strip()
        first_line = f"{platform} translation video"
    title = first_line
    if target_lang == "ja" and should_translate_title_to_ja(title):
        title = translate_plain_text(title, "ja", limit=160)
    elif target_lang.startswith("en") and re.search(r"[\u3040-\u30ff\u3400-\u9fff]", title):
        title = translate_plain_text(title, "en", limit=160)
    title = re.sub(r"\s+", " ", title).strip()
    suffix = title_suffix(target_lang, audio_mode)
    max_title_len = max(20, 72 - len(suffix))
    return f"{smart_truncate(title, max_title_len)} {suffix}"


def description_pair(source: dict[str, str], target_lang: str, translated_text: str) -> tuple[str, str, str]:
    primary = compact_description(translated_text)
    original = (source.get("source_title") or source.get("tweet_text") or "").strip()
    if is_generic_source_title(original):
        original = ""
    if not original:
        original = source.get("tweet_text", "").strip()
    if is_generic_source_title(original):
        original = ""
    lang = (target_lang or "").lower()
    if lang.startswith("en"):
        secondary = compact_description(original)
        if secondary and not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", secondary):
            secondary = translate_plain_text(secondary, "ja")
    elif lang.startswith("ja"):
        secondary = compact_description(original)
        if secondary and not re.search(r"[A-Za-z]", secondary):
            secondary = translate_plain_text(secondary, "en")
    else:
        secondary = compact_description(original)
    return primary, secondary, original


def bilingual_display_summary(target_lang: str, primary: str, secondary: str) -> str:
    primary = primary.strip()
    secondary = secondary.strip()
    if not secondary:
        return primary
    return (
        f"{target_language_name(target_lang)}:\n{primary}\n\n"
        f"{secondary_language_name(target_lang)}:\n{secondary}"
    ).strip()


def is_latin_caption(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    latin = len(re.findall(r"[A-Za-z0-9]", compact))
    cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]", compact))
    return latin > cjk


def split_long_latin_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.append(word[: max_chars - 1].rstrip() + "…")
            continue
        candidate = word if not current else current + " " + word
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
        current = word
    if current:
        chunks.append(current.strip())
    return chunks


def split_caption_text(text: str, max_chars: int | None = None, latin: bool | None = None) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    latin = is_latin_caption(text) if latin is None else latin
    max_chars = max_chars or (SUBTITLE_LATIN_MAX_CHARS if latin else SUBTITLE_CJK_MAX_CHARS)

    # Do not split on numeric thousands separators such as "1,000".
    # Japanese commas and sentence punctuation are safe caption boundaries.
    if not latin:
        text = re.sub(r"(?<!\d),(?!\d)", "、", text)
    parts = [p for p in re.split(r"(?<=[。！？!?、,.])\s*", text) if p]
    chunks: list[str] = []
    current = ""
    for part in parts:
        separator = " " if latin and current else ""
        if len(current) + len(separator) + len(part) <= max_chars:
            current += separator + part
            continue
        if current:
            chunks.append(current.strip())
        while len(part) > max_chars:
            if latin:
                split_parts = split_long_latin_text(part, max_chars)
                chunks.extend(split_parts[:-1])
                part = split_parts[-1] if split_parts else ""
                break
            chunks.append(part[:max_chars].strip())
            part = part[max_chars:]
        current = part
    if current:
        chunks.append(current.strip())
    return chunks


def wrap_latin_caption_text(text: str, line_chars: int, max_lines: int) -> str:
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if len(candidate) <= line_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines - 1:
            break
    if current and len(lines) < max_lines:
        remaining = words[sum(len(line.split()) for line in lines):]
        tail = " ".join(remaining)
        lines.append(tail if len(tail) <= line_chars else tail[: line_chars - 1].rstrip() + "…")
    return r"\N".join(lines[:max_lines])


def wrap_caption_text(text: str, line_chars: int | None = None, max_lines: int | None = None, latin: bool | None = None) -> str:
    text = text.strip()
    latin = is_latin_caption(text) if latin is None else latin
    line_chars = line_chars or (SUBTITLE_LATIN_LINE_CHARS if latin else SUBTITLE_CJK_LINE_CHARS)
    max_lines = max_lines or SUBTITLE_MAX_LINES
    if len(text) <= line_chars:
        return text
    if latin:
        return wrap_latin_caption_text(text, line_chars, max_lines)
    lines: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if len(current) >= line_chars:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return r"\N".join(lines[:max_lines])


def make_kurage_ass(
    translated_srt: Path,
    out_dir: Path,
    target_duration: float | None = None,
    marginl: int | None = None,
    marginr: int | None = None,
    cjk_line_chars: int | None = None,
    latin_line_chars: int | None = None,
) -> Path:
    import pysubs2

    source = pysubs2.load(str(translated_srt), encoding="utf-8")
    source_duration = max((int(event.end) for event in source), default=0) / 1000.0
    scale = 1.0
    if target_duration and source_duration > 0:
        scale = max(1.0, target_duration / source_duration)
    ass = pysubs2.SSAFile()
    ass.info["ScriptType"] = "v4.00+"
    ass.info["PlayResX"] = "576"
    ass.info["PlayResY"] = "1024"
    ass.info["WrapStyle"] = "2"
    shift_x = max(0, int(SUBTITLE_SHIFT_RIGHT_CHARS)) * int(SUBTITLE_FONT_SIZE)
    shift_y = max(0, int(SUBTITLE_SHIFT_UP_LINES)) * (int(SUBTITLE_FONT_SIZE) + 8)
    base_margin_l = SUBTITLE_MARGIN_L if marginl is None else marginl
    base_margin_r = SUBTITLE_MARGIN_R if marginr is None else marginr
    subtitle_x = int(base_margin_l + shift_x)
    subtitle_y = int(1024 - (SUBTITLE_MARGIN_V + shift_y))
    position_tag = rf"{{\pos({subtitle_x},{subtitle_y})}}"
    ass.styles["Default"] = pysubs2.SSAStyle(
        fontname="Noto Sans CJK JP",
        fontsize=SUBTITLE_FONT_SIZE,
        primarycolor=pysubs2.Color(255, 255, 255, 0),
        outlinecolor=pysubs2.Color(0, 0, 0, 0),
        backcolor=pysubs2.Color(0, 0, 0, 120),
        bold=True,
        borderstyle=1,
        outline=4,
        shadow=2,
        alignment=1,
        marginl=base_margin_l,
        marginr=base_margin_r,
        marginv=SUBTITLE_MARGIN_V,
    )

    for event in source:
        latin = is_latin_caption(event.plaintext)
        line_chars = latin_line_chars if latin else cjk_line_chars
        chunk_max_chars = (line_chars * SUBTITLE_MAX_LINES) if line_chars else None
        chunks = split_caption_text(event.plaintext, max_chars=chunk_max_chars, latin=latin)
        if not chunks:
            continue
        start = int(event.start * scale)
        end = int(event.end * scale)
        duration = max(600, end - start)
        chunk_duration = max(650, duration // len(chunks))
        for index, chunk in enumerate(chunks):
            ev_start = start + index * chunk_duration
            ev_end = end if index == len(chunks) - 1 else min(end, ev_start + chunk_duration)
            if ev_end <= ev_start:
                ev_end = ev_start + 650
            ass.events.append(
                pysubs2.SSAEvent(
                    start=ev_start,
                    end=ev_end,
                    text=position_tag + wrap_caption_text(
                        chunk,
                        line_chars=line_chars,
                        latin=latin,
                    ),
                    style="Default",
                )
            )

    out = out_dir / "translated.kurage.ass"
    ass.save(str(out))
    return out


def burn_subtitles(
    video: Path,
    translated_srt: Path,
    out_dir: Path,
    target_duration: float | None = None,
    subtitle_target_duration: float | None = None,
    vtuber_mode: bool = False,
) -> Path:
    out = out_dir / "subtitled.mp4"
    subtitle_margin_l = max(SUBTITLE_MARGIN_L, VTUBER_SUBTITLE_MARGIN_L) if vtuber_mode else SUBTITLE_MARGIN_L
    subtitle_margin_r = max(SUBTITLE_MARGIN_R, VTUBER_SUBTITLE_MARGIN_R) if vtuber_mode else SUBTITLE_MARGIN_R
    ass = make_kurage_ass(
        translated_srt,
        out_dir,
        target_duration=subtitle_target_duration,
        marginl=subtitle_margin_l,
        marginr=subtitle_margin_r,
        cjk_line_chars=VTUBER_SUBTITLE_CJK_LINE_CHARS if vtuber_mode else None,
        latin_line_chars=VTUBER_SUBTITLE_LATIN_LINE_CHARS if vtuber_mode else None,
    )
    filter_complex = (
        "[0:v]scale=576:1024:force_original_aspect_ratio=increase,"
        "crop=576:1024,boxblur=18:1,eq=brightness=-0.20[bg];"
        "[0:v]scale=576:1024:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"subtitles={ass.as_posix()}[v]"
    )
    run_cmd([
        FFMPEG_BIN,
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(video),
        "-t",
        f"{target_duration:.3f}" if target_duration else f"{media_duration(video):.3f}",
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-an",
        str(out),
    ], timeout=3600)
    ensure_rendered_video(out, "subtitled")
    return out


def dub_audio_filter() -> str | None:
    """吹替音声に掛けるフィルタ。volume倍率 + loudnorm(割れない音量底上げ)。"""
    filters: list[str] = []
    if TRANSLATED_AUDIO_VOLUME != 1.0:
        filters.append(f"volume={TRANSLATED_AUDIO_VOLUME:.3f}")
    if TRANSLATED_AUDIO_LOUDNORM:
        filters.append(
            f"loudnorm=I={TRANSLATED_AUDIO_LOUDNORM_I:.1f}:"
            f"TP={TRANSLATED_AUDIO_LOUDNORM_TP:.1f}:"
            f"LRA={TRANSLATED_AUDIO_LOUDNORM_LRA:.1f}"
        )
    return ",".join(filters) if filters else None


def replace_audio(video: Path, translated_audio: Path, out_dir: Path) -> Path:
    out = out_dir / "dubbed.mp4"
    duration = media_duration(video)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(video),
        "-i",
        str(translated_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
    ]
    audio_filter = dub_audio_filter()
    if audio_filter:
        cmd.extend(["-filter:a:0", audio_filter])
    cmd.extend([
        "-t",
        f"{duration:.3f}",
        str(out),
    ])
    run_cmd(cmd, timeout=3600)
    ensure_rendered_video(out, "dubbed")
    return out


def make_full_video(subtitled_video: Path, translated_audio: Path, out_dir: Path) -> Path:
    out = out_dir / "translated_subtitled_dubbed.mp4"
    duration = media_duration(subtitled_video)
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-i",
        str(subtitled_video),
        "-i",
        str(translated_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
    ]
    audio_filter = dub_audio_filter()
    if audio_filter:
        cmd.extend(["-filter:a:0", audio_filter])
    cmd.extend([
        "-t",
        f"{duration:.3f}",
        str(out),
    ])
    run_cmd(cmd, timeout=3600)
    ensure_rendered_video(out, "translated subtitled dubbed")
    return out


def apply_vtuber_overlay(video: Path, out_dir: Path) -> Path:
    """Overlay the Kurage PNG-tuber avatar on the completed Voice Pro video."""
    if not VTUBER_AVATAR_IDLE.exists() or not VTUBER_AVATAR_TALK.exists():
        return video

    out = out_dir / "final_vtuber.mp4"
    duration = media_duration(video)
    width = max(80, int(VTUBER_AVATAR_WIDTH))
    margin_x = max(0, int(VTUBER_AVATAR_MARGIN_X))
    margin_y = max(0, int(VTUBER_AVATAR_MARGIN_Y))
    avatar_shift_x = max(0, int(VTUBER_AVATAR_SHIFT_RIGHT_CHARS)) * int(SUBTITLE_FONT_SIZE)
    filter_complex = (
        f"[1:v]format=rgba,scale={width}:-1[idle];"
        f"[2:v]format=rgba,scale={width}:-1[talk];"
        f"[0:v][idle]overlay=x=W-w-{margin_x}+{avatar_shift_x}:y=H-h-{margin_y}:format=auto[base];"
        f"[base][talk]overlay=x=W-w-{margin_x}+{avatar_shift_x}:y=H-h-{margin_y}:"
        "enable='lt(mod(t,0.28),0.10)':format=auto[v]"
    )
    run_cmd([
        FFMPEG_BIN,
        "-y",
        "-i",
        str(video),
        "-loop",
        "1",
        "-i",
        str(VTUBER_AVATAR_IDLE),
        "-loop",
        "1",
        "-i",
        str(VTUBER_AVATAR_TALK),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "copy",
        "-t",
        f"{duration:.3f}",
        str(out),
    ], timeout=3600)
    ensure_rendered_video(out, "vtuber voice pro")
    return out


def make_subtitle_only_video(subtitled_video: Path, source_video: Path, out_dir: Path) -> Path:
    out = out_dir / "translated_subtitled_original_audio.mp4"
    duration = media_duration(subtitled_video)
    run_cmd([
        FFMPEG_BIN,
        "-y",
        "-i",
        str(subtitled_video),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-t",
        f"{duration:.3f}",
        str(out),
    ], timeout=3600)
    ensure_rendered_video(out, "translated subtitled original audio")
    return out


def make_thumbnail(video: Path, out: Path) -> Path:
    run_cmd([
        FFMPEG_BIN,
        "-y",
        "-ss",
        "3",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out),
    ], timeout=120)
    return out


def publish_to_kurage(
    job_id: str,
    full_video: Path,
    translated_srt: Path,
    translated_audio: Path | None,
    source_url: str,
    target_lang: str,
    translated_text: str,
    *,
    original_url: str = "",
    source_title: str = "",
    source_platform: str = "",
    vtuber_mode: bool = DEFAULT_VTUBER_MODE,
    original_text: str = "",
) -> dict[str, str]:
    public_dir = KURAGE_JOBS_DIR / job_id
    public_dir.mkdir(parents=True, exist_ok=True)
    output = public_dir / "output.mp4"
    thumbnail = public_dir / "thumbnail.jpg"
    shutil.copy2(full_video, output)
    try:
        make_thumbnail(output, thumbnail)
    except Exception:
        thumbnail.write_bytes(b"")

    created = now()
    display_source_url = (original_url or source_url or "").strip()
    source = source_metadata(display_source_url, source_title, source_platform)
    audio_mode = "subtitle_only" if not translated_audio else "dubbed"
    source_title_text = (source.get("source_title") or source.get("tweet_text") or "").strip()
    title_source_text = source_title_text or (original_text if is_latin_heavy_text(original_text) else "")
    title = public_title_from_source(source, target_lang, audio_mode, translated_text, title_source_text)
    primary_desc, secondary_desc, original_desc = description_pair(source, target_lang, translated_text)
    display_summary = bilingual_display_summary(target_lang, primary_desc, secondary_desc)
    voice_label = mode_label(target_lang, audio_mode)
    data = {
        "job_id": job_id,
        "status": "done",
        "progress": 100,
        "source": "kuragevp",
        "content_type": "voice_pro_translation",
        "title": title,
        "display_title": title,
        "summary_title": title,
        "tweet_url": display_source_url,
        "tweet_text": primary_desc or title,
        "tweet_author": source["tweet_author"],
        "tweet_author_name": source["tweet_author_name"],
        "source_url": display_source_url,
        "source_title": source["source_title"],
        "source_platform": source["source_platform"],
        "original_url": display_source_url,
        "source_media_path": source_url if source_url != display_source_url else "",
        "audio_mode": audio_mode,
        "vtuber_mode": vtuber_mode,
        "voice_pro_label": voice_label,
        "summary": primary_desc or title,
        "display_summary": display_summary,
        "copy_summary": primary_desc or title,
        "primary_description": primary_desc,
        "secondary_description": secondary_desc,
        "original_description": original_desc,
        "target_language_name": target_language_name(target_lang),
        "secondary_language_name": secondary_language_name(target_lang),
        "article_url": "",
        "translated_text": translated_text,
        "video_file": str(output),
        "thumbnail_file": str(thumbnail),
        "translated_srt": str(translated_srt),
        "translated_audio": str(translated_audio) if translated_audio else "",
        "views": 0,
        "created_at": created,
        "updated_at": created,
        "script": {
            "title": title,
            "scenes": [{"index": 0, "narration": translated_text, "image_prompt": ""}] if translated_text else [],
        },
        "kuragevp_job_id": job_id,
    }
    meta = KURAGE_JOBS_DIR / f"{job_id}.json"
    tmp = meta.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(meta)
    return {
        "kurage_job_id": job_id,
        "kurage_url": f"{KURAGE_PUBLIC_BASE_URL}/kuragev.php?id={job_id}",
        "kurage_video_file": str(output),
        "kurage_thumbnail_file": str(thumbnail),
    }


def run_pipeline(
    job_id: str,
    url: str,
    source_lang: str,
    target_lang: str,
    tts_voice: str,
    *,
    audio_mode: str = "dubbed",
    original_url: str = "",
    source_title: str = "",
    source_platform: str = "",
    vtuber_mode: bool = DEFAULT_VTUBER_MODE,
) -> None:
    out_dir = job_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_mode = "subtitle_only" if audio_mode == "subtitle_only" else "dubbed"
    try:
        update_job(
            job_id,
            status="downloading",
            progress=5,
            audio_mode=audio_mode,
            original_url=original_url,
            source_title=source_title,
            source_platform=source_platform,
            vtuber_mode=vtuber_mode,
            note="動画取得中",
        )
        video = download_video(url, out_dir)
        update_job(job_id, status="extracting_audio", progress=15, source_video=str(video), note="音声抽出中")
        ensure_rendered_video(video, "source")

        audio = extract_audio(video, out_dir)
        update_job(job_id, status="transcribing", progress=30, audio_file=str(audio), note="音声テキスト化中")

        source_srt, source_txt = transcribe_audio(audio, out_dir, source_lang)
        update_job(
            job_id,
            status="translating",
            progress=50,
            source_srt=str(source_srt),
            source_txt=str(source_txt),
            translator=TRANSLATOR,
            note="翻訳中" + ("（Claude）" if TRANSLATOR == "claude" else ""),
        )

        translated_srt = translate_srt(source_srt, out_dir, source_lang, target_lang)
        translated_text = srt_plain_text(translated_srt)

        video_duration = media_duration(video)
        translated_audio: Path | None = None
        if audio_mode == "dubbed":
            update_job(job_id, status="tts", progress=65, translated_srt=str(translated_srt), note="翻訳音声生成中")
            translated_audio = tts_from_srt(translated_srt, out_dir, tts_voice, target_duration=video_duration)
            audio_duration = media_duration(translated_audio)
            update_job(
                job_id,
                status="rendering_subtitle",
                progress=78,
                translated_audio=str(translated_audio),
                translated_audio_duration=audio_duration,
                source_video_duration=video_duration,
                tts_rate=DEFAULT_TTS_RATE,
                translated_audio_volume=TRANSLATED_AUDIO_VOLUME,
                note="元動画のタイムラインに合わせて字幕を動画に合成中",
            )
        else:
            update_job(
                job_id,
                status="rendering_subtitle",
                progress=78,
                translated_srt=str(translated_srt),
                translated_audio="",
                translated_audio_duration=0,
                source_video_duration=video_duration,
                note="元音声のまま翻訳字幕を動画に合成中",
            )

        subtitled = burn_subtitles(video, translated_srt, out_dir, target_duration=video_duration, vtuber_mode=vtuber_mode)
        if audio_mode == "dubbed" and translated_audio:
            update_job(job_id, status="rendering_audio", progress=88, subtitled_video=str(subtitled), note="翻訳音声を動画に合成中")
            dubbed = replace_audio(video, translated_audio, out_dir)
            full = make_full_video(subtitled, translated_audio, out_dir)
        else:
            update_job(job_id, status="rendering_audio", progress=88, subtitled_video=str(subtitled), note="元音声を字幕付き動画に合成中")
            dubbed = None
            full = make_subtitle_only_video(subtitled, video, out_dir)

        if vtuber_mode:
            update_job(job_id, status="rendering_vtuber", progress=92, final_video=str(full), vtuber_mode=True, note="VTuberアバターを動画に合成中")
            full = apply_vtuber_overlay(full, out_dir)

        update_job(job_id, status="publishing", progress=95, note="Kurage動画として公開中")
        kurage_public = publish_to_kurage(
            job_id,
            full,
            translated_srt,
            translated_audio,
            url,
            target_lang,
            translated_text,
            original_url=original_url,
            source_title=source_title,
            source_platform=source_platform,
            vtuber_mode=vtuber_mode,
            original_text=source_txt.read_text(encoding="utf-8", errors="ignore"),
        )
        update_job(
            job_id,
            status="done",
            progress=100,
            note="完了",
            audio_mode=audio_mode,
            vtuber_mode=vtuber_mode,
            dubbed_video=str(dubbed) if dubbed else "",
            final_video=str(full),
            video_file=str(full),
            translated_text=translated_text,
            **kurage_public,
            completed_at=now(),
        )
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            progress=0,
            error=str(exc),
            traceback=traceback.format_exc(),
            note="失敗",
        )
