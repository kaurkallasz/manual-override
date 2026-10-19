/* Mobile presentation of Game/Progress/Cal 2 facts. No local progression authority. */
(()=>{
'use strict';
const names=['Joint','XYZ','Targeting','Cue'],tracks=['damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'];
const side=document.documentElement.dataset.mobileTeam==='purple'?'purple':'green';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state,send,move,busy=false,history=[],profileRevision=null,lastBeat=0,historyBusy=false,historyPending=false,signature='',previewed=false,previewStep=null,selectedRun=null;
const filters={combined:'1',tier:'',side_at_run:'',level:'',from:'',to:''};
const panel=document.createElement('section');panel.id='gameJourney';panel.className='gameJourney glass';panel.hidden=true;
panel.innerHTML='<button id="journeyToggle" type="button">Players · Upgrades · Stats</button><div id="calibrationIntro" hidden></div><div id="calibrationQuickPoints" hidden></div><div id="journeyContent"></div><p id="journeyMessage" role="status"></p><button id="journeyClose" type="button" hidden>Back to controls</button>';
document.body.append(panel);
const content=panel.querySelector('#journeyContent'),message=panel.querySelector('#journeyMessage');
const intro=panel.querySelector('#calibrationIntro'),quickPoints=panel.querySelector('#calibrationQuickPoints'),outerMarkers=[31,35,33,34];
let browsing=false,showDetails=false,lessonCollapsed=false,editingArmPoints=false,lessonKey=null,lastResultSeen=null,revealingUpgrade=null,dismissedPanel=null;
let chosenGame='',gameOperation=null;
function savedGameView(){
 const games=state.mobile_progress?.saved_games;if(!games)return '';
 const blocked=!state.mobile_progress?.events?.active_id||busy||state.phase==='running'||state.journey?.phase==='calibration'||state.result_save?.status==='saving';
 const rows=games.rows||[],chosen=rows.find(r=>r.id===(chosenGame||games.active_id));
 return `<section class="savedGamePanel"><h3>Co-op game</h3><p>${games.pair_locked?'Player pair locked for this game.':'New games begin with L1 joint controls for both players.'} Credits, debt and upgrades stay with each player inside this event.</p><label>Previous game <select id="journeySavedGame" ${blocked?'disabled':''}><option value="">Choose a saved game</option>${rows.map(r=>`<option value="${esc(r.id)}" ${r.id===(chosenGame||games.active_id)?'selected':''}>${esc(r.name)} · ${esc(new Date(r.saved_at*1000).toLocaleString())}</option>`).join('')}</select></label>${chosen?`<ul>${Object.entries(chosen.players).map(([team,p])=>`<li>${esc(team)}: ${esc(p.name)} · L${p.tier} · ${p.credits} credits · ${Object.entries(p.levels).filter(([,level])=>level>1).map(([track,level])=>esc(track.replace('damage-',''))+' L'+level).join(', ')||'base upgrades'}</li>`).join('')}</ul>`:''}<div class="savedGameButtons"><button data-saved-game="new" ${blocked?'disabled':''}>New game · L1</button><button data-saved-game="load" ${blocked||!chosen?'disabled':''}>Load linked players</button><button data-saved-game="save" ${blocked||Object.keys(state.mobile_progress?.roster||{}).length!==2?'disabled':''}>Save game</button></div><p>Progress saves automatically after Start. Unfinished battlefields are not restored.</p></section>`;
}
async function savedGameAction(action){
 if(busy)return;
 const value={action,event_id:state.mobile_progress?.events?.active_id,...(action==='load'?{game_id:chosenGame||state.mobile_progress?.saved_games?.active_id}:{})};
 const key=JSON.stringify(value);
 if(gameOperation?.key!==key)gameOperation={key,id:LtzOperationId()};
 busy=true;signature='';render();
 try{await send('saved-game',{...value,operation_id:gameOperation.id});gameOperation=null;chosenGame='';showDetails=true;browsing=true;message.textContent=action==='load'?'Linked players and saved progress loaded.':action==='new'?'New game prepared at L1. Choose your players before Start.':'Game saved with both linked players.';}
 catch(error){message.textContent=error.message;}
 finally{busy=false;signature='';render();}
}
let perspectivePoint=null,savedCalibrations=[],savedSelection='',savedKey=null,savedError='',savedBusy=false;
async function loadCalibrations(){
 if(savedBusy)return;savedBusy=true;
 try{const value=await send('calibrations');if(value?.contract!=='hhh.cal2.history'||value.version!==1||value.status!=='ready'||!Array.isArray(value.rows))throw Error('Saved calibrations unavailable');savedCalibrations=value.rows;savedError='';}
 catch(error){savedError=error.message;}finally{savedBusy=false;signature='';render();}
}
function savedCalibrationView(){
 const row=savedCalibrations.find(r=>r.id===savedSelection),fixed=v=>Number.isFinite(v)?v.toFixed(1):'—';
 return `<label>Saved calibrations <select id="savedCalibration"><option value="">Current lesson</option>${savedCalibrations.map(r=>`<option value="${esc(r.id)}" ${savedSelection===r.id?'selected':''}>${esc(r.label||'Saved lesson')} · v${esc(r.revision)}${r.saved_at?' · '+esc(new Date(r.saved_at*1000).toLocaleString()):''}</option>`).join('')}</select></label>${savedError?`<p role="status">${esc(savedError)}</p><button id="reloadCalibrations">Retry saved calibrations</button>`:''}${row?`<div id="savedCalibrationDetails"><p>Saved measurements · viewing only</p><table><thead><tr><th>Tag</th><th>X</th><th>Y</th><th>Z</th></tr></thead><tbody>${Object.values(row.draft.points||{}).map(p=>`<tr><td>${esc(p.marker)}</td><td>${fixed(p.pose?.x)}</td><td>${fixed(p.pose?.y)}</td><td>${fixed(p.pose?.z)}</td></tr>`).join('')}</tbody></table><p>Pickup Z ${fixed(row.draft.pickup_height)} · Transport Z ${fixed(row.transport_height)} mm</p><p>3 cm perspective: ${Object.values(row.draft.parallax_points||{}).filter(Boolean).length}/4 saved</p></div>`:''}`;
}
function armPointButtons(cal,markersReady,located){
 return `<div class="calibrationPoints">${[30,31,32,33,34,35].map(marker=>{
  const saved=!!cal.captures[String(marker)];
  return `<button data-capture="${marker}" ${busy||!saved&&!markersReady?'disabled':''} class="${located[String(marker)]?'identified ':''}${saved?'calibrated':''}" aria-pressed="${saved}" aria-label="Marker ${marker}: ${saved?'saved; tap to undo':located[String(marker)]?'identified; tap to save':'waiting for camera'}">${marker}${saved?' ✓':''}</button>`;
 }).join('')}</div>`;
}
async function undoSample(actionName,marker){
 if(busy)return;
 perspectivePoint=null;
 await action('journey',{action:actionName,marker});
}
function wantsPerspective(){return calibrationSide(state)===side&&state.mobile_calibration?.stage==='perspective';}
function perspectiveTarget(){
 if(!wantsPerspective())return null;
 const cal=state.mobile_calibration,next=outerMarkers.find(m=>!cal.draft.parallax_points[String(m)])??31;
 const ground=Object.values(cal.draft.points||{}).find(p=>p.marker===next)?.camera;
 return {camera:perspectivePoint||ground||{u:.5,v:.5},mapped:!!perspectivePoint};
}
function previewPerspective(camera){
 if(!wantsPerspective()||state.mobile_camera?.status!=='ready'||busy)return;
 if(!['u','v'].every(k=>Number.isFinite(camera[k])&&camera[k]>=0&&camera[k]<=1)){message.textContent='Tap inside the camera image.';return;}
 const alreadyMapped=!!perspectivePoint;
 perspectivePoint={u:camera.u,v:camera.v};message.textContent='Crosshair positioned. Tap the reference number to save this 3 cm sample.';
 // Once the save buttons are enabled, dragging only needs to repaint the
 // crosshair. Keep the instruction panel stable while a finger is moving.
 if(alreadyMapped)window.dispatchEvent(new Event('calibrationtargetchange'));
 else{signature='';render();}
}
async function capturePerspective(marker){
 if(!outerMarkers.includes(marker)||!perspectivePoint||!wantsPerspective()||!state?.mobile_calibration_ready||state.mobile_camera?.status!=='ready'||busy)return;
 const camera={...perspectivePoint};busy=true;
 try{await send('journey',{action:'raised',marker,camera});perspectivePoint=null;message.textContent=`Saved reference ${marker} · 3 cm perspective correction`;}
 catch(error){message.textContent=error.message;}finally{busy=false;signature='';render();}
}
async function completeCalibration(){
 if(busy)return;busy=true;signature='';render();message.textContent='Completing calibration…';
 try{await send('journey',{action:'complete'});message.textContent='Calibration complete';}
 catch(error){message.textContent=error.message;}
 finally{busy=false;signature='';render();}
}
function calibrationSide(value){const j=value?.journey;return j?.phase==='calibration'?(j.calibration_side??j.queue?.[j.turn??0]??j.active_side):null;}
function panelKey(){const p=state?.mobile_progress?.player;return JSON.stringify([state?.journey?.phase,state?.journey?.id,p?.id,p?.selected_control,p?.levels,state?.mobile_progress?.saved_games?.active_id,['green','purple'].map(side=>state?.mobile_progress?.roster?.[side]?.id)]);}
function closePanel(){dismissedPanel=panelKey();browsing=false;signature='';render();}
panel.querySelector('#journeyClose').onclick=closePanel;
async function confirmReady(choice="continue"){
 if(typeof choice!=="string")choice="continue";
 if(busy)return;busy=true;
 try{await send('journey',{action:'ready',choice,run_id:state.run_id||state.journey?.run_id||null});if(state.journey?.phase!=='results')closePanel();}
 catch(error){message.textContent=error.message;}
 finally{busy=false;signature='';render();}
}
panel.querySelector('#journeyToggle').onclick=()=>{if(calibrationSide(state)===side){lessonCollapsed=!lessonCollapsed;}else if(['lobby','ready'].includes(state?.journey?.phase)){showDetails=!showDetails;}else browsing=!browsing;signature='';render();};
async function action(path,value){if(busy)return;busy=true;try{const result=await send(path,value);if(value.action==='purchase'&&result?.result){revealingUpgrade=value.track+':'+value.level;message.textContent=`Paid ${result.result.price} · ${result.result.balance} credits left · L${result.result.level} installed`;}else if(['undo_capture','undo_raised'].includes(value.action))message.textContent=`Removed ${value.action==='undo_capture'?'arm position':'raised sample'} ${value.marker}. Tap the number again to save a new measurement.`;else message.textContent='Saved';}catch(error){message.textContent=error.message;}finally{busy=false;signature='';render();}}
async function loadHistory(){if(historyBusy){historyPending=true;return;}historyBusy=true;const scope=JSON.stringify([state?.mobile_progress?.player?.id,filters]);try{
 const query=new URLSearchParams();for(const [key,value]of Object.entries(filters)){if(!value)continue;query.set(key,key==='from'||key==='to'?String(Date.parse(value+(key==='to'?'T23:59:59Z':'T00:00:00Z'))/1000):value);}
 let cursor=null,rows=[];
 do{const previous=Number(query.get('cursor')||0);if(cursor!=null)query.set('cursor',String(cursor));const page=(await send('history?'+query)).history;rows.push(...page.rows);cursor=page.next_cursor;if(cursor!=null&&(!Number.isInteger(cursor)||cursor<=previous))throw Error('Invalid history cursor');}while(cursor!=null);
 if(scope===JSON.stringify([state?.mobile_progress?.player?.id,filters])){history=rows;signature='';render();}else historyPending=true;
}catch(error){message.textContent=error.message;}finally{historyBusy=false;if(historyPending){historyPending=false;loadHistory();}}}
function statsFilters(){
 const options=(key,items)=>items.map(([v,label])=>`<option value="${v}" ${filters[key]===v?'selected':''}>${label}</option>`).join('');
 return `<div class="journeyStatsFilters"><label>History <select data-filter="combined">${options('combined',[['1','Both teams · one score per game'],['0','This player']])}</select></label><label>Control <select data-filter="tier">${options('tier',[['','All'],...names.map((n,i)=>[String(i+1),n])])}</select></label><label>Side at game <select data-filter="side_at_run">${options('side_at_run',[['','Both'],['green','Green'],['purple','Purple']])}</select></label><label>Map ID <input data-filter="level" value="${esc(filters.level)}"></label><label>From (UTC) <input type="date" data-filter="from" value="${esc(filters.from)}"></label><label>To (UTC) <input type="date" data-filter="to" value="${esc(filters.to)}"></label><button id="journeyHistoryRefresh">Refresh history</button></div>`;
}
function plot(key,label){
 const rows=history.filter(r=>key==='score'||r.outcome==='won'&&Number.isFinite(r[key]));
 if(!rows.length)return `<p>No ${esc(label.toLowerCase())} for these filters.</p>`;
 const max=Math.max(1,...rows.map(r=>r[key])),colors=['#49d99b','#60cfff','#f3c35b','#c796ff'];
 const xy=(r,i,value=r[key])=>`${20+(rows.length===1?150:i*300/(rows.length-1))},${100-value*80/max}`;
 const groups=new Map();rows.forEach((r,i)=>{if(!groups.has(r.cohort))groups.set(r.cohort,[]);groups.get(r.cohort).push({r,i});});
 let lines='';for(const group of groups.values()){
  const color=colors[group[0].r.control_tier-1]||colors[0];
  lines+=`<polyline points="${group.map(({r,i})=>xy(r,i)).join(' ')}" fill="none" stroke="${color}" stroke-width="1" opacity=".4"/>`;
  const means=group.map(({r,i},n)=>n<2?null:xy(r,i,group.slice(n-2,n+1).reduce((sum,x)=>sum+x.r[key],0)/3)).filter(Boolean);
  if(means.length)lines+=`<polyline points="${means.join(' ')}" fill="none" stroke="${color}" stroke-width="3"/>`;
 }
 return `<svg class="journeyGraph" viewBox="0 0 340 120" role="group" aria-label="${esc(label)}: use Tab and Enter to inspect games">${lines}${rows.map((r,i)=>{const[x,y]=xy(r,i).split(',');return `<circle data-run="${esc(r.run_id)}" tabindex="0" role="button" aria-label="${esc(names[r.control_tier-1])}: ${r[key].toFixed(1)} ${key==='score'?'kill credits':'seconds'}, ${esc(r.outcome)}" cx="${x}" cy="${y}" r="5" fill="${colors[r.control_tier-1]||colors[0]}"><title>${esc(r.run_id)} · ${r[key].toFixed(1)}</title></circle>`;}).join('')}</svg>`;
}
function graph(){
 return plot('score','Shared kill-credit history')+`<p>One score per game. Lines connect matching map, settings and loadouts; thick lines show the trailing three-game mean within that group.</p><table><caption>Completed games; tap a game for its saved details</caption><thead><tr><th>Control</th><th>Kill credits</th><th>Seconds</th><th>Result</th></tr></thead><tbody>${history.map(r=>`<tr><td><button data-run="${esc(r.run_id)}">${esc(names[r.control_tier-1])}</button></td><td>${r.score}</td><td>${r.active_seconds==null?'Unavailable':r.active_seconds.toFixed(1)}</td><td>${esc(r.outcome)}</td></tr>`).join('')}</tbody></table>`;
}
function speedGraph(){
 const rows=history.filter(r=>r.outcome==='won'&&Number.isFinite(r.active_seconds));
 return plot('active_seconds','Completion times by control')+`<p>${names.map((name,i)=>{const times=rows.filter(r=>r.control_tier===i+1);return times.length?`${name}: best ${Math.min(...times.map(r=>r.active_seconds)).toFixed(1)}s, recent ${times.at(-1).active_seconds.toFixed(1)}s`:`${name}: unavailable`;}).join(' · ')}</p>`;
}
function runDetails(){
 const r=history.find(row=>row.run_id===selectedRun);if(!r)return '<p id="journeyRunDetails" aria-live="polite">Select a graph point or table game to inspect its saved details.</p>';
 const t=r.telemetry,participants=r.participants.map(p=>`${p.name} (${p.side}, ${names[p.control_tier-1]}) · ${Object.entries(p.levels).map(([k,v])=>`${k} L${v}`).join(', ')}`).join('\n');
 return `<div id="journeyRunDetails" aria-live="polite"><h4>${esc(r.run_id)}</h4><p>${esc(new Date(r.finished_at*1000).toISOString())} · ${esc(r.outcome)} · ${r.score} score · ${r.active_seconds??'Unavailable'} active seconds · ${r.released_orcs??'Unavailable'} released orcs</p><p>Result saved. Completion award: ${r.completion_awarded?'Yes':'No'}. Calibration milestone: ${Object.keys(r.calibration_milestones||{}).length?'Reached':'None'}.</p><pre>${esc(participants)}</pre><p>${t?`First placement: Green ${t.first_placement_s.green??'Unavailable'}s · Purple ${t.first_placement_s.purple??'Unavailable'}s · Pauses ${t.pause_count} · ${esc(t.outcome_reason||'Outcome reason unavailable')}`:'Placement telemetry unavailable for this older game.'}</p>${LTZShop.heatmap(r.kill_heatmap)}<details><summary>Frozen map, preset and game settings</summary><pre>${esc(JSON.stringify(r.metadata,null,2))}</pre></details></div>`;
}
function render(){
 if(!state)return;
 const j=state.journey||{},p=state.mobile_progress?.player,selected=calibrationSide(state);
 const waiting=j.phase==='calibration'&&selected!==side;
 const active=j.phase==='calibration'&&selected===side;
 const cal=state.mobile_calibration||{stage:'points',captures:{},draft:{parallax_points:{}},arrivals:[]};
 const preparation=state.mobile_calibration_preparation||{},located=preparation.marker_positions||{},markersReady=preparation.ready===true;
 const ready=active&&state.mobile_calibration_ready===true;
 const referenceNotice=preparation.movement_pending?'Camera movement detected. Waiting for stable targets before clearing references.':cal.stage==='points'?(preparation.notice||cal.reference_reset?.reason):null;
 const error=state.mobile_calibration_error||j.motion_error||j.error||referenceNotice;
 const key=active?j.id+':'+side:null;
 if(lessonKey!==key){lessonKey=key;lessonCollapsed=false;editingArmPoints=false;perspectivePoint=null;savedSelection='';message.textContent='';}
 if(cal.stage!=='perspective'){perspectivePoint=null;editingArmPoints=false;}
 document.body.dataset.calibrationStage=active?cal.stage:'';
 const saving=state.result_save?.status==='saving';
 const playerReady=j.readiness?.status==='ready'?j.readiness.players?.[side]?.ready:!!p&&j.ready?.[side]?.id===p.id;
 const readyLabel=j.auto_start?.error?'Retry next level':playerReady?(j.run_id?'Ready ✓ · waiting for partner':'Ready ✓ · waiting for Game Master'):'Ready to play';
 const dismissed=j.phase!=='results'&&(dismissedPanel===panelKey()||playerReady);
 const briefing=!!p&&!saving&&state.phase==='setup'&&['lobby','ready'].includes(j.phase)&&!showDetails&&(!dismissed||browsing);
 const dismissible=!saving&&!active&&!waiting&&(['results','ready'].includes(j.phase)||j.phase==='lobby'&&!!p);
 const mandatory=saving||['results','ready','calibration','lobby'].includes(j.phase)&&!(dismissible&&dismissed);
 panel.hidden=!(mandatory||browsing||active||waiting||briefing);
 panel.classList.toggle('missionBriefing',briefing);
 panel.classList.toggle('levelCelebration',saving||j.phase==='results');
 window.MobileCountdown?.setWaiting(!!p&&panel.hidden&&state.phase==='setup'&&['lobby','ready','results'].includes(j.phase));
 if(panel.hidden)return;
 const countdown=j.deadline==null?null:Math.max(0,Math.ceil(j.deadline-j.server_time));
 const visibleCal=cal?{id:cal.id,stage:cal.stage,captures:cal.captures,located:Object.keys(located),markersReady,draft:cal.draft,pickup_height:cal.pickup_height,transport_height:cal.transport_height,arrivals:cal.arrivals,pickup_evidence:cal.pickup_evidence,paused:cal.paused}:null;
 const upgradeTier=Math.max(1,...Object.values(state.mobile_progress?.roster||{}).map(p=>p.selected_control||1));
 const upgradeTuning=state.next_match?.tiers?.find(t=>t.tier===upgradeTier)?.weapon_upgrades;
 const nextSignature=JSON.stringify([j.phase,j.revision,j.readiness,selected,ready,error,lessonCollapsed,perspectivePoint,state.mobile_camera?.status,savedSelection,savedError,savedCalibrations.map(r=>r.id),countdown,p?.id,p?.revision,visibleCal,history.map(r=>r.run_id),state.mobile_progress?.latest_result?.run_id,[state.mobile_progress?.shop?.catalog_revision,state.mobile_progress?.shop?.status,state.mobile_progress?.shop?.deadline],state.result_save,browsing,showDetails,selectedRun,filters,upgradeTuning,state.mobile_progress?.saved_games,chosenGame,busy,state.phase]);if(signature===nextSignature)return;signature=nextSignature;
 const compact=['lobby','ready'].includes(j.phase)&&!showDetails;
 panel.classList.toggle('playerPrompt',compact);
 panel.querySelector('#journeyClose').hidden=briefing||active||waiting||saving||(!dismissible&&mandatory);
 panel.querySelector('#journeyToggle').textContent=active?(lessonCollapsed?'Show calibration':'Hide steps'):['lobby','ready'].includes(j.phase)?(showDetails?'Back to player':briefing?'Players & upgrades':'Upgrades & stats'):'Close';
 panel.querySelector('#journeyToggle').hidden=saving||waiting||j.phase==='results';
 panel.querySelector('#journeyToggle').setAttribute('aria-expanded',String(active?!lessonCollapsed:showDetails));
 panel.classList.toggle('calibrationLesson',active);panel.classList.toggle('journeyBlocking',!active&&(mandatory||waiting));
 panel.classList.toggle('calibrationCollapsed',active&&lessonCollapsed);content.hidden=active&&lessonCollapsed;
 intro.hidden=!active||lessonCollapsed;quickPoints.hidden=!active;
 const remaining=j.deadline==null?null:Math.max(0,Math.ceil(j.deadline-j.server_time));
 if(saving){
  content.innerHTML=LTZShop.pendingResult(state)+`<p class="ltzSaving" role="status">Saving result… ${esc(state.result_save.error||'Your results will appear here once the save is confirmed.')}</p>`;
  return;
 }
 if(active){
  intro.innerHTML=`<h2>${esc(side[0].toUpperCase()+side.slice(1))} calibration</h2><p>Auto PP Cal 2 · ${cal.stage==='points'?'1. Capture six targets':cal.stage==='perspective'?'2. Four raised-tag references':'3. Click to move'}</p>${cal.stage==='points'?'<p>Keep the arm clear until all six targets are identified. Their camera positions then stay fixed for all captures. Place the arm on each target and tap its number to save the arm position. Targets can be covered after identification. ✓ means saved. Tap a saved number again to undo it.</p>':cal.stage==='perspective'?'<p>Place a physical 100-series ArUco tag 3 cm above each outer reference: 31, 35, 33 and 34. The four targets start green; saving a sample turns off its glow. Tap its centre in the image or drag the crosshair onto it. Fine tune makes dragging 10× smaller. Then tap the matching reference number to save. Tap a saved number again to undo it. The crosshair does not move the arm.</p>':''}`;
  const status=!ready?`<p class="calibrationStatus" role="status">${esc(error||'Connect and enable the arm to capture. Marker detection runs while disconnected.')}</p>`:error?`<p class="calibrationStatus" role="status">${esc(error)}</p>`:'';
  if(cal.stage==='points')quickPoints.innerHTML=`<p class="calibrationLocated ${markersReady?'ready':''}" role="status" aria-live="polite">${Object.keys(located).length}/6 markers identified · ${markersReady?'Ready to capture':`Keep ${[30,31,32,33,34,35].filter(i=>!located[String(i)]).join(', ')||'the camera'} visible`}</p><fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Six arm calibration points">${armPointButtons(cal,markersReady,located)}</fieldset><p>${Object.keys(cal.captures).length}/6 saved arm positions</p>`;
  else if(cal.stage==='perspective')quickPoints.innerHTML=`<p class="perspectiveCount">${Object.values(cal.draft.parallax_points).filter(Boolean).length}/4 raised samples · 3 cm</p><fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Four raised-tag reference points"><div class="perspectivePoints">${outerMarkers.map(marker=>`<button data-parallax="${marker}" ${!busy&&(cal.draft.parallax_points[String(marker)]||perspectivePoint&&!preparation.movement_pending&&state.mobile_camera?.status==='ready')?'':'disabled'} class="${cal.draft.parallax_points[String(marker)]?'calibrated':''}" aria-pressed="${!!cal.draft.parallax_points[String(marker)]}" aria-label="${cal.draft.parallax_points[String(marker)]?'Undo saved raised sample':'Save raised sample'} for reference ${marker}">${marker}${cal.draft.parallax_points[String(marker)]?' ✓':''}</button>`).join('')}</div></fieldset><p>${perspectivePoint?'Tap the reference number to save.':outerMarkers.every(m=>cal.draft.parallax_points[String(m)])?'All four saved. Complete calibration to continue.':'Tap the tag centre or drag the crosshair onto it.'}</p>`;
  else quickPoints.replaceChildren();
  if(cal.stage==='perspective')quickPoints.insertAdjacentHTML('beforeend',`<details class="calibrationSavedPoints" ${editingArmPoints?'open':''}><summary>Saved arm positions · edit</summary><p>Tap a saved number to undo its arm position.</p><fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Saved arm calibration points">${armPointButtons(cal,markersReady,located)}</fieldset></details>`);
  const savedPoints=quickPoints.querySelector('.calibrationSavedPoints');if(savedPoints)savedPoints.ontoggle=()=>{if(savedPoints.isConnected)editingArmPoints=savedPoints.open;};
  const missing=[];
  if(Object.keys(cal.captures).length!==6)missing.push('six arm points');
  if(!outerMarkers.every(m=>cal.draft.parallax_points[String(m)]))missing.push('four raised samples');
  if(!Number.isFinite(cal.pickup_height)||!Number.isFinite(cal.transport_height))missing.push('calculated heights from six arm points');
  quickPoints.insertAdjacentHTML('beforeend',`${Number.isFinite(cal.pickup_height)&&Number.isFinite(cal.transport_height)?`<p class="calibrationHeightSummary">Pickup Z ${cal.pickup_height.toFixed(1)} mm · six-point average<br>Transport Z ${cal.transport_height.toFixed(1)} mm · +40 mm</p>`:''}<button id="calibrationComplete" ${!busy&&!preparation.movement_pending&&!missing.length&&cal.stage!=='complete'?'':'disabled'}>Complete calibration</button><p class="calibrationCompletionHint">${missing.length?'Still needed: '+missing.join(', ')+'.':cal.stage==='complete'?'Calibration saved. Advancing to the next turn.':'All measurements saved. You can complete calibration with the arm disconnected.'}</p>`);
  let body=`<fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Calibration steps">`;
  if(cal.stage==='perspective')body+='<button id="calibrationCommit">Save and try guided movement (optional)</button>';
  if(previewStep!==cal.id+':'+cal.arrivals.length){previewed=false;previewStep=cal.id+':'+cal.arrivals.length;}
  if(cal.stage==='tutorial')body+=`<p>Tap the highlighted destination to preview it; press Move. Z and suction stay separate. Optional movement exercise: complete both guided arrivals, then pick up your Atom with suction, lift it at least 10 mm, place it over a calibration marker, and turn the pump off. You can use Complete calibration above to continue without this exercise.</p><button id="tutorialPreview">Preview highlighted point</button><button id="tutorialMove" ${previewed?'':'disabled'}>Move to previewed target</button><button id="tutorialArrival" ${cal.arrivals.length>=2?'hidden':''}>Confirm measured arrival ${Math.min(2,cal.arrivals.length+1)}/2</button><button id="tutorialFinish">Finish after pickup and placement</button>`;
  content.innerHTML=body+'</fieldset>'+status+savedCalibrationView();
  content.querySelector('#savedCalibration').onchange=event=>{savedSelection=event.target.value;signature='';render();};
  content.querySelector('#reloadCalibrations')?.addEventListener('click',loadCalibrations);
  quickPoints.querySelectorAll('[data-capture]').forEach(b=>b.onclick=()=>{const marker=Number(b.dataset.capture);return cal.captures[String(marker)]?undoSample('undo_capture',marker):action('journey',{action:'capture',marker});});
  quickPoints.querySelectorAll('[data-parallax]').forEach(b=>b.onclick=()=>{const marker=Number(b.dataset.parallax);return cal.draft.parallax_points[String(marker)]?undoSample('undo_raised',marker):capturePerspective(marker);});
  quickPoints.querySelector('#calibrationComplete').onclick=completeCalibration;
  content.querySelector('#calibrationCommit')?.addEventListener('click',()=>action('journey',{action:'commit'}));
  content.querySelector('#tutorialPreview')?.addEventListener('click',async()=>{try{await move(state.mobile_calibration_target,true);previewed=true;content.querySelector('#tutorialMove').disabled=false;}catch(error){message.textContent=error.message;}});
  content.querySelector('#tutorialMove')?.addEventListener('click',async()=>{try{if(!previewed)throw Error('Preview the point first');await move(state.mobile_calibration_target);previewed=false;}catch(error){message.textContent=error.message;}});
  content.querySelector('#tutorialArrival')?.addEventListener('click',()=>action('journey',{action:'arrival'}));
  content.querySelector('#tutorialFinish')?.addEventListener('click',()=>action('journey',{action:'finish'}));
 }else{
  const heading=waiting?'Equipment':j.phase==='results'?'Level results':j.phase==='ready'?'Ready for the next match':compact?'Choose your player':'Players and equipment';
  let body=`<p class="ltzEyebrow">Event · ${esc(state.mobile_progress?.events?.active?.name||'Waiting for Game Master to select an event')}</p><h2>${esc(heading)}</h2>`;
  if(!compact&&!saving)body+=LTZShop.receipt(state.mobile_progress?.latest_result,p);
  if(j.phase==='results')body+=LTZShop.resultActions(state.mobile_progress?.latest_result,j,side,!p||busy||saving);
  if(!compact&&!j.game_complete)body+=`<p class="ltzNextMatch">${esc(LTZShop.next(state.next_match,p?.current_control_tier||1))}</p>`;
  if(waiting)body+=`<p class="journeyWaiting" role="status">${selected?`Waiting for ${esc(selected[0].toUpperCase()+selected.slice(1))} to finish calibration.`:'Preparing the next calibration turn.'} You can browse upgrades while you wait.</p>${state.mobile_calibration_connect?'<button id="calibrationReconnect">Connect to confirm previous stop</button>':''}`;
  if(waiting&&!p)body+=`<div class="journeyUpgrades">${tracks.map(track=>`<button disabled>${esc(track.replace('damage-',''))}</button>`).join('')}</div><p>No player selected. Choose a player before calibration to view saved equipment.</p>`;
  if(p&&j.phase!=='results')body+=`<p class="journeyPlayerSummary">${esc(p.name)} · L${p.current_control_tier} ${esc(names[p.current_control_tier-1])} · ${p.credits} credits</p>${compact?'':`<p>Event kills ${p.lifetime_kills} · Score ${p.lifetime_kill_credits} · Bonus ${p.lifetime_bonus_credits} · Wins ${p.wins}/${p.attempts}</p>`}`;
  if(['lobby','ready'].includes(j.phase))body+=`<label>Saved player <select id="journeyPlayer"><option value="">Choose a name</option>${(state.mobile_progress?.players||[]).map(x=>`<option value="${esc(x.id)}" ${p?.id===x.id?'selected':''}>${esc(x.name)} · ${esc(x.id.slice(0,6))}</option>`).join('')}</select></label><label for="journeyNewName">Or enter a new name</label><div class="journeyNameRow"><input id="journeyNewName" maxlength="32" autocomplete="nickname" placeholder="Your name"><button id="journeyCreate">Add</button></div><button id="journeyReady" ${p?'':'disabled'}>${esc(readyLabel)}</button>`;
  if(briefing)body=`<p class="eyebrow">${esc(state.mobile_progress?.events?.active?.name)} · ${esc(p.name)} · Mission briefing</p><p class="journeyPlayerSummary">L${p.current_control_tier} ${esc(names[p.current_control_tier-1])} controls · ${p.credits} credits</p><h2>Hold the line.</h2><ol class="missionObjectives"><li>Your mission is to hold off the orcs</li><li>Do this by activating the turrets using the robot arm to place the ATOM tags on top of the aruco codes on the playfield.</li><li>Complete a ring of 8–16 turrets. Then stack one Green and one Purple Atom on the core to unlock the next level.</li></ol><p class="missionReminder">Don't forget to aim your turrets!</p><button id="journeyReady" ${busy?'disabled':''}>${esc(readyLabel)}</button>`;
  if(j.phase!=='results')body+=savedGameView();
  if(p&&!compact&&j.phase!=='results')body+=LTZShop.html({profile:p,shop:state.mobile_progress?.shop,side,busy,revealing:revealingUpgrade,upgrades:upgradeTuning})+`${j.phase==='lobby'?'<button id="journeyReplay">Replay calibration and click-to-move lesson</button>':''}<h3>Score history</h3>${statsFilters()}${graph()}<h3>Completion time by control</h3>${speedGraph()}${runDetails()}`;
  if(j.error)body+=`<p role="alert">${esc(j.error)}</p>`;
  if(j.auto_start?.error)body+=`<p role="alert">${esc(j.auto_start.error)}</p>`;
  // Do not overwrite a name while it is being entered.
  const draft=content.querySelector('#journeyNewName')?.value||'',focused=document.activeElement?.id,selection=focused==='journeyNewName'?[document.activeElement.selectionStart,document.activeElement.selectionEnd]:null;
  content.innerHTML=body;
  LTZShop.mount(content);
  content.querySelector('#journeySavedGame')?.addEventListener('change',e=>{chosenGame=e.target.value;signature='';render();});
  content.querySelectorAll('[data-saved-game]').forEach(button=>button.onclick=()=>savedGameAction(button.dataset.savedGame));
  if(!state.mobile_progress?.events?.active_id||state.mobile_progress?.saved_games?.pair_locked||state.phase==='running')for(const id of ['journeyPlayer','journeyNewName','journeyCreate']){const node=content.querySelector('#'+id);if(node)node.disabled=true;}
  content.querySelector('#calibrationReconnect')?.addEventListener('click',()=>document.getElementById('connect').click());
  const input=content.querySelector('#journeyNewName');if(input){input.value=draft;if(selection){input.focus();input.setSelectionRange(...selection);}}
  content.querySelector('#journeyPlayer')?.addEventListener('change',e=>action('player',{action:'select',player_id:e.target.value||null}));
  content.querySelector('#journeyCreate')?.addEventListener('click',async()=>{if(busy)return;busy=true;try{await send('player',{action:'create',select:true,name:input.value,operation_id:LtzOperationId()});const field=content.querySelector('#journeyNewName');if(field)field.value='';showDetails=false;browsing=false;signature='';render();message.textContent='Player created and selected';}catch(error){message.textContent=error.message;}finally{busy=false;signature='';render();}});
  input?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();content.querySelector('#journeyCreate')?.click();}});
  content.querySelector('#journeyReady')?.addEventListener('click',confirmReady);
  content.querySelectorAll('[data-result-choice]').forEach(button=>button.onclick=()=>confirmReady(button.dataset.resultChoice));
  content.querySelector('#journeyReplay')?.addEventListener('click',()=>action('journey',{action:'replay'}));
  content.querySelectorAll('[data-filter]').forEach(input=>input.addEventListener('change',()=>{filters[input.dataset.filter]=input.value;loadHistory();}));
  content.querySelector('#journeyHistoryRefresh')?.addEventListener('click',loadHistory);
  content.querySelectorAll('[data-run]').forEach(point=>{const inspect=()=>{selectedRun=point.dataset.run;signature='';render();};point.addEventListener('click',inspect);point.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspect();}});});
 }
 window.dispatchEvent(new Event('calibrationtargetchange'));
}
window.MobileJourney={calibrationSide,previewPerspective,perspectiveTarget,wantsPerspective,open(){browsing=true;lessonCollapsed=false;showDetails=!['lobby','ready'].includes(state?.journey?.phase);signature='';render();},update(value,request,movement){
 const resetToNames=value.journey?.phase==='lobby'&&!value.mobile_progress?.player&&(state?.mobile_progress?.player||value.journey.reset_operation!==state?.journey?.reset_operation);
 if(resetToNames){
  browsing=false;showDetails=false;dismissedPanel=null;chosenGame='';lastResultSeen=null;selectedRun=null;signature='';message.textContent='';
  const draft=content.querySelector('#journeyNewName');if(draft)draft.value='';
 }
 if(value.phase==='running'&&state?.phase!=='running'||value.journey?.phase==='playing'&&state?.journey?.phase!=='playing'){browsing=false;showDetails=false;}state=value;send=(path,value)=>request(path,value&&['player','saved-game','journey'].includes(path)?{...value,event_id:state.mobile_progress?.events?.active_id}:value);move=movement;const receipt=value.mobile_progress?.latest_result;if(receipt&&value.phase!=='running'&&receipt.run_id!==lastResultSeen){lastResultSeen=receipt.run_id;browsing=true;showDetails=true;signature='';}if(value.result_save?.status==='saving'){browsing=true;showDetails=true;}const p=value.mobile_progress?.player;let reload=false;if(p&&profileRevision!==p.id+':'+p.revision){if(!profileRevision?.startsWith(p.id+':')){history=[];selectedRun=null;}profileRevision=p.id+':'+p.revision;reload=true;}else if(!p){profileRevision=null;history=[];}render();if(resetToNames)panel.scrollTop=0;if(calibrationSide(value)===side){const key=JSON.stringify([value.journey.id,value.mobile_calibration?.calibration_revision]);if(savedKey!==key){savedKey=key;loadCalibrations();}}if(reload)loadHistory();if(value.journey?.active_side===side&&performance.now()-lastBeat>2000){lastBeat=performance.now();send('journey',{action:'heartbeat'}).catch(error=>{message.textContent=error.message;});}}};
})();
