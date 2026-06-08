from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any
from urllib import request, error
import json


def _json_request(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw[:500]}") from exc
    except Exception as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"invalid json: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("invalid json object")
    return parsed


def standard_result(
    *,
    ok: bool,
    status: str,
    items: int = 0,
    metrics: dict[str, Any] | None = None,
    note: str = "",
    artifacts: list[dict[str, Any]] | None = None,
    error: Any = None,
    **extra: Any,
) -> dict[str, Any]:
    result = {
        "ok": bool(ok),
        "status": status,
        "items": int(items or 0),
        "metrics": metrics or {},
        "note": note,
        "artifacts": artifacts or [],
        "error": error,
    }
    result.update(extra)
    return result


def generate_video_job(
    url: str,
    source_lang: str = "auto",
    target_lang: str = "ja",
    tts_voice: str = "ja-JP-NanamiNeural",
    source: str = "web_online",
    api_base: str | None = None,
    poll_interval: int = 10,
    max_wait_sec: int = 7200,
    **_meta: Any,
) -> dict[str, Any]:
    api = (api_base or os.environ.get("KURAGEVP_API_BASE") or "http://exbridge.ddns.net:18202").rstrip("/")
    url = (url or "").strip()
    if not url:
        raise ValueError("url is required")

    created = _json_request("POST", api + "/generate", {
        "url": url,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "tts_voice": tts_voice,
    }, timeout=60)
    if not created.get("ok") or not created.get("job_id"):
        raise RuntimeError(f"KurageVP generate failed: {created}")

    job_id = str(created["job_id"])
    deadline = time.time() + max(60, int(max_wait_sec))
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _json_request("GET", api + "/status/" + job_id, None, timeout=30)
        status = str(last.get("status") or "")
        if status == "done":
            kurage_url = str(last.get("kurage_url") or "")
            artifacts = [{"type": "url", "label": "kurage", "url": kurage_url}] if kurage_url else []
            return standard_result(
                ok=True,
                status="ok",
                items=1,
                metrics={"created": 1, "progress": int(last.get("progress") or 100)},
                note=f"KurageVP complete job_id={job_id}",
                artifacts=artifacts,
                source=source,
                job_id=job_id,
                kurage_url=kurage_url,
                target_lang=target_lang,
                created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        if status == "error":
            raise RuntimeError(f"KurageVP error job_id={job_id}: {last.get('error') or last.get('note')}")
        time.sleep(max(3, int(poll_interval)))

    return standard_result(
        ok=False,
        status="down",
        items=0,
        metrics={"created": 0, "timeout": 1, "progress": int(last.get("progress") or 0)},
        note=f"KurageVP timeout job_id={job_id}",
        error=last,
        source=source,
        job_id=job_id,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
