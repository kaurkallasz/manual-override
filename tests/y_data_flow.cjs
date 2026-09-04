const assert = require('node:assert/strict');
let clock=100, graphWidth=1140;
const all = node => [node, ...node.children.flatMap(all)];
const text = node => all(node).map(n=>n.textContent).join(' ');
class Element {
  constructor(tag) {this.tag=tag;this.children=[];this.attrs={};this.style={};this.dataset={};this.textContent='';this.handlers={};this.open=false;this.id='diagram';this.className='';this.classes=new Set();this.classList={toggle:name=>{if(this.classes.has(name)){this.classes.delete(name);return false;}this.classes.add(name);return true;}};}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=children;}
  setAttribute(key,value) {this.attrs[key]=value;}
  addEventListener(key,fn) {this.handlers[key]=fn;}
  removeEventListener(key) {delete this.handlers[key];}
  showModal() {this.open=true;}
  close() {this.open=false;this.handlers.close?.();}
  focus() {this.focused=true;}
  getBoundingClientRect() {
    if(!this.dataset.node)return {left:-scroller.scrollLeft,right:graphWidth-scroller.scrollLeft,top:-scroller.scrollTop,bottom:1100-scroller.scrollTop,width:graphWidth,height:1100};
    const width=(graphWidth-24-4*82)/5;
    const left=12+((+this.style.gridColumn-1)/2)*(width+82)-scroller.scrollLeft,top=42+(+this.style.gridRow-1)*208-scroller.scrollTop;
    return {left,top,right:left+width,bottom:top+160,width,height:160};
  }
}
global.document={createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)};
global.performance={now:()=>clock};
const timers=new Set();
global.setInterval=fn=>{timers.add(fn);return fn;};global.clearInterval=fn=>timers.delete(fn);
let resize;
global.ResizeObserver=class {constructor(fn){resize=fn;}observe(){}disconnect(){this.disconnected=true;}};
require('../sandboxes/gamemaster/prototypes/laser-tag-y/data-flow.js');
const elements=Object.fromEntries(['dialog','openButton','closeButton','motionButton','graph','health','received','details'].map(key=>[key,new Element(key)]));
const scroller={scrollTop:0,scrollLeft:0,getBoundingClientRect:()=>({left:0,top:0,width:1140,height:420}),
  scrollTo(value){this.scrollTop=Math.max(0,value.top);this.scrollLeft=Math.max(0,value.left);}};
elements.graph.parentElement=scroller;
const flow=YDataFlow.create({...elements,self:'/s/gamemaster/p/laser-tag-y',sandboxRoot:'/s/gamemaster'});
const snapshot={contract:'photon.game',version:2,status:'ready',phase:'running',wave:1,virtual_play:true,server_time:1000,
  towers:[{}],active_enemies:7,level:{name:'fixture',width:1696,height:960,sockets:[{}],scene:{layers:[]}},
  inputs:{level:{status:'ready',revision:17},board:{status:'unavailable',error:'Fixture Board disabled'}},
  presentation:{status:'ready',base:'/p/content-owner/assets',assets:{'map/test':'test.png'},revision:'hash-one'}};
