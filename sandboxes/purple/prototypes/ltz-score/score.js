(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const side = location.pathname.includes('/purple/') ? 'purple' : 'green';
  const API = '/s/gamemaster/p/photon-progress/api';
  const GAME = '/s/gamemaster/p/photon-game/api';
  const modes = ['Joint-angle', 'Cartesian XYZ', 'Image Targeting', 'Cue Autonomy'];
  if (side === 'purple') { document.documentElement.style.setProperty('--accent', '#b86bff'); document.documentElement.style.setProperty('--accent-rgb', '184,107,255'); }
  const tracks = [
    {id:'control',name:'Control System',baseline:'Joint-angle control',names:modes.slice(1),sprites:['assets/control-xyz-v1.png','assets/control-click-v1.png','assets/control-cue-v1.png']},
    {id:'damage-machine-gun',name:'Machine Gun',weapon:'machine-gun',names:['Hot Feed','Twin Actuator','Storm Driver']},
    {id:'damage-flamethrower',name:'Flamethrower',weapon:'flamethrower',names:['Hotter Mix','Pressure Chamber','Inferno Manifold']},
    {id:'damage-mortar',name:'Mortar',weapon:'mortar',names:['Packed Shell','Twin Loader','Siege Breech']},
    {id:'damage-tesla-coil',name:'Tesla Coil',weapon:'photon-detonator',names:['Focused Coil','Dual Capacitor','Storm Core']},
    {id:'forcefield',name:'Force Field',names:['Expanded Arc','Dual-Layer Field','Bastion Barrier']}
  ];
  let state = null, busy = false, revealing = null, previews = [], history = [], historyData = null, nextCursor = null, historyGeneration = 0, selectedId = null, toastTimer;
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = value => Number(value || 0).toLocaleString();
  const clock = value => value == null ? '—' : `${Math.floor(value/60)}:${(value%60).toFixed(1).padStart(4,'0')}`;
  const when = value => new Date(value*1000).toLocaleString();
  const operation = () => crypto.randomUUID();
  async function json(url, options) { const response=await fetch(url,options); const data=await response.json(); if(!response.ok||data.ok===false||data.status==='unavailable') throw Error(data.error||'Progress unavailable'); return data; }
  function status(text,error=false){$('saveStatus').textContent=text;$('saveStatus').classList.toggle('error',error);}
  function toast(text){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').classList.add('show');toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2200);}
  function active(){return Boolean(state?.active_attempts?.some(a=>a.participants.some(p=>p.player_id===state?.player?.id)));}
  function tile(label,value){return `<div class="stat-tile"><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`;}
  function cost(track,level){return (track==='forcefield'?1000:250)*(level-1);}
  function apply(data){
    if(data.status!=='ready')throw Error(data.error||'Progress unavailable');
    if(data.contract!=='photon.progress'||data.version!==1)throw Error('Progress contract mismatch');
    if(state&&data.revision<state.revision)return;
    const changed=data.revision!==state?.revision,old=state?.player;
    state=data;
    if(old&&old.id===data.player?.id&&data.player.unlocked_control>old.unlocked_control){revealing=`control:${data.player.unlocked_control}`;toast(`${modes[data.player.unlocked_control-1]} unlocked`);setTimeout(()=>{revealing=null;render();},1100);}
    render();status('Saved on the game server');
    if(changed){if(selectedId!==state.player?.id){selectedId=state.player?.id;$('cohort').value='';}loadHistory();}
  }
  function render(){
    const p=state?.player,locked=busy||active();
    $('scoreValue').textContent=p?number(p.credits):'—';
    const currentChoice=$('playerSelect').value;
    $('playerSelect').innerHTML='<option value="">Select a player</option>'+(state?.players||[]).map(x=>`<option value="${esc(x.id)}">${esc(x.name)} · ${esc(x.id.slice(0,6))}</option>`).join('');
    $('playerSelect').value=p?.id||currentChoice;
    $('controlSelect').innerHTML=modes.map((name,i)=>`<option value="${i+1}" ${!p||i+1>p.unlocked_control?'disabled':''}>${name}${!p||i+1>p.unlocked_control?' · locked':''}</option>`).join('');
    $('controlSelect').value=p?.selected_control||1;$('controlSelect').disabled=!p||locked;
    for(const id of ['loadPlayer','releasePlayer','createPlayer'])$(id).disabled=locked;
    const run=state?.active_attempts?.find(a=>a.participants.some(x=>x.player_id===p?.id));
    const roster=Object.values(state?.roster||{});const contractTier=Math.max(1,...roster.map(x=>x.selected_control));
    $('runStatus').textContent=run?`${run.reward_enabled?'Scored game':'Practice game'} in progress · ${run.banked_kills} kills checkpointed. Profiles and upgrades are fixed until this attempt ends.`:p?`Selected: ${modes[p.selected_control-1]} · Shared battlefield: ${modes[contractTier-1]}${previews[contractTier-1]?` · ${number(previews[contractTier-1].total)} scheduled orcs`:''}.`:'Load a saved player before joining a scored game.';
    $('tracks').innerHTML=tracks.map((track,index)=>{
      const current=track.id==='control'?(p?.unlocked_control||1):(p?.levels[track.id]||1);
      const cards=[2,3,4].map(level=>{
        const owned=current>=level,available=track.id==='control'?owned:current+1===level;
        const cardState=owned?'unlocked':available?'available':'sealed';
        const credits=track.id==='control'?0:cost(track.id,level);
        const wins=p?.wins_by_tier[level-2]||0;
        const button=track.id==='control'?(owned?(p?.selected_control===level?'Selected':'Select method'):`${Math.min(3,wins)}/3 wins with ${modes[level-2]}`):(owned?'Installed':available?`Upgrade · ${number(credits)}`:`Requires Level ${level-1}`);
        const detail=track.id==='control'?`${previews[level-1]?Math.round(previews[level-1].multiplier*100)+'% of authored orcs':'More orcs at this tier'} · ${previews[level-1]?number(previews[level-1].total)+' scheduled':''}`:track.id==='forcefield'?`+${20*(level-1)}% hit capacity`:`+${10*(level-1)}% damage and unit health${level===4 ? " · Same-weapon companion with shared health and aim, except in the middle line" : ""}`;
        const sprite=track.sprites?.[level-2]||(track.weapon?`art/structures/upgrades/${track.weapon}-upgrade-l${level}-v1.png`:'assets/force-field-atlas.png');
        const enabled=p&&!locked&&(track.id==='control'?owned&&p.selected_control!==level:!owned&&available&&p.credits>=credits);
        return `<article class="upgrade-card ${track.weapon?'damage':track.id} level-${level} ${cardState} ${revealing===track.id+':'+level?'revealing':''}"><div class="card-topline"><span>${esc(track.name)} · L${level}</span><span>${owned?'Online':available?'Ready':'Path locked'}</span></div><div class="card-visual">${track.id==='forcefield'?`<span class="field-upgrade-art" role="img" aria-label="Force field level ${level}" style="background-position:center ${(level-2)*50}%"></span>`:`<img class="upgrade-sprite" src="${sprite}" alt="${esc(track.name)} level ${level}" draggable="false">`}</div><div class="card-copy"><h3>${esc(track.names[level-2])}</h3><p>${esc(detail)}</p></div>${owned?'':'<div class="shutters" aria-hidden="true"><i class="shutter-half shutter-half--left"></i><i class="shutter-half shutter-half--right"></i><img class="shutter-lock" src="assets/upgrade-lock-shutter-v1.png" alt=""></div>'}<div class="reveal-flash" aria-hidden="true"></div><button class="buy-button" data-track="${track.id}" data-level="${level}" ${enabled?'':'disabled'}>${esc(button)}</button></article>`;
      }).join('');
      return `<section class="track"><header class="track-label"><div class="track-label__index">SYS / 0${index+1}</div><h2>${esc(track.name)}</h2><div class="track-label__baseline"><strong>${esc(track.baseline||'Weapon system')}</strong>${track.id==='control'?'Three wins unlock each new method':'Saved upgrades apply on the next game map'}</div><div class="track-label__level"><div class="level-readout"><span>Installed tier</span><strong>L${current}</strong></div></div></header>${cards}`+'</section>';
    }).join('');
    $('tracks').querySelectorAll('[data-track]').forEach(button=>button.onclick=()=>mutate({action:button.dataset.track==='control'?'control':'purchase',track:button.dataset.track,level:Number(button.dataset.level)}));
    $('statsPlayer').textContent=p?`${p.name} · Whole-profile totals across scored games`:'Choose a saved player to load their statistics.';
    $('statsTiles').innerHTML=[['Lifetime score / credited kills',number(p?.lifetime_score)],['Available credits',number(p?.credits)],['Attempts',number(p?.attempts)],['Wins',number(p?.wins)],['Win rate',p?.attempts?`${Math.round(100*p.wins/p.attempts)}%`:'—'],['Highest control',p?modes[p.unlocked_control-1]:'—']].map(x=>tile(...x)).join('');
    $('mastery').innerHTML=(p?.wins_by_tier.every(n=>n>=3)?'<strong>All four levels mastered</strong>':'')+modes.map((name,i)=>`<span>${name} · ${Math.min(3,p?.wins_by_tier[i]||0)}/3 wins</span>`).join('');
  }
  async function post(data){return json(`${API}/player?side=${side}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,side})});}
  async function mutate(data){if(!state?.player||busy)return;busy=true;render();status('Saving…');try{apply(await post({...data,revision:state.player.revision,operation_id:operation()}));if(data.action==='purchase'){revealing=`${data.track}:${data.level}`;render();toast('Upgrade installed for your next game');setTimeout(()=>{revealing=null;render();},1100);}}catch(e){status(e.message,true);try{apply(await json(`${API}/state?side=${side}`));status(e.message,true);}catch(_) {}}finally{busy=false;render();}}
  $('loadPlayer').onclick=async()=>{try{apply(await post({action:'select',player_id:$('playerSelect').value||null}));}catch(e){status(e.message,true);}};
  $('releasePlayer').onclick=async()=>{try{apply(await post({action:'select',player_id:null}));}catch(e){status(e.message,true);}};
  $('createPlayer').onclick=async()=>{if(busy)return;busy=true;render();try{const data=await post({action:'create',name:$('playerName').value,operation_id:operation()});apply(await post({action:'select',player_id:data.result.player_id}));$('playerName').value='';}catch(e){status(e.message,true);}finally{busy=false;render();}};
  $('controlSelect').onchange=()=>mutate({action:'control',level:Number($('controlSelect').value)});
  function filters(){const q=new URLSearchParams({side,dataset:$('dataset').value});for(const [id,key]of[['tierFilter','tier'],['cohort','cohort']])if($(id).value)q.set(key,$(id).value);if($('fromDate').value)q.set('from',new Date($('fromDate').value+'T00:00:00').getTime()/1000);if($('toDate').value)q.set('to',new Date($('toDate').value+'T23:59:59').getTime()/1000);return q;}
  async function loadHistory(append=false){const generation=++historyGeneration;if(!state?.player){history=[];historyData=null;nextCursor=null;drawHistory();return;}if(!append){history=[];$('historyStatus').textContent='Loading performance history…';}try{const q=filters();if(append&&nextCursor!=null)q.set('cursor',nextCursor);const data=(await json(`${API}/history?${q}`)).history;if(generation!==historyGeneration)return;history=append?history.concat(data.rows):data.rows;historyData=data;nextCursor=data.next_cursor;const selected=$('cohort').value;$('cohort').innerHTML='<option value="">All configurations</option>'+data.cohorts.map((c,i)=>`<option value="${c.id}">${esc(modes[c.tier-1])} · ${c.metadata.orc_schedule?.total??'?'} orcs · ${c.count} games · ${c.id.slice(0,5)}</option>`).join('');$('cohort').value=selected;drawHistory();}catch(e){if(generation===historyGeneration){$('historyStatus').textContent=`Could not load history: ${e.message}`;$('historyChart').replaceChildren();$('historyRows').replaceChildren();}}}
  function details(row){return `${when(row.finished_at)} · ${modes[row.control_tier-1]} · ${row.outcome} · ${row.score} credits · ${clock(row.active_seconds)} · ${row.partner} · ${row.released_orcs??'?'} / ${row.metadata.orc_schedule?.total??'?'} orcs released/scheduled · settings revision ${row.metadata.settings_revision??'?'} · companion rules ${row.metadata.companion_policy?.version??'legacy'} · ${row.unlocked_control?'Unlocked '+modes[row.unlocked_control-1]:row.completion_awarded?'counts toward progression':'no completion'} · upgrades ${Object.entries(row.levels).map(([k,v])=>k.replace('damage-','')+' L'+v).join(', ')}`;}
  function drawHistory(){
    const summary=historyData?.summary,metric=$('metric').value;
    const change=metric==='time'?summary?.time_change:metric==='score'?summary?.score_change:null;
    $('historySummary').innerHTML=[['Filtered attempts',number(summary?.attempts)],['Best comparable score',summary?.best_score??'—'],['Best comparable time',clock(summary?.best_time)],['Recent improvement',change?(change.percent==null?`${change.absolute>=0?'+':''}${change.absolute.toFixed(1)}`:`${change.percent>=0?'+':''}${change.percent.toFixed(1)}%`):'—']].map(x=>tile(...x)).join('');
    $('historyStatus').textContent=!state?.player?'Select a player to see their performance.':history.length?`${history.length} of ${historyData.total} results shown. ${summary.comparable?'Comparing matching configurations.':'Select one configuration for a meaningful trend.'}${!change?' More comparable runs are needed for a recent-improvement percentage.':''}`:'No finished games yet. Your results will appear here.';
    $('loadMore').hidden=nextCursor==null;
    $('historyRows').innerHTML=history.map((r,i)=>`<tr tabindex="0" data-result="${i}"><td>${esc(when(r.finished_at))}</td><td>${esc(modes[r.control_tier-1])}</td><td>${esc(r.outcome)}</td><td>${r.score}</td><td>${clock(r.active_seconds)}</td><td>${esc(r.partner)}</td><td>${r.released_orcs??'—'} / ${r.metadata.orc_schedule?.total??'—'}</td><td>${r.unlocked_control?'Unlocked '+esc(modes[r.unlocked_control-1]):r.completion_awarded?'Win credited':'No completion'}</td></tr>`).join('');
    $('historyRows').querySelectorAll('[data-result]').forEach(row=>{const show=()=>{$('pointDetails').textContent=details(history[Number(row.dataset.result)]);};row.onfocus=show;row.onclick=show;});
    const wrap=$('historyChart');wrap.replaceChildren();
    const points=history.filter(r=>metric!=='time'||r.outcome==='won'&&r.active_seconds!=null);
    if(!points.length){wrap.textContent=metric==='time'?'No completed wins in this view.':'No results to graph yet.';return;}
    const ns='http://www.w3.org/2000/svg',el=(name,attrs={},text)=>{const e=document.createElementNS(ns,name);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!=null)e.textContent=text;return e;};
    const svg=el('svg',{viewBox:'0 0 1080 300',role:'img','aria-label':`${metric==='time'?'Completion time (lower is better)':metric==='winrate'?'Cumulative win rate':'Run score'} over time`});wrap.append(svg);
    let winCount=0;const values=points.map((p,i)=>metric==='time'?p.active_seconds:metric==='winrate'?(winCount+=p.outcome==='won'?1:0)/(i+1)*100:p.score);
    const max=Math.max(1,...values)*1.1,first=points[0].finished_at,last=points.at(-1).finished_at;
    const x=(p,i)=>60+960*($('axis').value==='attempt'?(points.length===1?.5:i/(points.length-1)):(last===first?.5:(p.finished_at-first)/(last-first)));
    const y=v=>250-220*v/max;
    for(let i=0;i<5;i++){const v=max*i/4;svg.append(el('line',{x1:60,y1:y(v),x2:1020,y2:y(v),stroke:'#253c47'}),el('text',{x:50,y:y(v)+4,fill:'#9eb8c1','font-size':12,'text-anchor':'end'},metric==='time'?clock(v):Math.round(v)+(metric==='winrate'?'%':'')));}
    svg.append(el('text',{x:60,y:281,fill:'#9eb8c1','font-size':12},$('axis').value==='attempt'?'Attempt 1':new Date(first*1000).toLocaleDateString()),el('text',{x:1020,y:281,fill:'#9eb8c1','font-size':12,'text-anchor':'end'},$('axis').value==='attempt'?`Attempt ${points.length}`:new Date(last*1000).toLocaleDateString()));
    const groups=new Map();points.forEach((p,i)=>{if(!groups.has(p.cohort))groups.set(p.cohort,[]);groups.get(p.cohort).push({p,i,v:values[i]});});
    const colors=['#49d99b','#c796ff','#f3c35b','#60cfff'];let groupIndex=0;
    for(const entries of groups.values()){const color=colors[groupIndex++%colors.length];svg.append(el('polyline',{points:entries.map(({p,i,v})=>`${x(p,i)},${y(v)}`).join(' '),fill:'none',stroke:color,'stroke-width':1.5,opacity:.65}));if(metric!=='winrate')svg.append(el('polyline',{points:entries.map(({p,i},j)=>`${x(p,i)},${y(entries.slice(Math.max(0,j-2),j+1).reduce((s,e)=>s+e.v,0)/Math.min(3,j+1))}`).join(' '),fill:'none',stroke:color,'stroke-dasharray':'6 5','stroke-width':2}));for(const{p,i,v}of entries){const circle=el('circle',{cx:x(p,i),cy:y(v),r:5,fill:p.outcome==='won'?color:'#10222b',stroke:color,'stroke-width':2,tabindex:0,role:'button','aria-label':details(p)});circle.append(el('title',{},details(p)));circle.onclick=circle.onfocus=()=>{$('pointDetails').textContent=details(p);};circle.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')circle.onclick();};svg.append(circle);if(p.unlocked_control)svg.append(el('text',{x:x(p,i),y:y(v)-13,fill:color,'font-size':11,'text-anchor':'middle'},'↑ L'+p.unlocked_control));}}
  }
  for(const id of ['dataset','tierFilter','fromDate','toDate','cohort'])$(id).onchange=()=>{if(id!=='cohort')$('cohort').value='';loadHistory();};
  for(const id of ['metric','axis'])$(id).onchange=drawHistory;
  $('loadMore').onclick=()=>loadHistory(true);
  render();drawHistory();json(`${API}/state?side=${side}`).then(apply).catch(e=>status(e.message,true));
  const events=new EventSource(`${API}/events?side=${side}`);events.onmessage=e=>{try{apply(JSON.parse(e.data));}catch(error){status(error.message,true);}};events.onerror=()=>status('Connection lost. Reconnecting to saved progress…',true);
  const gameEvents=new EventSource(`${GAME}/events?view=configuration`);gameEvents.onmessage=e=>{try{const data=JSON.parse(e.data);previews=data.previews||[];render();}catch(_){}};
  window.addEventListener('pagehide',()=>{events.close();gameEvents.close();});
})();
