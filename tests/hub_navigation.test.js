const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../hub/dashboard.html'),'utf8');
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/\nload\(\);\s*$/,'');
function fixture(){
  const nodes=new Map(),listeners={},frames=[];
  function node(){return {style:{},children:[],dataset:{},contentWindow:{},listeners:{},
    classList:{toggle(){}},addEventListener(name,fn){this.listeners[name]=fn;},
    appendChild(child){this.children.push(child);},
    replaceWith(next){this.disposed=true;nodes.set(this.id,next);frames.push(next);}};}
  const context=vm.createContext({URL,location:{origin:'http://localhost:8000',href:'http://localhost:8000/s/green/'},
    document:{getElementById(id){if(!nodes.has(id))nodes.set(id,Object.assign(node(),{id}));return nodes.get(id);},createElement:node},
    window:{addEventListener(name,fn){listeners[name]=fn;}},localStorage:{setItem(){},getItem(){return null;}}});
  vm.runInContext(source,context);
  return {nodes,frames,listeners,run:script=>vm.runInContext(script,context)};
}
const prototype=(slug,enabled=true)=>({slug,enabled,description:'',default_url:`/s/green/p/${slug}/`,pages:[]});

test('switching and reload dispose the previous document before loading a fresh frame',()=>{
  const f=fixture(),initial=f.nodes.get('frame');
  f.run(`selectProto(${JSON.stringify(prototype('webcam'))})`);
  assert(initial.disposed);
  const webcam=f.nodes.get('frame');
  f.run(`selectProto(${JSON.stringify(prototype('photon-board'))})`);
  assert(webcam.disposed);
  const board=f.nodes.get('frame');
  assert.match(board.src,/photon-board/);
  f.nodes.get('reload').onclick();
  assert(board.disposed);
  assert.match(f.nodes.get('frame').src,/photon-board/);
  assert.equal(f.frames.length,3);
});

test('disabled modules dispose active streams without loading their page',()=>{
  const f=fixture(),old=f.nodes.get('frame');
  f.run(`selectProto(${JSON.stringify(prototype('webcam',false))})`);
  assert(old.disposed);
  assert.equal(f.nodes.get('frame').style.display,'none');
  assert(!f.nodes.get('frame').src);
});

test('fullscreen messages apply only to the current player frame after replacement',()=>{
  const f=fixture(),old=f.nodes.get('frame');
  f.run(`selectProto(${JSON.stringify(prototype('mobile-ltz'))})`);
  const frame=f.nodes.get('frame');
  const event={origin:'http://localhost:8000',source:old.contentWindow,data:{type:'mobile-ltz:expand',expanded:true}};
  f.listeners.message(event);
  assert(!frame.style.cssText);
  f.listeners.message({...event,source:frame.contentWindow});
  assert.match(frame.style.cssText,/position:fixed/);
  frame.listeners.load();
  assert.equal(frame.style.cssText,'');
});

test('both players default to Mobile LTZ despite old tab links and preferences',()=>{
  for(const team of ['green','purple']){
    const f=fixture();
    f.run(`meta={sandbox:'${team}',admin:false}; location.hash='#ltx'; localStorage.getItem=()=> 'ltx';
      protos=${JSON.stringify([prototype('ltx'),prototype('mobile-ltz'),prototype('ltz-score')])};`);
    assert.equal(f.run('initialProto().slug'),'mobile-ltz');
    assert.equal(f.run('visibleProtos().map(p=>p.slug).join(",")'),'mobile-ltz');
    assert.equal(f.run('protos.every(p=>p.enabled)'),true,'filter never disables dependencies');
    f.run('showOtherPlayerTabs=true');
    assert.equal(f.run('visibleProtos().length'),3);
    assert.equal(f.run('initialProto().slug'),'ltx');
  }
});

test('game master keeps full navigation, including when viewing a team dashboard',()=>{
  const f=fixture();
  f.run(`meta={sandbox:'green',admin:true}; location.hash='#ltx';
    protos=${JSON.stringify([prototype('ltx'),prototype('mobile-ltz')])};`);
  assert.equal(f.run('visibleProtos().length'),2);
  assert.equal(f.run('initialProto().slug'),'ltx');
});

test('missing or disabled Mobile LTZ cannot select another player module by default',()=>{
  const f=fixture();
  f.run(`meta={sandbox:'green',admin:false}; location.hash=''; protos=${JSON.stringify([prototype('ltx')])};`);
  assert.equal(f.run('initialProto()'),undefined);
  f.run(`protos.push(${JSON.stringify(prototype('mobile-ltz',false))})`);
  assert.equal(f.run('initialProto().slug'),'mobile-ltz');
  assert.equal(f.run('initialProto().enabled'),false);
});
