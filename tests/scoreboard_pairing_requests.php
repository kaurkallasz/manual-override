<?php
declare(strict_types=1);
require __DIR__.'/../deploy/score/core.php';
$dir=sys_get_temp_dir().'/pairing-tests-'.bin2hex(random_bytes(8));
$cfg=['data_dir'=>$dir,'base_url'=>'https://example.test/score','admins'=>['admin@example.test']];$db=database($cfg);$passed=0;
function check(bool $v,string $name):void{global $passed;if(!$v)throw new RuntimeException($name);$passed++;echo "PASS $name\n";}
function rejected(callable $fn,int $status,string $name):void{try{$fn();}catch(ScoreError $e){check($e->status===$status,$name);return;}throw new RuntimeException('Not rejected: '.$name);}
function device():array{return ['request_id'=>bin2hex(random_bytes(16)),'upload_key'=>bin2hex(random_bytes(32)),'name'=>'Test arena','contact_email'=>'operator@example.test'];}
try{
$d=device();$r=create_pairing_request($db,$d,'ip1');
check($r['status']==='pending'&&$r['expires']>time()+604790,'request expires after seven days');
check($r['key_hash']===codehash($d['upload_key']),'only hashed installation proof is stored');
rejected(fn()=>authenticate_installation($db,'Bearer '.$d['upload_key']),401,'pending request cannot upload');
check(create_pairing_request($db,$d,'ip1')['id']===$r['id'],'lost create response retries same request');
rejected(fn()=>create_pairing_request($db,array_replace($d,['upload_key'=>str_repeat('0',64)]),'ip1'),403,'request ID alone cannot take over request');
rejected(fn()=>create_pairing_request($db,array_replace($d,['name'=>'Changed']),'ip1'),409,'request details cannot change after submission');
rejected(fn()=>pairing_request_owner($db,array_replace($d,['upload_key'=>str_repeat('0',64)])),403,'request polling requires private proof');
rejected(fn()=>cancel_pairing_request($db,array_replace($d,['upload_key'=>str_repeat('0',64)])),403,'cancellation requires private proof');
rejected(fn()=>create_pairing_request($db,array_replace($d,['request_id'=>bin2hex(random_bytes(16))]),'ip2'),409,'one proof cannot register multiple requests');
$messages=[];$mailer=function($to,$subject,$body)use(&$messages){$messages[]=[$to,$subject,$body];return true;};
notify_pairing_request($db,$cfg,$r['id'],$mailer);notify_pairing_request($db,$cfg,$r['id'],$mailer);
check(count($messages)===1&&$messages[0][0]==='admin@example.test','polling sends one admin notification only');
check(str_contains($messages[0][2],'#pairing-request='.$r['id'])&&!str_contains($messages[0][2],$d['upload_key'])&&!str_contains($messages[0][2],'#signin='),'notification contains review link with no secret or login');
check(pairing_request_reply($db,pairing_request_owner($db,$d))['notification']==='submitted','mail acceptance reported honestly');
check(count(pending_pairing_requests($db))===1,'pending requests visible in admin list');
$a=decide_pairing_request($db,$r['id'],'approved','admin@example.test');
check($a['status']==='approved'&&authenticate_installation($db,'Bearer '.$d['upload_key'])['id']===$a['installation_id'],'approval grants upload access to original device proof');
check(decide_pairing_request($db,$r['id'],'approved','admin@example.test')['installation_id']===$a['installation_id'],'duplicate approval does not create another installation');
check(count(pending_pairing_requests($db))===0,'approved request leaves pending list');
check(pairing_request_reply($db,pairing_request_owner($db,$d))['installation_id']===$a['installation_id'],'device recovers approval after restart');
check(database($cfg)->query('SELECT count(*) FROM installations')->fetchColumn()===1,'schema initialization preserves existing installation');
cancel_pairing_request($db,$d);cancel_pairing_request($db,$d);
rejected(fn()=>authenticate_installation($db,'Bearer '.$d['upload_key']),401,'cancellation wins race with approval and revokes access');
rejected(fn()=>decide_pairing_request($db,$r['id'],'approved','admin@example.test'),409,'cancelled request cannot be approved');
$d2=device();$r2=create_pairing_request($db,$d2,'ip2');$calls=0;$failed=function()use(&$calls){$calls++;return false;};
notify_pairing_request($db,$cfg,$r2['id'],$failed);notify_pairing_request($db,$cfg,$r2['id'],$failed);
check($calls===1&&pairing_request_reply($db,pairing_request_owner($db,$d2))['notification']==='retrying','mail failure remains pending without poll flooding');
sql($db,'UPDATE pairing_requests SET notify_after=0 WHERE id=?',[$r2['id']]);notify_pairing_request($db,$cfg,$r2['id'],$mailer);
check(pairing_request_owner($db,$d2)['notified_at']>0,'failed notification can retry successfully');
decide_pairing_request($db,$r2['id'],'rejected','admin@example.test');
rejected(fn()=>decide_pairing_request($db,$r2['id'],'approved','admin@example.test'),409,'rejected request cannot later be approved');
rejected(fn()=>authenticate_installation($db,'Bearer '.$d2['upload_key']),401,'rejection grants no upload access');
$d3=device();$r3=create_pairing_request($db,$d3,'ip3');sql($db,'UPDATE pairing_requests SET expires=1 WHERE id=?',[$r3['id']]);
check(pairing_request_reply($db,pairing_request_owner($db,$d3))['status']==='expired','expiry visible to game');
rejected(fn()=>decide_pairing_request($db,$r3['id'],'approved','admin@example.test'),409,'expired request cannot be approved');
notify_pairing_request($db,$cfg,$r3['id'],$mailer);check(count($messages)===2,'expired requests do not send notifications');
for($n=0;$n<3;$n++)create_pairing_request($db,device(),'limited-ip');
rejected(fn()=>create_pairing_request($db,device(),'limited-ip'),429,'new request rate limit prevents admin mailbox flooding');
$d4=device();$r4=create_pairing_request($db,$d4,'ip4');$a4=decide_pairing_request($db,$r4['id'],'approved','admin@example.test');sql($db,'UPDATE installations SET revoked_at=? WHERE id=?',[time(),$a4['installation_id']]);
check(pairing_request_reply($db,pairing_request_owner($db,$d4))['status']==='revoked','revoked approval is not reactivated by polling');
check(cancel_pairing_request($db,device())['status']==='cancelled','unsubmitted local request can be cancelled');
rejected(fn()=>create_pairing_request($db,array_replace(device(),['contact_email'=>"bad\n@example.com"]),'ip5'),400,'invalid contact cannot inject notification headers');
echo "$passed pairing assertions passed\n";
}finally{$db=null;foreach(glob($dir.'/*') as $file)unlink($file);rmdir($dir);}
