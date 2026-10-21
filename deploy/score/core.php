<?php
declare(strict_types=1);
require __DIR__.'/pairing-requests.php';

final class ScoreError extends RuntimeException {
    public int $status;
    public function __construct(string $message, int $status = 400) { parent::__construct($message); $this->status = $status; }
}
function fail(string $message, int $status = 400): never { throw new ScoreError($message, $status); }
function codehash(string $v): string { return hash('sha256', $v); }
function textfield(mixed $v, int $max=128): string {
    if (!is_string($v) || strlen($v)<1 || strlen($v)>$max || preg_match('/[\x00-\x1f\x7f]/', $v)) fail('Invalid text field');
    return $v;
}
function ident(mixed $v): string {
    if (!is_string($v) || !preg_match('/^[A-Za-z0-9:_-]{1,128}$/D', $v)) fail('Invalid record identifier');
    return $v;
}
function email_value(mixed $v): string {
    if (!is_string($v) || strlen($v)>254 || !filter_var($v, FILTER_VALIDATE_EMAIL) || preg_match('/[\r\n]/', $v)) fail('Enter a valid email address');
    return strtolower(trim($v));
}
function email_values(mixed $value): array {
    if(!is_string($value)||strlen($value)>2600)fail('Enter up to 10 email addresses separated by commas');
    $parts=explode(',',$value);if(count($parts)>20)fail('Too many email addresses');
    $emails=array_values(array_unique(array_map(fn($v)=>email_value(trim($v)),$parts)));sort($emails,SORT_STRING);
    if(count($emails)<1||count($emails)>10)fail('Use 1–10 email addresses per profile');
    return $emails;
}
function number(mixed $v, float $lo=0, float $hi=1000000000): int|float {
    if ((!is_int($v) && !is_float($v)) || !is_finite((float)$v) || $v<$lo || $v>$hi) fail('Invalid numeric field');
    return $v;
}
function integer(mixed $v, int $lo=0, int $hi=1000000000): int {
    if (!is_int($v)) fail('Expected an integer');
    return (int)number($v,$lo,$hi);
}
function jsondata(mixed $v): string { return json_encode($v, JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES); }
function sql(PDO $db, string $query, array $params=[]): PDOStatement { $s=$db->prepare($query);$s->execute($params);return $s; }
function transaction(PDO $db, callable $fn): mixed {
    $db->exec('BEGIN IMMEDIATE');
    try { $v=$fn();$db->exec('COMMIT');return $v; } catch(Throwable $e) { $db->exec('ROLLBACK');throw $e; }
}
function database(array $cfg): PDO {
    $dir=$cfg['data_dir'];
    if (!is_dir($dir) && !mkdir($dir,0700,true)) fail('Storage unavailable',503);
    chmod($dir,0700);
    $db=new PDO('sqlite:'.$dir.'/score.sqlite3',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    chmod($dir.'/score.sqlite3',0600);
    $db->exec('PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;');
    $db->exec(<<<'SQL'
CREATE TABLE IF NOT EXISTS installations(id TEXT PRIMARY KEY,name TEXT NOT NULL,key_hash TEXT UNIQUE NOT NULL,created_at INTEGER NOT NULL,revoked_at INTEGER,last_seen INTEGER);
CREATE TABLE IF NOT EXISTS pairings(code_hash TEXT PRIMARY KEY,created_by TEXT NOT NULL,expires INTEGER NOT NULL,installation_id TEXT,proof_hash TEXT);
CREATE TABLE IF NOT EXISTS pairing_requests(id TEXT PRIMARY KEY,key_hash TEXT UNIQUE NOT NULL,name TEXT NOT NULL,contact_email TEXT NOT NULL,created_at INTEGER NOT NULL,expires INTEGER NOT NULL,status TEXT NOT NULL,notified_at INTEGER,notify_after INTEGER NOT NULL DEFAULT 0,installation_id TEXT,decided_at INTEGER,decided_by TEXT);
CREATE INDEX IF NOT EXISTS pairing_request_status ON pairing_requests(status,expires);
CREATE TABLE IF NOT EXISTS profiles(installation_id TEXT NOT NULL,player_id TEXT NOT NULL,email TEXT NOT NULL,name TEXT NOT NULL,event_id TEXT NOT NULL,welcome_sent INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(installation_id,player_id));
CREATE INDEX IF NOT EXISTS profile_mail ON profiles(email);
CREATE TABLE IF NOT EXISTS profile_emails(installation_id TEXT NOT NULL,player_id TEXT NOT NULL,email TEXT NOT NULL,welcome_sent INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(installation_id,player_id,email));
CREATE INDEX IF NOT EXISTS profile_emails_mail ON profile_emails(email);
CREATE TABLE IF NOT EXISTS results(installation_id TEXT NOT NULL,run_id TEXT NOT NULL,event_id TEXT NOT NULL,event_name TEXT NOT NULL,finished_at REAL NOT NULL,body TEXT NOT NULL,body_hash TEXT NOT NULL,PRIMARY KEY(installation_id,run_id));
CREATE TABLE IF NOT EXISTS members(installation_id TEXT NOT NULL,run_id TEXT NOT NULL,player_id TEXT NOT NULL,PRIMARY KEY(installation_id,run_id,player_id));
CREATE INDEX IF NOT EXISTS member_player ON members(installation_id,player_id);
CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,email TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,email TEXT NOT NULL,csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY,count INTEGER NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER NOT NULL,kind TEXT NOT NULL,actor TEXT NOT NULL,subject TEXT NOT NULL);
SQL);
    // Preserve legacy profiles and delivery flags, including uploads from old game clients.
    sql($db,'INSERT OR IGNORE INTO profile_emails(installation_id,player_id,email,welcome_sent) SELECT installation_id,player_id,email,welcome_sent FROM profiles');
    return $db;
}
function audit(PDO $db,string $kind,string $actor,string $subject): void {sql($db,'INSERT INTO audit(at,kind,actor,subject) VALUES(?,?,?,?)',[time(),$kind,$actor,$subject]);}
function limit_rate(PDO $db, string $key, int $maximum, int $seconds): bool {
    return transaction($db,function()use($db,$key,$maximum,$seconds){
        $now=time();$row=sql($db,'SELECT * FROM limits WHERE key=?',[$key])->fetch();
        if (!$row || $row['expires']<=$now) {sql($db,'INSERT OR REPLACE INTO limits VALUES(?,1,?)',[$key,$now+$seconds]);return true;}
        if ($row['count'] >= $maximum) return false;
        sql($db,'UPDATE limits SET count=count+1 WHERE key=?',[$key]);return true;
    });
}
function cleanup(PDO $db): void {
    foreach(['tokens','sessions','pairings','limits'] as $table)sql($db,"DELETE FROM $table WHERE expires<?",[time()-3600]);
}
function validate_heatmap(mixed $h, int $kills): ?array {
    if ($h===null) return null;
    if(!is_array($h))fail('Invalid heatmap');
    $out=['width'=>number($h['width']??null,1,100000),'height'=>number($h['height']??null,1,100000),
          'columns'=>integer($h['columns']??null,1,128),'rows'=>integer($h['rows']??null,1,128),'unlocated'=>integer($h['unlocated']??null)];
    if(!is_array($h['counts']??null)||count($h['counts'])!==$out['columns']*$out['rows'])fail('Invalid heatmap cells');
    $out['counts']=array_map(fn($n)=>integer($n),$h['counts']);
    if(array_sum($out['counts'])+$out['unlocated']!==$kills)fail('Heatmap kills disagree');
    $point=function($p) {if(!is_array($p)||count($p)!==2)fail('Invalid map point');return [number($p[0],-100000,100000),number($p[1],-100000,100000)];};
    $out['core']=$point($h['core']??null);$out['roads']=[];$out['markers']=[];
    if(!is_array($h['roads']??null)||count($h['roads'])>64||!is_array($h['markers']??null)||count($h['markers'])>256)fail('Invalid map landmarks');
    foreach($h['roads'] as $road){if(!is_array($road)||count($road)>256)fail('Invalid road');$out['roads'][]=array_map($point,$road);}
    foreach($h['markers'] as $m){if(!is_array($m)||count($m)!==3)fail('Invalid marker');$out['markers'][]=[...$point(array_slice($m,0,2)),integer($m[2],0,100000)];}
    if(isset($h['timeline'])) {
        $t=$h['timeline'];
        if(!is_array($t)||($t['version']??null)!==1||!is_array($t['events']??null)||count($t['events'])>8192)fail('Invalid heatmap timeline');
        $timeline=['version'=>1,'bin_seconds'=>number($t['bin_seconds']??null,1,2592000),'events'=>[]];
        $counts=array_fill(0,count($out['counts']),0);$missing=0;$last=0;
        foreach($t['events'] as $e){
            if(!is_array($e)||count($e)!==3)fail('Invalid kill event');
            $last=number($e[0],$last,2592000);$cell=integer($e[1],-1,count($counts)-1);$n=integer($e[2],1);
            if($cell===-1)$missing+=$n;else $counts[$cell]+=$n;
            $timeline['events'][]=[$last,$cell,$n];
        }
        if($counts!==$out['counts']||$missing!==$out['unlocated'])fail('Kill timeline does not reconcile');
        $out['timeline']=$timeline;
    }
    return $out;
}
function validate_movement(mixed $v): ?array {
    if($v===null)return null;
    if(!is_array($v)||($v['version']??null)!==1||($v['units']??null)!=='mm'||($v['height_basis']??null)!=='Calibrated ground plane')fail('Invalid robot recording');
    $out=['version'=>1,'units'=>'mm','height_basis'=>'Calibrated ground plane','duration_s'=>number($v['duration_s']??null,0,2592000),'field'=>null,'arms'=>[]];
    if(($v['field']??null)!==null){$f=$v['field'];if(!is_array($f)||!is_array($f['core']??null)||count($f['core'])!==2)fail('Invalid recorded field');$out['field']=['width_mm'=>number($f['width_mm']??null,100,5000),'height_mm'=>number($f['height_mm']??null,100,5000),'core'=>array_map(fn($n)=>number($n,0,1),$f['core'])];}
    foreach(['green','purple'] as $side){
        $a=$v['arms'][$side]??null;if(!is_array($a)||!in_array($a['status']??null,['ready','partial','unavailable'],true))fail('Invalid arm status');
        $arm=['status'=>$a['status'],'error'=>isset($a['error'])?textfield($a['error'],240):null,'gaps'=>integer($a['gaps']??null), 'segments'=>[]];
        foreach(['simplified','truncated'] as $flag){if(!is_bool($a[$flag]??null))fail('Invalid recording flag');$arm[$flag]=$a[$flag];}
        if(!is_array($a['segments']??null)||count($a['segments'])>128)fail('Too many segments');
        $total=0;$last=-1;
        foreach($a['segments'] as $segment){
            if(!$out['field']||!is_array($segment)||!count($segment)||($total+=count($segment))>3000)fail('Invalid recording segment');
            $points=[];foreach($segment as $p){if(!is_array($p)||count($p)!==4)fail('Invalid recording point');$last=number($p[0],$last,$out['duration_s']);$points[]=[$last,number($p[1],-10000,15000),number($p[2],-10000,15000),number($p[3],-500,2000)];}
            $arm['segments'][]=$points;
        }
        if((bool)$arm['segments']===($arm['status']==='unavailable'))fail('Recording availability disagrees');
        $out['arms'][$side]=$arm;
    }
    return $out;
}
function validate_receipt(mixed $r,string $pid,string $run): array {
    if(!is_array($r)||($r['player_id']??null)!==$pid||($r['run_id']??null)!==$run)fail('Result membership mismatch');
    if(!in_array($r['outcome']??null,['won','overrun','operator_ended','aborted'],true)||!in_array($r['side']??null,['green','purple'],true))fail('Invalid result');
    $s=$r['statistics']??[];
    $out=['player_id'=>$pid,'run_id'=>$run,'side'=>$r['side'],'outcome'=>$r['outcome'],
          'control_tier'=>integer($r['control_tier']??null,1,4),'kills'=>integer($r['kills']??null),
          'kill_credits'=>number($r['kill_credits']??null),'stack_bonus'=>number($r['stack_bonus']??0),
          'total_earned'=>number($r['total_earned']??null),'active_seconds'=>number($r['active_seconds']??null,0,2592000),
          'score'=>number($s['score']??$r['kill_credits']),'assisted'=>(bool)($s['assisted']??false),'purchases'=>[]];
    foreach($r['purchases']??[] as $p){if(count($out['purchases'])>=30)fail('Too many upgrades');$out['purchases'][]=['track'=>textfield($p['track']??null,60),'level'=>integer($p['level']??null,1,10),'price'=>number($p['price']??0)];}
    $out['kill_heatmap']=validate_heatmap($s['kill_heatmap']??$r['kill_heatmap']??null,$out['kills']);
    $out['robot_movement']=validate_movement($s['robot_movement']??$r['robot_movement']??null);
    $out['players']=[];foreach($s['players']??[] as $p){if(count($out['players'])>=2)fail('Too many players');$out['players'][]=['player_id'=>ident($p['player_id']??null),'name'=>textfield($p['name']??null,128),'side'=>in_array($p['side']??null,['green','purple'],true)?$p['side']:fail('Invalid team')];}
    return $out;
}
function load_initial_pairing(PDO $db,array $cfg): void {
    // Hosting-owner setup: this file must be placed OUTSIDE the website using
    // authenticated hosting access. It grants one upload-only pairing, never a
    // browser session or administration. It is ignored after any installation exists.
    if(sql($db,'SELECT 1 FROM installations LIMIT 1')->fetchColumn())return;
    $path=$cfg['data_dir'].'/initial-pairing.json';
    if(!is_file($path))return;
    $p=json_decode(file_get_contents($path,false,null,0,2048),true);
    if(!is_array($p)||!is_string($p['code_hash']??null)||!preg_match('/^[a-f0-9]{64}$/D',$p['code_hash'])||!is_int($p['expires']??null)||$p['expires']<=time()||$p['expires']>time()+600)return;
    transaction($db,function()use($db,$cfg,$p){
        if(sql($db,'SELECT 1 FROM installations LIMIT 1')->fetchColumn())return;
        sql($db,'INSERT OR IGNORE INTO pairings(code_hash,created_by,expires) VALUES(?,?,?)',[$p['code_hash'],$cfg['admins'][0],$p['expires']]);
    });
}
function pair_installation(PDO $db,array $data): array {
    $code=strtoupper(str_replace('-','',textfield($data['code']??null,60)));$name=textfield($data['name']??null,80);$key=$data['upload_key']??'';
    if(!preg_match('/^[a-f0-9]{64}$/D',$key))fail('Invalid installation key');
    return transaction($db,function()use($db,$code,$name,$key){
        $p=sql($db,'SELECT * FROM pairings WHERE code_hash=?',[codehash($code)])->fetch();
        if(!$p||$p['expires']<time())fail('Pairing code invalid or expired',403);
        if($p['installation_id']){
            $i=sql($db,'SELECT * FROM installations WHERE id=?',[$p['installation_id']])->fetch();
            if(!hash_equals($p['proof_hash'],codehash($key))||!$i||$i['revoked_at'])fail('Pairing code already used',403);
            return ['ok'=>true,'installation_id'=>$i['id']];
        }
        $id=bin2hex(random_bytes(16));sql($db,'INSERT INTO installations(id,name,key_hash,created_at) VALUES(?,?,?,?)',[$id,$name,codehash($key),time()]);
        sql($db,'UPDATE pairings SET installation_id=?,proof_hash=? WHERE code_hash=?',[$id,codehash($key),codehash($code)]);
        audit($db,'paired',$p['created_by'],$id);
        return ['ok'=>true,'installation_id'=>$id];
    });
}
function authenticate_installation(PDO $db,string $authorization): array {
    if(!preg_match('/^Bearer ([a-f0-9]{64})$/D',$authorization,$m))fail('Upload access required',401);
    $i=sql($db,'SELECT * FROM installations WHERE key_hash=? AND revoked_at IS NULL',[codehash($m[1])])->fetch();
    if(!$i)fail('Upload access rejected',401);
    return $i;
}
function ingest(PDO $db,array $i,array $data): array {
    $iid=$i['id'];
    if(($data['kind']??null)==='profile'){
        $pid=ident($data['player_id']??null);$emails=email_values($data['email']??null);$name=textfield($data['name']??null,128);$event=ident($data['event_id']??null);
        transaction($db,function()use($db,$iid,$pid,$emails,$name,$event){
            $old=sql($db,'SELECT * FROM profiles WHERE installation_id=? AND player_id=?',[$iid,$pid])->fetch();
            // An addition must include the original mailbox. Old retries remain
            // valid and can never remove subsequently registered teammates.
            if($old&&(!in_array($old['email'],$emails,true)||$old['name']!==$name||$old['event_id']!==$event))fail('Profile already registered with different details; include its original email',409);
            $existing=sql($db,'SELECT email FROM profile_emails WHERE installation_id=? AND player_id=?',[$iid,$pid])->fetchAll(PDO::FETCH_COLUMN);
            if(count(array_unique(array_merge($existing,$emails)))>10)fail('Use no more than 10 email addresses per profile');
            if(!$old)sql($db,'INSERT INTO profiles(installation_id,player_id,email,name,event_id) VALUES(?,?,?,?,?)',[$iid,$pid,$emails[0],$name,$event]);
            foreach($emails as $email)sql($db,'INSERT OR IGNORE INTO profile_emails(installation_id,player_id,email) VALUES(?,?,?)',[$iid,$pid,$email]);
        });
        return ['ok'=>true,'accepted_id'=>'profile:'.$pid,'profile_id'=>$pid];
    }
    if(($data['kind']??null)!=='result')fail('Unsupported upload kind');
    $run=ident($data['run_id']??null);$event=ident($data['event_id']??null);$name=textfield($data['event_name']??null,128);$finished=number($data['finished_at']??null,0,time()+86400);
    $ids=$data['player_ids']??null;$receipts=$data['receipts']??null;
    if(!is_array($ids)||!array_is_list($ids)||count($ids)<1||count($ids)>2||!is_array($receipts)||count($receipts)!==count($ids))fail('Invalid participants');
    foreach($ids as $pid)ident($pid);
    if(count(array_unique($ids))!==count($ids))fail('Duplicate participants');
    $safe=[];foreach($ids as $pid){ident($pid);$safe[$pid]=validate_receipt($receipts[$pid]??null,$pid,$run);}
    $body=jsondata($safe);$hash=codehash(jsondata([$event,$name,$finished,$safe]));
    transaction($db,function()use($db,$iid,$run,$event,$name,$finished,$body,$hash,$ids){
        $old=sql($db,'SELECT body_hash FROM results WHERE installation_id=? AND run_id=?',[$iid,$run])->fetch();
        if($old){if(!hash_equals($old['body_hash'],$hash))fail('A different result already exists for this match',409);return;}
        sql($db,'INSERT INTO results VALUES(?,?,?,?,?,?,?)',[$iid,$run,$event,$name,$finished,$body,$hash]);
        foreach($ids as $pid)sql($db,'INSERT INTO members VALUES(?,?,?)',[$iid,$run,$pid]);
    });
    sql($db,'UPDATE installations SET last_seen=? WHERE id=?',[time(),$iid]);
    return ['ok'=>true,'accepted_id'=>'result:'.$run];
}
function request_signin(PDO $db,array $cfg,string $email,callable $mailer,bool $welcome=false): bool {
    $kind=$welcome?'welcome':'sign-in';$recipient=codehash($email);
    if(!limit_rate($db,'email:'.$recipient,4,3600)){audit($db,'mail-limited',$recipient,$kind);return false;}
    if(!limit_rate($db,'mail-global',150,3600)){audit($db,'mail-limited',$recipient,$kind);return false;}
    $token=bin2hex(random_bytes(32));sql($db,'INSERT INTO tokens VALUES(?,?,?)',[codehash($token),$email,time()+900]);
    $url=$cfg['base_url'].'/#signin='.$token;
    $subject=$welcome?'Your MechArena scoreboard':'Your MechArena sign-in link';
    $body=($welcome?"Your game profile is connected. We use this email to share your game statistics.\n\n":"")."Open your private scoreboard:\n$url\n\nThis link works once and expires in 15 minutes.\n\nYour scoreboard is always at ".$cfg['base_url'].". Enter your email there whenever you need a new link.\n\nIf you did not request this, you can ignore this email.\n";
    if(!$mailer($email,$subject,$body)){sql($db,'DELETE FROM tokens WHERE hash=?',[codehash($token)]);audit($db,'mail-rejected',$recipient,$kind);return false;}
    audit($db,'mail-accepted',$recipient,$kind);
    return true;
}
function send_profile_welcomes(PDO $db,array $cfg,string $iid,string $pid,callable $mailer): bool {
    $all_sent=true;
    foreach(sql($db,'SELECT email,welcome_sent FROM profile_emails WHERE installation_id=? AND player_id=?',[$iid,$pid])->fetchAll() as $recipient){
        if($recipient['welcome_sent'])continue;
        $email=$recipient['email'];
        $already=sql($db,'SELECT 1 FROM profile_emails WHERE installation_id=? AND email=? AND welcome_sent=1 LIMIT 1',[$iid,$email])->fetchColumn();
        // Send separately: no teammate addresses in To, CC, BCC, or the body.
        if(!$already&&!request_signin($db,$cfg,$email,$mailer,true)){$all_sent=false;continue;}
        sql($db,'UPDATE profile_emails SET welcome_sent=1 WHERE installation_id=? AND player_id=? AND email=?',[$iid,$pid,$email]);
        sql($db,'UPDATE profiles SET welcome_sent=1 WHERE installation_id=? AND player_id=? AND email=?',[$iid,$pid,$email]);
    }
    return $all_sent;
}
function verify_signin(PDO $db,string $token,int $seconds): array {
    if(!preg_match('/^[a-f0-9]{64}$/D',$token))fail('Sign-in link invalid or expired',401);
    return transaction($db,function()use($db,$token,$seconds){
        $row=sql($db,'SELECT * FROM tokens WHERE hash=?',[codehash($token)])->fetch();
        if(!$row||$row['expires']<time())fail('Sign-in link invalid or expired. Request a new link.',401);
        sql($db,'DELETE FROM tokens WHERE hash=?',[codehash($token)]);
        $session=bin2hex(random_bytes(32));$csrf=bin2hex(random_bytes(24));sql($db,'INSERT INTO sessions VALUES(?,?,?,?)',[codehash($session),$row['email'],$csrf,time()+$seconds]);
        return ['session'=>$session,'csrf'=>$csrf,'email'=>$row['email']];
    });
}
function session_user(PDO $db,string $cookie): array {
    $s=sql($db,'SELECT * FROM sessions WHERE hash=? AND expires>?',[codehash($cookie),time()])->fetch();
    if(!$s)fail('Sign in to view your scoreboard',401);
    return $s;
}
function own_results(PDO $db,string $email,int $offset=0): array {
    $total=(int)sql($db,'SELECT count(*) FROM members m JOIN profiles p ON p.installation_id=m.installation_id AND p.player_id=m.player_id JOIN profile_emails e ON e.installation_id=p.installation_id AND e.player_id=p.player_id WHERE e.email=?',[$email])->fetchColumn();
    $rows=sql($db,'SELECT r.*,m.player_id,p.name FROM members m JOIN profiles p ON p.installation_id=m.installation_id AND p.player_id=m.player_id JOIN results r ON r.installation_id=m.installation_id AND r.run_id=m.run_id JOIN profile_emails e ON e.installation_id=p.installation_id AND e.player_id=p.player_id WHERE e.email=? ORDER BY r.finished_at DESC,r.installation_id,r.run_id,m.player_id LIMIT 25 OFFSET ?',[$email,$offset])->fetchAll();
    return ['ok'=>true,'total'=>$total,'next_cursor'=>$offset+count($rows)<$total?$offset+count($rows):null,'rows'=>array_map(function($r){$body=json_decode($r['body'],true,64,JSON_THROW_ON_ERROR);$receipt=$body[$r['player_id']];unset($receipt['robot_movement'],$receipt['kill_heatmap']);return ['installation_id'=>$r['installation_id'],'run_id'=>$r['run_id'],'player_id'=>$r['player_id'],'player_name'=>$r['name'],'event_name'=>$r['event_name'],'finished_at'=>$r['finished_at'],'receipt'=>$receipt];},$rows)];
}
function own_result(PDO $db,string $email,string $iid,string $run,string $pid): array {
    $r=sql($db,'SELECT r.* FROM results r JOIN members m ON r.installation_id=m.installation_id AND r.run_id=m.run_id JOIN profiles p ON p.installation_id=m.installation_id AND p.player_id=m.player_id JOIN profile_emails e ON e.installation_id=p.installation_id AND e.player_id=p.player_id WHERE e.email=? AND r.installation_id=? AND r.run_id=? AND p.player_id=?',[$email,$iid,$run,$pid])->fetch();
    if(!$r)fail('Result unavailable',404);
    return ['ok'=>true,'receipt'=>json_decode($r['body'],true,64,JSON_THROW_ON_ERROR)[$pid]];
}
