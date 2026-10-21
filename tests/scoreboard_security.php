<?php
declare(strict_types=1);
require __DIR__.'/../deploy/score/core.php';
$dir=sys_get_temp_dir().'/mecharena-test-'.bin2hex(random_bytes(8));
$cfg=['data_dir'=>$dir,'base_url'=>'https://example.test/score','admins'=>['admin@example.test']];$db=database($cfg);$passed=0;
function check(bool $v,string $name): void {global $passed;if(!$v)throw new RuntimeException($name);$passed++;echo "PASS $name\n";}
function rejected(callable $fn,int $status,string $name): void {try{$fn();}catch(ScoreError $e){check($e->status===$status,$name);return;}throw new RuntimeException('Not rejected: '.$name);}
function pairing(PDO $db,string $code,string $key): array {sql($db,'INSERT INTO pairings(code_hash,created_by,expires) VALUES(?,?,?)',[codehash($code),'admin@example.test',time()+600]);return pair_installation($db,['code'=>$code,'upload_key'=>$key,'name'=>'Test arena']);}
try {
    load_initial_pairing($db,$cfg);check((int)$db->query('SELECT count(*) FROM pairings')->fetchColumn()===0,'no initial pairing without private hosting file');
    $setup=['code_hash'=>codehash(str_repeat('A',32)),'expires'=>time()-1];
    file_put_contents($dir.'/initial-pairing.json',jsondata($setup));load_initial_pairing($db,$cfg);
    check((int)$db->query('SELECT count(*) FROM pairings')->fetchColumn()===0,'expired hosting setup ignored');
    $setup['expires']=time()+3600;file_put_contents($dir.'/initial-pairing.json',jsondata($setup));load_initial_pairing($db,$cfg);
    check((int)$db->query('SELECT count(*) FROM pairings')->fetchColumn()===0,'long-lived hosting setup rejected');
    $setup['expires']=time()+600;file_put_contents($dir.'/initial-pairing.json',jsondata($setup));load_initial_pairing($db,$cfg);load_initial_pairing($db,$cfg);
    check((int)$db->query('SELECT count(*) FROM pairings')->fetchColumn()===1,'private hosting setup seeds exactly one pairing code');
    $key=str_repeat('a',64);$i=pair_installation($db,['code'=>str_repeat('A',32),'upload_key'=>$key,'name'=>'Test arena']);$iid=$i['installation_id'];
    $setup['code_hash']=codehash(str_repeat('C',32));file_put_contents($dir.'/initial-pairing.json',jsondata($setup));load_initial_pairing($db,$cfg);
    rejected(fn()=>pair_installation($db,['code'=>str_repeat('C',32),'upload_key'=>str_repeat('c',64),'name'=>'Second bootstrap']),403,'hosting setup cannot provision another installation');
    check(pair_installation($db,['code'=>str_repeat('A',32),'upload_key'=>$key,'name'=>'Test arena'])['installation_id']===$iid,'lost pairing response can be retried with same proof');
    rejected(fn()=>pair_installation($db,['code'=>str_repeat('A',32),'upload_key'=>str_repeat('b',64),'name'=>'Impostor']),403,'pairing code cannot provision a second key');
    sql($db,'UPDATE pairings SET expires=1');rejected(fn()=>pair_installation($db,['code'=>str_repeat('A',32),'upload_key'=>$key,'name'=>'Expired']),403,'pairing expiry enforced');
    $inst=authenticate_installation($db,'Bearer '.$key);check($inst['id']===$iid,'installation authentication');
    rejected(fn()=>authenticate_installation($db,'Bearer '.str_repeat('f',64)),401,'unknown upload key denied');
    $profile=['kind'=>'profile','player_id'=>'green','email'=>'player@example.test','name'=>'Green','event_id'=>'event'];ingest($db,$inst,$profile);ingest($db,$inst,$profile);
    check((int)$db->query('SELECT count(*) FROM profiles')->fetchColumn()===1,'profile retries do not duplicate');
    rejected(fn()=>ingest($db,$inst,array_replace($profile,['email'=>'other@example.test'])),409,'profile mailbox cannot be replaced by uploader');
    $r=['player_id'=>'green','run_id'=>'run','side'=>'green','outcome'=>'won','control_tier'=>4,'kills'=>4,'kill_credits'=>8,'stack_bonus'=>2,'total_earned'=>10,'active_seconds'=>600,'statistics'=>['score'=>8,'players'=>[['player_id'=>'green','name'=>'Green','side'=>'green']]],'kill_heatmap'=>['width'=>600,'height'=>300,'columns'=>2,'rows'=>1,'unlocated'=>0,'counts'=>[1,3],'core'=>[300,150],'roads'=>[[[0,0],[300,150]]],'markers'=>[[20,20,100]]], 'robot_movement'=>['version'=>1,'units'=>'mm','height_basis'=>'Calibrated ground plane','duration_s'=>600,'field'=>['width_mm'=>600,'height_mm'=>300,'core'=>[0.5,0.5]],'arms'=>['green'=>['status'=>'ready','error'=>null,'gaps'=>0,'simplified'=>false,'truncated'=>false,'segments'=>[[[0,20,20,10],[600,500,200,30]]]],'purple'=>['status'=>'unavailable','error'=>'No feedback','gaps'=>0,'simplified'=>false,'truncated'=>false,'segments'=>[]]]]];
    $payload=['kind'=>'result','run_id'=>'run','event_id'=>'event','event_name'=>'Test event','finished_at'=>time(),'player_ids'=>['green'],'receipts'=>['green'=>$r]];
    ingest($db,$inst,$payload);ingest($db,$inst,$payload);check((int)$db->query('SELECT count(*) FROM results')->fetchColumn()===1,'result retries are idempotent');
    $changed=$payload;$changed['receipts']['green']['kill_credits']=99;rejected(fn()=>ingest($db,$inst,$changed),409,'accepted results are immutable');
    $attack=$payload;$attack['receipts']['green']['kill_heatmap']['core'][0]='0" onload="alert(1)';rejected(fn()=>ingest($db,$inst,$attack),400,'heatmap HTML injection rejected');
    $attack=$payload;$attack['receipts']['green']['robot_movement']['arms']['green']['segments'][0][1][1]='injection';rejected(fn()=>ingest($db,$inst,$attack),400,'movement coordinates validated');
    $other=pairing($db,str_repeat('B',32),str_repeat('b',64));$otherInst=authenticate_installation($db,'Bearer '.str_repeat('b',64));
    ingest($db,$otherInst,array_replace($profile,['email'=>'other@example.test']));ingest($db,$otherInst,$payload);
    check(own_results($db,'player@example.test')['total']===1,'same player and run IDs are isolated across installations');
    rejected(fn()=>own_result($db,'player@example.test',$other['installation_id'],'run','green'),404,'another installation result cannot be read');
    rejected(fn()=>own_result($db,'outsider@example.test',$iid,'run','green'),404,'unrelated player cannot read result');
    $detail=own_result($db,'player@example.test',$iid,'run','green')['receipt'];check($detail['robot_movement']['duration_s']===600,'3D recordings survive storage');
    check(!isset(own_results($db,'player@example.test')['rows'][0]['receipt']['robot_movement']),'history loads recordings only on demand');
    $sent=[];$mailer=function($to,$subject,$body)use(&$sent){$sent[]=[$to,$subject,$body];return true;};
    check(request_signin($db,$cfg,'player@example.test',$mailer),'sign-in email queued');check((int)sql($db,"SELECT count(*) FROM audit WHERE kind='mail-accepted'")->fetchColumn()===1,'mail acceptance recorded without raw email or token');check(!request_signin($db,$cfg,'failure@example.test',fn()=>false),'mail rejection reported');check((int)sql($db,"SELECT count(*) FROM audit WHERE kind='mail-rejected'")->fetchColumn()===1,'mail rejection recorded');preg_match('/#signin=([a-f0-9]+)/',$sent[0][2],$m);$token=$m[1];
    check($db->query('SELECT hash FROM tokens')->fetchColumn()!==$token,'only token hashes stored');
    $login=verify_signin($db,$token,3600);check(session_user($db,$login['session'])['email']==='player@example.test','verified email establishes session');
    rejected(fn()=>verify_signin($db,$token,3600),401,'magic link is single use');
    $expired=str_repeat('c',64);sql($db,'INSERT INTO tokens VALUES(?,?,?)',[codehash($expired),'player@example.test',time()-1]);rejected(fn()=>verify_signin($db,$expired,3600),401,'expired magic link denied');
    check(limit_rate($db,'test',1,600)&&!limit_rate($db,'test',1,600),'rate limit enforced');
    sql($db,'UPDATE installations SET revoked_at=? WHERE id=?',[time(),$iid]);rejected(fn()=>authenticate_installation($db,'Bearer '.$key),401,'revoked upload key denied');
    echo "$passed security assertions passed.\n";
}finally{$db=null;foreach(glob($dir.'/*')as$p)unlink($p);rmdir($dir);}
