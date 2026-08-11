#!/usr/bin/env python3
"""Kurage Voice Pro — 段階実行CLI（KrillinAI式のstage分割＋manifest再利用）。

各段階が独立実行・成果物をjobディレクトリに書き、`manifest.json` に記録する。
後段は manifest から前段の成果物を再利用するので、途中から再開・段階だけ再実行できる。
AIエージェントからも段ごとに呼べる（結果はstdoutに1行JSON）。

  python -m backend.cli download   --url <URL> [--job <id>]
  python -m backend.cli transcribe --job <id> [--source-lang auto] [--force]
  python -m backend.cli translate  --job <id> [--target-lang ja]
  python -m backend.cli tts        --job <id> [--tts-voice ja-JP-NanamiNeural]
  python -m backend.cli render     --job <id> [--vtuber/--no-vtuber]
  python -m backend.cli render-vertical --job <id>
  python -m backend.cli pipeline   --url <URL> --stages download,transcribe,translate,tts,render

新機能:
  - captions優先: YouTube/Bilibili等は yt-dlp で既存字幕を取得し、無ければWhisperへフォールバック（ASRコスト削減）
  - 縦動画(9:16)＋短尺字幕: render-vertical で TikTok/Shorts 向けを1本から生成
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:  # サービスと同じ相対/絶対 両対応
    from . import pipeline as P
    from . import config as C
except ImportError:  # 直接実行
    import pipeline as P  # type: ignore
    import config as C  # type: ignore

STAGES = ["download", "transcribe", "translate", "tts", "render", "render-vertical", "publish"]


# ---------- manifest ----------
def manifest_path(job_id: str) -> Path:
    return P.job_dir(job_id) / "manifest.json"


def load_manifest(job_id: str) -> dict[str, Any]:
    p = manifest_path(job_id)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"job_id": job_id, "stages": {}}


def save_manifest(job_id: str, man: dict[str, Any]) -> None:
    manifest_path(job_id).write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact_ok(job_id: str, rel: str | None) -> bool:
    if not rel:
        return False
    p = P.job_dir(job_id) / rel
    return p.is_file() and p.stat().st_size > 0


def _rel(job_id: str, path: Path) -> str:
    try:
        return str(Path(path).relative_to(P.job_dir(job_id)))
    except ValueError:
        return str(path)


def _record(man: dict[str, Any], stage: str, **artifacts: Any) -> None:
    man.setdefault("stages", {})[stage] = {
        "done": True,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **artifacts,
    }


def _out(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


# ---------- captions優先（yt-dlp）----------
def fetch_captions(url: str, source_lang: str, out_dir: Path) -> Path | None:
    """YouTube/Bilibili等の既存字幕を yt-dlp で取得しSRTを返す。無ければNone。"""
    if not url.startswith("http"):
        return None
    langs = "en,ja,zh,zh-Hans,zh-Hant" if source_lang == "auto" else f"{source_lang},{source_lang}-orig,en"
    tmpl = str(out_dir / "captions.%(ext)s")
    try:
        subprocess.run(
            ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
             "--sub-langs", langs, "--convert-subs", "srt", "--sub-format", "srt/best",
             "-o", tmpl, url],
            cwd=str(out_dir), timeout=300, capture_output=True, text=True, check=False,
        )
    except Exception:
        return None
    cands = sorted(out_dir.glob("captions*.srt"), key=lambda p: p.stat().st_size, reverse=True)
    for c in cands:
        if c.stat().st_size > 40:
            dst = out_dir / "source.srt"
            dst.write_text(c.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            return dst
    return None


def ytdlp_download(url: str, out_dir: Path) -> Path | None:
    """プラットフォームURL(YouTube/Bilibili等)は yt-dlp で本体DL。成功時パスを返す。"""
    out = out_dir / "source_ytdlp.mp4"
    try:
        subprocess.run(
            ["yt-dlp", "-f", "mp4/best", "--no-playlist", "-o", str(out), url],
            timeout=1800, capture_output=True, text=True, check=False,
        )
    except Exception:
        return None
    if out.is_file() and out.stat().st_size > 0:
        return out
    cands = sorted(out_dir.glob("source_ytdlp*"), key=lambda p: p.stat().st_size, reverse=True)
    return cands[0] if cands else None


# ---------- stages ----------
def stage_download(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    out = P.job_dir(job_id)
    url = man.get("url") or args.url
    if not url:
        raise SystemExit("download: --url が必要です")
    man["url"] = url
    # プラットフォームURL(YouTube/Bilibili等・直リンクでない)は yt-dlp、
    # それ以外(X/直リンク/ローカル)は既存 download_video を使う。
    video: Path | None = None
    if url.startswith("http") and not any(k in url for k in ("x.com/", "twitter.com/")):
        last = url.split("?", 1)[0].rsplit("/", 1)[-1]
        ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
        if ext not in {"mp4", "mov", "m4v", "webm"}:
            video = ytdlp_download(url, out)
    if video is None:
        video = P.download_video(url, out)
    P.ensure_rendered_video(video, "source")
    _record(man, "download", video=_rel(job_id, video))
    return {"video": _rel(job_id, video)}


def stage_transcribe(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    out = P.job_dir(job_id)
    video = out / man["stages"]["download"]["video"]
    source_lang = man.get("source_lang") or args.source_lang or C.DEFAULT_SOURCE_LANG
    man["source_lang"] = source_lang
    method = "whisper"
    srt = None
    if not args.no_captions:
        srt = fetch_captions(man.get("url", ""), source_lang, out)
        if srt is not None:
            method = "captions"
    if srt is None:  # captionsなし → 音声抽出＋Whisper
        audio = P.extract_audio(video, out)
        srt, txt = P.transcribe_audio(audio, out, source_lang)
    else:
        txt = out / "source.txt"
        txt.write_text(P.srt_plain_text(srt), encoding="utf-8")
    _record(man, "transcribe", source_srt=_rel(job_id, srt), source_txt=_rel(job_id, txt), method=method)
    return {"source_srt": _rel(job_id, srt), "method": method}


def stage_translate(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    out = P.job_dir(job_id)
    source_srt = out / man["stages"]["transcribe"]["source_srt"]
    source_lang = man.get("source_lang", C.DEFAULT_SOURCE_LANG)
    target_lang = man.get("target_lang") or args.target_lang or C.DEFAULT_TARGET_LANG
    man["target_lang"] = target_lang
    translated = P.translate_srt(source_srt, out, source_lang, target_lang)
    _record(man, "translate", translated_srt=_rel(job_id, translated), translator=C.TRANSLATOR)
    return {"translated_srt": _rel(job_id, translated)}


def stage_tts(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    out = P.job_dir(job_id)
    translated_srt = out / man["stages"]["translate"]["translated_srt"]
    video = out / man["stages"]["download"]["video"]
    tts_voice = man.get("tts_voice") or args.tts_voice or C.DEFAULT_TTS_VOICE
    man["tts_voice"] = tts_voice
    dur = P.media_duration(video)
    audio = P.tts_from_srt(translated_srt, out, tts_voice, target_duration=dur)
    _record(man, "tts", translated_audio=_rel(job_id, audio))
    return {"translated_audio": _rel(job_id, audio)}


def stage_render(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    out = P.job_dir(job_id)
    video = out / man["stages"]["download"]["video"]
    translated_srt = out / man["stages"]["translate"]["translated_srt"]
    vtuber = C.DEFAULT_VTUBER_MODE if args.vtuber is None else args.vtuber
    dur = P.media_duration(video)
    subtitled = P.burn_subtitles(video, translated_srt, out, target_duration=dur, vtuber_mode=vtuber)
    tts_stage = man["stages"].get("tts")
    if tts_stage and _artifact_ok(job_id, tts_stage.get("translated_audio")):
        translated_audio = out / tts_stage["translated_audio"]
        full = P.make_full_video(subtitled, translated_audio, out)
    else:
        full = P.make_subtitle_only_video(subtitled, video, out)
    if vtuber:
        full = P.apply_vtuber_overlay(full, out)
    _record(man, "render", final_video=_rel(job_id, full), vtuber=vtuber)
    return {"final_video": _rel(job_id, full)}


def render_vertical(job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    """横動画→9:16縦動画（背景ぼかしパッド）＋短尺字幕。TikTok/Shorts向け。"""
    out = P.job_dir(job_id)
    render = man["stages"].get("render")
    src = out / (render["final_video"] if render else man["stages"]["download"]["video"])
    translated_srt = out / man["stages"]["translate"]["translated_srt"]
    vert = out / "vertical.mp4"
    # 9:16 (1080x1920): 前景=幅1080に収め中央、背景=拡大ぼかし
    vf = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2[bg];"
          "[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]")
    tmp = out / "vertical_base.mp4"
    P.run_cmd([C.FFMPEG_BIN, "-y", "-i", str(src), "-filter_complex", vf, "-map", "[v]",
               "-map", "0:a?", "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", str(tmp)], timeout=3600)
    # 短尺字幕(1行あたりの文字数を絞る=縦向けの短い字幕)をASSで焼く
    ass = P.make_kurage_ass(translated_srt, out, target_duration=P.media_duration(tmp),
                            cjk_line_chars=12, latin_line_chars=26)
    ass_esc = str(ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    P.run_cmd([C.FFMPEG_BIN, "-y", "-i", str(tmp), "-vf", f"subtitles='{ass_esc}'",
               "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(vert)],
              timeout=3600)
    tmp.unlink(missing_ok=True)
    _record(man, "render-vertical", vertical_video=_rel(job_id, vert))
    return {"vertical_video": _rel(job_id, vert)}


STAGE_FUNCS = {
    "download": stage_download,
    "transcribe": stage_transcribe,
    "translate": stage_translate,
    "tts": stage_tts,
    "render": stage_render,
    "render-vertical": render_vertical,
}

# 各stageの成果物キー（skip判定用）
STAGE_OUTPUT = {
    "download": ("download", "video"),
    "transcribe": ("transcribe", "source_srt"),
    "translate": ("translate", "translated_srt"),
    "tts": ("tts", "translated_audio"),
    "render": ("render", "final_video"),
    "render-vertical": ("render-vertical", "vertical_video"),
}


def run_one(stage: str, job_id: str, man: dict[str, Any], args) -> dict[str, Any]:
    skey, akey = STAGE_OUTPUT[stage]
    prev = man.get("stages", {}).get(skey, {})
    if not args.force and prev.get("done") and _artifact_ok(job_id, prev.get(akey)):
        return {"stage": stage, "skipped": True, akey: prev.get(akey)}
    res = STAGE_FUNCS[stage](job_id, man, args)
    save_manifest(job_id, man)
    return {"stage": stage, "skipped": False, **res}


def main() -> None:
    ap = argparse.ArgumentParser(description="Kurage Voice Pro staged CLI")
    ap.add_argument("stage", choices=STAGES + ["pipeline"])
    ap.add_argument("--job")
    ap.add_argument("--url")
    ap.add_argument("--source-lang")
    ap.add_argument("--target-lang")
    ap.add_argument("--tts-voice")
    ap.add_argument("--stages", help="pipeline用: 実行する段階のカンマ区切り")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-captions", action="store_true", help="captions優先を無効化しWhisperを使う")
    ap.add_argument("--vtuber", dest="vtuber", action="store_true", default=None)
    ap.add_argument("--no-vtuber", dest="vtuber", action="store_false")
    args = ap.parse_args()

    job_id = args.job or P.new_job_id()
    P.job_dir(job_id).mkdir(parents=True, exist_ok=True)
    man = load_manifest(job_id)
    for k in ("url", "source_lang", "target_lang", "tts_voice"):
        v = getattr(args, k.replace("-", "_"), None)
        if v:
            man[k] = v

    try:
        if args.stage == "pipeline":
            stages = (args.stages or "download,transcribe,translate,tts,render").split(",")
            results = []
            for st in [s.strip() for s in stages if s.strip()]:
                results.append(run_one(st, job_id, man, args))
            _out({"ok": True, "job_id": job_id, "results": results, "manifest": str(manifest_path(job_id))})
        else:
            res = run_one(args.stage, job_id, man, args)
            _out({"ok": True, "job_id": job_id, **res, "manifest": str(manifest_path(job_id))})
    except Exception as exc:
        import traceback
        _out({"ok": False, "job_id": job_id, "stage": args.stage, "error": str(exc),
              "traceback": traceback.format_exc()[-1500:]})
        sys.exit(1)


if __name__ == "__main__":
    main()
