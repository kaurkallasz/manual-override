/* Operator-only scoreboard link notice, updated by the existing game stream. */
window.LTZScoreboardNotice={create({container,title,message,link,root}){
 let lastState=null,completed=false,received=performance.now();
 const set=(node,text)=>{if(node.textContent!==text)node.textContent=text;};
 link.href=`${root}/p/photon-progress/#online-scoreboard`;
 function paint(state,heading,detail,label='Open linking page ↗'){
  container.dataset.state=state;set(title,heading);set(message,detail);set(link,label);
 }
 function disconnect(){paint('unavailable','Scoreboard link status unavailable','Linking status could not be confirmed. Open the linking page to check this installation.');}
 function update(value){
  if(value?.contract!=='photon.scoreboard-link'||value.version!==1||value.status!=='ready'||typeof value.upload_delayed!=='boolean')return disconnect();
  const state=value.state;
  if(!['linked','unlinked','submitting','pending','cancelling','cancelled','rejected','expired','revoked'].includes(state))return disconnect();
  received=performance.now();
  if(state==='linked'){
   if(lastState&&lastState!=='linked')completed=true;
   if(value.upload_delayed)paint('attention','Scoreboard linked · uploads need attention','Results stay saved locally. Open the linking page to check the upload status.');
   else paint('linked',completed?'Scoreboard linking complete':'Online scoreboard linked','Automatic uploads are enabled for this game.','Manage linking ↗');
  }else{
   completed=false;
   if(state==='pending')paint('pending','Scoreboard linking awaiting approval','Waiting for Kaur to approve this installation. Uploads start automatically after approval.');
   else if(state==='submitting')paint('pending','Requesting scoreboard linking','The request is saved locally and will retry automatically when connected.');
   else if(state==='cancelling')paint('pending','Cancelling scoreboard linking','Keep the game connected until cancellation is confirmed.');
   else {
    const detail={unlinked:'Player statistics and emails stay queued until this installation is linked.',cancelled:'The pairing request was cancelled. Open the linking page to submit a new request.',rejected:'The pairing request was rejected. Open the linking page to review setup or request again.',expired:'The pairing request expired. Open the linking page to submit a new request.',revoked:'Upload access was revoked. Open the linking page to request access again.'}[state];
    paint('unlinked','Online scoreboard not linked',detail);
   }
  }
  lastState=state;
 }
 const watchdog=setInterval(()=>{if(performance.now()-received>25000)disconnect();},5000);
 return {update,disconnect,destroy(){clearInterval(watchdog);}};
}};
