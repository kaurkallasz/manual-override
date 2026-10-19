/* Event selection and explicit Game Master overrides. */
window.LTZPlayerAdmin={create({root,command}){
 const el=id=>document.getElementById(id),select=el('eventSelect');
 let state=null,busy=false,eventsKey='',atomsKey='',pending=null;
 const eventId=()=>state?.next_loadouts?.events?.active_id;
 async function changeEvent(value){
  if(busy)return;busy=true;render();
  const key=JSON.stringify(value);if(pending?.key!==key)pending={key,id:LtzOperationId()};
  try{const response=await fetch(`${root}/p/photon-game/api/event`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...value,operation_id:pending.id})});const result=await response.json();if(!response.ok||result.ok===false)throw Error(result.error||'Event change failed');pending=null;el('eventCreateForm').hidden=true;el('eventStatus').textContent='Event selected. Choose both players on their phones.';eventsKey='';}
  catch(error){el('eventStatus').textContent=error.message;}
  finally{busy=false;render();}
 }
 select.onchange=()=>{if(select.value==='__create'){el('eventCreateForm').hidden=false;el('eventName').focus();return;}if(select.value)changeEvent({action:'select',event_id:select.value});};
 el('eventCreateForm').onsubmit=e=>{e.preventDefault();changeEvent({action:'create',name:el('eventName').value});};
 async function flow(action){
  if(busy)return;busy=true;render();
  try{await command({action,event_id:eventId(),run_id:state.run_id||state.progress?.result?.run_id||state.journey?.id});el('eventStatus').textContent='Saved';}
  catch(error){el('eventStatus').textContent=error.message;}
  finally{busy=false;render();}
 }
 for(const[id,action]of [['endMatch','end_match'],['unlockNextLevel','unlock_next_level'],['continueMatch','next_match']])el(id).onclick=()=>flow(action);
 function render(){
  const events=state?.next_loadouts?.events,game=state?.next_loadouts?.saved_games?.active,phase=state?.phase,j=state?.journey||{};
  const key=JSON.stringify(events);
  if(events&&key!==eventsKey){eventsKey=key;select.replaceChildren();const add=(value,label)=>{const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);};add('','Select an event');for(const e of events.rows)add(e.id,e.name);add('__create','+ Create event…');select.value=events.active_id||'';}
  select.disabled=busy||phase==='running'||j.phase==='calibration';el('createEvent').disabled=select.disabled;
  el('endMatch').disabled=busy||phase!=='running';
  const result=state?.progress?.result,ended=result&&['won','overrun','operator_ended'].includes(result.outcome);
  el('unlockNextLevel').disabled=busy||phase==='running'||j.phase==='calibration'||!ended||game?.level>=4||!!Object.keys(result?.unlocks||{}).length;
  el('continueMatch').disabled=busy||phase==='running'||j.phase==='calibration'||!ended||phase==='setup';
  const binding=JSON.stringify([game?.id,game?.atoms,state?.movable_piece_codes]);
  if(binding!==atomsKey){atomsKey=binding;for(const side of ['green','purple']){const input=el(side+'StartingAtom');input.replaceChildren();const values=[[null,'Detect automatically'],[state?.movable_piece_codes?.[side]?.[0],side==='green'?'Machine Gun':'Mortar'],[state?.movable_piece_codes?.[side]?.[1],side==='green'?'Flamethrower':'Tesla Coil']];for(const[tag,label]of values){if(tag===undefined)continue;const o=document.createElement('option');o.value=tag??'';o.textContent=tag==null?label:`${tag} · ${label}`;input.append(o);}input.value=game?.atoms?.[side]?.tag??'';}}
  for(const side of ['green','purple'])el(side+'StartingAtom').disabled=busy||phase==='running'||!!game?.atoms?.[side];
 }
 return {eventId,startingAtoms(){return Object.fromEntries(['green','purple'].map(side=>[side,el(side+'StartingAtom').value===''?null:Number(el(side+'StartingAtom').value)]));},update(value){state=value;render();}};
}};
