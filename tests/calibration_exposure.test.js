const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../sandboxes/gamemaster/prototypes/camera-calibration/controller.html'),'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/renderBrightness\(\);loadPlayfieldBrightness\(\);[\s\S]*$/, '');
function fixture(){
 const nodes=new Map(),streams=[],calls=[],listeners={},timers=new Map();let timerId=0;
 const ctx=vm.createContext({location:{pathname:'/s/gamemaster/p/camera-calibration/'},
  document:{hidden:false,getElementById(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',checked:false});return nodes.get(id);},addEventListener(name,fn){listeners[name]=fn;}},
  window:{addEventListener(name,fn){listeners[name]=fn;}},localStorage:{getItem(){return null;},setItem(){}},AbortSignal,
  setTimeout(fn){timers.set(++timerId,fn);return timerId;},clearTimeout(id){timers.delete(id);},
  EventSource:class {constructor(url){this.url=url;streams.push(this);}close(){this.closed=true;}},
  fetch:async(url,options)=>{calls.push({url,options,activeStreams:streams.filter(s=>!s.closed).length});return {ok:true,json:async()=>({ok:true,camera_open:true,autoexposure_supported:true,exposure_supported:true,autoexposure:false,exposure:300,exposure_min:1,exposure_max:80000,exposure_step:1})};}
 });vm.runInContext(source,ctx);
 return {ctx,nodes,streams,calls,listeners,timers,run:s=>vm.runInContext(s,ctx)};
}
test('80% of exposure travel gives individual 100 µs steps around 0.03 seconds',()=>{
 const f=fixture();f.run('exposureRange={min:1,max:80000,step:1}');
 assert.equal(f.run('exposureSliderPosition(300)'),250);
 for(let pos=50;pos<=450;pos++)assert.equal(f.run(`exposureFromSlider(${pos})`),pos+50);
 assert.equal(f.run('exposureFromSlider(0)'),1);
 assert.equal(f.run('exposureFromSlider(500)'),80000);
 assert(f.run('exposureFromSlider(499)-exposureFromSlider(498)')>1000);
});
test('exposure scale is monotonic, reversible and clamped across camera ranges',()=>{
 for(const range of [{min:1,max:80000,step:1},{min:200,max:10000,step:5},{min:1,max:350,step:1},{min:250,max:400,step:1},{min:600,max:9000,step:2},{min:1,max:50,step:1}]){
  const f=fixture();f.run(`exposureRange=${JSON.stringify(range)}`);let previous=range.min;
  for(let i=0;i<=500;i++){
   const value=f.run(`exposureFromSlider(${i})`);assert(value>=previous&&value<=range.max);
   const roundtrip=f.run(`exposureFromSlider(exposureSliderPosition(${value}))`);assert.equal(roundtrip,value);previous=value;
  }
  assert.equal(f.run('exposureFromSlider(-10)'),range.min);
  assert.equal(f.run('exposureFromSlider(510)'),range.max);
 }
});
test('manual-mode request frees the video connection and enables the existing slider',async()=>{
 const f=fixture();f.run('startCameraEvents()');f.nodes.get('autoexposure').checked=false;
 await f.nodes.get('autoexposure').onchange();
 assert.equal(f.calls.length,1);assert.equal(f.calls[0].activeStreams,0);
 assert.equal(JSON.parse(f.calls[0].options.body).autoexposure,false);
 assert.equal(f.nodes.get('manualExposure').disabled,false);
 assert.equal(f.nodes.get('exposureValue').value,'0.0300 s');
 assert.equal(f.streams.filter(s=>!s.closed).length,1);
});
test('pending control request keeps its connection across hide/show and reads the full response first',async()=>{
 const f=fixture();let finish;
 f.ctx.fetch=async()=>({ok:true,json:()=>new Promise(resolve=>{finish=resolve;})});
 f.run('startCameraEvents()');const pending=f.run("post('api/focus',{autoexposure:false})");await new Promise(setImmediate);
 f.listeners.pageshow();assert(f.streams.every(s=>s.closed));
 finish({ok:true});await pending;assert.equal(f.streams.filter(s=>!s.closed).length,1);
 f.listeners.pagehide();assert(f.streams.every(s=>s.closed));
 f.ctx.document.hidden=true;f.listeners.pageshow();assert(f.streams.every(s=>s.closed));
});
test('stream delivers preview and state without polling and cannot overwrite a slider edit',async()=>{
 const f=fixture();f.run('startCameraEvents()');const stream=f.streams[0];
 const controls={ok:true,camera_open:true,autoexposure_supported:true,exposure_supported:true,autoexposure:false,exposure:309,exposure_min:1,exposure_max:80000,exposure_step:1};
 stream.onmessage({data:JSON.stringify({preview:'data:image/jpeg;base64,test',controls})});
 assert.equal(f.nodes.get('manualExposure').value,259);assert.equal(f.calls.length,0);
 f.nodes.get('manualExposure').value=251;f.nodes.get('manualExposure').oninput();
 stream.onmessage({data:JSON.stringify({controls})});assert.equal(f.nodes.get('exposureValue').value,'0.0301 s');
 await [...f.timers.values()][0]();assert.equal(JSON.parse(f.calls[0].options.body).exposure,301);
});
test('successive slider writes are serialized and old readback does not reset newer input',async()=>{
 const f=fixture();const responses=[];
 f.ctx.fetch=()=>new Promise(resolve=>responses.push(resolve));
 const first=f.run("saveControls({exposure:300},()=> 'first')");await new Promise(setImmediate);
 const second=f.run("saveControls({exposure:301},()=> 'second')");await new Promise(setImmediate);assert.equal(responses.length,1);
 responses[0]({ok:true,json:async()=>({exposure:300})});await first;await new Promise(setImmediate);
 assert.notEqual(f.nodes.get('focusMsg')?.textContent,'first');assert.equal(responses.length,2);
 responses[1]({ok:true,json:async()=>({exposure:301})});await second;assert.equal(f.nodes.get('focusMsg').textContent,'second');
});
