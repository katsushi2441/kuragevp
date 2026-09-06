#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壊れた公開タイトル（Google翻訳のエラーページ本文やプレースホルダ直訳）を、
修正後の public_title_from_source で作り直して kurage 側の job JSON に書き戻す。

  python3 scripts/repair_broken_titles.py --dry     # 対象と新タイトルを表示
  python3 scripts/repair_broken_titles.py --apply   # 書き戻す（title/display_title/summary_title、seo_title も壊れていれば）
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
import pipeline as pl  # noqa: E402

JOBS = "/mnt/data/kurage/storage/jobs"
APPLY = "--apply" in sys.argv


_SUFFIX_RX = re.compile(r"\s*(\[English[^\]]*\]|【日本語[^】]*】|\[[A-Za-z ]*Subtitles\])\s*$")


def broken(t: str) -> bool:
    """壊れ判定: エラーページ本文、またはサフィックスを除いた本体がプレースホルダ。
    先頭の [Sad News] のような角括弧は本体の一部なので消さない（誤検出の前例 2026-09-07）。"""
    core = _SUFFIX_RX.sub("", t or "").strip()
    return pl.looks_like_translation_error(t) or pl.is_generic_source_title(core)


def target_lang_of(d: dict) -> str:
    t = str(d.get("title") or "")
    if "[English" in t:
        return "en"
    if "【日本語" in t:
        return "ja"
    sec = str(d.get("secondary_language_name") or "")
    return "en" if sec == "日本語" else "ja"


def main():
    n = 0
    for f in sorted(glob.glob(os.path.join(JOBS, "*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if (d.get("source") or "") != "kuragevp":
            continue
        old = str(d.get("title") or "")
        if not broken(old):
            continue
        target = target_lang_of(d)
        audio_mode = "subtitle_only" if "Subtitles]" in old and "Dub" not in old or "字幕】" in old and "吹替" not in old else "dubbed"
        source = {
            "source_title": d.get("source_title") or "",
            "tweet_text": d.get("tweet_text") or "",
            "source_platform": d.get("source_platform") or "",
        }
        fallback = d.get("primary_description") or d.get("script") or d.get("copy_summary") or ""
        title_src = "" if pl.is_generic_source_title(source["source_title"]) else source["source_title"]
        new = pl.public_title_from_source(source, target, audio_mode, fallback, title_src)
        if broken(new) or not new.strip():
            print(f"  skip {os.path.basename(f)[:-5]}: 生成不能 old={old[:40]!r}")
            continue
        n += 1
        print(f"  {os.path.basename(f)[:-5]} [{target}] {old[:38]!r} → {new!r}")
        if APPLY:
            for k in ("title", "display_title", "summary_title"):
                if k in d:
                    d[k] = new
            if broken(str(d.get("seo_title") or "")):
                d["seo_title"] = new
            if broken(str(d.get("tweet_text") or "")):
                d["tweet_text"] = new
            json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  対象 {n} 件 {'(書き戻し済み)' if APPLY else '(dry)'}")


if __name__ == "__main__":
    main()
