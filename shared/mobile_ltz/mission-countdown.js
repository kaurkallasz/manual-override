/* Both players render Game's countdown clock; reconnecting never restarts it. */
(() => {
 'use strict';
 const overlay=document.createElement('div');
 overlay.id='missionCountdown';overlay.hidden=true;overlay.setAttribute('aria-live','assertive');
 overlay.setAttribute('aria-atomic','true');overlay.setAttribute('role','status');
 const numeral=document.createElement('span');overlay.append(numeral);
 document.getElementById('app').append(overlay);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let key=null,animation=null,currentState=null,waiting=false;
 function clear(){overlay.hidden=true;animation?.cancel();animation=null;key=null;numeral.textContent='';overlay.classList.remove('gettingReady');}
 function show(label,nextKey,gettingReady=false){
  overlay.hidden=false;overlay.classList.toggle('gettingReady',gettingReady);
  if(key===nextKey)return;
  key=nextKey;animation?.cancel();animation=null;numeral.textContent=label;
  if(!reduced.matches)animation=numeral.animate([
   {transform:'scale(.55)',opacity:1},
   {transform:'scale(1.65)',opacity:0}
  ],{duration:gettingReady?2000:1000,iterations:gettingReady?Infinity:1,easing:'cubic-bezier(.16,.5,.32,1)',fill:'both'});
 }
 function update(state){
  currentState=state;
  if(state.status==='ready'&&state.phase==='setup'&&waiting){
   show('Get ready','waiting:'+reduced.matches,true);return;
  }
  const c=state.start_countdown;
  if(state.status!=='ready'||state.phase!=='running'||c?.contract!=='photon.game.start-countdown'||c.version!==1||!(c.duration_s>0)){clear();return;}
  const remaining=Number(c.remaining_s),elapsed=Number(c.go_elapsed_s);
  if(!Number.isFinite(remaining)||!Number.isFinite(elapsed)||remaining<0||elapsed<0||(remaining===0&&elapsed>=1)){clear();return;}
  const label=remaining>0?String(Math.ceil(remaining)):'GO!';
  const progress=remaining>0?Math.ceil(remaining)-remaining:elapsed;
  const nextKey=[state.run_id||c.started_at,label,reduced.matches].join(':');
  show(label,nextKey);
  if(animation){
   if(Math.abs((animation.currentTime||0)-progress*1000)>120||state.paused)animation.currentTime=progress*1000;
   if(state.paused)animation.pause();else if(animation.playState==='paused')animation.play();
  }
 }
 function setWaiting(value){if(waiting===value)return;waiting=value;if(currentState)update(currentState);}
 window.MobileCountdown={update,clear,setWaiting};
 window.addEventListener('pagehide',clear);
})();
