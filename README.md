# Kurage Voice Pro

Kurage Voice Pro (`kuragevp`) は、URLから動画を取得し、音声抽出、文字起こし、翻訳、翻訳字幕、翻訳音声、吹き替え動画生成までを行うためのプロジェクトです。

## 目的

- `url2ai` の UMedia が持つ URL/X動画取得の考え方を使う
- `kurage` の FastAPI + PHP proxy + 共通ログイン構成を流用する
- `voice-pro` の音声認識、翻訳、TTS、ffmpeg処理を利用する
- 元動画に翻訳字幕を入れる
- 元動画に翻訳音声を入れる

## 構成

- `web/kuragevp.php`  
  管理画面。共通Xログインを使う。
- `backend/main.py`  
  FastAPI。ジョブ投入、進捗確認、動画/字幕/音声取得。
- `backend/pipeline.py`  
  動画取得から翻訳動画生成までの処理。
- `vendor/voice-pro/`  
  `abus-aikorea/voice-pro` をcloneしたもの。重い依存は別途セットアップする。

## 処理フロー

1. URLから動画を取得
2. ffmpegで音声抽出
3. Whisper/Faster-WhisperでSRT生成
4. subtitleを翻訳
5. 翻訳SRTを動画に焼き込み
6. 翻訳SRTをTTS音声化
7. 翻訳音声を元動画に差し替え
8. ジョブ詳細から成果物を確認

## 初期実装方針

初期版はCLIで安定する経路を優先する。

- 動画取得: `umedia.php` と同じくFxTwitter + curlでX動画を取得。通常の動画URLはcurlで直接取得。
- 音声抽出/字幕焼き込み/音声差し替え: `ffmpeg`
- 文字起こし: `faster-whisper` があれば使用。なければエラーとして依存追加を促す。
- 翻訳: `deep-translator` があれば使用。
- TTS: `edge-tts` があれば使用。

voice-pro本体の関数は、依存が揃った段階で順次直接呼び出しへ寄せる。

## 起動

```bash
cd /home/kojima/work/kuragevp
mkdir -p vendor
git clone https://github.com/abus-aikorea/voice-pro.git vendor/voice-pro
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 18302
```

PHP側は `web/` 配下を `kurage.exbridge.jp` の公開ディレクトリ `/web/kurage_exbridge_jp` へ配置する。

生成完了した翻訳字幕・翻訳音声付き動画は、Kurageの動画として `/home/kojima/work/kurage/storage/jobs` に公開メタデータと動画ファイルを保存する。
