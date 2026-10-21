/* Read-only equipment and durable event match receipts. */
(function(root){
'use strict';
const names={'damage-machine-gun':'Machine Gun','damage-flamethrower':'Flamethrower','damage-mortar':'Mortar','damage-tesla-coil':'Tesla Coil'};
const weapons={'damage-machine-gun':'machine-gun','damage-flamethrower':'flamethrower','damage-mortar':'mortar','damage-tesla-coil':'photon-detonator'};
const controls=['Joint','XYZ','Image targeting','Cue'];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=v=>Number(v||0).toLocaleString();
let asset=id=>'/s/gamemaster/p/photon-level/assets/'+id;
function receipt(r,p){
 if(!r)return '';
 if(r.statistics)return levelReceipt(r,p);
 const retry=['interrupted','aborted'].includes(r.outcome);
 const label=retry?(r.outcome==='interrupted'?'Game interrupted':'Game stopped before completion'):r.outcome==='operator_ended'?'Ended by Game Master':r.victory_method==='center_stack'?'Center stack victory':r.victory_method==='waves_cleared'?'All waves survived':r.outcome==='overrun'?'Core overrun':r.outcome;
 const bought=r.purchases||[],balance=r.balance??p?.credits;
 return `<section class="ltzReceipt" data-result="${esc(r.run_id)}"><span class="ltzEyebrow">Event result saved</span><h2>${esc(label)}</h2><div class="ltzResultNumbers"><span><strong>${n(r.kills)}</strong> kills</span><span><strong>${n(r.kill_credits)}</strong> score</span><span><strong>+${n(r.stack_bonus)}</strong> stack bonus</span><span><strong>${n(r.total_earned)}</strong> credits earned</span><span>${r.active_seconds==null?'Duration unavailable':Math.floor(r.active_seconds/60)+':'+Math.floor(r.active_seconds%60).toString().padStart(2,'0')}</span></div>${bought.map(b=>`<p class="ltzBonus">${esc(names[b.track])} → T${b.level} · −${n(b.price)} credits${b.forced?' · Game Master upgrade':''}</p>`).join('')||'<p>Credits saved toward the next turret upgrade.</p>'}${balance!=null?`<p><strong>${n(balance)} credits remaining</strong>${balance<0?' · Future earnings repay this balance.':''}</p>`:''}${r.unlocked_control?`<p class="ltzBonus">L${r.unlocked_control} ${esc(controls[r.unlocked_control-1])} and force field unlocked${r.unlocked_control===4?' · Second Atom unlocked':''}${r.manual_advance?' · Game Master override':''}</p>`:''}</section>`;
}
function counter(value,extra=''){
 if(value==null)return '<strong>—</strong>';
 return `<strong data-count="${Number(value)}" ${extra}>${n(value)}</strong>`;
}
function compareCard(title,value,empty,detail){
 const amount=value?(value.percent??value.delta):null,unit=value?.percent!=null?'%':' pts';
 return `<article class="ltzCompare ${amount>0?'positive':amount<0?'negative':''}"><span>${esc(title)}</span>${value?counter(amount,`data-signed="1" data-decimals="${value.percent!=null?1:0}" data-unit="${unit}"`):'<strong>—</strong>'}<small>${esc(value?detail:empty)}</small></article>`;
}
function historyGraph(s){
 const rows=s.history||[],max=Math.max(1,...rows.map(r=>r.score))*1.15;
 const x=i=>rows.length===1?300:38+i*524/(rows.length-1),y=v=>132-v/max*106;
 const points=rows.map((r,i)=>`${x(i)},${y(r.score)}`).join(' ');
 const path=rows.map((r,i)=>`${i?'L':'M'}${x(i)},${y(r.score)}`).join(' ');
 return `<div class="ltzHistory"><div class="ltzHistoryTitle"><h3>Your team's journey</h3><span>${n(s.history_total)} games · ${rows.length<s.history_total?'latest 60 · ':''}all levels</span></div><div class="ltzHistoryPlot" data-reveal-key="history" style="--delay:700ms"><svg viewBox="0 0 600 165" role="img" aria-label="Team score history: ${esc(rows.map(r=>`Level ${r.level}, ${r.score} points${r.assisted?', assisted':''}`).join('; '))}"><line x1="38" y1="132" x2="562" y2="132" stroke="#35515b"/><line x1="38" y1="79" x2="562" y2="79" stroke="#243943" stroke-dasharray="3 6"/><text x="3" y="135">0</text><text x="3" y="29">${n(Math.round(max))}</text>${rows.length>1?`<path class="ltzHistoryArea" style="--delay:250ms" d="${path} L562,132 L38,132 Z"/><polyline class="ltzHistoryLine" style="--delay:0ms" points="${points}" pathLength="1"/>`:''}${rows.map((r,i)=>`<circle class="ltzHistoryDot ${r.assisted?'assisted':''}" style="--delay:${200+i*20}ms" cx="${x(i)}" cy="${y(r.score)}" r="${i===rows.length-1?5:3}"><title>L${r.level} · ${n(r.score)} score${r.assisted?' · Game Master assisted':''}</title></circle>`).join('')}<text x="38" y="157">${rows.length===1?'First game':'Earlier games'}</text><text x="562" y="157" text-anchor="end">This game · L${s.level}</text></svg></div><p>Weighted kill score · higher is better. Levels and difficulty may change. Hollow dots: assisted games.</p></div>`;
}
function heatmap(h){
 if(!h)return '<section class="ltzHeatmap"><h3>Orc kill heatmap</h3><p>Kill locations were not recorded for this older level.</p></section>';
 const max=Math.max(0,...h.counts),total=h.counts.reduce((a,b)=>a+b,0),w=640,height=w*h.height/h.width,cw=w/h.columns,ch=height/h.rows;
 const cells=h.counts.map((count,i)=>count?`<rect x="${i%h.columns*cw}" y="${Math.floor(i/h.columns)*ch}" width="${cw}" height="${ch}" fill="hsl(${48-48*count/max} 94% ${28+34*count/max}%)"><title>${n(count)} orcs killed here · column ${i%h.columns+1}, row ${Math.floor(i/h.columns)+1}</title></rect>`:'').join('');
 const roads=(h.roads||[]).map(points=>`<polyline points="${points.map(([x,y])=>`${x/h.width*w},${y/h.height*height}`).join(' ')}" fill="none" stroke="#537487" stroke-width="5" stroke-opacity=".5"/>`).join('');
 const markers=(h.markers||[]).map(([x,y,id])=>`<text x="${x/h.width*w}" y="${y/h.height*height+4}" text-anchor="middle" fill="#e6f6ff" stroke="#101e29" stroke-width="3" paint-order="stroke" font-size="12">${id}</text>`).join('');
 const cx=h.core[0]/h.width*w,cy=h.core[1]/h.height*height;
 return `<section class="ltzHeatmap"><div class="ltzHistoryTitle"><h3>Orc kill heatmap</h3><span>This level · top of playfield ↑</span></div><svg viewBox="0 0 ${w} ${height}" role="img" aria-label="Orc kill locations for this level. ${total} kills mapped. Hottest area: ${max} kills. ${h.unlocated} without a recorded location."><rect width="${w}" height="${height}" fill="#101e29"/>${roads}${cells}${markers}<path d="M${w/2} 0V${height}M0 ${height/2}H${w}" stroke="#c5dce6" stroke-opacity=".2" stroke-dasharray="4 8"/><circle cx="${cx}" cy="${cy}" r="11" fill="#0b1420" stroke="#e6f6ff" stroke-width="2"/><text x="${cx}" y="${cy+27}" text-anchor="middle" fill="#e6f6ff" font-size="13">Center</text></svg><div class="ltzHeatLegend"><span>Fewer</span><i></i><span>Most · ${n(max)} in one area</span></div><p>${total?`${n(total)} orcs mapped. Includes all turret, force-field and core-purge kills.`:h.unlocated?'No kill locations available for this level.':'No orcs were killed in this level.'}${h.unlocated?` ${n(h.unlocated)} kills have no recorded location.`:''}</p></section>`;
}
function movement(value,key,heatmap,duration){return root.LTZMovement?.html(value,key,heatmap,duration,asset)||'';}
function pendingResult(state){
 const won=state.phase==='won',level=state.contract_control_tier;
 const title=won&&level===4?'You Win! Game Over':won?`Level ${level} complete`:state.phase==='overrun'?`Level ${level} · Core overrun`:'Match ended';
 const score=state.match_score;
 return `<section class="ltzReceipt ltzPendingResult" data-result="${esc(state.run_id)}" aria-label="Level ${level} results awaiting save"><div class="ltzResultHeading"><div><span class="ltzEyebrow">Level ${level} · ${won?'Victory confirmed':'Match finished'}</span><h2>${esc(title)}</h2></div></div><div class="ltzResultNumbers"><span><strong>${n(state.kills)}</strong> Orcs killed</span>${score?.status==='ready'?`<span><strong>${n(score.kill_credits)}</strong> score</span>`:''}<span>${Math.floor((state.sim_time||0)/60)}:${Math.floor((state.sim_time||0)%60).toString().padStart(2,'0')} active time</span></div>${movement(state.robot_movement,state.run_id,state.kill_heatmap,state.sim_time)}<p>${won?'Your victory is confirmed. ':''}Saving your results. Replay options will appear when the save completes.</p></section>`;
}
function resultActions(r,j,side,disabled=false){
 if(!r||j?.phase!=='results'||j.run_id!==r.run_id)return '';
 const complete=r.outcome==='won'&&(r.statistics?.level??r.control_tier)===4;
 const retry=['interrupted','aborted'].includes(r.outcome);
 const options=[...(complete?[]:[['continue',retry?'Retry level · Ready':'Continue · Ready']]),['replay_level','Replay last level'],['replay_game','Replay whole game'],['new','New game']];
 const other=side==='green'?'purple':'green',choices=j.ready||{},mine=choices[side]?.choice,partner=choices[other]?.choice;
 const label=c=>options.find(([key])=>key===c)?.[1]||c;
 const team=s=>s==='green'?'Green':'Purple';
 const status=mine&&partner?(mine===partner?'Both players chose the same option. Continuing…':'Your choices differ. Choose the same option to continue.'):
  mine?`Waiting for ${team(other)} to choose.`:partner?`${team(other)} has chosen. Select the same option to continue, or choose another option.`:'Choose what to play next. Both players must select the same option.';
 const selections=[side,other].map(s=>`<div class="ltzPlayerChoice ${s}" data-player-choice="${s}"><span>${s===side?'You':'Partner'} · ${team(s)}</span><strong>${choices[s]?.choice?esc(label(choices[s].choice)):'Not selected yet'}</strong></div>`).join('');
 return `<section class="ltzResultActions" aria-label="Choose what to play next"><div class="ltzChoiceSummary" aria-live="polite" aria-atomic="true">${selections}</div><p class="ltzChoiceStatus" role="status" data-agreement="${mine&&partner?(mine===partner?'matched':'different'):'waiting'}">${esc(status)}</p><div>${options.map(([value,title])=>`<button type="button" ${value==='continue'?'id="journeyDoneShopping" class="ltzReady"':''} data-result-choice="${value}" data-result-run="${esc(r.run_id)}" aria-pressed="${mine===value}" ${disabled?'disabled':''}>${esc(title)}${mine===value?' ✓':''}</button>`).join('')}</div><p>You can change your selection while waiting. Matching choices continue automatically.</p><p>Replay last level: play this level again. Replay whole game: restart at Level 1 with the same team. New game: choose players. Earned credits and weapon upgrades are kept.</p></section>`;
}
function levelReceipt(r,p){
 const s=r.statistics,side=r.side,other=side==='green'?'purple':'green',own=s.players.find(x=>x.player_id===r.player_id),partner=s.players.find(x=>x.player_id!==r.player_id),k=s.kill_attribution;
 const label=r.outcome==='won'&&s.level===4?'You Win! Game Over':r.outcome==='won'?`Level ${s.level} complete`:r.outcome==='operator_ended'?`Level ${s.level} · Ended by Game Master`:`Level ${s.level} · Core overrun`;
 const peers=s.other_teams,balance=r.balance??p?.credits;
 const unlocks=s.players.flatMap(player=>(s.turrets_unlocked[player.player_id]||[]).map(b=>({...b,player})));
 for(const b of s.atoms_unlocked||[])unlocks.push({...b,secondAtom:true,player:s.players.find(p=>p.player_id===b.player_id)});
 const key=r.run_id+':'+r.player_id;
 const team=r.audience==='team';
 return `<section class="ltzReceipt ltzLevelResult" data-result="${esc(r.run_id)}" data-celebration="${esc(key)}" aria-label="Level ${s.level} results">
 <div class="ltzResultHeading"><div><span class="ltzEyebrow">${esc(own?.name)} + ${esc(partner?.name)} · Result saved</span><h2>${esc(label)}</h2></div><button type="button" class="ltzReplay" aria-label="Replay results animation">↻ Replay animation</button></div>
 ${s.assisted?'<span class="ltzAssisted">Game Master assisted · score kept</span>':''}
 <div class="ltzResultsGrid"><div class="ltzKillHero"><span>Total Orcs Killed</span>${counter(s.total_kills)}<div class="ltzKillSplit"><div class="${side}"><span>${team?'':'You · '}${esc(own?.name)}</span>${counter(k[side])}</div><div class="${other}"><span>${team?'':'Partner · '}${esc(partner?.name)}</span>${counter(k[other])}</div><div><span>Shared team kills</span>${counter(k.shared)}</div></div>${k.unattributed?`<small>${n(k.unattributed)} kills without individual attribution</small>`:''}<small>Turret kills go to the player who deals the final damage. Force fields and core purge are shared.</small></div>
 <div class="ltzPerformance"><div class="ltzTeamScore"><span>Team performance</span>${counter(s.score)}<small>Weighted kill score</small></div><div class="ltzComparisons">${compareCard('vs your previous game',s.previous,'First game · your baseline starts here','Previous score '+n(s.previous?.baseline))}${compareCard('vs your average so far',s.average,'Play another game to compare',n(s.average?.sample_count)+' previous games · average '+n(s.average?.baseline))}${compareCard('vs other teams in this event',peers,s.event_comparison_status==='assisted'?'Assisted result · outside event comparison':'Waiting for other teams at this level',`vs ${peers?.sample_count} team averages · this score ranks ${peers?.rank} / ${peers?.team_count}`)}</div><p class="ltzComparisonNote">Event comparison: same level and settings, unassisted games. Each other team has equal weight. Comparisons saved at finish.</p></div></div>
 ${movement(s.robot_movement,r.run_id,s.kill_heatmap,s.active_seconds)}
 ${historyGraph(s)}
 <div class="ltzUnlockSection"><div class="ltzHistoryTitle"><h3>${unlocks.length?'Turrets unlocked':'Upgrade progress'}</h3><span>Applied automatically</span></div>${unlocks.length?`<div class="ltzUnlocks">${unlocks.map((b,i)=>`<article class="ltzUnlock ltzResultMotion ${b.player.side}" data-reveal-key="${esc(b.player.player_id)}:${esc(b.track)}:${b.level}" style="--delay:${1500+i*220}ms"><div class="ltzUnlockArt"><img src="${esc(asset(b.level===1?'game-art/z-pixel-v2/normalized/structures/'+weapons[b.track]+'-active-l1.png':'shop/'+weapons[b.track]+'-upgrade-l'+b.level+'-v1.png'))}" alt="${esc(names[b.track])} tier ${b.level}"></div><div><span class="ltzEyebrow">${!team&&b.player.player_id===r.player_id?'You':esc(b.player.name)} · ${b.secondAtom?'Second Atom unlocked':b.forced?'Game Master unlock':'New upgrade'}</span><h4>${esc(names[b.track])}</h4><strong>${b.secondAtom?'Available at ':`T${b.level-1} → `}<b>T${b.level}</b></strong><p>${b.secondAtom?'Unlocked with L4':`−${n(b.price)} credits`}${b.level===4?' · Companion turret':''}</p></div></article>`).join('')}</div>`:'<p>Credits saved toward your next turret upgrade. Keep building your team score.</p>'}${r.unlocked_control?`<div class="ltzLevelUnlock ltzResultMotion" data-reveal-key="control:${r.unlocked_control}" style="--delay:2100ms">✦ L${r.unlocked_control} ${esc(controls[r.unlocked_control-1])} and force field unlocked${r.unlocked_control===4?' · Second Atom unlocked':''}${r.manual_advance?' · Game Master override':''}</div>`:''}</div>
 <div class="ltzResultFooter"><span>+${n(r.total_earned)} credits earned · includes ${n(r.stack_bonus)} stack bonus</span>${team?'':`<span>${n(balance)} credits remaining${balance<0?' · Future earnings repay this balance.':''}</span>`}<span>${r.active_seconds==null?'Duration unavailable':Math.floor(r.active_seconds/60)+':'+Math.floor(r.active_seconds%60).toString().padStart(2,'0')} active time</span></div></section>`;
}
const celebrations=new Map(),motionStarts=new Map(),waitingMotions=new Map();
let motionObserver;
function revealMotion(node){
 const info=waitingMotions.get(node);if(!info)return;
 if(!motionStarts.has(info.key))motionStarts.set(info.key,performance.now());
 node.style.setProperty('--elapsed',(performance.now()-motionStarts.get(info.key))+'ms');
 node.style.setProperty('--delay',info.delay+'ms');
 node.removeAttribute('data-waiting');node.classList.add('ltzMotionVisible');
 motionObserver?.unobserve(node);waitingMotions.delete(node);
}
function mountMotion(section,key,reduced){
 // Observe the HTML plot as a group. SVG shape intersection can be empty in
 // Safari (especially stroked/zero-score geometry), leaving every mark hidden.
 // Chart data stays visible even if no visibility callback arrives.
 for(const node of waitingMotions.keys())if(!node.isConnected){motionObserver?.unobserve(node);waitingMotions.delete(node);}
 if(!motionObserver&&root.IntersectionObserver)motionObserver=new root.IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)revealMotion(e.target);},{threshold:.15});
 for(const [i,node] of [...section.querySelectorAll('.ltzResultMotion,.ltzHistoryPlot')].entries()){
  const id=key+':motion:'+(node.dataset.revealKey||i);
  if(node.dataset.motionDelay==null)node.dataset.motionDelay=parseFloat(node.style.getPropertyValue('--delay'))||0;
  const original=Number(node.dataset.motionDelay);
  const delay=node.closest('.ltzUnlockSection')?Math.max(0,original-1500):Math.max(0,original-700);
  waitingMotions.set(node,{key:id,delay});
  if(reduced||motionStarts.has(id)||!motionObserver)revealMotion(node);
  else{node.setAttribute('data-waiting','');motionObserver.observe(node);}
 }
}
function mount(container){
 root.LTZMovement?.mount(container);
 for(const section of container.querySelectorAll('[data-celebration]')){
  if(section.dataset.mounted)return;
  section.dataset.mounted='1';
  const key=section.dataset.celebration,reduced=root.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if(!celebrations.has(key))celebrations.set(key,performance.now());
  // Keep replacement DOM on the same timeline when SSE or history refreshes.
  const animate=()=>{
   if(section._countFrame)cancelAnimationFrame(section._countFrame);
   const elapsed=reduced?10000:performance.now()-celebrations.get(key);
   section.style.setProperty('--elapsed',elapsed+'ms');
   const nodes=[...section.querySelectorAll('[data-count]')];
   const frame=()=>{
    if(!section.isConnected)return;
    const t=reduced?1:Math.min(1,(performance.now()-celebrations.get(key))/1800),ease=1-Math.pow(1-t,3);
    for(const node of nodes){const value=Number(node.dataset.count)*ease,decimals=Number(node.dataset.decimals||0);node.textContent=(node.dataset.signed&&value>0?'+':'')+value.toLocaleString(undefined,{minimumFractionDigits:decimals,maximumFractionDigits:decimals})+(node.dataset.unit||'');}
    if(t<1)section._countFrame=requestAnimationFrame(frame);
   };frame();
  };
  section.querySelector('.ltzReplay').onclick=()=>{celebrations.set(key,performance.now());section.classList.remove('ltzPlaying');for(const id of motionStarts.keys())if(id.startsWith(key+':motion:'))motionStarts.delete(id);section.querySelectorAll('.ltzMotionVisible').forEach(n=>n.classList.remove('ltzMotionVisible'));void section.offsetWidth;animate();mountMotion(section,key,reduced);section.classList.add('ltzPlaying');};
  animate();mountMotion(section,key,reduced);section.classList.add('ltzPlaying');
 }
}
function html({profile:p,shop:q,upgrades=null}){
 if(!p)return '<p>Select an event player to view unlocked equipment.</p>';
 if(q?.status!=='ready')return '<p>Equipment unavailable.</p>';
 const tracks=q.eligible_tracks||[];
 const next=tracks.filter(t=>p.levels[t]<4).sort((a,b)=>p.levels[a]-p.levels[b]||tracks.indexOf(a)-tracks.indexOf(b))[0];
 const price=next?q.prices[next]?.[String(p.levels[next]+1)]:null;
 return `<div class="ltzShop"><div class="ltzWallet"><strong>${n(p.credits)} credits${p.credits<0?' · balance owed':''}</strong><span>Upgrades apply automatically after each match.</span></div><div class="ltzShopTracks">${tracks.map(t=>{const level=p.levels[t],bonus=level===1?0:upgrades?.bonus_percent?.[String(level)];return `<section class="ltzTrack assigned"><header><span class="ltzEyebrow">Unlocked turret</span><h3>${esc(names[t])}</h3><strong>T${level}</strong></header>${level>1?`<img style="max-width:160px" src="${esc(asset('shop/'+weapons[t]+'-upgrade-l'+level+'-v1.png'))}" alt="${esc(names[t])} tier ${level}">`:''}<p>${bonus==null?'':`+${bonus}% damage and health`}${level===4&&upgrades?.l4_turrets_per_socket===2?' · Companion turret at eligible positions':''}</p></section>`;}).join('')}</div><p>L${p.current_control_tier} ${esc(controls[p.current_control_tier-1])} · Force field ${100+20*(p.current_control_tier-1)}% capacity · ${p.current_control_tier===4?'Both team Atoms available':'One starting Atom'}</p>${!tracks.length?'<p>Place the starting Atom on a numbered target before Start. Game Master can select it if detection fails.</p>':next?`<p>Next: ${esc(names[next])} T${p.levels[next]+1} · ${n(price)} credits${p.credits<price?' · '+n(price-p.credits)+' more needed':''}</p>`:'<p>Available turrets are fully upgraded.</p>'}</div>`;
}
function next(value,tier){const t=value?.tiers?.find(t=>t.tier===tier);return t?`Next match: L${tier} ${controls[tier-1]} · ${n(t.total)} scheduled enemies`:'';}
root.LTZShop={html,receipt,next,mount,heatmap,movement,resultActions,pendingResult,configure(options){if(options?.asset)asset=options.asset;}};
if(typeof module!=='undefined')module.exports=root.LTZShop;
})(typeof window==='undefined'?globalThis:window);
