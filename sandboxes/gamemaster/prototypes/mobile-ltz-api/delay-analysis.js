(()=>{
'use strict';
const $=id=>document.getElementById(id),ms=n=>Number.isFinite(n)?n.toFixed(n>=100?0:2)+' ms':'—';
let current=null,selected=null,busy=false;
const text=(tag,value,cls)=>{const el=document.createElement(tag);el.textContent=value;if(cls)el.className=cls;return el;};
function error(message){$('error').hidden=!message;$('error').textContent=message||'';}
async function request(action){
 const response=await fetch('api/delay',{method:action?'POST':'GET',headers:action?{'Content-Type':'application/json'}:{},body:action?JSON.stringify(action):undefined,cache:'no-store'});
 const value=await response.json();if(!response.ok)throw Error(value.error||'Delay recorder unavailable');return value;
}
async function command(action){if(busy)return;busy=true;try{error('');const value=await request(action);selected=null;render(value);}catch(e){error(e.message);}finally{busy=false;}}
$('start').onclick=()=>command({action:'start',side:$('side').value,seconds:Number($('seconds').value)});
$('stop').onclick=()=>command({action:'stop'});$('mark').onclick=()=>command({action:'mark'});$('clear').onclick=()=>command({action:'clear'});
$('filter').oninput=()=>current&&operations(current);
$('live').onclick=()=>{selected=null;if(current)timeline(current);};
function operations(value){
 const filter=$('filter').value.toLowerCase(),rows=[];
 for(const op of value.operations.filter(o=>(o.name+' '+o.source+' '+o.side).toLowerCase().includes(filter))){
  const tr=document.createElement('tr');if(op.max_ms>=250)tr.className='slow';
  const name=text('td',op.name);name.append(text('small',op.source+(op.side?' · '+op.side:'')+(op.kind==='gauge'?' · age / gap':'')));tr.append(name);
  for(const v of [op.count,ms(op.p50_ms),ms(op.p95_ms),ms(op.p99_ms),ms(op.max_ms),op.source.includes('/browser/')||op.kind==='gauge'?'—':ms(op.cpu_ms),op.source.includes('/browser/')||op.kind==='gauge'?'—':ms(op.self_ms)])tr.append(text('td',v));
  rows.push(tr);
 }
 if(!rows.length){const row=document.createElement('tr'),cell=text('td','No matching timings yet.');cell.colSpan=8;row.append(cell);rows.push(row);}
 $('operations').replaceChildren(...rows);
}
function timeline(value){
 const evidence=value.events.filter(e=>e.kind==='evidence').sort((a,b)=>b.collected_at-a.collected_at).slice(0,16);
 $('evidence').replaceChildren(...evidence.map(e=>{
  const item=document.createElement('details');item.append(text('summary',new Date(e.collected_at*1000).toLocaleTimeString()+' · '+e.name));
  item.append(text('pre',JSON.stringify(e.details||{},null,2)));return item;
 }));
 const groups=new Map();
 for(const e of value.events.filter(e=>e.kind==='span')){
  const clock=e.clock==='host-monotonic'?'Server + arm workers':e.source+' (independent clock)';
  if(!groups.has(clock))groups.set(clock,[]);groups.get(clock).push(e);
 }
 const lanes=[];
 for(const [clock,records] of groups){
  const list=records.sort((a,b)=>b.duration_ms-a.duration_ms).slice(0,24).sort((a,b)=>a.start_ms-b.start_ms);
  const start=Math.min(...list.map(e=>e.start_ms)),end=Math.max(...list.map(e=>e.start_ms+e.duration_ms)),width=Math.max(1,end-start);
  const lane=text('div','','lane');lane.append(text('h3',clock+' · '+ms(width)+' shown'));
  for(const e of list){
   const row=text('div','','event'),label=text('span',e.name,'event-label');
   row.title=e.source+' / '+e.thread+' · elapsed '+ms(e.duration_ms)+' · CPU '+ms(e.cpu_ms)+' · own '+ms(e.self_ms)+(e.sequence!=null?' · sequence '+e.sequence:'')+(e.parent_id?' · nested operation':'');
   const track=text('div','','track'),bar=text('div','','bar'+(e.duration_ms>=250?' slow':''));
   bar.style.left=((e.start_ms-start)/width*100)+'%';bar.style.width=(e.duration_ms/width*100)+'%';track.append(bar);row.append(label,track,text('span',ms(e.duration_ms),'event-value'));lane.append(row);
  }lanes.push(lane);
 }
 $('timeline').replaceChildren(...(lanes.length?lanes:[text('p','No retained execution spans for this view. Older details remain in the export.','note')]));
 $('timelineNote').textContent=(selected?'Selected incident: saved window from 10 seconds before to 5 seconds after collection, limited by capture start/stop and available detail storage. ':'Live rolling window: up to 60 seconds. ')+ 'Showing up to 24 of the slowest spans per clock group; overlaps include nested calls. Expand decision evidence to inspect board markers and driver errors.';
}
async function incident(id){selected=id;try{const r=await fetch('api/delay?incident='+encodeURIComponent(id),{cache:'no-store'});if(!r.ok)throw Error('Could not read incident');timeline(await r.json());}catch(e){error(e.message);}}
function render(value){
 current=value;const recording=value.recording,stopping=value.status==='stopping';
 $('state').textContent=recording?'Recording':stopping?'Draining buffer':'Recording off';$('state').dataset.recording=recording;
 $('start').disabled=recording||stopping;$('stop').disabled=!recording;$('mark').disabled=!recording;$('clear').disabled=recording||stopping||!value.capture_id;
 $('side').disabled=recording;$('seconds').disabled=recording;
 $('elapsed').textContent=Math.round(value.elapsed_s)+' s';
 $('build').textContent=ms(Math.max(0,...value.operations.filter(o=>o.name==='mobile.snapshot').map(o=>o.p95_ms)));
 $('peak').textContent=ms(Math.max(0,...value.operations.map(o=>o.max_ms)));
 $('records').textContent=value.received.toLocaleString()+' / '+value.dropped.toLocaleString();
 $('recordingNote').textContent=recording?`Recording ${value.side} · ${value.remaining_s==null?'until you press Stop recording':'automatic stop in '+Math.ceil(value.remaining_s)+' seconds'}. Whole-session summaries are active. You can close this window.`:value.capture_id?`Capture retained · stopped by ${value.stop_reason||'operator'}. Start creates a new capture; export these results first.`:'Recording is off. Starting and stopping does not restart the game.';
 const warnings=value.warnings||[];$('coverageWarning').hidden=!warnings.length;
 $('coverageWarning').replaceChildren(...warnings.map(message=>text('p',message)));
 $('state').dataset.warning=!!warnings.length;
 if(value.storage_error)error(value.storage_error);
 operations(value);
 $('incidents').replaceChildren(...value.incidents.slice().reverse().map(item=>{const b=text('button',new Date(item.at*1000).toLocaleTimeString()+' · '+item.name+(item.duration_ms==null?'':' · '+ms(item.duration_ms)));b.onclick=()=>incident(item.id);return b;}));
 if(!selected)timeline(value);
 const participants=[{source:'Host instrumentation',status:recording?'Recording enabled': 'Off'},...value.participants.map(p=>({source:p.source,status:Date.now()/1000-p.seen_at>6?'No recent acknowledgement':p.recording?(recording?'Recording acknowledged':'Stop not yet acknowledged; lease expires within 4 s'):'Stopped acknowledged'}))];
 if(!value.participants.some(p=>p.source.includes('/browser/')))participants.push({source:'Player browser',status:'No acknowledgement — open or refresh an updated player page'});
 if(!value.participants.some(p=>p.source.startsWith('worker.')))participants.push({source:'Arm worker',status:'No observation — requires an existing connected arm'});
 $('participants').replaceChildren(...participants.map(p=>{const row=text('div','','coverage-row');row.append(text('span',p.source),text('span',p.status));return row;}));
 const detailLimit=Number.isFinite(value.limits?.file_bytes)?value.limits.file_bytes/1048576:'—';
 $('storage').textContent=`Incident detail: ${(value.bytes_written/1048576).toFixed(2)} / ${detailLimit} MiB · summary: ${((value.summary_bytes||0)/1024).toFixed(0)} KiB · ${(value.fast_locks_aggregated||0).toLocaleString()} tiny lock timings aggregated · ${value.retained} rolling records · ${value.buffered} queued · ${value.dropped} dropped · ${(value.detail_omitted||0).toLocaleString()} incident records omitted by storage limit · last background write ${ms(value.writer_ms)}. Gateway timings appear only on the hosted route when supported.`;
}
request().then(render).catch(e=>error(e.message));
const source=new EventSource('api/delay/events');source.onmessage=e=>{try{render(JSON.parse(e.data));}catch(err){error(err.message);}};source.onerror=()=>error('Analysis feed disconnected. Recording is controlled by the server; reconnect to verify its state.');
window.addEventListener('pagehide',()=>source.close());
})();
