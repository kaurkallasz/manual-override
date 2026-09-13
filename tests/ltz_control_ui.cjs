// Exercise the real control visibility adapter without a robot connection.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('sandboxes/green/prototypes/auto-pickup-game/controller.html','utf8');
const adapter=source.slice(source.indexOf('const LTZ ='),source.indexOf('let ltzProgressEvents'));
const presentation=source.slice(source.indexOf('function applyLtxConfig('),source.indexOf('async function pollLtxConfig('));
const elements=new Map();const gid=id=>{if(!elements.has(id))elements.set(id,{hidden:false,textContent:''});return elements.get(id);};
const context=vm.createContext({LTX:true,TEAM:'green',location:{search:'?ltz=1'},URLSearchParams,
 document:{title:'',querySelector:()=>gid('heading')},gid,requestAnimationFrame:()=>{},renderCraneControls:()=>{},
 autoPpxRunning:false,autoPpxAbort:false,autoPpxClickOverride:null,ltxVideoClickEnabled:false,ltxGameMode:null,
 cancelAutoPpxClickOverride:()=>{},invalidateVideoClicks:()=>{}});
vm.runInContext(adapter+'\n'+presentation,context);
for(let tier=1;tier<=4;tier++){
 context.input={status:'ready',player:{name:'Pilot',selected_control:4},active_attempts:[{participants:[{side:'green',control_tier:tier}]}]};
 vm.runInContext('applyLtzProgress(input)',context);
 assert.equal(gid('jointAnglesPanel').hidden,false);
 assert.equal(gid('tcpPosePanel').hidden,tier<2);
 assert.equal(gid('autoPickPlacePanel').hidden,tier<3);
 assert.equal(gid('autoPpxPanel').hidden,tier<4);
 assert.equal(vm.runInContext('ltxVideoClickEnabled',context),tier>=3);
}
vm.runInContext("applyLtzProgress({status:'unavailable'})",context);
assert.equal(gid('jointAnglesPanel').hidden,true);
assert.equal(gid('autoPpxPanel').hidden,true);
console.log('LTZ controller visibility and frozen-tier checks passed.');