flow.snapshot(snapshot,'snapshot');
elements.openButton.onclick();
assert.equal(timers.size,1);
assert(scroller.scrollTop>0,'open on the main Game/Y connection');
assert(text(elements.health).includes('Snapshot received'));
assert(text(elements.details).includes('/s/gamemaster/p/laser-tag-y/api/events'));
const nodes=Object.fromEntries(all(elements.graph).filter(n=>n.dataset.node).map(n=>[n.dataset.node,n]));
assert.equal(Object.keys(nodes).length,17);
flow.focus('authored');assert.equal(scroller.scrollTop,0);
flow.focus('pickup');assert(scroller.scrollTop>700);
flow.focus('game');
const routes=YDataFlow.edges.map(([a,b])=>`${a}>${b}`);
for(const route of ['camera>webcam','webcam>correction','lens>correction','correction>board','correction>preview','robots>relay','relay>board','cal2>pickup','players>pickup','players>relay','board>pickup','pickup>board','board>game','game>y','authored>level','level>files','files>y'])assert(routes.includes(route),route);
assert(!routes.includes('preview>game')&&!routes.includes('preview>y'),'video never becomes gameplay input');
nodes.lens.onclick();assert(text(elements.details).includes('calibration.json'));
nodes.cal2.onclick();assert(text(elements.details).includes('auto-calibration-2.json'));
nodes.relay.onclick();assert(text(elements.details).includes('feedback_at'));
nodes.preview.onclick();assert(text(elements.details).includes('does not open it'));
assert(text(nodes.webcam).includes('Not reported'));
const particles=all(elements.graph).filter(n=>n.attrs.class?.startsWith('df-particles'));
assert(!particles.some(p=>p.dataset.active==='true'),'no fictitious activity after initial snapshot');
flow.snapshot(snapshot,'SSE');
assert.equal(elements.health.textContent,'SSE receiving');
assert.equal(particles.filter(p=>p.dataset.active==='true').length,1);
assert(text(nodes.y).includes('7 enemies'));
nodes.board.onclick();
assert(text(elements.details).includes('Fixture Board disabled'));
assert(text(elements.details).includes('not raw tracking'));
assert.equal(nodes.board.attrs['aria-pressed'],'true');
const reportSnapshot=structuredClone(snapshot);
reportSnapshot.inputs.board.upstream={reported_at:1000,source:'camera',inputs:{
  webcam:{status:'ready',contract:'hhh.webcam.tags',version:1},
  camera_calibration:{status:'unavailable',error:'lens calibration missing'},
  relay:{status:'ready',contract:'hhh.relay.arms',version:1}},
  tracking:{inputs:{cal2_projection:{status:'ready'},controller_intent:{status:'unavailable',error:'No LTX report'}}}};
flow.snapshot(reportSnapshot,'SSE');
nodes.correction.onclick();assert(text(elements.details).includes('lens calibration missing'));
assert(text(nodes.correction).includes('Board reports: unavailable'));
nodes.pickup.onclick();assert(text(elements.details).includes('No LTX report'));
assert(text(elements.details).includes('hhh.cal2.projection v1'));
flow.snapshot({...reportSnapshot,server_time:1005},'SSE');
assert.equal(elements.health.textContent,'SSE receiving');
assert(text(nodes.webcam).includes('Last report: ready'),'fresh Game SSE cannot revive old Board health');
assert(text(elements.details).includes('Historical report; not live'));
assert(text(nodes.board).includes('Not used · virtual play'));
flow.snapshot({...reportSnapshot,virtual_play:false,server_time:1005},'SSE');
assert(text(nodes.board).includes('Last Game report'));
flow.snapshot(reportSnapshot,'SSE');
flow.assets({requested:2,pending:1,loaded:1,failed:0,last_url:'/s/gamemaster/p/content-owner/assets/test.png'});
assert.equal(particles.filter(p=>p.dataset.active==='true').length,2);
nodes.files.onclick();
assert(text(elements.details).includes('/s/gamemaster/p/content-owner/assets'));
assert(text(elements.details).includes('1 loaded · 1 pending'));
flow.assets({requested:2,pending:0,loaded:1,failed:1,last_error:'fixture asset missing'});
assert(text(elements.details).includes('fixture asset missing'));
flow.connection('reconnecting','fixture stream disconnected');
assert(!particles.find(p=>p.attrs.class.includes('live')).dataset.active.includes('true'));
assert(text(nodes.y).includes('last-known'));
nodes.game.onclick();assert(text(elements.details).includes('fixture stream disconnected'));
flow.connection('open');
assert.equal(particles.find(p=>p.attrs.class.includes('live')).dataset.active,'false','reconnect needs a new event');
flow.snapshot(snapshot,'SSE');
assert.equal(elements.health.textContent,'SSE receiving');
clock+=4000;for(const fn of timers)fn();
assert(!particles.some(p=>p.dataset.active==='true'));
assert(text(elements.health).includes('stale'));
flow.snapshot({...snapshot,version:3},'SSE');
assert(text(elements.details).includes('Incompatible Game output'));
elements.motionButton.onclick();assert(elements.dialog.classes.has('df-still'));
assert.equal(elements.motionButton.textContent,'Resume motion');
elements.motionButton.onclick();assert(!elements.dialog.classes.has('df-still'));
graphWidth=1480;resize();
assert(all(elements.graph).filter(n=>n.tag==='path'&&n.attrs.class?.startsWith('df-wire')).every(n=>!n.attrs.d.includes('NaN')));
elements.closeButton.onclick();assert.equal(timers.size,0);assert(elements.openButton.focused);
elements.openButton.onclick();assert.equal(timers.size,1);flow.destroy();assert.equal(timers.size,0);
console.log('Diagram topology, sources, statuses, activity, stale recovery, reduced-motion control and cleanup passed.');
