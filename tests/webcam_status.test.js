const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../sandboxes/gamemaster/prototypes/webcam/controller.html'),'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nloadCameras\(\);\s*$/, '');

function fixture(){
  const nodes=new Map(),calls=[],streams=[],listeners={};
  const listen=(name,fn)=>{listeners[name]=fn;};
  function node(){return {value:'',textContent:'',innerHTML:'',style:{},options:[],
    replaceChildren(){this.options=[];this.value='';},append(option){this.options.push(option);if(this.options.length===1)this.value=option.value;}};}
  const context=vm.createContext({location:{pathname:'/s/gamemaster/p/webcam/controller'},
    document:{getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);},createElement:node,hidden:false,addEventListener:listen},
    window:{addEventListener:listen},setInterval(){},setTimeout(){},
    EventSource:class {constructor(url){this.url=url;this.closed=false;streams.push(this);}close(){this.closed=true;}},
    fetch:async (url,options)=>{calls.push({url,options,activeStreams:streams.filter(s=>!s.closed).length});return {json:async()=>({ok:true,open:false})};}});
  vm.runInContext(source,context);
  return {context,nodes,calls,streams,listeners,run:script=>vm.runInContext(script,context)};
}

test('disconnect clears live dimensions and relabels the cached camera without reopening it',()=>{
  const f=fixture();
  f.run(`cameraChoices=[{index:0,name:'Verbatim',unique_id:'usb'}];
    applyStatus({open:true,index:0,unique_id:'usb',width:3840,height:2160,preview_width:1920,preview_height:1080,tracking_width:1920,tracking_height:1080,fps:30});`);
  assert.equal(f.nodes.get('res').textContent,'3840×2160');
  assert.match(f.nodes.get('cam').options[0].textContent,/active/);
  f.run(`applyStatus({open:false,index:0,unique_id:'usb',width:3840,height:2160,error:'Camera disconnected',remembered:{index:0,unique_id:'usb',name:'Verbatim'}});`);
  for(const id of ['res','previewRes','trackingRes','fps'])assert.equal(f.nodes.get(id).textContent,'—');
  assert.equal(f.nodes.get('cam').options[0].textContent,'Verbatim (unavailable)');
  assert.equal(f.calls.length,0);
});

test('missing saved camera is not relabelled as another device at the same index',()=>{
  const f=fixture();
  f.run(`cameraChoices=[{index:0,name:'FaceTime',unique_id:'builtin'}];
    applyStatus({open:false,index:null,remembered:{index:0,name:'Verbatim',unique_id:'usb'}});`);
  assert.equal(f.nodes.get('cam').value,'');
  assert.equal(f.nodes.get('cam').options[0].textContent,'Verbatim (unavailable)');
  assert.equal(f.nodes.get('cam').options[1].textContent,'FaceTime');
});

test('Stop keeps observation only; Reconnect uses the explicit recovery route',async()=>{
  const f=fixture();
  await f.nodes.get('stop').onclick();
  assert(f.calls.some(c=>c.url.endsWith('/api/stop')));
  assert(!f.nodes.get('feed').src);
  await f.nodes.get('reconnect').onclick();
  assert(f.calls.some(c=>c.url.endsWith('/api/reconnect')&&c.options.method==='POST'));
  assert(!f.nodes.get('feed').src);
  assert(f.streams.every(s=>s.url.endsWith('/api/events?preview=1')));
  assert(f.calls.every(c=>c.activeStreams===0));
  assert.equal(f.streams.filter(s=>!s.closed).length,1);
});


test('one event stream delivers both the image and status without a second video request',()=>{
  const f=fixture();
  f.run('startStream(); startStream();');
  assert.equal(f.streams.length,1);
  f.streams[0].onmessage({data:JSON.stringify({preview:'data:image/jpeg;base64,ZmFrZQ==',status:{open:true,width:3840,height:2160,fps:25},tags:[]})});
  assert.equal(f.nodes.get('feed').src,'data:image/jpeg;base64,ZmFrZQ==');
  assert.equal(f.nodes.get('res').textContent,'3840×2160');
  assert.equal(f.calls.length,0);
  f.nodes.get('feed').onload();
  assert.equal(f.nodes.get('feedNotice').hidden,true);
  f.streams[0].onerror();
  assert.equal(f.nodes.get('feedNotice').hidden,false);
  assert.match(f.nodes.get('feedNotice').textContent,/reconnecting/);
});

test('hidden/unloaded views release their stream and resume once without using old events',()=>{
  const f=fixture();
  f.run('startStream();');
  const old=f.streams[0];
  f.context.document.hidden=true;
  f.listeners.visibilitychange();
  assert.equal(old.closed,true);
  f.listeners.pageshow();
  assert.equal(f.streams.length,1);
  f.context.document.hidden=false;
  f.listeners.visibilitychange();
  f.listeners.pageshow();
  assert.equal(f.streams.length,2);
  old.onmessage({data:JSON.stringify({preview:'data:image/jpeg;base64,old'})});
  old.onerror();
  assert(!f.nodes.get('feed').src);
  assert.notEqual(f.nodes.get('conn')?.textContent,'offline');
  f.listeners.pagehide();
  assert(f.streams.every(s=>s.closed));
});

test('loading cameras reserves the connection until the response, even across visibility events',async()=>{
  const f=fixture();
  let finish;
  f.context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  const loading=f.run('loadCameras()');
  f.listeners.pageshow();
  f.listeners.visibilitychange();
  assert.equal(f.streams.length,0);
  finish({json:async()=>({cameras:[],status:{open:false}})});
  await loading;
  assert.equal(f.streams.length,1);
});
