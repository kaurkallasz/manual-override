<?php
declare(strict_types=1);
require __DIR__.'/../deploy/score/core.php';
$dir=sys_get_temp_dir().'/team-email-test-'.bin2hex(random_bytes(8));$cfg=['data_dir'=>$dir,'base_url'=>'https://example.test/score','admins'=>['admin@example.test']];$db=database($cfg);$passed=0;
function check(bool $v,string $label):void{global $passed;if(!$v)throw new RuntimeException($label);$passed++;echo "PASS $label\n";}
function rejected(callable $fn,int $code,string $label):void{try{$fn();}catch(ScoreError $e){check($e->status===$code,$label);return;}throw new RuntimeException('Not rejected: '.$label);}
try{
check(email_values(' B@example.test, a@example.test, b@example.test ')===['a@example.test','b@example.test'],'email normalization removes spaces/case duplicates');
foreach(['a@example.test,','a@example.test,bad','a@example.test; b@example.test',implode(',',array_map(fn($i)=>"p$i@example.test",range(1,11)))] as $bad)rejected(fn()=>email_values($bad),400,'invalid or excessive list rejected');
sql($db,'INSERT INTO installations(id,name,key_hash,created_at) VALUES(?,?,?,?)',['arena','Test arena',codehash(str_repeat('a',64)),time()]);$i=authenticate_installation($db,'Bearer '.str_repeat('a',64));
// Legacy migration preserves access and avoids mailing the original owner again.
sql($db,'INSERT INTO profiles VALUES(?,?,?,?,?,?)',['arena','legacy','legacy@example.test','Legacy','event',1]);$db=database($cfg);
check((int)sql($db,'SELECT welcome_sent FROM profile_emails WHERE player_id=?',['legacy'])->fetchColumn()===1,'legacy recipient and mail flag migrate');
$legacy=['kind'=>'profile','player_id'=>'legacy','name'=>'Legacy','event_id'=>'event','email'=>'legacy@example.test'];
ingest($db,$i,array_replace($legacy,['email'=>'new@example.test, legacy@example.test']));
$sent=[];$mailer=function($to,$subject,$body)use(&$sent){$sent[]=[$to,$subject,$body];return true;};
check(send_profile_welcomes($db,$cfg,'arena','legacy',$mailer)&&count($sent)===1&&$sent[0][0]==='new@example.test','only new teammate gets welcome after migration');
ingest($db,$i,$legacy);check((int)sql($db,'SELECT count(*) FROM profile_emails WHERE player_id=?',['legacy'])->fetchColumn()===2,'old queued upload cannot remove new teammate');
$profile=['kind'=>'profile','player_id'=>'team','name'=>'Team','event_id'=>'event','email'=>'a@example.test,b@example.test,c@example.test'];
ingest($db,$i,$profile);ingest($db,$i,$profile);
check((int)sql($db,'SELECT count(*) FROM profile_emails WHERE player_id=?',['team'])->fetchColumn()===3,'three unique memberships on retry');
rejected(fn()=>ingest($db,$i,array_replace($profile,['email'=>'outsider@example.test'])),409,'original profile mailbox cannot be replaced');
$r=['player_id'=>'team','run_id'=>'run','side'=>'green','outcome'=>'won','control_tier'=>1,'kills'=>4,'kill_credits'=>4,'total_earned'=>4,'active_seconds'=>60];
ingest($db,$i,['kind'=>'result','run_id'=>'run','event_id'=>'event','event_name'=>'Team event','finished_at'=>time(),'player_ids'=>['team'],'receipts'=>['team'=>$r]]);
foreach(['a','b','c'] as $name){$email=$name.'@example.test';check(own_results($db,$email)['total']===1,'teammate sees shared profile history: '.$name);check(own_result($db,$email,'arena','run','team')['receipt']['kills']===4,'teammate opens same result: '.$name);}
check(own_results($db,'outsider@example.test')['total']===0,'unregistered mailbox sees no history');
rejected(fn()=>own_result($db,'outsider@example.test','arena','run','team'),404,'unregistered mailbox cannot read result');
$attempts=[];$partial=function($to,$subject,$body)use(&$attempts){$attempts[]=[$to,$subject,$body];return $to!=='b@example.test';};
check(!send_profile_welcomes($db,$cfg,'arena','team',$partial),'one failed recipient leaves upload retryable');
check(count($attempts)===3,'one failure does not block other teammates');
check((int)sql($db,"SELECT sum(welcome_sent) FROM profile_emails WHERE player_id='team'")->fetchColumn()===2,'successful recipients saved separately');
$sent=[];check(send_profile_welcomes($db,$cfg,'arena','team',$mailer),'retry completes remaining recipient');
check(count($sent)===1&&$sent[0][0]==='b@example.test','retry does not resend successful welcomes');
send_profile_welcomes($db,$cfg,'arena','team',$mailer);check(count($sent)===1,'fully acknowledged welcome is idempotent');
$tokens=[];foreach([$attempts[0],$sent[0],$attempts[2]] as [$to,$subject,$body]){
 foreach(['a','b','c'] as $name)if($to!==$name.'@example.test')check(!str_contains($body,$name.'@example.test'),'email does not disclose teammate address');
 preg_match('/#signin=([a-f0-9]{64})/',$body,$match);$tokens[]=$match[1];$login=verify_signin($db,$match[1],3600);check($login['email']===$to,'each sign-in link authenticates only its own mailbox');
}
check(count(array_unique($tokens))===3,'each teammate gets a distinct private token');
$added=array_replace($profile,['email'=>$profile['email'].',d@example.test']);ingest($db,$i,$added);
check(own_results($db,'d@example.test')['total']===1,'teammate added later sees existing results without re-upload');
check(!str_contains(jsondata(own_results($db,'a@example.test')),'b@example.test'),'scoreboard response exposes no teammate email list');
$max=array_replace($profile,['email'=>implode(',',array_merge(['a@example.test','b@example.test','c@example.test','d@example.test'],array_map(fn($n)=>'m'.$n.'@example.test',range(1,6))))]);ingest($db,$i,$max);
rejected(fn()=>ingest($db,$i,array_replace($profile,['email'=>'a@example.test,overflow@example.test'])),400,'incremental additions cannot bypass ten-recipient limit');
check((int)sql($db,"SELECT count(*) FROM profile_emails WHERE player_id='team'")->fetchColumn()===10,'over-limit addition rolls back atomically');
echo "$passed team-email assertions passed\n";
}finally{$db=null;foreach(glob($dir.'/*') as $p)unlink($p);rmdir($dir);}
