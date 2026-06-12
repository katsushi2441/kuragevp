"""RQDB4AI job wrappers for Kurage Voice Pro."""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_API = os.environ.get("KURAGEVP_API", "http://127.0.0.1:18302").rstrip("/")


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json", "User-Agent": "rqdb4ai-kuragevp/0.1"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"KurageVP API failed http={exc.code} url={url} body={raw[:1000]}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"KurageVP API returned non-object response: {raw[:1000]}")
    return parsed


def generate_video_job(
    url: str,
    source_lang: str = "auto",
    target_lang: str = "ja",
    tts_voice: str = "ja-JP-NanamiNeural",
    source: str = "rqdb4ai",
    original_url: str = "",
    source_title: str = "",
    source_platform: str = "",
    api_base: str = DEFAULT_API,
    wait: bool = True,
    poll_seconds: int = 10,
    timeout_seconds: int = 7200,
    **_: Any,
) -> dict[str, Any]:
    """Queue a KurageVP translation job and wait for completion by default."""
    if not str(url or "").strip():
        raise RuntimeError("url is required")
    api_base = api_base.rstrip("/")
    payload = {
        "url": url,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "tts_voice": tts_voice,
        "original_url": original_url or url,
        "source_title": source_title,
        "source_platform": source_platform,
    }
    created = _json_request("POST", api_base + "/generate", payload, timeout=60)
    if not created.get("ok") or not created.get("job_id"):
        raise RuntimeError(f"KurageVP enqueue failed: {created}")
    job_id = str(created["job_id"])
    if not wait:
        return {"ok": True, "status": "queued", "items": 1, "job_id": job_id, "source": source}

    deadline = time.time() + max(60, int(timeout_seconds))
    last: dict[str, Any] = {}
    terminal = {"done", "failed", "error"}
    while time.time() < deadline:
        last = _json_request("GET", api_base + "/status/" + job_id, timeout=30)
        status = str(last.get("status") or "")
        if status in terminal:
            if status == "done":
                return {
                    "ok": True,
                    "status": "ok",
                    "items": 1,
                    "job_id": job_id,
                    "kurage_job_id": last.get("kurage_job_id"),
                    "kurage_url": last.get("kurage_url"),
                    "note": last.get("note") or "KurageVP video generated",
                    "source": source,
                }
            raise RuntimeError(f"KurageVP job failed job_id={job_id} status={status} error={last.get('error')}")
        time.sleep(max(2, int(poll_seconds)))

    raise RuntimeError(f"KurageVP job timed out job_id={job_id} last_status={last}")
