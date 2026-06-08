<?php
require_once __DIR__ . '/config.php';
require_once __DIR__ . '/auth_common.php';
date_default_timezone_set('Asia/Tokyo');

$THIS_FILE = 'kuragevp.php';
$SITE_NAME = 'Kurage Voice Pro';
$KURAGEVP_API = rtrim(getenv('KURAGEVP_API') ?: 'http://exbridge.ddns.net:18202', '/');

if (isset($_GET['kvp_logout'])) {
    header('Location: ' . url2ai_auth_logout_url('/' . $THIS_FILE));
    exit;
}
if (isset($_GET['kvp_login'])) {
    header('Location: ' . url2ai_auth_login_url('/' . $THIS_FILE));
    exit;
}

$auth = url2ai_auth_bootstrap();
$logged_in = $auth['logged_in'];
$session_user = $auth['session_user'];
$is_admin = $auth['is_admin'];

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

function kvp_api($method, $path, $payload = null, $timeout = 20) {
    global $KURAGEVP_API;
    $ch = curl_init($KURAGEVP_API . $path);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_HTTPHEADER, array('Content-Type: application/json', 'Accept: application/json'));
    if ($payload !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE));
    }
    $body = curl_exec($ch);
    $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    curl_close($ch);
    if ($body === false || $err) {
        return array('ok' => false, 'status' => 0, 'error' => $err ?: 'request failed');
    }
    $json = json_decode($body, true);
    if (!is_array($json)) { $json = array('raw' => $body); }
    return array('ok' => ($status >= 200 && $status < 300), 'status' => $status, 'data' => $json);
}

$proxy = isset($_GET['proxy']) ? $_GET['proxy'] : '';
if ($proxy !== '') {
    if ($proxy === 'file' && isset($_GET['job_id'], $_GET['kind'])) {
        $jid = preg_replace('/[^a-zA-Z0-9]/', '', $_GET['job_id']);
        $kind = preg_replace('/[^a-zA-Z0-9_]/', '', $_GET['kind']);
        $url = $KURAGEVP_API . '/file/' . $jid . '/' . $kind;
        $ch = curl_init($url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 120);
        $data = curl_exec($ch);
        $ctype = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        if ($data && $code === 200) {
            header('Content-Type: ' . ($ctype ?: 'application/octet-stream'));
            echo $data;
        } else {
            header('HTTP/1.1 404 Not Found');
            echo 'not found';
        }
        exit;
    }
    header('Content-Type: application/json; charset=utf-8');
    if ($proxy === 'generate' && $_SERVER['REQUEST_METHOD'] === 'POST') {
        if (!$is_admin) {
            echo json_encode(array('ok' => false, 'error' => 'admin login required'), JSON_UNESCAPED_UNICODE);
            exit;
        }
        $body = json_decode(file_get_contents('php://input'), true);
        $res = kvp_api('POST', '/generate', is_array($body) ? $body : array(), 30);
        echo json_encode(isset($res['data']) ? $res['data'] : array('ok' => false, 'error' => $res['error']), JSON_UNESCAPED_UNICODE);
    } elseif ($proxy === 'status' && isset($_GET['job_id'])) {
        $jid = preg_replace('/[^a-zA-Z0-9]/', '', $_GET['job_id']);
        $res = kvp_api('GET', '/status/' . $jid, null, 15);
        echo json_encode(isset($res['data']) ? $res['data'] : array('ok' => false), JSON_UNESCAPED_UNICODE);
    } elseif ($proxy === 'jobs') {
        $res = kvp_api('GET', '/jobs?limit=20', null, 15);
        echo json_encode(isset($res['data']) ? $res['data'] : array('ok' => false, 'jobs' => array()), JSON_UNESCAPED_UNICODE);
    } elseif ($proxy === 'health') {
        $res = kvp_api('GET', '/health', null, 8);
        echo json_encode(isset($res['data']) ? $res['data'] : array('ok' => false), JSON_UNESCAPED_UNICODE);
    } else {
        echo json_encode(array('ok' => false, 'error' => 'unknown proxy'), JSON_UNESCAPED_UNICODE);
    }
    exit;
}

