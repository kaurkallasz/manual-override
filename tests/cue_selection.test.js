/* Actual cue UI and camera projection functions; no browser/robot/network I/O. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const mobile=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
const controller=fs.readFileSync('shared/robot_controls/controller.html','utf8');
class Node {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.textContent='';this.className='';this._value='';}
 set value(value){this._value=String(value);}get value(){return this._value;}
 setAttribute(){}
 append(...nodes){for(const node of nodes){node.remove();node.parentNode=this;this.children.push(node);}}
 remove(){if(this.parentNode){const list=this.parentNode.children;list.splice(list.indexOf(this),1);this.parentNode=null;}}
 replaceChildren(...nodes){for(const node of [...this.children])node.remove();this.append(...nodes);if(this.tagName==='SELECT')this.value=nodes[0]?.value??'';}
 contains(node){return node===this||this.children.some(child=>child.contains(node));}
 matches(query){if(query.startsWith('.'))return this.className===query.slice(1);const field=query.match(/^select\[data-field="(.+)"\]$/);return field?this.tagName==='SELECT'&&this.dataset.field===field[1]:this.tagName===query.toUpperCase();}
 querySelectorAll(query){return this.children.flatMap(child=>[...(child.matches(query)?[child]:[]),...child.querySelectorAll(query)]);}
 querySelector(query){return this.querySelectorAll(query)[0]||null;}
}
function ui(){
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 const c={$: $,document:{activeElement:null,createElement:tag=>new Node(tag)},cueDraft:[{piece:100,destination:40}],cueDirty:false,cueBusy:false,
  cueWaypointRow:new Node(),controlMode:'cue',state:{mobile_arm:{cue:{status:'idle',rows:[{piece:100,destination:40}],sources:[{id:100},{id:101}],destinations:[{id:40,cached:false},{id:45,cached:false}]}}},
  team:'green',cueNotice:'',cueLocked:()=>false,updateCueControls(){},drawMarkerLabels(){}};
 vm.createContext(c);
 vm.runInContext(mobile.slice(mobile.indexOf('function cueCandidates('),mobile.indexOf('function cueReadiness(')),c);
 vm.runInContext(mobile.slice(mobile.indexOf('function syncCue('),mobile.indexOf('async function cueAction(')),c);
 vm.runInContext(mobile.slice(mobile.indexOf("$('cueAdd').onclick"),mobile.indexOf("$('cuePlay').onpointerdown")),c);
 c.sync=()=>c.syncCue(c.state.mobile_arm);c.row=()=>$('cueRows').querySelector('.cueRow');c.select=()=>c.row().querySelector('select[data-field="destination"]');
 c.sync();return c;
}
test('cached/live updates keep the same rows and selects, with numeric labels',()=>{
 const c=ui(),row=c.row(),select=c.select(),source=row.querySelector('select[data-field="piece"]');
 for(let i=0;i<100;i++){
  const cached=i%2===0;c.state.mobile_arm.cue.destinations[0].cached=cached;c.sync();
  assert.equal(c.row(),row);assert.equal(c.select(),select);assert.equal(row.querySelector('select[data-field="piece"]'),source);
  assert.equal(select.value,'40');assert.equal(select.children[0].textContent,'40');
 }
});
test('an open native picker keeps its option nodes and draft through flicker, additions and server row updates',()=>{
 const c=ui(),select=c.select(),options=[...select.children],draft=c.cueDraft[0];c.document.activeElement=select;
 for(let i=0;i<100;i++){
  c.state.mobile_arm.cue.destinations=i%2?[{id:45,cached:false},{id:54,cached:true}]:[{id:40,cached:true},{id:45,cached:true}];
  c.state.mobile_arm.cue.rows=[{piece:101,destination:54}];c.sync();
  assert.equal(c.select(),select);assert.deepEqual(select.children,options);assert.equal(c.cueDraft[0],draft);assert.equal(select.value,'40');
 }
 select.value='45';select.onchange();assert.equal(c.cueDraft[0].destination,45);assert(c.cueDirty);
 c.document.activeElement=null;select.onblur();c.sync();
 assert.equal(c.select(),select);assert.equal(select.value,'45');assert.equal(c.cueDraft[0].piece,100);
 assert.equal(select.children.find(o=>o.value==='54').textContent,'54');
});
test('a selected tag that disappears keeps its number and is disabled after closing the picker',()=>{
 const c=ui(),select=c.select();c.document.activeElement=select;
 c.state.mobile_arm.cue.destinations=[];c.sync();assert.equal(select.children.length,2);
 c.document.activeElement=null;select.onblur();
 assert.equal(select.value,'40');assert.equal(select.children.length,1);assert.equal(select.children[0].textContent,'40');assert(select.children[0].disabled);
 c.state.mobile_arm.cue.destinations=[{id:40,cached:true}];c.sync();
 assert.equal(select.value,'40');assert.equal(select.children[0].textContent,'40');assert(!select.children[0].disabled);
});
test('retained change handlers edit the current row after server replacement and row removal',()=>{
 const c=ui(),select=c.select(),old=c.cueDraft[0];
 c.state.mobile_arm.cue.rows=[{piece:101,destination:45}];c.sync();assert.notEqual(c.cueDraft[0],old);assert.equal(c.select(),select);
 select.value='40';select.onchange();assert.equal(c.cueDraft[0].destination,40);assert.equal(old.piece,100);
 c.cueDraft.push({piece:100,destination:45});c.renderCueRows();c.row().querySelector('button').onclick();
 assert.equal(c.$('cueRows').querySelectorAll('.cueRow').length,1);assert.equal(c.select(),select);assert.equal(select.value,'45');
 select.value='40';select.onchange();assert.equal(c.cueDraft[0].piece,100);assert.equal(c.cueDraft[0].destination,40);
});
test('unreachable destinations show their numbers but cannot be selected as new choices',()=>{
 const c=ui();c.state.mobile_arm.cue.destinations.push({id:47,reachable:false});c.sync();
 const option=c.select().children.find(o=>o.value==='47');assert.equal(option.textContent,'47');assert(option.disabled);
 assert.equal(c.select().value,'40');
});
test('one tap inserts Clear view after its placement; sync preserves it and removal cannot orphan it',()=>{
 const c=ui();c.row().querySelector('.cueClearAdd').onclick();
 assert.equal(c.cueDraft.length,2);assert.equal(c.cueDraft[1].action,'clear_view');
 assert.equal(c.$('cueRows').querySelectorAll('.cueRow')[1].querySelector('.cueSummary').textContent,'← Clear view · 5 cm');
 c.row().querySelector('.cueClearAdd').onclick();assert.equal(c.cueDraft.length,2,'No duplicate clearance row');
 c.cueDirty=false;c.state.mobile_arm.cue.rows=[{piece:100,destination:40},{action:'clear_view'}];
 c.sync();assert.deepEqual(Object.keys(c.cueDraft[1]),['action'],'Clearance has no fabricated piece or destination');
 c.$('cueRows').querySelectorAll('.cueRow')[1].querySelector('.cueRemove').onclick();assert.equal(c.cueDraft.length,1);
 c.row().querySelector('.cueClearAdd').onclick();c.row().querySelector('button').onclick();
 assert.equal(c.cueDraft.length,0,'Removing a placement also removes its dependent clearance');
});
test('Clear view direction and distance remain editable through live updates and survive receipts',()=>{
 const c=ui();c.row().querySelector('.cueClearAdd').onclick();
 const clear=c.$('cueRows').querySelectorAll('.cueRow')[1],input=clear.querySelector('input');
 assert.equal(input.value,'5');
 clear.querySelectorAll('.cueClearDirection').find(b=>b.dataset.direction==='right').onclick();
 input.value='7.5';input.oninput();c.document.activeElement=input;
 for(let i=0;i<20;i++)c.sync();
 assert.equal(clear.querySelector('input'),input);assert.equal(input.value,'7.5');
 assert.equal(c.cueDraft[1].direction,'right');assert.equal(c.cueDraft[1].distance_cm,7.5);
 assert.equal(clear.querySelector('.cueSummary').textContent,'→ Clear view · 7.5 cm');
 assert.equal(JSON.stringify(c.cueRowPayload(c.cueDraft[1])),'{"action":"clear_view","direction":"right","distance_cm":7.5}');
 assert(!c.cueRowsEqual([c.cueDraft[1]],[{action:'clear_view'}]));
 assert(c.cueRowsEqual([{action:'clear_view'}],[{action:'clear_view',direction:'left',distance_cm:5}]));
 input.value='';input.oninput();assert(!c.cueClearValid(c.cueDraft[1]));
 clear.querySelector('.cueRemove').onclick();assert.equal(c.cueDraft.length,1);
});
test('initial and added placements include removable Clear view; removal survives sync and row limit',()=>{
 const c=ui();c.cueDraft=[];c.state.mobile_arm.cue.rows=[];c.sync();
 assert.equal(c.cueDraft.length,2);assert.equal(c.cueDraft[1].action,'clear_view');
 c.$('cueRows').querySelectorAll('.cueRow')[1].querySelector('.cueRemove').onclick();
 c.sync();assert.equal(c.cueDraft.length,1,'Sync must not restore an opted-out action');
 c.cueDirty=false;c.state.mobile_arm.cue.rows=[{piece:100,destination:40}];c.sync();
 assert.equal(c.cueDraft.length,1,'Saved opt-out survives reload');
 c.$('cueAdd').onclick();assert.equal(c.cueDraft.length,3);assert.equal(c.cueDraft[2].action,'clear_view');
 c.cueDraft=Array.from({length:30},()=>({piece:100,destination:40}));c.$('cueAdd').onclick();
 assert.equal(c.cueDraft.length,32);assert.equal(c.cueDraft[31].action,'clear_view');
 c.cueDraft.pop();c.$('cueAdd').onclick();assert.equal(c.cueDraft.length,31,'Do not silently omit the default clearance at capacity');
});
test('camera hold after completion keeps current level destinations editable without motion evidence',()=>{
 const c=ui();c.state.virtual_play=false;c.state.movable_piece_codes={green:[100,101],purple:[102,103]};
 c.state.level={sockets:[{aruco_id:40},{aruco_id:42},{aruco_id:48}],core:{x:1,y:1}};
 c.state.mobile_cue_targets={status:'unavailable',pending_fixed_ids:[40,48],tags:[]};
 c.state.mobile_arm.cue.status='completed';c.state.mobile_arm.cue.destinations=[];c.sync();
 const options=c.select().children;
 for(const id of [38,40,42,48,102,103]){
  const option=options.find(o=>o.value===String(id));assert(option,`Known target ${id} remains listed`);
  assert(!option.disabled);assert.equal(option.textContent,String(id));
 }
 assert(!options.some(o=>o.value==='100'),'Own pieces are not destinations');
 c.select().value='42';c.select().onchange();c.sync();assert.equal(c.cueDraft[0].destination,42);
 assert.equal(c.state.mobile_arm.cue.destinations.length,0,'Editing does not create camera evidence');
 c.state.level.sockets=[{aruco_id:50}];c.sync();
 assert(c.select().children.find(o=>o.value==='42').disabled,'Old-layout selection becomes missing');
 assert(!c.select().children.some(o=>o.value==='48'),'Do not cache obsolete layout IDs');
});
test('reopening a still-focused picker refreshes choices recovered since its last opening',()=>{
 const c=ui();c.state.mobile_arm.cue.destinations=[];c.sync();
 const select=c.select();assert.equal(select.children.length,1);c.document.activeElement=select;
 c.state.mobile_arm.cue.destinations=[{id:40},{id:42},{id:45}];c.sync();
 assert.equal(select.children.length,1,'Do not mutate a native picker during live updates');
 select.onpointerdown({button:0});assert.equal(select.children.length,3,'Refresh before native picker reopens');
 assert.equal(select.value,'40');assert.equal(c.select(),select);
});
function camera(){
 let now=10000;
 const c={Date:{now:()=>now},performance:{now:()=>now},TEAM:'green',gameCalibration2:{revision:3},mobileGameAt:now,
  mobileGame:{movable_piece_codes:{green:[100]}},gid:()=>({checked:false}),gameDisplayTag:t=>({...t}),
  autoPpxCueMap:{status:'ready',frameAtLocal:now-200,frame_at:9.8,epoch:'one',scope:'layout',calibrationRevision:3},
  latestVisibleArucoTags:[{id:40,fixed:true,visible:true,lastSeenAt:9800},{id:45,fixed:true,visible:false,lastSeenAt:100}],tick:ms=>now+=ms};
 vm.createContext(c);
 vm.runInContext(controller.slice(controller.indexOf('function autoPpxCueMapKey('),controller.indexOf('async function readAutoPpxCueTargets(')),c);
 c.observe=extra=>{c.mobileGameAt=now;c.mobileGame.mobile_cue_targets={contract:'photon.board.cue-targets',version:1,status:'ready',coordinate_space:'corrected-camera-normalized',epoch:'one',scope:'layout',server_time:now/1000,frame_at:(now-200)/1000,tags:[{id:40,nx:.2,ny:.4,last_seen:(now-200)/1000,fixed:true,visible:true,stable:true}],...extra};};
 return c;
}
test('poll interval does not turn a visible fixed marker into cached or refresh detection age',()=>{
 const c=camera();c.tick(600);
 const tags=c.autoPpxCueDisplayTags(),choices=c.autoPpxCueCandidates();
 assert.equal(choices.destinations.find(t=>t.id===40).cached,false);
 assert.equal(choices.destinations.find(t=>t.id===45).cached,true);
 assert.equal(tags[0].lastSeenAt,9800);c.tick(1000);assert.equal(c.autoPpxCueDisplayTags().length,0);
});
test('latest SSE evidence updates labels before the slower acquisition refresh without mutating its evidence',()=>{
 const c=camera(),saved=c.latestVisibleArucoTags,map=c.autoPpxCueMap;c.tick(400);c.observe();
 let tags=c.autoPpxCueDisplayTags();assert.equal(Math.round(tags[0].lastSeenAt),10200);
 assert.equal(c.autoPpxCueCandidates().destinations[0].cached,false);
 c.mobileGame.mobile_cue_targets.tags[0].visible=false;
 assert.equal(c.autoPpxCueCandidates().destinations[0].cached,true);
 assert.equal(c.latestVisibleArucoTags,saved);assert.equal(c.latestVisibleArucoTags[0].lastSeenAt,9800);assert.equal(c.autoPpxCueMap,map);
 c.tick(200);tags=c.autoPpxCueDisplayTags();assert.equal(Math.round(tags[0].lastSeenAt),10200,'Receipts cannot refresh the observation timestamp');
});
test('unavailable, malformed, changed-scope and expired maps cannot show usable cached destinations',()=>{
 for(const change of ['unavailable','malformed','epoch','scope','calibration','expired']){
  const c=camera();c.observe();
  if(change==='unavailable')c.mobileGame.mobile_cue_targets.status='unavailable';
  if(change==='malformed')c.mobileGame.mobile_cue_targets.contract='unknown';
  if(change==='epoch')c.mobileGame.mobile_cue_targets.epoch='two';
  if(change==='scope')c.mobileGame.mobile_cue_targets.scope='other';
  if(change==='calibration')c.gameCalibration2.revision++;
  if(change==='expired')c.tick(1600);
  assert.equal(c.autoPpxCueCandidates().destinations.length,0,change);
 }
});

test('a reachable edge destination stays selectable and displays only its number',()=>{
 const c=ui();c.state.mobile_arm.cue.destinations.push({id:42,reachable:true,placement_offset_mm:4.071});c.sync();
 const option=c.select().children.find(o=>o.value==='42');assert.equal(option.textContent,'42');assert(!option.disabled);
 c.select().value='42';c.select().onchange();assert.equal(c.cueDraft[0].destination,42);
});
