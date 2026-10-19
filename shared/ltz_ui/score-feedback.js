/* Bounded cumulative feedback. Mirrored counters share one animation clock. */
(function(root){
'use strict';
class RingNotice{
 constructor(){this.key=null;this.timer=null;this.node=null;}
 update(state){
  if(typeof document==='undefined')return;
  const notice=state?.core_sequence?.ring_notice,key=state?.run_id+':'+notice?.sequence;
  if(state?.phase!=='running'||!notice){if(this.node)this.node.hidden=true;this.key=null;clearTimeout(this.timer);return;}
  if(key===this.key)return;
  this.key=key;clearTimeout(this.timer);
  if(!this.node){this.node=document.createElement('div');this.node.className='ltzRingNotice';this.node.setAttribute('role','status');this.node.setAttribute('aria-live','polite');document.body.append(this.node);}
  const remaining=8000-Math.max(0,((state.server_time||Date.now()/1000)-notice.at)*1000);
  this.node.hidden=notice.kind==='activated'&&remaining<=0;
  this.node.dataset.kind=notice.kind;this.node.textContent=notice.message;
  if(notice.kind==='activated'&&remaining>0)this.timer=setTimeout(()=>{this.node.hidden=true;},remaining);
 }
}
class ScoreFeedback{
 constructor(number,burst,detail,{killNumber=null,copies=[],now=()=>performance.now(),raf=fn=>requestAnimationFrame(fn),reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches}={}){Object.assign(this,{number,burst,detail,now,raf,reduced});this.ringNotice=new RingNotice();this.numbers=[number,...copies.map(c=>c.number)].filter(Boolean);this.killNumbers=[killNumber,...copies.map(c=>c.killNumber)].filter(Boolean);this.run=null;this.sequence=-1;this.total=0;this.shown=0;this.shownKills=0;this.kills=0;this.frame=null;this.resetNext=false;this.burstAt=-Infinity;this.burstValue=0;this.burstKills=0;this.burstBrutes=0;this.lastReceipt=null;this.animations=[];}
 reconnect(){this.resetNext=true;}
 write(nodes,value){const text=typeof value==='number'?Math.floor(value).toLocaleString():value;for(const node of nodes){node.textContent=text;node.style?.setProperty('--score-digits',String(text.length));}}
 render(value,kills){this.shown=value;this.shownKills=kills;this.write(this.numbers,value);this.write(this.killNumbers,kills);}
 update(state){
  this.ringNotice.update(state);
  const s=state?.match_score;if(s?.contract!=='photon.match-score'||s.version!==1||s.status!=='ready'){this.unavailable=true;this.resetNext=true;this.write([...this.numbers,...this.killNumbers],'—');return;}
  const run=state.run_id||'preview',now=this.now(),initial=this.run!==run||this.resetNext;
  const receipt=state.mobile_progress?.latest_result,attempt=state.progress?.result;
  const saved=receipt?.run_id===run?receipt:attempt?.run_id===run?{stack_bonus:attempt.reward_enabled?attempt.bonus_credits||0:0,total_earned:(attempt.kill_credits||0)+(attempt.reward_enabled?attempt.bonus_credits||0:0)}:null;
  const bonus=saved?.stack_bonus||0,total=s.kill_credits+bonus,kills=state.kills||0;
  if(!Number.isSafeInteger(total)||total<0||!Number.isSafeInteger(s.sequence)||!Number.isSafeInteger(kills)||kills<0)return;
  if(!initial&&(s.sequence<this.sequence||total<this.total||kills<this.kills))return;
  this.unavailable=false;
  if(this.burst&&now-this.burstAt>1000)this.burst.textContent='';
  if(initial){this.run=run;this.sequence=s.sequence;this.total=total;this.kills=kills;this.counts={...s.counts};this.resetNext=false;if(this.burst)this.burst.textContent='';this.burstValue=0;this.render(total,kills);this.start=now;this.from=total;this.fromKills=kills;this.lastReceipt=saved?run:null;}
  else if(s.sequence>=this.sequence&&total>=this.total){
   const delta=total-this.total,dk=kills-this.kills,brutes=(s.counts?.brute||0)-(this.counts?.brute||0);
   if(delta>0||dk>0){
    if(now-this.burstAt>220){this.burstValue=0;this.burstKills=0;this.burstBrutes=0;}
    this.burstValue+=delta;this.burstKills+=Math.max(0,dk);this.burstBrutes+=Math.max(0,brutes);this.burstAt=now;
    if(this.burst){this.burst.textContent=bonus&&this.lastReceipt!==run?`Center health bonus +${bonus.toLocaleString()}`:`+${this.burstValue.toLocaleString()} · ${this.burstKills} kills${this.burstBrutes?' · Large brute':''}`;this.burst.classList?.toggle('large',this.burstBrutes>0||bonus>0);}
    this.animations.forEach(a=>a?.cancel());
    this.animations=[...(delta>0?this.numbers:[]),...(dk>0?this.killNumbers:[])].map(node=>node.animate?.(this.reduced()?[{opacity:.65},{opacity:1}]:[{transform:'scale(1.08)',color:'#ffe1a1'},{transform:'scale(1)',color:'inherit'}],{duration:this.burstBrutes?280:180}));
    this.from=this.shown;this.fromKills=this.shownKills;this.start=now;this.total=total;this.kills=kills;
    if(this.reduced())this.render(total,kills);else if(this.frame==null)this.frame=this.raf(()=>this.tick());
   }
   this.sequence=s.sequence;this.kills=state.kills||0;this.counts={...s.counts};if(saved)this.lastReceipt=run;
  }
  if(this.detail)this.detail.textContent=`Event score · ${(state.kills||0).toLocaleString()} kills`;
 }
 tick(){this.frame=null;if(this.unavailable)return;const amount=Math.min(1,(this.now()-this.start)/180),eased=1-(1-amount)**3;this.render(this.from+(this.total-this.from)*eased,this.fromKills+(this.kills-this.fromKills)*eased);if(amount<1)this.frame=this.raf(()=>this.tick());else this.render(this.total,this.kills);}
}
root.LTZScoreFeedback=ScoreFeedback;if(typeof module!=='undefined')module.exports=ScoreFeedback;
})(typeof window==='undefined'?globalThis:window);