$health = kvp_api('GET', '/health', null, 5);
$api_ok = $health['ok'] && !empty($health['data']['ok']);
?><!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?php echo h($SITE_NAME); ?></title>
<meta name="description" content="URL動画から音声を抽出し、文字起こし、翻訳、翻訳字幕、翻訳音声、吹き替え動画を生成するKurage Voice Pro。">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://kurage.exbridge.jp/kuragevp.php">
<style>
:root{--bg:#f6f8f8;--surface:#fff;--border:#dbe5e8;--accent:#007f96;--accent2:#102a43;--text:#132329;--muted:#60717a;--green:#2f8f45;--red:#b83232}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;font-size:14px}
header{background:#fff;border-bottom:1px solid var(--border);padding:14px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:2}
.brand{font-weight:900;font-size:18px;text-decoration:none;color:var(--text)}.brand span{color:var(--accent)}
.userbar{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px}.btn-sm{border:1px solid var(--border);border-radius:6px;padding:5px 10px;text-decoration:none;color:var(--muted);background:#fff}
.wrap{max-width:980px;margin:0 auto;padding:24px}.hero{padding:28px 0 16px}.hero h1{font-size:28px;margin:0 0 8px}.hero p{color:var(--muted);line-height:1.8;margin:0;max-width:760px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin:16px 0;box-shadow:0 2px 10px rgba(15,35,45,.04)}.card h2{font-size:14px;margin:0;padding:12px 16px;border-bottom:1px solid var(--border);color:var(--muted);letter-spacing:.04em;text-transform:uppercase}.body{padding:16px}
.row{display:grid;grid-template-columns:1fr 140px 140px;gap:10px}.row2{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
input,select{width:100%;border:1px solid #c9d8dd;border-radius:8px;padding:11px 12px;font:inherit;background:#fff}button{border:none;border-radius:8px;background:var(--accent);color:#fff;font-weight:800;padding:11px 18px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}
.status{display:none}.bar{height:8px;background:#e3ecef;border-radius:999px;overflow:hidden;margin:12px 0}.fill{height:100%;background:linear-gradient(90deg,var(--accent),#2f8f45);width:0;transition:width .25s}.note{color:var(--muted);line-height:1.8}.badge{display:inline-block;border-radius:999px;padding:4px 9px;background:#e8f6f8;color:var(--accent);font-weight:800;font-size:12px}
.links{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.links a{border:1px solid var(--border);border-radius:7px;padding:7px 10px;text-decoration:none;color:var(--accent);background:#fff;font-weight:700}
.jobs{display:grid;gap:8px}.job{border:1px solid var(--border);border-radius:8px;background:#fbfdfd;padding:10px;display:grid;grid-template-columns:120px 1fr 70px;gap:10px;align-items:center}.job small{color:var(--muted)}
.api{font-size:12px;font-weight:800;color:<?php echo $api_ok ? 'var(--green)' : 'var(--red)'; ?>}
@media(max-width:720px){.row{grid-template-columns:1fr}.job{grid-template-columns:1fr}.wrap{padding:16px}header{align-items:flex-start;gap:10px;flex-direction:column}}
</style>
</head>
<body>
<header>
  <a class="brand" href="<?php echo h($THIS_FILE); ?>">Kurage <span>Voice Pro</span></a>
  <div class="userbar">
    <span class="api">API <?php echo $api_ok ? 'OK' : '未確認'; ?></span>
    <?php if ($logged_in): ?>
      <span>@<strong><?php echo h($session_user); ?></strong></span>
      <a class="btn-sm" href="?kvp_logout=1">logout</a>
    <?php else: ?>
      <a class="btn-sm" href="?kvp_login=1">Xでログイン</a>
    <?php endif; ?>
  </div>
</header>
<main class="wrap">
  <section class="hero">
    <h1>動画翻訳・字幕・吹き替え生成</h1>
    <p>URL動画を取得し、音声抽出、文字起こし、翻訳、翻訳字幕、翻訳音声、吹き替え動画生成までを一つの流れで処理します。</p>
  </section>

  <?php if (!$is_admin): ?>
    <div class="card"><h2>Login</h2><div class="body"><p class="note">管理者アカウントでログインしてください。</p><p><a class="btn-sm" href="?kvp_login=1">Xでログイン</a></p></div></div>
  <?php else: ?>
    <section class="card">
      <h2>New Job</h2>
      <div class="body">
        <div class="row">
          <input id="url" type="text" placeholder="YouTube / X / 動画URL またはサーバ上の動画パス">
          <select id="target_lang">
            <option value="ja">日本語</option>
            <option value="en">English</option>
            <option value="ko">한국어</option>
            <option value="zh-CN">中文</option>
          </select>
          <select id="voice">
            <option value="ja-JP-NanamiNeural">Nanami JP</option>
            <option value="ja-JP-KeitaNeural">Keita JP</option>
            <option value="en-US-JennyNeural">Jenny EN</option>
            <option value="ko-KR-SunHiNeural">SunHi KO</option>
          </select>
        </div>
        <div class="row2">
          <button id="run">生成開始</button>
          <span class="note">source language は初期版では auto です。</span>
        </div>
      </div>
    </section>
  <?php endif; ?>

  <section id="status" class="card status">
    <h2>Status</h2>
    <div class="body">
      <span id="badge" class="badge">queued</span>
      <div class="bar"><div id="fill" class="fill"></div></div>
      <div id="note" class="note"></div>
      <div id="outputs" class="links"></div>
    </div>
  </section>

  <section class="card">
    <h2>Recent Jobs</h2>
    <div class="body"><div id="jobs" class="jobs"><p class="note">読み込み中...</p></div></div>
  </section>
</main>
<script>
const isAdmin = <?php echo $is_admin ? 'true' : 'false'; ?>;
const qs = s => document.querySelector(s);
function esc(s){return String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
async function api(path, opt){const r=await fetch(path,opt);return await r.json();}
async function loadJobs(){
  const d = await api('?proxy=jobs');
  const box = qs('#jobs');
  if(!d.jobs || !d.jobs.length){box.innerHTML='<p class="note">まだジョブはありません。</p>';return;}
  box.innerHTML = d.jobs.map(j=>`<div class="job" onclick="watch('${esc(j.job_id)}')"><b>${esc(j.status)}</b><div><div>${esc(j.url)}</div><small>${esc(j.created_at||'')}</small></div><small>${esc(j.progress)}%</small></div>`).join('');
}
async function watch(jobId){
  qs('#status').style.display='block';
  const d = await api('?proxy=status&job_id='+encodeURIComponent(jobId));
  qs('#badge').textContent = d.status || 'unknown';
  qs('#fill').style.width = (d.progress || 0) + '%';
  qs('#note').textContent = d.error || d.note || '';
  const outputs = qs('#outputs');
  outputs.innerHTML = '';
  if(d.status === 'done'){
    outputs.innerHTML = [
      ['翻訳字幕','translated_srt'],
      ['翻訳音声','translated_audio'],
      ['吹き替え動画','dubbed_video'],
      ['字幕+吹き替え動画','final_video']
    ].map(x=>`<a target="_blank" href="?proxy=file&job_id=${encodeURIComponent(jobId)}&kind=${x[1]}">${x[0]}</a>`).join('');
    if(d.kurage_url){
      outputs.innerHTML += `<a target="_blank" href="${esc(d.kurage_url)}">Kurage公開ページ</a>`;
    }
  } else if(d.status !== 'error') {
    setTimeout(()=>watch(jobId), 5000);
  }
}
if(isAdmin){
  qs('#run').addEventListener('click', async ()=>{
    const url = qs('#url').value.trim();
    if(!url){alert('URLを入力してください');return;}
    qs('#run').disabled = true;
    try{
      const d = await api('?proxy=generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url,source_lang:'auto',target_lang:qs('#target_lang').value,tts_voice:qs('#voice').value})});
      if(!d.ok){alert(d.error || '登録失敗');return;}
      await watch(d.job_id);
      await loadJobs();
    } finally {
      qs('#run').disabled = false;
    }
  });
}
loadJobs();
</script>
</body>
</html>
