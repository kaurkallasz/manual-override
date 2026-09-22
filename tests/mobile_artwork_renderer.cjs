const assert=require('node:assert/strict');
let now=0;const pending=[],drawn=[],reports=[];
global.performance={now:()=>now};global.requestAnimationFrame=()=>1;global.cancelAnimationFrame=()=>{};
const context=new Proxy({drawImage:image=>drawn.push(image.src),measureText:()=>({width:0})},{get:(obj,key)=>key in obj?obj[key]:()=>{}});
const canvas=()=>({style:{},getContext:()=>context});
global.document={hidden:false,createElement:canvas,addEventListener(){},removeEventListener(){}};
global.Image=class{set src(value){this._src=value;this.naturalWidth=128;this.naturalHeight=128;pending.push(this)}get src(){return this._src}};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js');
const view=global.TowerDefenceView.create({mapCanvas:canvas(),gameCanvas:canvas(),onAssetStatus:s=>reports.push(s)});
const level=name=>({name,width:1696,height:960,paths:{},sockets:[],scene:{contract:'photon.visual-scene',version:1,layers:[{items:[{kind:'sprite',asset_id:'terrain',origin_x:0,origin_y:0,draw_x:0,draw_y:0,width:1696,height:960}]}]}});
const presentation=revision=>({contract:'photon.level.assets',version:1,status:'ready',base:'/art',revision,assets:{'map/terrain':revision+'.png','marker/38':revision+'-38.png'}});
const state=(revision,name)=>({phase:'setup',enemies:[],towers:[],level_revision:revision,level:level(name),presentation:presentation(name)});
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function finish(){for(const image of pending.splice(0))image.onload()}
(async()=>{
 view.applyState(state(1,'first'));assert.equal(view.levelReady,true,'first arrival supports the existing vector fallback');finish();await settle();assert.equal(view.level.name,'first');
 const requests=reports.at(-1).requested;view.applyState({phase:'setup',level_revision:1});view.renderMap();
 assert.equal(reports.at(-1).requested,requests);assert.equal(reports.at(-1).revision,'["/art","first","ready"]');assert.equal(view.level.name,'first');
 view.applyState(state(2,'second'));assert.equal(view.level.name,'first','keep the old map while replacement art loads');view.renderMap();assert.ok(drawn.includes('/art/first.png'));
 const older=pending.splice(0);view.applyState(state(3,'third'));for(const image of older)image.onload();await settle();assert.equal(view.level.name,'first','late artwork cannot publish an obsolete level');
 finish();await settle();assert.equal(view.level.name,'third');view.renderMap();assert.ok(drawn.includes('/art/third.png'));
 view.applyState({status:'unavailable'});view.renderMap();assert.equal(view.level.name,'third');assert.equal(reports.at(-1).revision,'["/art","third","ready"]');view.destroy();
 console.log('Artwork survives missing descriptors, loads atomically and rejects superseded map loads.');
})().catch(e=>{console.error(e);process.exitCode=1});
