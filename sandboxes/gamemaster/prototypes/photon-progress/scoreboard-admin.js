(()=>{'use strict';
const $=id=>document.getElementById(id);let busy=false,last=null;
function render(s){last=s;const r=s.pairing_request,active=r&&['submitting','pending','cancelling'].includes(r.status);let message;
if(s.paired)message='Paired: '+s.name+' — automatic uploads enabled.';
else if(active){message={submitting:'Submitting pairing request. It is saved on this computer and will retry automatically.',pending:'Awaiting approval from kaur@mecharena.eu. No separate email is needed.',cancelling:'Cancelling request. Keep the game online until cancellation is confirmed.'}[r.status];if(r.status==='pending')message+='\n'+(r.notification==='submitted'?'Administrator notification submitted for email delivery.':'Administrator notification is waiting for delivery; the server will retry.');if(r.expires)message+='\nExpires: '+new Date(r.expires*1000).toLocaleString();message+='\nRequest ID: '+r.id;}
else if(r)message='Pairing request '+r.status+'. Submit a new request to connect this game.';
else message='Setup required. Request pairing to enable player emails and online statistics.';
$('scoreStatus').textContent=message+'\nQueued uploads: '+s.pending+(s.error?'\n'+s.error:'');
for(const id of ['requestPairing','pairInstallation','installationName','pairingContact','pairCode'])$(id).disabled=busy||s.paired||!!active;
$('cancelPairing').hidden=!active;$('cancelPairing').disabled=busy||r?.status==='cancelling';
$('disconnectScore').disabled=busy||!s.paired;$('retryScore').disabled=busy;
if(s.name&&!$('installationName').value)$('installationName').value=s.name;if(r?.contact_email&&!$('pairingContact').value)$('pairingContact').value=r.contact_email;
}
async function request(data){const r=await fetch('api/scoreboard',{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,cache:'no-store'});const v=await r.json();if(!r.ok||!v.ok)throw Error(v.error||'Scoreboard unavailable');render(v.scoreboard);return v.scoreboard;}
async function action(data){if(busy)return;busy=true;if(last)render(last);try{await request(data);if(data.action==='pair')$('pairCode').value='';}catch(e){$('scoreStatus').textContent=e.message;}finally{busy=false;if(last){const message=$('scoreStatus').textContent;render(last);$('scoreStatus').textContent=message;}}}
$('requestPairingForm').onsubmit=e=>{e.preventDefault();action({action:'request_pairing',name:$('installationName').value,contact_email:$('pairingContact').value});};
$('cancelPairing').onclick=()=>{if(confirm('Cancel this installation’s pairing request? Queued results will stay saved locally.'))action({action:'cancel_request'});};
$('pairInstallation').onclick=()=>action({action:'pair',name:$('installationName').value,code:$('pairCode').value});$('retryScore').onclick=()=>action({action:'retry'});
$('disconnectScore').onclick=()=>{if(confirm('Disconnect this computer? Queued results remain saved. Revoke its key on the website if access should be permanently removed.'))action({action:'disconnect'});};
request().catch(e=>$('scoreStatus').textContent=e.message);setInterval(()=>{if(!busy)request().catch(()=>{});},15000);
})();
