# Kurage Voice Pro Architecture

## 役割分担

- Kurage: UI、ジョブ一覧、進捗表示、動画成果物の見せ方を流用する。
- UMedia: URL/X投稿から動画を取得する考え方を流用する。
- Voice-Pro: 音声抽出、Whisper字幕、翻訳、TTS、ffmpegによる音声差し替え・字幕処理の部品を利用する。

## サーバ構成

- PHP画面: `kurage.exbridge.jp/kuragevp.php`
- Python API: `http://exbridge.ddns.net:18302`
- ローカル作業ディレクトリ: `/home/kojima/work/kuragevp`
- 公開先: heteml `/web/kurage_exbridge_jp`
- Kurage動画公開先: `/home/kojima/work/kurage/storage/jobs`

## 初期API

- `GET /health`
- `POST /generate`
- `GET /status/{job_id}`
- `GET /jobs`
- `GET /file/{job_id}/{kind}`

## 成果物

- `source.wav`: 元動画から抽出した音声
- `source.srt`: 文字起こし字幕
- `translated.<lang>.srt`: 翻訳字幕
- `translated_voice.m4a`: 翻訳音声
- `subtitled.mp4`: 翻訳字幕付き動画
- `dubbed.mp4`: 翻訳音声差し替え動画
- `translated_subtitled_dubbed.mp4`: 翻訳字幕 + 翻訳音声動画
- Kurage公開動画: `kurage/storage/jobs/{job_id}/output.mp4`
- Kurage公開メタデータ: `kurage/storage/jobs/{job_id}.json`

## 注意

TTS音声を字幕タイムスタンプへ完全同期するには、Voice-Proの `EdgeTTS.srt_to_voice()` や F5-TTS/CosyVoice の同期ロジックを直接利用する方向へ寄せる。初期版はまず成果物生成を優先し、音声は元動画の声ではなく Edge-TTS を使う。
## Shared TTS pronunciation

Kurage Voice Pro normalizes only the text sent to TTS through the shared Kurage normalizer. Subtitles and job metadata remain unchanged. The default normalizer path is `/home/kojima/work/kurage/backend` and can be overridden with `KURAGE_TTS_NORMALIZER_DIR`. Product names and AI/OSS terms should be added to Kurage `config/tts_pronunciation.json`, not duplicated here.

