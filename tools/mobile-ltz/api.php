<?php
// Same-origin authenticated proxy; the browser never receives bridge credentials.
declare(strict_types=1);
$cfg = require __DIR__ . '/bridge-config.php';
header('Cache-Control: no-store, max-age=0, must-revalidate');
header('Expires: 0');
header('X-Content-Type-Options: nosniff');
function fail(int $status, string $message): never {
    http_response_code($status); header('Content-Type: application/json');
    echo json_encode(['ok'=>false, 'error'=>$message]); exit;
}
$path = $_GET['path'] ?? '';
// Presentation URLs may carry an asset revision; it is never an upstream route.
$path = explode('?', $path, 2)[0];
$client = preg_match('/^client\/(?:manifest|(?:[a-f0-9]{32}|latest)\/(?:index\.html|mobile\.css|mobile\.js|viewport\.js|live-game\.js|network\.js|joint-rig\.js))$/D', $path) === 1;
if (!$client && !in_array($path, ['login','state','events','command','renderer.js'], true) && !str_starts_with($path, 'assets/')) fail(404,'Not found');
if (str_contains($path,'..') || str_contains($path,'\\') || str_contains($path,'#')) fail(400,'Invalid path');
$post = in_array($path, ['login','command'], true);
if ($_SERVER['REQUEST_METHOD'] !== ($post ? 'POST' : 'GET')) fail(405,'Method not allowed');
if ($post && ($_SERVER['HTTP_ORIGIN'] ?? '') !== 'https://mecharena.eu') fail(403,'Origin rejected');
if ($post && !str_starts_with($_SERVER['CONTENT_TYPE'] ?? '', 'application/json')) fail(415,'JSON required');
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 4096) fail(413,'Request too large');
session_name('mobile_ltz');
session_start(['cookie_secure'=>true,'cookie_httponly'=>true,'cookie_samesite'=>'Strict','cookie_path'=>'/TowerDefence/','use_strict_mode'=>true]);
if ($path === 'login') {
    if (time() - ($_SESSION['login_at'] ?? 0) < 2) fail(429,'Try again shortly');
    $_SESSION['login_at'] = time();
}
$auth = $_SESSION['auth'] ?? '';
session_write_close(); // Do not hold the session lock across live events.
// Only published frontend files are public; live game data still needs login.
if ($path !== 'login' && !$client && !$auth) fail(401,'Sign in to Green to join.');
$ch = curl_init(rtrim($cfg['url'],'/') . '/' . implode('/', array_map('rawurlencode',explode('/',$path))));
$headers = ['X-Mobile-Bridge: '.$cfg['secret'],'ngrok-skip-browser-warning: 1','Accept-Encoding: identity'];
if ($auth) $headers[] = 'X-Mobile-Auth: '.$auth;
if ($post) $headers[] = 'Content-Type: application/json';
curl_setopt_array($ch,[CURLOPT_HTTPHEADER=>$headers,CURLOPT_CONNECTTIMEOUT=>8,CURLOPT_TIMEOUT=>$path==='events'?55:15,CURLOPT_FOLLOWLOCATION=>false]);
if ($post) curl_setopt_array($ch,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>file_get_contents('php://input')]);
if ($client && $path !== 'client/manifest') {
    curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);
    curl_setopt($ch,CURLOPT_HEADERFUNCTION,function($curl,$line){
        if (stripos($line,'X-Mobile-Build:')===0) header(trim($line));
        return strlen($line);
    });
    $raw=curl_exec($ch);$code=(int)curl_getinfo($ch,CURLINFO_HTTP_CODE);
    $type=(string)curl_getinfo($ch,CURLINFO_CONTENT_TYPE);curl_close($ch);
    if ($raw===false || $code!==200) {
        if (defined('MOBILE_ENTRY')) {
            http_response_code(503);header('Content-Type: text/html; charset=utf-8');
            echo '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="5"><title>mobile ltz</title><style>body{background:#101715;color:#e5f9ec;font:18px -apple-system,system-ui;padding:12vh 8vw}button{font:inherit;padding:12px}</style></head><body><h1>Waiting for Gamemaster</h1><p>The local game server is offline or restarting. This page will reconnect automatically.</p><button onclick="location.reload()">Refresh</button></body></html>';exit;
        }
        fail($code===409?409:503,$code===409?'Game server restarted. Refresh the mobile page.':'Mobile interface unavailable. Check the local game server.');
    }
    header('Content-Type: '.$type);echo $raw;exit;
}
if ($path === 'login') {
    curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);
    $raw=curl_exec($ch);$code=(int)curl_getinfo($ch,CURLINFO_HTTP_CODE);curl_close($ch);
    if ($raw===false) fail(503,'Local Gamemaster is offline.');
    $result=json_decode($raw,true);
    if ($code!==200 || empty($result['auth'])) fail($code===401?401:503,$code===401?'Wrong Green password.':'Local Gamemaster is offline.');
    session_start();session_regenerate_id(true);$_SESSION['auth']=$result['auth'];session_write_close();
    header('Content-Type: application/json');echo '{"ok":true}';exit;
}
// Never pass a tunnel HTML error page or a truncated JSON body to Safari.
if ($path === 'state' || $path === 'command' || $path === 'client/manifest') {
    curl_setopt($ch,CURLOPT_RETURNTRANSFER,true);
    $raw=curl_exec($ch);$code=(int)curl_getinfo($ch,CURLINFO_HTTP_CODE);curl_close($ch);
    if ($raw===false) fail(503,'Local Gamemaster connection was interrupted. Try again.');
    $result=json_decode($raw,true);
    if (!is_array($result) || json_last_error() !== JSON_ERROR_NONE) fail(502,'Local relay returned an invalid response. Check that Gamemaster and the tunnel are running.');
    http_response_code($code>=200 && $code<=599 ? $code : 502);
    header('Content-Type: application/json');echo json_encode($result);exit;
}
if ($path==='events') {
    header('X-Accel-Buffering: no');header('Cache-Control: no-store, no-transform');
    header('X-Mobile-Stream: 2');
    ini_set('zlib.output_compression','0');set_time_limit(65);
    while(ob_get_level())ob_end_flush();
}
$started=false;
curl_setopt($ch,CURLOPT_HEADERFUNCTION,function($curl,$line) use (&$started){
    if (preg_match('/^HTTP\/\S+ (\d+)/',$line,$m)) http_response_code((int)$m[1]);
    if (stripos($line,'Content-Type:')===0) header(trim($line));
    return strlen($line);
});
$eventBuffer='';
curl_setopt($ch,CURLOPT_WRITEFUNCTION,function($curl,$chunk) use (&$started,$path,&$eventBuffer){
    if ($path!=='events') {$started=true;echo $chunk;return strlen($chunk);}
    if (!$started) {
        // A complete comment also pushes response headers through common
        // proxy buffers. Events remain individually framed below.
        echo 'retry: 1000'."\n".': '.str_repeat(' ',4096)."\n\n";
        $started=true;flush();
    }
    $eventBuffer.=$chunk;
    while (($end=strpos($eventBuffer,"\n\n"))!==false) {
        $frame=substr($eventBuffer,0,$end+2);$eventBuffer=substr($eventBuffer,$end+2);
        echo $frame;flush();
    }
    if (connection_aborted()) return 0;
    return strlen($chunk);
});
$ok=curl_exec($ch);curl_close($ch);
if (!$ok && !$started) fail(503,'Local Gamemaster is offline.');
