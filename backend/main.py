from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

try:
    from .config import DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG, DEFAULT_TTS_VOICE, JOBS_DIR, PORT, VOICE_PRO_DIR
    from .pipeline import load_job, new_job_id, run_pipeline, update_job
except ImportError:
    from config import DEFAULT_SOURCE_LANG, DEFAULT_TARGET_LANG, DEFAULT_TTS_VOICE, JOBS_DIR, PORT, VOICE_PRO_DIR
    from pipeline import load_job, new_job_id, run_pipeline, update_job


app = FastAPI(title="Kurage Voice Pro API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def allowed_client_ips() -> set[str]:
    raw = os.environ.get("KURAGEVP_ALLOWED_CLIENT_IPS", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()}


@app.middleware("http")
async def restrict_client_ip(request: Request, call_next):
    allowed = allowed_client_ips()
    client_host = request.client.host if request.client else ""
    if allowed and client_host not in allowed:
        return JSONResponse(
            {"ok": False, "error": "forbidden", "client": client_host},
            status_code=403,
        )
    return await call_next(request)


class GenerateRequest(BaseModel):
    url: str
    source_lang: str = DEFAULT_SOURCE_LANG
    target_lang: str = DEFAULT_TARGET_LANG
    tts_voice: str = DEFAULT_TTS_VOICE
    audio_mode: str = "dubbed"
    original_url: str = ""
    source_title: str = ""
    source_platform: str = ""


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "kuragevp",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "voice_pro_dir": str(VOICE_PRO_DIR),
        "voice_pro_exists": VOICE_PRO_DIR.exists(),
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    job_id = new_job_id()
    update_job(
        job_id,
        status="queued",
        progress=0,
        url=url,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        tts_voice=req.tts_voice,
        audio_mode=req.audio_mode,
        original_url=req.original_url.strip(),
        source_title=req.source_title.strip(),
        source_platform=req.source_platform.strip(),
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    t = threading.Thread(
        target=run_pipeline,
        args=(job_id, url, req.source_lang, req.target_lang, req.tts_voice),
        kwargs={
            "audio_mode": req.audio_mode,
            "original_url": req.original_url.strip(),
            "source_title": req.source_title.strip(),
            "source_platform": req.source_platform.strip(),
        },
        daemon=True,
    )
    t.start()
    return {"ok": True, "job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    resp: dict[str, Any] = {
        "ok": True,
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "url": job.get("url"),
        "source_lang": job.get("source_lang"),
        "target_lang": job.get("target_lang"),
        "tts_voice": job.get("tts_voice"),
        "audio_mode": job.get("audio_mode", "dubbed"),
        "note": job.get("note"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }
    if job.get("status") == "done":
        resp.update({
            "source_srt_url": f"/file/{job_id}/source_srt",
            "translated_srt_url": f"/file/{job_id}/translated_srt",
            "translated_audio_url": f"/file/{job_id}/translated_audio",
            "dubbed_video_url": f"/file/{job_id}/dubbed_video",
            "final_video_url": f"/file/{job_id}/final_video",
            "kurage_job_id": job.get("kurage_job_id"),
            "kurage_url": job.get("kurage_url"),
        })
    return resp


@app.get("/jobs")
def jobs(limit: int = 20):
    files = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:limit]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "job_id": p.stem,
                "status": d.get("status"),
                "progress": d.get("progress", 0),
                "url": d.get("url"),
                "target_lang": d.get("target_lang"),
                "audio_mode": d.get("audio_mode", "dubbed"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
                "note": d.get("note"),
                "kurage_url": d.get("kurage_url"),
            })
        except Exception:
            pass
    return {"ok": True, "jobs": out}


@app.get("/file/{job_id}/{kind}")
def file(job_id: str, kind: str):
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    mapping = {
        "source_srt": ("source_srt", "text/plain", f"kuragevp_{job_id}_source.srt"),
        "translated_srt": ("translated_srt", "text/plain", f"kuragevp_{job_id}_translated.srt"),
        "translated_audio": ("translated_audio", "audio/mp4", f"kuragevp_{job_id}_translated.m4a"),
        "dubbed_video": ("dubbed_video", "video/mp4", f"kuragevp_{job_id}_dubbed.mp4"),
        "final_video": ("final_video", "video/mp4", f"kuragevp_{job_id}_final.mp4"),
    }
    if kind not in mapping:
        raise HTTPException(status_code=404, detail="Unknown file kind")
    key, media_type, filename = mapping[kind]
    path = Path(job.get(key) or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path), media_type=media_type, filename=filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
