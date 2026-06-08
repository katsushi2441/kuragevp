from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

try:
    from .config import (
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        DEFAULT_TTS_VOICE,
        JOBS_DIR,
        KURAGE_JOBS_DIR,
        KURAGE_PUBLIC_BASE_URL,
        TMP_DIR,
        VOICE_PRO_DIR,
        WHISPER_MODEL,
    )
except ImportError:
    from config import (
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        DEFAULT_TTS_VOICE,
        JOBS_DIR,
        KURAGE_JOBS_DIR,
        KURAGE_PUBLIC_BASE_URL,
        TMP_DIR,
        VOICE_PRO_DIR,
        WHISPER_MODEL,
    )


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


def download_video(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if re.match(r"^https?://", url):
        tmpl = str(out_dir / "%(title).80s.%(ext)s")
        run_cmd([
            "yt-dlp",
            "-f",
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format",
            "mp4",
            "-o",
            tmpl,
            url,
        ], timeout=1800)
        files = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise RuntimeError("yt-dlp did not create mp4")
        return files[0]

    src = Path(url)
    if src.exists():
        dst = out_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst
    raise RuntimeError(f"unsupported url/path: {url}")


def extract_audio(video: Path, out_dir: Path) -> Path:
    audio = out_dir / "source.wav"
    run_cmd(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(audio)], timeout=1800)
    return audio


def transcribe_audio(audio: Path, out_dir: Path, source_lang: str) -> tuple[Path, Path]:
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
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


def translate_srt(source_srt: Path, out_dir: Path, source_lang: str, target_lang: str) -> Path:
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


async def _edge_tts(text: str, out: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out))


def tts_from_srt(translated_srt: Path, out_dir: Path, voice: str) -> Path:
    import pysubs2

    subs = pysubs2.load(str(translated_srt), encoding="utf-8")
    segments_dir = out_dir / "tts_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    concat_file = out_dir / "tts_concat.txt"
    segment_files: list[Path] = []
    for i, event in enumerate(subs, 1):
        text = event.plaintext.strip()
        if not text:
            continue
        mp3 = segments_dir / f"{i:05d}.mp3"
        asyncio.run(_edge_tts(text, mp3, voice))
        segment_files.append(mp3)
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in segment_files), encoding="utf-8")
    out = out_dir / "translated_voice.m4a"
    if segment_files:
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "aac", str(out)], timeout=1800)
    else:
        run_cmd(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", str(out)], timeout=60)
    return out


def burn_subtitles(video: Path, translated_srt: Path, out_dir: Path) -> Path:
    out = out_dir / "subtitled.mp4"
    vf = f"subtitles={translated_srt.as_posix()}:force_style='FontSize=22,Outline=2,Shadow=1'"
    run_cmd(["ffmpeg", "-y", "-i", str(video), "-vf", vf, "-c:a", "copy", str(out)], timeout=3600)
    return out


def replace_audio(video: Path, translated_audio: Path, out_dir: Path) -> Path:
    out = out_dir / "dubbed.mp4"
    run_cmd([
        "ffmpeg",
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
        "-shortest",
        str(out),
    ], timeout=3600)
    return out


def make_full_video(subtitled_video: Path, translated_audio: Path, out_dir: Path) -> Path:
    out = out_dir / "translated_subtitled_dubbed.mp4"
    run_cmd([
        "ffmpeg",
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
        "-shortest",
        str(out),
    ], timeout=3600)
    return out


def make_thumbnail(video: Path, out: Path) -> Path:
    run_cmd([
        "ffmpeg",
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


def publish_to_kurage(job_id: str, full_video: Path, translated_srt: Path, translated_audio: Path, source_url: str, target_lang: str) -> dict[str, str]:
    public_dir = KURAGE_JOBS_DIR / job_id
    public_dir.mkdir(parents=True, exist_ok=True)
    output = public_dir / "output.mp4"
    thumbnail = public_dir / "thumbnail.jpg"
    shutil.copy2(full_video, output)
    try:
        make_thumbnail(output, thumbnail)
    except Exception:
        thumbnail.write_bytes(b"")

    title = f"Kurage Voice Pro 翻訳動画 {target_lang.upper()}"
    created = now()
    data = {
        "job_id": job_id,
        "status": "done",
        "progress": 100,
        "source": "kuragevp",
        "content_type": "voice_pro_translation",
        "title": title,
        "tweet_url": source_url,
        "tweet_text": "Kurage Voice Proで生成した翻訳字幕・翻訳音声付き動画です。",
        "tweet_author": "Kurage Voice Pro",
        "tweet_author_name": "Kurage Voice Pro",
        "video_file": str(output),
        "thumbnail_file": str(thumbnail),
        "translated_srt": str(translated_srt),
        "translated_audio": str(translated_audio),
        "views": 9999,
        "created_at": created,
        "updated_at": created,
        "script": {
            "title": title,
            "scenes": [],
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


def run_pipeline(job_id: str, url: str, source_lang: str, target_lang: str, tts_voice: str) -> None:
    out_dir = job_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        update_job(job_id, status="downloading", progress=5, note="動画取得中")
        video = download_video(url, out_dir)
        update_job(job_id, status="extracting_audio", progress=15, source_video=str(video), note="音声抽出中")

        audio = extract_audio(video, out_dir)
        update_job(job_id, status="transcribing", progress=30, audio_file=str(audio), note="音声テキスト化中")

        source_srt, source_txt = transcribe_audio(audio, out_dir, source_lang)
        update_job(job_id, status="translating", progress=50, source_srt=str(source_srt), source_txt=str(source_txt), note="翻訳中")

        translated_srt = translate_srt(source_srt, out_dir, source_lang, target_lang)
        update_job(job_id, status="tts", progress=65, translated_srt=str(translated_srt), note="翻訳音声生成中")

        translated_audio = tts_from_srt(translated_srt, out_dir, tts_voice)
        update_job(job_id, status="rendering_subtitle", progress=78, translated_audio=str(translated_audio), note="翻訳字幕を動画に合成中")

        subtitled = burn_subtitles(video, translated_srt, out_dir)
        update_job(job_id, status="rendering_audio", progress=88, subtitled_video=str(subtitled), note="翻訳音声を動画に合成中")

        dubbed = replace_audio(video, translated_audio, out_dir)
        full = make_full_video(subtitled, translated_audio, out_dir)
        update_job(job_id, status="publishing", progress=95, note="Kurage動画として公開中")
        kurage_public = publish_to_kurage(job_id, full, translated_srt, translated_audio, url, target_lang)
        update_job(
            job_id,
            status="done",
            progress=100,
            note="完了",
            dubbed_video=str(dubbed),
            final_video=str(full),
            video_file=str(full),
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
