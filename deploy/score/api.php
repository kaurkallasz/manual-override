<?php
declare(strict_types=1);
ini_set('display_errors','0');
require __DIR__.'/core.php';
$cfg=require __DIR__.'/config.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header("Content-Security-Policy: default-src 'none'; frame-ancestors 'none'");
function respond(array $v,int $status=200): never {http_response_code($status);echo jsondata($v);exit;}
try {
    if(($_SERVER['HTTPS']??'')!=='on' && !($cfg['local_test']??false))fail('HTTPS required',400);
    $action=$_GET['action']??'state';$method=$_SERVER['REQUEST_METHOD'];
    $reads=['state','results','result','admin'];
    if($method!==(in_array($action,$reads,true)?'GET':'POST'))fail('Method not allowed',405);
    $data=[];
    if($method==='POST'){
        if(!str_starts_with(strtolower($_SERVER['CONTENT_TYPE']??''),'application/json'))fail('JSON required',415);
        if((int)($_SERVER['CONTENT_LENGTH']??0)>2000000)fail('Upload exceeds 2 MB',413);
        $raw=file_get_contents('php://input',false,null,0,2000001);
        if(strlen($raw)>2000000)fail('Upload exceeds 2 MB',413);
        $data=json_decode($raw,true,64,JSON_THROW_ON_ERROR);
        if(!(json_decode($raw,false,64,JSON_THROW_ON_ERROR) instanceof stdClass))fail('JSON object required');
        $origin=$_SERVER['HTTP_ORIGIN']??'';
        if(in_array($action,['pair','ingest','request-pairing','pairing-status','cancel-pairing-request'],true)) {if($origin!=='')fail('Uploads are available only to game servers',403);}
        elseif($origin!==$cfg['origin'])fail('Same-origin request required',403);
    }
    $db=database($cfg);cleanup($db);
    $ip=codehash($_SERVER['REMOTE_ADDR']??'unknown');
    $mailer=function($email,$subject,$body)use($cfg){
        $from=email_value($cfg['from']);
        return mail($email,$subject,$body,['From'=>'MechArena Scoreboard <'.$from.'>','Content-Type'=>'text/plain; charset=UTF-8','MIME-Version'=>'1.0'], '-f'.$from);
    };
    if(in_array($action,['request-pairing','pairing-status','cancel-pairing-request'],true)){
        // Device requests never use a browser session. Possession of the local
        // secret is required for status/cancellation; it grants no upload yet.
        if(!limit_rate($db,'pair-device:'.$ip,2000,3600))fail('Pairing checks limited; retry later',429);
        if($action==='cancel-pairing-request')respond(cancel_pairing_request($db,$data));
        $row=$action==='request-pairing'?create_pairing_request($db,$data,$ip):pairing_request_owner($db,$data);
        notify_pairing_request($db,$cfg,$row['id'],$mailer);
        respond(pairing_request_reply($db,pairing_request_owner($db,$data)));
    }
    if($action==='pair'){
        if(!limit_rate($db,'pair:'.$ip,15,600))fail('Too many pairing attempts; wait ten minutes',429);
        load_initial_pairing($db,$cfg);
        respond(pair_installation($db,$data));
    }
    if($action==='ingest'){
        $i=authenticate_installation($db,$_SERVER['HTTP_AUTHORIZATION']??$_SERVER['REDIRECT_HTTP_AUTHORIZATION']??'');
        if(!limit_rate($db,'upload:'.$i['id'],120,3600))fail('Hourly upload limit reached; retry later',429);
        if(!limit_rate($db,'upload-day:'.$i['id'],1000,86400))fail('Daily upload limit reached',429);
        if(filesize($cfg['data_dir'].'/score.sqlite3')>2000000000)fail('Storage capacity reached; contact scoreboard administrator',503);
        $reply=ingest($db,$i,$data);
        if(isset($reply['profile_id'])){
            if(!send_profile_welcomes($db,$cfg,$i['id'],$reply['profile_id'],$mailer))fail('Some sign-in emails are temporarily unavailable; the game will retry those recipients',503);
            unset($reply['profile_id']);
        }
        respond($reply);
    }
    if($action==='request-link'){
        $email=email_value($data['email']??null);
        if(!limit_rate($db,'login:'.$ip,15,3600))fail('Too many requests. Please try again later.',429);
        $known=in_array($email,$cfg['admins'],true)||sql($db,'SELECT 1 FROM profile_emails WHERE email=? LIMIT 1',[$email])->fetchColumn();
        if($known)request_signin($db,$cfg,$email,$mailer);
        respond(['ok'=>true,'message'=>'If this email is connected to a profile, a sign-in link will arrive shortly. Check your spam folder too.']);
    }
    if($action==='verify'){
        if(!limit_rate($db,'verify:'.$ip,30,600))fail('Too many attempts',429);
        $r=verify_signin($db,textfield($data['token']??null,64),$cfg['session_seconds']);
        setcookie('__Secure-mecharena_score',$r['session'],['expires'=>time()+$cfg['session_seconds'],'path'=>'/score','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);
        respond(['ok'=>true]);
    }
    $user=session_user($db,$_COOKIE['__Secure-mecharena_score']??'');
    $admin=in_array($user['email'],$cfg['admins'],true);
    if($method==='POST' && !hash_equals($user['csrf'],$_SERVER['HTTP_X_CSRF_TOKEN']??''))fail('Refresh the page before continuing',403);
    if($action==='state')respond(['ok'=>true,'email'=>$user['email'],'csrf'=>$user['csrf'],'admin'=>$admin]);
    if($action==='logout'){
        sql($db,'DELETE FROM sessions WHERE hash=?',[$user['hash']]);
        setcookie('__Secure-mecharena_score','',['expires'=>1,'path'=>'/score','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);respond(['ok'=>true]);
    }
    if($action==='results')respond(own_results($db,$user['email'],max(0,min(1000000,(int)($_GET['cursor']??0)))));
    if($action==='result')respond(own_result($db,$user['email'],ident($_GET['installation_id']??null),ident($_GET['run_id']??null),ident($_GET['player_id']??null)));
    if(!$admin)fail('Scoreboard administrator required',403);
    if($action==='admin')respond(['ok'=>true,'installations'=>sql($db,'SELECT id,name,created_at,revoked_at,last_seen FROM installations ORDER BY created_at DESC')->fetchAll(),'requests'=>pending_pairing_requests($db)]);
    if(in_array($action,['approve-pairing','reject-pairing'],true)){
        respond(decide_pairing_request($db,pairing_request_id($data['request_id']??null),$action==='approve-pairing'?'approved':'rejected',$user['email']));
    }
    if($action==='create-pairing'){
        if(!limit_rate($db,'admin-code:'.codehash($user['email']),20,3600))fail('Pairing limit reached',429);
        $code=strtoupper(bin2hex(random_bytes(16)));$expires=time()+600;
        sql($db,'INSERT INTO pairings(code_hash,created_by,expires) VALUES(?,?,?)',[codehash($code),$user['email'],$expires]);audit($db,'pairing-issued',$user['email'],'');
        respond(['ok'=>true,'code'=>implode('-',str_split($code,8)),'expires'=>$expires]);
    }
    if($action==='revoke'){
        $id=ident($data['installation_id']??null);
        sql($db,'UPDATE installations SET revoked_at=? WHERE id=?',[time(),$id]);audit($db,'revoked',$user['email'],$id);respond(['ok'=>true]);
    }
    fail('Unknown action',404);
} catch(ScoreError $e){respond(['ok'=>false,'error'=>$e->getMessage()],$e->status);}
catch(JsonException $e){respond(['ok'=>false,'error'=>'Invalid JSON'],400);}
catch(Throwable $e){error_log('MechArena scoreboard: '.get_class($e));respond(['ok'=>false,'error'=>'Scoreboard temporarily unavailable. Your game keeps results locally.'],503);}
