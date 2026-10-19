const {test}=require('node:test'),assert=require('node:assert/strict');
const {WaveTimeline,layout,clock,progressTone}=require('../shared/ltz_ui/wave-timeline.js');
class Node{
 constructor(){this.children=[];this.attributes={};this.dataset={};this.classList={add(){}};this.hidden=false;}
 append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}
 setAttribute(key,value){this.attributes[key]=value;}
}
global.document={createElementNS:()=>new Node(),createElement:()=>new Node()};
function fixture(){let now=0;const panel=new Node(),ui=new WaveTimeline(panel,{now:()=>now,raf:()=>1,cancel(){}});
 const data={status:'ready',run_id:'one',phase:'running',paused:false,server_time:10,active_enemies:2,wave_timeline:{contract:'photon.wave-timeline',version:1,status:'ready',time_s:20,end_s:120,queued_orcs:0,waves:[{wave:1,start_s:30,end_s:60,duration_s:30,state:'upcoming'}]}};
 return {ui,panel,data,advance:n=>now+=n};}
test('overlapping waves occupy separate lanes and preserve real duration',()=>{
 const {bars,lanes}=layout([{wave:1,start_s:10,end_s:40},{wave:2,start_s:20,end_s:50},{wave:3,start_s:40,end_s:60}],100);
 assert.equal(lanes,2);assert.deepEqual(bars.map(w=>w.lane),[0,1,0]);assert.equal(bars[0].width,288);assert.equal(clock(125),'2:05');
});
test('playhead moves only with fresh running time; pauses and disconnect freeze it',()=>{
 const {ui,panel,data,advance}=fixture();ui.update(data);const before=+panel.dataset.time;
 advance(100);ui.paint();assert(+panel.dataset.time>before);
 ui.update({...data,paused:true});advance(500);ui.paint();assert.equal(+panel.dataset.time,20);assert.match(ui.clockText.textContent,/PAUSED/);
 ui.update({...data,server_time:11});ui.setConnected(false);advance(500);ui.paint();assert.equal(+panel.dataset.time,20);assert.match(ui.clockText.textContent,/FEED PAUSED/);
 ui.update({...data,server_time:12});advance(1600);ui.paint();assert.equal(+panel.dataset.time,20);
});
test('reset, calibration, terminal state and stale snapshots do not invent progress',()=>{
 const {ui,panel,data,advance}=fixture();ui.update(data);
 ui.update({...data,server_time:9,wave_timeline:{...data.wave_timeline,time_s:99}});assert.equal(+panel.dataset.time,20);
 ui.update({...data,server_time:11,phase:'overrun'});advance(500);ui.paint();assert.equal(+panel.dataset.time,20);
 ui.update({...data,run_id:null,server_time:12,phase:'setup',wave_timeline:{...data.wave_timeline,time_s:0}});assert.equal(+panel.dataset.time,0);
 ui.update({...data,journey:{phase:'calibration'}});assert.equal(panel.hidden,true);
 ui.update(data);assert.equal(panel.hidden,false);ui.destroy();assert.equal(ui.frame,null);
});
test('idle snapshots do not falsely report a stalled running clock',()=>{
 const {ui,data,advance}=fixture();ui.update({...data,phase:'setup'});advance(5000);ui.paint();
 assert.match(ui.clockText.textContent,/READY/);
 ui.update({...data,paused:true});advance(5000);ui.paint();assert.match(ui.clockText.textContent,/^PAUSED/);
 ui.setConnected(false);assert.match(ui.clockText.textContent,/FEED PAUSED/);
});
test('progress warms over the final 30 seconds, stays orange during release and returns green',()=>{
 const waves=[{start_s:60,state:'upcoming'},{start_s:180,state:'upcoming'}];
 assert.deepEqual(progressTone(waves,29.9,'running'),{state:'clear',color:'rgb(54, 224, 124)'});
 assert.deepEqual(progressTone(waves,30,'running'),{state:'warning',color:'rgb(54, 224, 124)'});
 assert.deepEqual(progressTone(waves,45,'running'),{state:'warning',color:'rgb(150, 195, 80)'});
 assert.equal(progressTone(waves,60,'running').color,'rgb(245, 166, 35)');
 assert.equal(progressTone(waves,60.25,'running').color,'rgb(245, 166, 35)');
 waves[0].state='spawning';
 assert.deepEqual(progressTone(waves,80,'running'),{state:'spawning',color:'rgb(245, 166, 35)'});
 waves[0].state='released';
 assert.deepEqual(progressTone(waves,100,'running'),{state:'clear',color:'rgb(54, 224, 124)'});
 assert.equal(progressTone(waves,165,'running').state,'warning');
 for(const phase of ['setup','won','overrun','aborted'])assert.equal(progressTone(waves,165,phase).color,'rgb(54, 224, 124)');
});
test('overlapping releases stay orange until all spawning windows finish',()=>{
 const waves=[{start_s:60,state:'released'},{start_s:80,state:'spawning'}];
 assert.equal(progressTone(waves,100,'running').state,'spawning');
 waves[1].state='released';
 assert.deepEqual(progressTone(waves,120,'running'),{state:'clear',color:'rgb(54, 224, 124)'});
});
test('solid elapsed fill grows between waves, freezes with the clock and clears on reset',()=>{
 const {ui,panel,data,advance}=fixture();
 const update=(time,extra={})=>ui.update({...data,paused:true,...extra,wave_timeline:{...data.wave_timeline,time_s:time,waves:[]}});
 update(60);assert.equal(+ui.progress.attributes.width,480);assert.equal(panel.dataset.tone,'clear');
 update(90);assert.equal(+ui.progress.attributes.width,720);assert.equal(+ui.progressShine.attributes.width,720);
 advance(1000);ui.paint();assert.equal(+ui.progress.attributes.width,720);
 update(100,{paused:false});advance(100);ui.paint();assert(+ui.progress.attributes.width>800);
 ui.setConnected(false);const frozen=ui.progress.attributes.width;advance(500);ui.paint();assert.equal(ui.progress.attributes.width,frozen);
 update(150);assert.equal(+ui.progress.attributes.width,960);
 update(0,{phase:'setup',run_id:'reset'});assert.equal(+ui.progress.attributes.width,0);
});
