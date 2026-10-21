<?php
declare(strict_types=1);

function pairing_request_id(mixed $id): string {
    if(!is_string($id)||!preg_match('/^[a-f0-9]{32}$/D',$id))fail('Invalid pairing request');
    return $id;
}
function pairing_request_key(mixed $key): string {
    if(!is_string($key)||!preg_match('/^[a-f0-9]{64}$/D',$key))fail('Invalid installation key');
    return codehash($key);
}
function pairing_request_reply(PDO $db,array $row): array {
    $state=$row['status'];
    if($state==='pending' && $row['expires']<=time())$state='expired';
    if($state==='approved'){
        $i=sql($db,'SELECT revoked_at FROM installations WHERE id=?',[$row['installation_id']])->fetch();
        if(!$i||$i['revoked_at'])$state='revoked';
    }
    return ['ok'=>true,'request_id'=>$row['id'],'status'=>$state,'expires'=>(int)$row['expires'],
        'notification'=>$row['notified_at']?'submitted':'retrying',
        'installation_id'=>$state==='approved'?$row['installation_id']:null];
}
function pairing_request_owner(PDO $db,array $data): array {
    $id=pairing_request_id($data['request_id']??null);$hash=pairing_request_key($data['upload_key']??null);
    $row=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
    if(!$row||!hash_equals($row['key_hash'],$hash))fail('Pairing request access rejected',403);
    return $row;
}
function create_pairing_request(PDO $db,array $data,string $ip): array {
    $id=pairing_request_id($data['request_id']??null);$hash=pairing_request_key($data['upload_key']??null);
    $name=trim(textfield($data['name']??null,80));if($name==='')fail('Enter an installation name');
    $contact=email_value($data['contact_email']??null);
    $existing=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
    if(!$existing){
        if(!limit_rate($db,'pair-request-ip:'.$ip,3,3600)||!limit_rate($db,'pair-request-day:'.$ip,10,86400)
            ||!limit_rate($db,'pair-request-global',20,3600)||!limit_rate($db,'pair-request-global-day',100,86400))
            fail('Too many pairing requests. Please try again later.',429);
    }
    return transaction($db,function()use($db,$id,$hash,$name,$contact){
        // Replays must use the same secret and immutable operator details.
        $row=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
        if($row){
            if(!hash_equals($row['key_hash'],$hash))fail('Pairing request access rejected',403);
            if($row['name']!==$name||$row['contact_email']!==$contact)fail('Cancel the existing request before changing its details',409);
            return $row;
        }
        if(sql($db,'SELECT 1 FROM installations WHERE key_hash=?',[$hash])->fetchColumn()
            ||sql($db,'SELECT 1 FROM pairing_requests WHERE key_hash=?',[$hash])->fetchColumn())fail('This installation key is already registered',409);
        sql($db,"INSERT INTO pairing_requests(id,key_hash,name,contact_email,created_at,expires,status) VALUES(?,?,?,?,?,?,'pending')",
            [$id,$hash,$name,$contact,time(),time()+604800]);
        audit($db,'pairing-requested',codehash($contact),$id);
        return sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
    });
}
function notify_pairing_request(PDO $db,array $cfg,string $id,callable $mailer): void {
    // Claim a retry slot before sending: polling cannot flood the administrator.
    $row=transaction($db,function()use($db,$id){
        $r=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
        if(!$r||$r['status']!=='pending'||$r['expires']<=time()||$r['notified_at']||$r['notify_after']>time())return null;
        sql($db,'UPDATE pairing_requests SET notify_after=? WHERE id=?',[time()+300,$id]);
        return $r;
    });
    if(!$row)return;
    if(!limit_rate($db,'pair-notify-global',20,3600))return;
    $to=email_value($cfg['admins'][0]);
    $url=$cfg['base_url'].'/#pairing-request='.$id;
    $body="A game installation is asking to upload to the MechArena scoreboard.\n\nInstallation: ".$row['name']."\nOperator contact (provided by requester): ".$row['contact_email']."\nRequest ID: $id\n\nReview this request:\n$url\n\nSign in with your scoreboard administrator email, check the installation details, then choose Approve upload access or Reject request. Opening this link does not approve anything.\n\nApproval allows only new profile and result uploads. It grants no DreamHost management access or private scoreboard reading.\n\nThe request expires seven days after submission. The game completes pairing automatically after approval. No separate email from the operator is needed.\n";
    try{$sent=$mailer($to,'MechArena installation pairing request',$body);}catch(Throwable $e){$sent=false;}
    if($sent)sql($db,'UPDATE pairing_requests SET notified_at=? WHERE id=?',[time(),$id]);
    audit($db,$sent?'pairing-notification-accepted':'pairing-notification-rejected',codehash($to),$id);
}
function decide_pairing_request(PDO $db,string $id,string $decision,string $admin): array {
    pairing_request_id($id);if(!in_array($decision,['approved','rejected'],true))fail('Invalid pairing decision');
    return transaction($db,function()use($db,$id,$decision,$admin){
        $r=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
        if(!$r)fail('Pairing request unavailable',404);
        if($r['status']===$decision)return pairing_request_reply($db,$r);
        if($r['status']!=='pending'||$r['expires']<=time())fail('This pairing request is no longer pending',409);
        $iid=null;
        if($decision==='approved'){
            // Only this authenticated administrator action creates upload access.
            if(sql($db,'SELECT 1 FROM installations WHERE key_hash=?',[$r['key_hash']])->fetchColumn())fail('Installation already paired',409);
            $iid=bin2hex(random_bytes(16));
            sql($db,'INSERT INTO installations(id,name,key_hash,created_at) VALUES(?,?,?,?)',[$iid,$r['name'],$r['key_hash'],time()]);
        }
        sql($db,'UPDATE pairing_requests SET status=?,installation_id=?,decided_at=?,decided_by=? WHERE id=?',[$decision,$iid,time(),$admin,$id]);
        audit($db,'pairing-request-'.$decision,$admin,$id);
        return pairing_request_reply($db,sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch());
    });
}
function cancel_pairing_request(PDO $db,array $data): array {
    return transaction($db,function()use($db,$data){
        $id=pairing_request_id($data['request_id']??null);$hash=pairing_request_key($data['upload_key']??null);
        $r=sql($db,'SELECT * FROM pairing_requests WHERE id=?',[$id])->fetch();
        if(!$r)return ['ok'=>true,'request_id'=>$id,'status'=>'cancelled'];
        if(!hash_equals($r['key_hash'],$hash))fail('Pairing request access rejected',403);
        // If approval and cancellation cross in flight, cancellation wins.
        if($r['installation_id'])sql($db,'UPDATE installations SET revoked_at=COALESCE(revoked_at,?) WHERE id=?',[time(),$r['installation_id']]);
        sql($db,"UPDATE pairing_requests SET status='cancelled' WHERE id=?",[$id]);
        if($r['status']!=='cancelled')audit($db,'pairing-request-cancelled',codehash($r['contact_email']),$id);
        return ['ok'=>true,'request_id'=>$id,'status'=>'cancelled'];
    });
}
function pending_pairing_requests(PDO $db): array {
    return sql($db,"SELECT id,name,contact_email,created_at,expires,notified_at FROM pairing_requests WHERE status='pending' AND expires>? ORDER BY created_at DESC",[time()])->fetchAll();
}
