/* Mobile presentation of Game/Progress/Cal 2 facts. No local progression authority. */
(()=>{
'use strict';
const names=['Joint','XYZ','Targeting','Cue'],tracks=['damage-machine-gun','damage-flamethrower','damage-mortar','damage-tesla-coil','forcefield'];
const side=document.documentElement.dataset.mobileTeam==='purple'?'purple':'green';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state,send,move,busy=false,history=[],profileRevision=null,lastBeat=0,historyBusy=false,historyPending=false,signature='',previewed=false,previewStep=null,selectedRun=null;
const filters={combined:'1',dataset:'scored',tier:'',side_at_run:'',level:'',from:'',to:''};
const panel=document.createElement('section');panel.id='gameJourney';panel.className='gameJourney glass';panel.hidden=true;
panel.innerHTML='<button id="journeyToggle" type="button">Players · Upgrades · Stats</button><div id="calibrationIntro" hidden></div><div id="calibrationQuickPoints" hidden></div><div id="journeyContent"></div><p id="journeyMessage" role="status"></p><button id="journeyClose" type="button" hidden>Back to controls</button>';
document.body.append(panel);
const content=panel.querySelector('#journeyContent'),message=panel.querySelector('#journeyMessage');
const intro=panel.querySelector('#calibrationIntro'),quickPoints=panel.querySelector('#calibrationQuickPoints'),outerMarkers=[31,35,33,34];
let browsing=false,showDetails=false,lessonCollapsed=false,lessonKey=null;
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
panel.querySelector('#journeyClose').onclick=()=>{browsing=false;signature='';render();};
panel.querySelector('#journeyToggle').onclick=()=>{if(calibrationSide(state)===side){lessonCollapsed=!lessonCollapsed;}else if(['lobby','ready'].includes(state?.journey?.phase)){showDetails=!showDetails;}else browsing=!browsing;signature='';render();};
async function action(path,value){if(busy)return;busy=true;try{await send(path,value);message.textContent='Saved';}catch(error){message.textContent=error.message;}finally{busy=false;signature='';render();}}
async function loadHistory(){if(historyBusy){historyPending=true;return;}historyBusy=true;const scope=JSON.stringify([state?.mobile_progress?.player?.id,filters]);try{
 const query=new URLSearchParams();for(const [key,value]of Object.entries(filters)){if(!value)continue;query.set(key,key==='from'||key==='to'?String(Date.parse(value+(key==='to'?'T23:59:59Z':'T00:00:00Z'))/1000):value);}
 let cursor=null,rows=[];
 do{const previous=Number(query.get('cursor')||0);if(cursor!=null)query.set('cursor',String(cursor));const page=(await send('history?'+query)).history;rows.push(...page.rows);cursor=page.next_cursor;if(cursor!=null&&(!Number.isInteger(cursor)||cursor<=previous))throw Error('Invalid history cursor');}while(cursor!=null);
 if(scope===JSON.stringify([state?.mobile_progress?.player?.id,filters])){history=rows;signature='';render();}else historyPending=true;
}catch(error){message.textContent=error.message;}finally{historyBusy=false;if(historyPending){historyPending=false;loadHistory();}}}
function statsFilters(){
 const options=(key,items)=>items.map(([v,label])=>`<option value="${v}" ${filters[key]===v?'selected':''}>${label}</option>`).join('');
 return `<div class="journeyStatsFilters"><label>History <select data-filter="combined">${options('combined',[['1','Both teams · one score per game'],['0','This player']])}</select></label><label>Dataset <select data-filter="dataset">${options('dataset',[['scored','Scored'],['practice','Practice']])}</select></label><label>Control <select data-filter="tier">${options('tier',[['','All'],...names.map((n,i)=>[String(i+1),n])])}</select></label><label>Side at game <select data-filter="side_at_run">${options('side_at_run',[['','Both'],['green','Green'],['purple','Purple']])}</select></label><label>Map ID <input data-filter="level" value="${esc(filters.level)}"></label><label>From (UTC) <input type="date" data-filter="from" value="${esc(filters.from)}"></label><label>To (UTC) <input type="date" data-filter="to" value="${esc(filters.to)}"></label><button id="journeyHistoryRefresh">Refresh history</button></div>`;
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
 return `<svg class="journeyGraph" viewBox="0 0 340 120" role="group" aria-label="${esc(label)}: use Tab and Enter to inspect games">${lines}${rows.map((r,i)=>{const[x,y]=xy(r,i).split(',');return `<circle data-run="${esc(r.run_id)}" tabindex="0" role="button" aria-label="${esc(names[r.control_tier-1])}: ${r[key].toFixed(1)} ${key==='score'?'kills':'seconds'}, ${esc(r.outcome)}" cx="${x}" cy="${y}" r="5" fill="${colors[r.control_tier-1]||colors[0]}"><title>${esc(r.run_id)} · ${r[key].toFixed(1)}</title></circle>`;}).join('')}</svg>`;
}
function graph(){
 return plot('score','Shared score history')+`<p>One score per game. Lines connect matching map, settings and loadouts; thick lines show the trailing three-game mean within that group.</p><table><caption>Completed games; tap a game for its saved details</caption><thead><tr><th>Control</th><th>Score</th><th>Seconds</th><th>Result</th></tr></thead><tbody>${history.map(r=>`<tr><td><button data-run="${esc(r.run_id)}">${esc(names[r.control_tier-1])}</button></td><td>${r.score}</td><td>${r.active_seconds==null?'Unavailable':r.active_seconds.toFixed(1)}</td><td>${esc(r.outcome)}</td></tr>`).join('')}</tbody></table>`;
}
function speedGraph(){
 const rows=history.filter(r=>r.outcome==='won'&&Number.isFinite(r.active_seconds));
 return plot('active_seconds','Completion times by control')+`<p>${names.map((name,i)=>{const times=rows.filter(r=>r.control_tier===i+1);return times.length?`${name}: best ${Math.min(...times.map(r=>r.active_seconds)).toFixed(1)}s, recent ${times.at(-1).active_seconds.toFixed(1)}s`:`${name}: unavailable`;}).join(' · ')}</p>`;
}
function runDetails(){
 const r=history.find(row=>row.run_id===selectedRun);if(!r)return '<p id="journeyRunDetails" aria-live="polite">Select a graph point or table game to inspect its saved details.</p>';
 const t=r.telemetry,participants=r.participants.map(p=>`${p.name} (${p.side}, ${names[p.control_tier-1]}) · ${Object.entries(p.levels).map(([k,v])=>`${k} L${v}`).join(', ')}`).join('\n');
 return `<div id="journeyRunDetails" aria-live="polite"><h4>${esc(r.run_id)}</h4><p>${esc(new Date(r.finished_at*1000).toISOString())} · ${esc(r.outcome)} · ${r.score} score · ${r.active_seconds??'Unavailable'} active seconds · ${r.released_orcs??'Unavailable'} released orcs</p><p>Result saved. Completion award: ${r.completion_awarded?'Yes':'No'}. Calibration milestone: ${Object.keys(r.calibration_milestones||{}).length?'Reached':'None'}.</p><pre>${esc(participants)}</pre><p>${t?`First placement: Green ${t.first_placement_s.green??'Unavailable'}s · Purple ${t.first_placement_s.purple??'Unavailable'}s · Pauses ${t.pause_count} · ${esc(t.outcome_reason||'Outcome reason unavailable')}`:'Placement telemetry unavailable for this older game.'}</p><details><summary>Frozen map, preset and game settings</summary><pre>${esc(JSON.stringify(r.metadata,null,2))}</pre></details></div>`;
}
function render(){
 if(!state)return;
 const j=state.journey||{},p=state.mobile_progress?.player,selected=calibrationSide(state);
 const waiting=j.phase==='calibration'&&selected!==side;
 const active=j.phase==='calibration'&&selected===side;
 const cal=state.mobile_calibration||{stage:'points',captures:{},draft:{parallax_points:{}},arrivals:[]};
 const preparation=state.mobile_calibration_preparation||{},located=preparation.marker_positions||{},markersReady=preparation.ready===true;
 const ready=active&&state.mobile_calibration_ready===true;
 const error=state.mobile_calibration_error||j.motion_error||j.error;
 const key=active?j.id+':'+side:null;
 if(lessonKey!==key){lessonKey=key;lessonCollapsed=false;perspectivePoint=null;savedSelection='';message.textContent='';}
 if(cal.stage!=='perspective')perspectivePoint=null;
 document.body.dataset.calibrationStage=active?cal.stage:'';
 const mandatory=['upgrades','ready','calibration','lobby'].includes(j.phase)&&state.virtual_test_control==null;
 panel.hidden=!(mandatory||browsing||active||waiting);
 if(panel.hidden)return;
 const countdown=j.deadline==null?null:Math.max(0,Math.ceil(j.deadline-j.server_time));
 const visibleCal=cal?{id:cal.id,stage:cal.stage,captures:cal.captures,located:Object.keys(located),markersReady,draft:cal.draft,pickup_height:cal.pickup_height,transport_height:cal.transport_height,arrivals:cal.arrivals,pickup_evidence:cal.pickup_evidence,paused:cal.paused}:null;
 const nextSignature=JSON.stringify([j.phase,j.revision,selected,ready,error,lessonCollapsed,perspectivePoint,state.mobile_camera?.status,savedSelection,savedError,savedCalibrations.map(r=>r.id),countdown,p?.id,p?.revision,visibleCal,history.map(r=>r.run_id),browsing,showDetails,selectedRun,filters]);if(signature===nextSignature)return;signature=nextSignature;
 const compact=['lobby','ready'].includes(j.phase)&&!showDetails;
 panel.classList.toggle('playerPrompt',compact);
 panel.querySelector('#journeyClose').hidden=mandatory||active||waiting||!compact;
 panel.querySelector('#journeyToggle').textContent=active?(lessonCollapsed?'Show calibration':'Hide steps'):['lobby','ready'].includes(j.phase)?(showDetails?'Back to player':'Upgrades & stats'):'Close';
 panel.querySelector('#journeyToggle').hidden=waiting||j.phase==='upgrades';
 panel.querySelector('#journeyToggle').setAttribute('aria-expanded',String(active?!lessonCollapsed:showDetails));
 panel.classList.toggle('calibrationLesson',active);panel.classList.toggle('journeyBlocking',!active&&(mandatory||waiting));
 panel.classList.toggle('calibrationCollapsed',active&&lessonCollapsed);content.hidden=active&&lessonCollapsed;
 intro.hidden=!active||lessonCollapsed;quickPoints.hidden=!active;
 const remaining=j.deadline==null?null:Math.max(0,Math.ceil(j.deadline-j.server_time));
 if(active){
  intro.innerHTML=`<h2>${esc(side[0].toUpperCase()+side.slice(1))} calibration</h2><p>Auto PP Cal 2 · ${cal.stage==='points'?'1. Capture six targets':cal.stage==='perspective'?'2. Four raised-tag references':'3. Click to move'}</p>${cal.stage==='points'?'<p>Let the camera identify all six targets. Place the arm on each target and tap its number to save the arm position. Cached targets can be covered. ✓ means saved.</p>':cal.stage==='perspective'?'<p>Place a physical 100-series ArUco tag 3 cm above each outer reference: 31, 35, 33 and 34. Tap its centre in the image or drag the crosshair onto it. Fine tune makes dragging 10× smaller. Then tap the matching reference number to save. The crosshair does not move the arm.</p>':''}`;
  const status=!ready?`<p class="calibrationStatus" role="status">${esc(error||'Connect and enable the arm to capture. Marker detection runs while disconnected.')}</p>`:error?`<p class="calibrationStatus" role="status">${esc(error)}</p>`:'';
  if(cal.stage==='points')quickPoints.innerHTML=`<p class="calibrationLocated ${markersReady?'ready':''}" role="status" aria-live="polite">${Object.keys(located).length}/6 markers identified · ${markersReady?'Ready to capture':`Keep ${[30,31,32,33,34,35].filter(i=>!located[String(i)]).join(', ')||'the camera'} visible`}</p><fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Six arm calibration points"><div class="calibrationPoints">${[30,31,32,33,34,35].map(marker=>`<button data-capture="${marker}" ${markersReady?'':'disabled'} class="${located[String(marker)]?'identified ':''}${cal.captures[String(marker)]?'calibrated':''}" aria-label="Marker ${marker}: ${cal.captures[String(marker)]?'captured':located[String(marker)]?'identified':'waiting for camera'}">${marker}${cal.captures[String(marker)]?' ✓':''}</button>`).join('')}</div></fieldset><p>${Object.keys(cal.captures).length}/6 saved arm positions</p>`;
  else if(cal.stage==='perspective')quickPoints.innerHTML=`<p class="perspectiveCount">${Object.values(cal.draft.parallax_points).filter(Boolean).length}/4 raised samples · 3 cm</p><fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Four raised-tag reference points"><div class="perspectivePoints">${outerMarkers.map(marker=>`<button data-parallax="${marker}" ${perspectivePoint&&state.mobile_camera?.status==='ready'?'':'disabled'} class="${cal.draft.parallax_points[String(marker)]?'calibrated':''}" aria-label="Save raised sample for reference ${marker}${cal.draft.parallax_points[String(marker)]?', captured':''}">${marker}${cal.draft.parallax_points[String(marker)]?' ✓':''}</button>`).join('')}</div></fieldset><p>${perspectivePoint?'Tap the reference number to save.':outerMarkers.every(m=>cal.draft.parallax_points[String(m)])?'All four saved. Complete calibration when both heights are captured.':'Tap the tag centre or drag the crosshair onto it.'}</p>`;
  else quickPoints.replaceChildren();
  const missing=[];
  if(Object.keys(cal.captures).length!==6)missing.push('six arm points');
  if(!outerMarkers.every(m=>cal.draft.parallax_points[String(m)]))missing.push('four raised samples');
  if(!Number.isFinite(cal.pickup_height))missing.push('pickup Z');
  if(!Number.isFinite(cal.transport_height))missing.push('transport Z');
  quickPoints.insertAdjacentHTML('beforeend',`<button id="calibrationComplete" ${ready&&!busy&&!missing.length&&cal.stage!=='complete'?'':'disabled'}>Complete calibration</button><p class="calibrationCompletionHint">${missing.length?'Still needed: '+missing.join(', ')+'. Show calibration for height controls.':cal.stage==='complete'?'Calibration saved. Waiting for the arm to stop before the next turn.':'All measurements saved. Complete calibration to continue.'}</p>`);
  let body=`<fieldset class="calibrationActions" ${ready?'':'disabled'} aria-label="Calibration steps">`;
  if(['perspective','tutorial'].includes(cal.stage))body+=`<button data-height="pickup_height">Capture pickup Z${Number.isFinite(cal.pickup_height)?' ✓':''}</button><button data-height="transport_height">Capture transport Z${Number.isFinite(cal.transport_height)?' ✓':''}</button>`;
  if(cal.stage==='perspective')body+='<button id="calibrationCommit">Save and practice movement (optional)</button>';
  if(previewStep!==cal.id+':'+cal.arrivals.length){previewed=false;previewStep=cal.id+':'+cal.arrivals.length;}
  if(cal.stage==='tutorial')body+=`<p>Tap the highlighted destination to preview it; press Move. Z and suction stay separate. Optional practice: complete both guided arrivals, then pick up your Atom with suction, lift it at least 10 mm, place it over a calibration marker, and turn the pump off. You can use Complete calibration above to continue without this exercise.</p><button id="tutorialPreview">Preview highlighted point</button><button id="tutorialMove" ${previewed?'':'disabled'}>Move to previewed target</button><button id="tutorialArrival" ${cal.arrivals.length>=2?'hidden':''}>Confirm measured arrival ${Math.min(2,cal.arrivals.length+1)}/2</button><button id="tutorialFinish">Finish after pickup and placement</button>`;
  content.innerHTML=body+'</fieldset>'+status+savedCalibrationView();
  content.querySelector('#savedCalibration').onchange=event=>{savedSelection=event.target.value;signature='';render();};
  content.querySelector('#reloadCalibrations')?.addEventListener('click',loadCalibrations);
  quickPoints.querySelectorAll('[data-capture]').forEach(b=>b.onclick=()=>action('journey',{action:'capture',marker:Number(b.dataset.capture)}));
  quickPoints.querySelectorAll('[data-parallax]').forEach(b=>b.onclick=()=>capturePerspective(Number(b.dataset.parallax)));
  quickPoints.querySelector('#calibrationComplete').onclick=completeCalibration;
  content.querySelectorAll('[data-height]').forEach(b=>b.onclick=()=>action('journey',{action:'height',height:b.dataset.height}));
  content.querySelector('#calibrationCommit')?.addEventListener('click',()=>action('journey',{action:'commit'}));
  content.querySelector('#tutorialPreview')?.addEventListener('click',async()=>{try{await move(state.mobile_calibration_target,true);previewed=true;content.querySelector('#tutorialMove').disabled=false;}catch(error){message.textContent=error.message;}});
  content.querySelector('#tutorialMove')?.addEventListener('click',async()=>{try{if(!previewed)throw Error('Preview the point first');await move(state.mobile_calibration_target);previewed=false;}catch(error){message.textContent=error.message;}});
  content.querySelector('#tutorialArrival')?.addEventListener('click',()=>action('journey',{action:'arrival'}));
  content.querySelector('#tutorialFinish')?.addEventListener('click',()=>action('journey',{action:'finish'}));
 }else{
  const heading=waiting?'Upgrades':j.phase==='upgrades'?`Upgrades · ${remaining??30} seconds`:j.phase==='ready'?'Ready for the next game':compact?'Choose your player':'Players and loadout';
  let body=`<h2>${esc(heading)}</h2>`;
  if(waiting)body+=`<p class="journeyWaiting" role="status">${selected?`Waiting for ${esc(selected[0].toUpperCase()+selected.slice(1))} to finish calibration.`:'Preparing the next calibration turn.'} You can browse upgrades while you wait.</p>${state.mobile_calibration_connect?'<button id="calibrationReconnect">Connect to confirm previous stop</button>':''}`;
  if(waiting&&!p)body+=`<div class="journeyUpgrades">${tracks.map(track=>`<button disabled>${esc(track.replace('damage-',''))}</button>`).join('')}</div><p>No player selected. Choose a player before calibration to purchase and save upgrades.</p>`;
  if(Object.values(state.mobile_progress?.roster||{}).some(x=>x.is_test)||p?.is_test)body+='<p role="status">Test player · Practice only. This game will not count toward either player’s scored statistics, credits or unlocks. Use Game Master test unlocks and loadouts.</p>';
  if(p)body+=`<p class="journeyPlayerSummary">${esc(p.name)} · Required tier: ${esc(names[p.current_control_tier-1])} · ${Math.min(3,p.wins_by_tier[p.current_control_tier-1])}/3 wins</p>${compact?'':`<p>Lifetime score ${p.lifetime_score} · Credits ${p.credits} · Wins ${p.wins}/${p.attempts} (${p.attempts?Math.round(100*p.wins/p.attempts):0}%)</p>`}`;
  if(['lobby','ready'].includes(j.phase))body+=`<label>Saved player <select id="journeyPlayer"><option value="">Choose a name</option>${(state.mobile_progress?.players||[]).map(x=>`<option value="${esc(x.id)}" ${p?.id===x.id?'selected':''}>${esc(x.name)} · ${x.is_test?'Practice only':esc(x.id.slice(0,6))}</option>`).join('')}</select></label><label for="journeyNewName">Or enter a new name</label><div class="journeyNameRow"><input id="journeyNewName" maxlength="32" autocomplete="nickname" placeholder="Your name"><button id="journeyCreate">Add</button></div><button id="journeyReady" ${p?'':'disabled'}>${j.ready?.[side]?'Ready ✓ · waiting for Game Master':'Ready to play'}</button>`;
  if(p&&!compact)body+=`<div class="journeyUpgrades">${tracks.map(track=>{const level=p.levels[track],cost=(track==='forcefield'?1000:250)*level;return `<button data-upgrade="${track}" ${p.is_test||level===4||p.credits<cost||j.phase==='ready'||j.phase==='playing'?'disabled':''}>${esc(track.replace('damage-',''))} L${level}${level<4?` → L${level+1} · ${cost}`:' · Max'}</button>`;}).join('')}</div>${j.phase==='lobby'?'<button id="journeyReplay">Replay calibration and click-to-move lesson</button>':''}<h3>Score history</h3>${statsFilters()}${graph()}<h3>Completion time by control</h3>${speedGraph()}${runDetails()}`;
  if(j.error)body+=`<p role="alert">${esc(j.error)}</p>`;
  // Do not overwrite a name while it is being entered.
  const draft=content.querySelector('#journeyNewName')?.value||'',focused=document.activeElement?.id,selection=focused==='journeyNewName'?[document.activeElement.selectionStart,document.activeElement.selectionEnd]:null;
  content.innerHTML=body;
  content.querySelector('#calibrationReconnect')?.addEventListener('click',()=>document.getElementById('connect').click());
  const input=content.querySelector('#journeyNewName');if(input){input.value=draft;if(selection){input.focus();input.setSelectionRange(...selection);}}
  content.querySelector('#journeyPlayer')?.addEventListener('change',e=>action('player',{action:'select',player_id:e.target.value||null}));
  content.querySelector('#journeyCreate')?.addEventListener('click',async()=>{if(busy)return;busy=true;try{await send('player',{action:'create',select:true,name:input.value,operation_id:LtzOperationId()});const field=content.querySelector('#journeyNewName');if(field)field.value='';message.textContent='Player created and selected';}catch(error){message.textContent=error.message;}finally{busy=false;}});
  input?.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();content.querySelector('#journeyCreate')?.click();}});
  content.querySelector('#journeyReady')?.addEventListener('click',()=>action('journey',{action:'ready'}));
  content.querySelector('#journeyReplay')?.addEventListener('click',()=>action('journey',{action:'replay'}));
  content.querySelectorAll('[data-filter]').forEach(input=>input.addEventListener('change',()=>{filters[input.dataset.filter]=input.value;loadHistory();}));
  content.querySelector('#journeyHistoryRefresh')?.addEventListener('click',loadHistory);
  content.querySelectorAll('[data-run]').forEach(point=>{const inspect=()=>{selectedRun=point.dataset.run;signature='';render();};point.addEventListener('click',inspect);point.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();inspect();}});});
  content.querySelectorAll('[data-upgrade]').forEach(b=>b.onclick=()=>action('player',{action:'purchase',track:b.dataset.upgrade,level:p.levels[b.dataset.upgrade]+1,revision:p.revision,operation_id:LtzOperationId()}));
 }
 window.dispatchEvent(new Event('calibrationtargetchange'));
}
window.MobileJourney={calibrationSide,previewPerspective,perspectiveTarget,wantsPerspective,open(){browsing=true;lessonCollapsed=false;showDetails=!['lobby','ready'].includes(state?.journey?.phase);signature='';render();},update(value,request,movement){if(value.journey?.phase==='playing'&&state?.journey?.phase!=='playing'){browsing=false;showDetails=false;}state=value;send=request;move=movement;const p=value.mobile_progress?.player;let reload=false;if(p&&profileRevision!==p.id+':'+p.revision){if(!profileRevision?.startsWith(p.id+':')){filters.dataset=p.is_test?'practice':'scored';history=[];selectedRun=null;}profileRevision=p.id+':'+p.revision;reload=true;}else if(!p){profileRevision=null;history=[];}render();if(calibrationSide(value)===side){const key=JSON.stringify([value.journey.id,value.mobile_calibration?.calibration_revision]);if(savedKey!==key){savedKey=key;loadCalibrations();}}if(reload)loadHistory();if(value.journey?.active_side===side&&performance.now()-lastBeat>2000){lastBeat=performance.now();send('journey',{action:'heartbeat'}).catch(error=>{message.textContent=error.message;});}}};
})();
