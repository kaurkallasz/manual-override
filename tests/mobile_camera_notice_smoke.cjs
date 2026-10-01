/* Run: node tests/mobile_camera_notice_smoke.cjs. No camera, browser or robot. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('shared/mobile_ltz/mobile.js','utf8');
const html=fs.readFileSync('shared/mobile_ltz/index.html','utf8');
for(const id of ['empty','emptyMessage','turretAimStatus','cueStatus','controlPathStatus']){
 assert(!html.includes(`id="${id}"`),`${id} cannot flash over the playfield`);
 assert(!source.includes(`$('${id}')`),`${id} has no remaining runtime writes`);
}
let now=100,ready=true,rows=[];
const element=()=>({attrs:{},setAttribute(key,value){this.attrs[key]=value;}});
const elements={feedback:{replaceChildren(...items){rows=items;}}};
const ctx={performance:{now:()=>now},document:{createElement:element},
 $:id=>{assert(elements[id],`Unexpected status destination ${id}`);return elements[id];},
 state:{virtual_play:false,mobile_camera:{status:'ready'}},feedReady:true,
 turretOverlay:{imageAt:100,cameraReady:()=>ready},view:null};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('const feedbackLines='),source.indexOf('function syncViewport('))+
 source.slice(source.indexOf("let sceneNotice='';"),source.indexOf('function applyState(')),ctx);
ctx.syncSceneNotice();assert.equal(rows.length,0);
ready=false;ctx.state.mobile_camera={status:'unavailable',error:'Camera alignment is unstable.'};ctx.syncSceneNotice();
assert.equal(rows[0].textContent,'Camera alignment is unstable.');
assert.equal(rows[0].attrs.class,'urgent','Urgent camera notices have purple, bold styling');
const first=rows[0];
for(let i=0;i<100;i++){now+=80;ctx.syncSceneNotice();}
assert.equal(rows[0],first,'Video callbacks log one transition, not every frame');
vm.runInContext("feedback('Connected')",ctx);assert.equal(rows[0].textContent,'Connected','Repeated callbacks do not extend the eight-second pin');
assert.equal(rows[1].attrs.class,'urgent','History retains the urgent style');
ready=true;ctx.syncSceneNotice();
for(let i=0;i<50;i++){ready=false;ctx.syncSceneNotice();ready=true;ctx.syncSceneNotice();}
assert.equal(rows.filter(row=>row.textContent==='Camera alignment is unstable.').length,1,'Readiness fluctuations reuse one log entry and never write an overlay');
ctx.state.mobile_camera={status:'ready'};
now+=1;vm.runInContext("feedback('Routine feedback')",ctx);assert.equal(rows[0].attrs.class,'urgent','A recovered camera notice stays readable');
now+=8000;vm.runInContext("feedback('Routine feedback')",ctx);assert.equal(rows[0].textContent,'Routine feedback');
ready=false;ctx.syncSceneNotice();assert.equal(rows[0].textContent,'Camera paused · showing last frame.');assert.equal(rows[0].attrs.class,'urgent');
ctx.state.virtual_play=true;ctx.syncSceneNotice();assert.equal(rows[0].textContent,'Camera paused · showing last frame.','Virtual loading does not overwrite a pinned physical camera fault');
now+=8000;ctx.view={levelReady:true};ctx.syncSceneNotice();ctx.view.levelReady=false;ctx.syncSceneNotice();
assert.equal(rows[0].textContent,'Waiting for the live level…');assert.equal(rows[0].attrs.class,undefined);
ctx.state.virtual_play=false;ctx.turretOverlay.imageAt=0;ctx.syncSceneNotice();
assert.equal(rows[0].textContent,'Waiting for corrected live video…');assert.equal(rows[0].attrs.class,undefined,'Initial loading is a log notice, not an urgent failure');
ctx.feedReady=false;ctx.state.error='Gamemaster connection unavailable.';ready=true;ctx.syncSceneNotice();
assert.equal(rows[0].textContent,ctx.state.error);assert.equal(rows[0].attrs.class,'urgent','Feed errors reach the log even when a frame remains visible');

// Cue progress/errors also have one destination, with one entry per transition.
now+=8000;ctx.state.mobile_arm={cue:{status:'running',index:0,stage:'pickup'}};
for(const id of ['cueAdd','cuePlay','cueStop','cueWaypointCancel'])elements[id]=element();
elements.cueRows={querySelectorAll:()=>[],querySelector:()=>null};
Object.assign(ctx,{controlMode:'joint',cueNotice:'',cueLogNotice:'',cueLastStatus:'',cueBusy:false,cueDirty:false,switchBusy:false,cueDraft:[],cueWaypointRow:{},available:()=>true});
vm.runInContext(source.slice(source.indexOf('function updateCueControls('),source.indexOf('function syncCue(')),ctx);
const beforeCue=rows[0];ctx.updateCueControls();assert.equal(rows[0],beforeCue,'Hidden cue controls do not emit idle/progress messages');
ctx.controlMode='cue';ctx.updateCueControls();assert.equal(rows[0].textContent,'Row 1 · pickup');
const cueRow=rows[0];for(let i=0;i<100;i++)ctx.updateCueControls();assert.equal(rows[0],cueRow);
ctx.state.mobile_arm.cue.error='Cue marker unavailable.';ctx.updateCueControls();assert.equal(rows[0].textContent,'Cue marker unavailable.');assert.equal(rows[0].attrs.class,'urgent');
for(let i=0;i<100;i++){now+=80;ctx.updateCueControls();}
vm.runInContext("feedback('After cue')",ctx);assert.equal(rows[0].textContent,'After cue','Repeated cue refreshes do not extend the urgent pin');

// Turret helper keeps its persistent title, but reports saves/errors through the log callback.
const {TurretOverlay}=require('../shared/mobile_ltz/turret-overlay.js');
const previousDocument=global.document,title={};let calls=0;
global.document={getElementById:id=>{assert.equal(id,'turretAimTitle');return title;}};
try{
 const overlay=Object.create(TurretOverlay.prototype);overlay.o={message:(text,important)=>{calls++;ctx.turretMessage=text;ctx.turretImportant=important;vm.runInContext('feedback(turretMessage,turretImportant)',ctx);}};
 overlay.status('Saving…','Turret · 180');overlay.status('Saved','Turret · 180');assert.equal(rows[0].textContent,'Saved');
 overlay.status('Tracking unavailable','Turret',true);assert.equal(rows[0].textContent,'Tracking unavailable');assert.equal(rows[0].attrs.class,'urgent');
 const tracking=rows[0];for(let i=0;i<100;i++){now+=80;overlay.status('Tracking unavailable','Turret',true);}
 assert.equal(rows[0],tracking);assert.equal(calls,3,'Turret refreshes deduplicate before the log callback');
 vm.runInContext("feedback('Tracking restored')",ctx);assert.equal(rows[0].textContent,'Tracking restored');
 overlay.status('Aim save failed.','Turret',true);assert.equal(rows[0].textContent,'Aim save failed.');assert.equal(title.textContent,'Turret');
}finally{global.document=previousDocument;}
console.log('PASS: camera/loading/feed, cue and turret notices use only the left log; readiness fluctuations cannot flash overlays; urgent styling, readable lifetime and deduplication pass');
