# Kurage Voice Pro Workflow

## ユーザー要件

新しいプロジェクト `Kurage Voice Pro` を `kuragevp` フォルダに作る。

- URLから動画を取得する
- 動画から音声を取得する
- 音声をテキスト化する
- テキストを翻訳する
- 翻訳テキストを音声化する
- 翻訳音声を動画に入れる
- 翻訳字幕を動画に入れる
- `voice-pro` をcloneし、その機能を使って実現する
- `kurage` の基本機能を流用する
- `url2ai` の `umedia` の動画取得思想を流用する
- 共通ログイン、共通セッションを使う

## 現在の実装状況

作成済み:

- `/home/kojima/exdirect/kuragevp`
- `/home/kojima/exdirect/kuragevp/vendor/voice-pro`
- `/home/kojima/exdirect/kuragevp/backend/main.py`
- `/home/kojima/exdirect/kuragevp/backend/pipeline.py`
- `/home/kojima/exdirect/kuragevp/web/kuragevp.php`
- `/home/kojima/exdirect/kuragevp/web/auth_common.php`
- `/home/kojima/exdirect/kuragevp/web/config.php`

確認済み:

- Python import / syntax OK
- PHP syntax OK
- `voice-pro` clone OK
- API health 関数 OK

## 初期版の処理

画面の「生成開始」は `oss.php` と同じ考え方で、RQDB4AIに `kuragevp_jobs.generate_video_job` をenqueueする。
PHP側はキュー投入だけを行い、RQDB4AI本体は触らない。
画面にはキュー登録済みのRQ job IDを表示する。

API単体で動作確認する場合は `POST /generate` に動画URLを渡す。

処理:

1. `yt-dlp` で動画取得
2. `ffmpeg` で `source.wav` 抽出
3. `faster-whisper` で `source.srt` / `source.txt` 作成
4. `deep-translator` で `translated.<lang>.srt` 作成
5. `edge-tts` で `translated_voice.m4a` 作成
6. `ffmpeg` で `subtitled.mp4` 作成
7. `ffmpeg` で `dubbed.mp4` 作成
8. `ffmpeg` で `translated_subtitled_dubbed.mp4` 作成

## Voice-Proから使う部品

直接参考にしたファイル:

- `vendor/voice-pro/app/abus_downloader.py`
- `vendor/voice-pro/app/abus_subtitle.py`
- `vendor/voice-pro/app/abus_translate_deep.py`
- `vendor/voice-pro/app/abus_tts_edge.py`
- `vendor/voice-pro/app/abus_ffmpeg.py`

初期実装は、voice-proの設計に沿ってCLIで安定実行する形にしている。
依存が揃ったら、以下を直接呼び出す方向へ寄せる。

- `YoutubeDownloader.yt_download`
- `DeepTranslator.translate_file`
- `EdgeTTS.srt_to_voice`
- `ffmpeg_replace_audio`
- `ffmpeg_extract_audio`

## 公開時の想定

PHP:

```text
web/kuragevp.php -> /web/kurage_exbridge_jp/kuragevp.php
web/auth_common.php -> /web/kurage_exbridge_jp/auth_common.php
web/config.php -> /web/kurage_exbridge_jp/config.php
```

XログインのOAuth入口は `kurage.exbridge.jp` には置かない。
`auth_common.php` から `https://aiknowledgecms.exbridge.jp/aiknowledgesns.php` へ飛ばし、戻り先だけ `https://kurage.exbridge.jp/...` にする。

API:

```text
http://exbridge.ddns.net:18202
```

ルーターで外部公開する場合は `18202` を開放する。

生成完了後はKurage動画としても公開する。

```text
/home/kojima/exdirect/kurage/storage/jobs/{job_id}.json
/home/kojima/exdirect/kurage/storage/jobs/{job_id}/output.mp4
/home/kojima/exdirect/kurage/storage/jobs/{job_id}/thumbnail.jpg
https://kurage.exbridge.jp/kuragev.php?id={job_id}
```

## 次にやること

- `.venv` を作成して `backend/requirements.txt` を入れる
- 実動画URLで `yt-dlp` と `ffmpeg` の動作確認
- `faster-whisper` のGPU/CPU設定を調整
- 長尺動画向けにジョブタイムアウト、分割処理を追加
- TTS音声のタイミング同期精度を上げる
- `voice-pro` の `EdgeTTS.srt_to_voice()` 直接利用へ寄せる

## RQDB4AI連携

- PHP: `web/kuragevp.php`
- RQDB4AI callable: `kuragevp_jobs.generate_video_job`
- callableの動作:
  1. `KURAGEVP_API_BASE` または `http://exbridge.ddns.net:18202` に `POST /generate`
  2. `/status/{job_id}` をpoll
  3. 完了したら `items=1`, `status=ok`, `kurage_url` を返す

RQDB4AI本体にはKurageVP固有コードを入れない。KurageVPのjob callableはKurageVPリポジトリ側のアプリ固有コードとして管理する。
