/* Camera presentation/startup regressions. No network or robot commands. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
function display(team='green'){
 const labels={children:[],replaceChildren(...children){this.children=children;}};
 const c={LTZMarkerPresence:require('../shared/ltz_ui/marker-presence.js'),team,markerSignature:'',feedReady:true,lastFeed:1000,now:1000,performance:{now:()=>c.now},
  viewport:{w:1280,h:720,direction:team==='purple'?-1:1,rotation:team==='purple'?180:0,scale:.5},
  document:{createElement:()=>({dataset:{},style:{}})},$:()=>labels,
  state:{virtual_play:false,mobile_arm:null,movable_piece_codes:{green:[100,101],purple:[102,103]},
   mobile_cue_targets:{contract:'photon.board.cue-targets',version:1,status:'ready',source:'camera',
    coordinate_space:'corrected-camera-normalized',server_time:100,frame_at:99.9,tags:[
     {id:40,nx:.2,ny:.3,last_seen:99.9,fixed:true,visible:true},
     {id:49,nx:.7,ny:.5,last_seen:40,fixed:true,visible:false},
     {id:team==='green'?100:102,nx:.4,ny:.6,last_seen:99.9,fixed:false,visible:true}]}}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('const cameraLabelPresence='),source.indexOf('let baseGoal=null;')),c);
 c.ids=()=>labels.children.map(el=>el.textContent);c.labels=labels;return c;
}
test('both players see camera labels without any arm feedback, including before game start',()=>{
 for(const side of ['green','purple']){
  const c=display(side);c.state.phase='setup';c.drawMarkerLabels();
  assert.deepEqual(c.ids(),['#40','#49',side==='green'?'#100':'#102']);
  assert.equal(c.labels.children[0].style.left,'256px');
  assert.equal(c.labels.children[2].dataset.kind,'piece');
  assert(c.labels.children[0].style.transform.includes(`rotate(${-c.viewport.rotation}deg)`));
  assert.equal(c.state.mobile_arm,null,'Displaying tags must not manufacture robot readiness');
  c.state.phase='running';c.drawMarkerLabels();assert.equal(c.ids().length,3);
 }
});
test('camera labels survive robot disconnect and do not use the robot marker cache',()=>{
 const c=display();c.state.mobile_arm={markers:[{id:55,x:1,y:2}],tags:[]};c.drawMarkerLabels();
 assert.deepEqual(c.ids(),['#40','#49','#100']);
 c.state.mobile_arm=null;c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#49','#100']);
});
function detections(c){
 const piece=c.team==='green'?100:102;
 c.state.mobile_camera={status:'ready',tracking:{contract:'photon.board.camera-markers',version:1,status:'ready',source:'camera',
  coordinate_space:'corrected-camera-normalized',max_age_s:1.5,server_time:100,frame_at:99.9,tags:[
   {id:40,camera:[.2,.3],last_seen:99.9},{id:piece,camera:[.4,.6],last_seen:99.9}]}};
 return c.state.mobile_camera.tracking;
}
test('cue-map and alignment holds do not black out fresh detections for either player',()=>{
 for(const side of ['green','purple']){
  const c=display(side);detections(c);c.drawMarkerLabels();assert.equal(c.ids().length,3);
  c.state.mobile_cue_targets.status='unavailable';c.state.mobile_cue_targets.tags=[];
  c.state.mobile_camera.status='unavailable';c.state.mobile_camera.error='Not enough markers for alignment';
  c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40',side==='green'?'#100':'#102']);
  assert.equal(c.state.mobile_arm,null);assert.equal(c.state.mobile_cue_targets.status,'unavailable');
  assert.equal(c.state.mobile_cue_targets.tags.length,0,'Display fallback cannot supply acquisition coordinates');
  c.now+=950;c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
  c.now+=1000;c.drawMarkerLabels();assert.deepEqual(c.ids(),[],'True camera staleness still clears detections');
 }
});
test('invalid detection contracts and malformed tags never keep a held-map display alive',()=>{
 for(const [field,value] of [['contract','wrong'],['version',true],['status','unavailable'],['source','simulation'],
  ['coordinate_space','robot-mm'],['server_time',NaN],['frame_at',98],['frame_at',101],['max_age_s',20],['tags',null]]){
  const c=display(),d=detections(c);c.state.mobile_cue_targets.status='unavailable';d[field]=value;c.drawMarkerLabels();assert.deepEqual(c.ids(),[],field);
 }
 const c=display(),d=detections(c);c.state.mobile_cue_targets.status='unavailable';
 d.tags.push(null,{id:101,camera:[NaN,.2],last_seen:99.9},{id:'101',camera:[.1,.2],last_seen:99.9},{id:101,camera:[.1,.2],last_seen:98});
 c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#100']);
});
test('moving-piece labels expire while fixed memory remains only under a fresh camera map',()=>{
 const c=display();c.now+=950;c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#49']);
 c.now+=1000;c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
 c.lastFeed=c.now;c.state.mobile_cue_targets.server_time=102;c.state.mobile_cue_targets.frame_at=101.9;
 c.state.mobile_cue_targets.tags[2].last_seen=101.9;c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#49','#100']);
});
test('partial cue maps keep independent fixed labels and discard quarantined poses',()=>{
 const c=display();c.drawMarkerLabels();
 c.state.mobile_cue_targets.status='partial';
 c.state.mobile_cue_targets.quarantined_tags=[{id:49}];
 c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#100']);
 assert.equal(c.state.mobile_arm,null);
 assert.equal(c.state.mobile_cue_targets.status,'partial','Presentation cannot upgrade motion authority');
});
test('one-second display grace survives dropped detections without renewing their timestamps',()=>{
 for(const side of ['green','purple']){
  const c=display(side),d=detections(c);c.state.mobile_cue_targets.status='unavailable';
  c.drawMarkerLabels();const expected=['#40',side==='green'?'#100':'#102'];
  c.now+=300;c.lastFeed=c.now;d.server_time+=.3;d.frame_at+=.3;d.tags=[];
  c.drawMarkerLabels();assert.deepEqual(c.ids(),expected);
  c.now+=400;c.drawMarkerLabels();assert.deepEqual(c.ids(),expected);
  c.now+=301;c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
  assert.equal(c.state.mobile_arm,null);
 }
});
test('invalid, held or stale camera contracts cannot fall back to old arm labels',()=>{
 const bad=[['contract','wrong'],['version',true],['version',3],['status','unavailable'],['source','simulation'],
  ['coordinate_space','robot-mm'],['server_time',NaN],['frame_at',98],['frame_at',101],['tags',null]];
 for(const [field,value] of bad){const c=display();c.drawMarkerLabels();c.state.mobile_cue_targets[field]=value;c.drawMarkerLabels();assert.deepEqual(c.ids(),[],field);}
 const c=display();c.feedReady=false;c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
});
test('malformed and obscured movable detections are not displayed',()=>{
 const c=display(),tags=c.state.mobile_cue_targets.tags;
 tags.push(null,{...tags[2],id:101,nx:1.1},{...tags[2],id:'101'},
  {...tags[2],id:101,last_seen:NaN},{...tags[2],id:101,visible:false});
 c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#49','#100']);
});
test('virtual marker geometry and calibration labels retain their existing sources',()=>{
 const c=display();c.state.virtual_play=true;c.state.level={sockets:[{aruco_id:40,marker_x:444,marker_y:333,marker_size:30}]};
 c.state.mobile_arm={markers:[{id:40,x:1,y:2,kind:'socket'}],tags:[{id:100,x:10,y:20}]};
 c.drawMarkerLabels();assert.deepEqual(c.ids(),['#40','#100']);assert.equal(c.labels.children[0].style.left,'444px');
 c.state.virtual_play=false;c.state.mobile_arm=null;c.state.journey={phase:'calibration'};
 c.state.mobile_camera={status:'ready',tags:[{id:30,u:.25,v:.5}]};c.drawMarkerLabels();
 assert.deepEqual(c.ids(),['#30']);assert.equal(c.labels.children[0].style.left,'320px');
});
test('empty initial state is safe before the first response',()=>{
 const c=display();c.state=null;c.feedReady=false;c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
});
function startup(){
 let finishRenderer;
 const calls=[],rendering=new Promise(resolve=>finishRenderer=resolve);
 const c={booting:false,local:true,state:null,feedReady:true,publishedAssets:{},document:{hidden:false},
  request:async()=>({virtual_play:false,server_time:100}),
  physicalArm:{activate:active=>{calls.push(['controller',active]);return new Promise(()=>{});}},
  gameState:{receive:value=>{c.state=value;calls.push(['state']);}},openEvents:()=>calls.push(['events']),
  ensureRenderer:()=>{calls.push(['renderer']);return rendering;},
  view:{setFeedConnected(){},applyState:value=>calls.push(['paint',value.server_time])},
  turretOverlay:{sync(){}},syncSceneNotice(){},feedback:message=>calls.push(['error',message]),setTimeout(){}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('async function boot(){'),source.indexOf("$('loginForm').onsubmit")),c);
 return {c,calls,finishRenderer};
}
test('state, stream and controller start before the renderer finishes; newest state is painted',async()=>{
 const {c,calls,finishRenderer}=startup(),pending=c.boot();await new Promise(setImmediate);
 assert.deepEqual(calls.map(call=>call[0]),['controller','state','events','renderer']);
 c.state={virtual_play:false,server_time:105};finishRenderer();await pending;
 assert.deepEqual(calls.at(-1),['paint',105]);assert.equal(c.booting,false);
});
test('renderer failure does not discard already available tracking state',async()=>{
 const {c,calls}=startup();c.ensureRenderer=async()=>{throw Error('Renderer unavailable');};await c.boot();
 assert.equal(c.state.server_time,100);assert(calls.some(call=>call[0]==='events'));
 assert.deepEqual(calls.at(-1),['error','Renderer unavailable']);assert.equal(c.booting,false);
});

function fixedBoard(c){
 const d=c.state.mobile_cue_targets;
 Object.assign(d,{version:2,epoch:'camera-one',scope:'game-one',blocked_fixed_ids:[],
  fixed_tags:d.tags.filter(t=>t.fixed).map(t=>({...t}))});
 return d;
}
test('v2 fixed labels survive total occlusion, quarantines and camera/feed outages without enabling motion',()=>{
 for(const team of ['green','purple']){
  const c=display(team),d=fixedBoard(c);c.drawMarkerLabels();
  d.status='unavailable';d.tags=[];d.quarantined_tags=[{id:40,reason:'marker_geometry'}];
  c.now+=60000;c.feedReady=false;c.drawMarkerLabels();
  assert.deepEqual(c.ids(),['#40','#49']);assert.equal(c.state.mobile_arm,null);
  d.epoch='camera-two';d.fixed_tags=[];c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
 }
});
test('v2 remembered core and live Atom labels survive unrelated alignment size rejection',()=>{
 const c=display(),d=fixedBoard(c),raw=detections(c);
 d.fixed_tags.push({id:38,nx:.5,ny:.5,last_seen:40,fixed:true});
 raw.size_filter={rejected:[{id:38,reason:'size_outlier'},{id:40,reason:'size_outlier'},{id:100,reason:'size_outlier'}]};
 c.drawMarkerLabels();assert.deepEqual(c.ids(),['#38','#40','#49','#100']);
 c.now+=1100;c.drawMarkerLabels();assert.deepEqual(c.ids(),['#38','#40','#49'],'Atom remains live and expires');
});
test('v2 new game starts without old fixed labels; late tags extend the same epoch',()=>{
 const c=display(),d=fixedBoard(c);c.drawMarkerLabels();
 d.scope='game-two';d.epoch='new';d.fixed_tags=[];d.tags=[];c.drawMarkerLabels();assert.deepEqual(c.ids(),[]);
 d.fixed_tags=[{id:55,nx:.8,ny:.7,last_seen:100,fixed:true}];c.drawMarkerLabels();assert.deepEqual(c.ids(),['#55']);
});
