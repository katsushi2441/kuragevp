---
name: kuragevp-pipeline
description: Kurage Voice Pro（動画翻訳・吹替）を段階ごとに実行するSkill。各段は独立実行・成果物をjobのmanifest.jsonに記録し、後段が再利用する。途中再開・段階だけ再実行が可能。
---

# Kurage Voice Pro 段階CLI

動画URL（YouTube/Bilibili/X/直リンク/ローカル）を、翻訳・吹き替え・字幕付き動画へ。
各段階は独立に呼べ、結果はstdoutに1行JSON。成果物は `storage/jobs/<job_id>/` と `manifest.json` に記録される。

実行: `cd /home/kojima/work/kuragevp && .venv/bin/python -m backend.cli <stage> [options]`

## 段階（この順で依存）

| stage | 入力(前段成果物) | 出力 | 備考 |
|---|---|---|---|
| `download` | `--url` | `video` | YouTube等はyt-dlp、X/直リンクは既存DL。返る`job_id`を以降で使う |
| `transcribe` | video | `source_srt`,`source_txt`,`method` | **captions優先**(yt-dlpで既存字幕→無ければWhisper)。`--no-captions`でWhisper強制 |
| `translate` | source_srt | `translated_srt` | Claude翻訳(google fallback)。`--target-lang ja` |
| `tts` | translated_srt | `translated_audio` | Edge TTS吹替。`--tts-voice`。字幕は無しでも可(subtitle_only) |
| `render` | video,translated_srt,(translated_audio) | `final_video` | 字幕焼き＋吹替音声＋VTuberオーバーレイ(`--no-vtuber`で無効) |
| `render-vertical` | render or video, translated_srt | `vertical_video` | **9:16縦動画＋短尺字幕**(TikTok/Shorts向け) |

## 使い方

```bash
# 段階を1つずつ（AIエージェント向け・途中確認しながら）
.venv/bin/python -m backend.cli download --url "<URL>"          # → {"job_id":"...","video":...}
.venv/bin/python -m backend.cli transcribe --job <id>           # captions優先
.venv/bin/python -m backend.cli translate  --job <id> --target-lang ja
.venv/bin/python -m backend.cli tts        --job <id> --tts-voice ja-JP-NanamiNeural
.venv/bin/python -m backend.cli render     --job <id>
.venv/bin/python -m backend.cli render-vertical --job <id>      # 縦動画も欲しいとき

# まとめて（従来相当＋縦動画）
.venv/bin/python -m backend.cli pipeline --url "<URL>" \
  --stages download,transcribe,translate,tts,render,render-vertical
```

## 契約（安定）
- 各stageは成功時 `{"ok":true,"job_id":...,"stage":...,"skipped":bool,<成果物キー>...,"manifest":path}` を1行JSONで返す。
- **成果物が既にあれば `skipped:true` で即返る**（`--force`で再実行）。→ 「吹替だけやり直す」等が、文字起こしを再実行せずにできる。
- 失敗時 `{"ok":false,"error":...,"traceback":...}` を返し exit 1。
- 既存の常駐API(`backend/main.py`, kuragevp-api.service)はそのまま。CLIは追加レイヤーで副作用なし。

## 参考にした設計（KrillinAI）
段階分割・manifestによる成果物再利用・段ごとのSkill契約・captions優先・縦動画/短尺字幕。
