/* Operator display consumes the same fixed map; no network or physical I/O. */
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('sandboxes/gamemaster/prototypes/laser-tag-y/index.html','utf8');
function fixture(){
 let now=100,value;
 const c={LTZMarkerPresence:require('../shared/ltz_ui/marker-presence.js'),document:{createElementNS:()=>({attrs:{},setAttribute(k,v){this.attrs[k]=v}})}};
 vm.createContext(c);vm.runInContext(source.slice(source.indexOf('function createArucoMonitor('),source.indexOf('const arucoMonitor=')),c);
 const overlay={children:[],toggleAttribute(){},replaceChildren(){this.children=[]},setAttribute(){},append(node){this.children.push(node)}};
 const monitor=c.createArucoMonitor({overlay,now:()=>now,onChange:v=>value=v});
 monitor.setEnabled(true);
 const board={contract:'photon.board.cue-targets',version:2,status:'ready',source:'camera',coordinate_space:'corrected-camera-normalized',
  scope:'game',epoch:'map',width:1280,height:720,server_time:100,frame_at:100,tags:[],fixed_tags:[
   {id:38,nx:.5,ny:.5,last_seen:100,fixed:true,visible:true},
   {id:40,nx:.3,ny:.4,last_seen:100,fixed:true,visible:true}]};
 const data={contract:'photon.board.tracking',version:1,status:'ready',tags:[],fixed_board:board,
  camera_markers:{status:'unavailable',size_filter:{rejected:[{id:38,reason:'size_outlier'},{id:40,reason:'size_outlier'}]}}};
 return {monitor,board,data,overlay,ids:()=>value.tags.map(t=>t.id),value:()=>value,tick:n=>now+=n};
}
test('fixed 30/40/50-series labels keep one-second styling through the Board 350ms visibility cutoff',()=>{
 const f=fixture();f.board.fixed_tags.push({id:54,nx:.7,ny:.6,last_seen:100,fixed:true,visible:true});
 for(let frame=0;frame<8;frame++){
  const seen=100+frame*.6;
  f.board.frame_at=seen;
  f.board.fixed_tags.forEach(t=>{t.last_seen=seen;t.visible=true});f.monitor.update(f.data);
  const nodes=[...f.overlay.children];
  for(let sample=0;sample<3;sample++){
   f.tick(.2);f.board.fixed_tags.forEach(t=>t.visible=false);f.monitor.update(f.data);f.monitor.check();
   assert(f.value().tags.every(t=>!t.visible&&t.recent&&!t.cached),'Presentation grace must not claim current camera visibility');
   assert.equal(f.value().cachedCount,0);
   assert(f.overlay.children.filter(n=>n.textContent).every(n=>!n.textContent.includes('cached')));
   assert(f.overlay.children.every((n,i)=>n===nodes[i]),'Unchanged fixed labels should not be torn down on each event/watchdog tick');
  }
 }
});
test('fixed grace expires from the sighting, even if repeated packets still say visible',()=>{
 const f=fixture();f.monitor.update(f.data);f.tick(1.01);f.monitor.update(f.data);
 assert(f.value().tags.every(t=>!t.visible&&!t.recent&&t.cached));
 assert.equal(f.value().cachedCount,2);
 assert.deepEqual(f.overlay.children.filter(n=>n.textContent).map(n=>n.textContent),['#38 · cached','#40 · cached']);
 f.tick(.1);f.monitor.update(f.data);assert(f.value().tags.every(t=>t.cached));
});
test('unavailable or stale mapping revokes fresh styling without erasing fixed labels',()=>{
 for(const invalidate of [f=>{f.board.status='unavailable'},f=>{f.board.frame_at=98},f=>{f.tick(1.6)}]){
  const f=fixture();f.monitor.update(f.data);invalidate(f);f.monitor.check();
  assert.deepEqual([...f.ids()],[38,40]);assert(f.value().tags.every(t=>!t.visible&&!t.recent&&t.cached));
 }
});
test('operator fixed numbers survive malformed geometry, occlusion and camera outage',()=>{
 const f=fixture();f.monitor.update(f.data);assert.deepEqual([...f.ids()],[38,40]);
 f.board.status='unavailable';f.board.fixed_tags.forEach(t=>t.visible=false);f.tick(60);f.monitor.update(f.data);
 assert.deepEqual([...f.ids()],[38,40]);assert(f.value().ready);assert.equal(f.board.status,'unavailable');
 f.board.epoch='moved';f.board.fixed_tags=[];f.monitor.update(f.data);assert.deepEqual([...f.ids()],[]);
});
test('operator moving numbers expire and new fixed markers join without changing the map',()=>{
 const f=fixture();f.board.tags=[{id:100,nx:.4,ny:.3,last_seen:100,fixed:false,visible:true}];
 f.monitor.update(f.data);assert.deepEqual([...f.ids()],[38,40,100]);
 f.tick(1.1);f.monitor.check();assert.deepEqual([...f.ids()],[38,40]);
 f.board.fixed_tags.push({id:54,nx:.7,ny:.6,last_seen:101,fixed:true});f.monitor.update(f.data);
 assert.deepEqual([...f.ids()],[38,40,54]);
 f.board.scope='new-game';f.board.fixed_tags=[];f.monitor.update(f.data);assert.deepEqual([...f.ids()],[]);
});
test('same-ID coordinate and frame-size updates reposition operator overlay controls',()=>{
 const f=fixture();f.monitor.update(f.data);
 assert.equal(f.value().tags.find(t=>t.id===40).camera[0],.3);
 f.board.fixed_tags[1].nx=.65;f.monitor.update(f.data);
 assert.equal(f.value().tags.find(t=>t.id===40).camera[0],.65);
 f.board.width=1920;f.board.height=1080;f.monitor.update(f.data);
 assert.equal(f.value().width,1920);assert.equal(f.value().height,1080);
});
