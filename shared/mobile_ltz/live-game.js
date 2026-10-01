(function(root){
'use strict';
const sceneFields=['level','presentation','settings','loadout','force_field_blockers','row_barrier_geometry','mobile_progress'];
const hasLevel=level=>!!level&&Number.isFinite(+level.width)&&+level.width>0&&Number.isFinite(+level.height)&&+level.height>0&&!!level.paths&&Array.isArray(level.sockets);
const sameScene=(a,b)=>a?.level_revision===b?.level_revision;
class MobileGameState {
  constructor({apply,load,error=()=>{}}){this.apply=apply;this.load=load;this.error=error;this.value=null;this.pending=null;this.retryAt=0;}
  receive(incoming,partial=false){
    if(!incoming||typeof incoming!=='object'||Array.isArray(incoming))throw Error('Invalid game state.');
    const wrapped=incoming.contract==='hub.live';
    if(wrapped){
      if(incoming.version!==1||!['snapshot','update'].includes(incoming.kind)||!incoming.state||typeof incoming.state!=='object'||Array.isArray(incoming.state))throw Error('Invalid live message.');
      partial=incoming.kind==='update';incoming=incoming.state;
      if(incoming.status==='ready'&&(!Object.hasOwn(incoming,'run_id')||!Number.isInteger(incoming.level_revision)))throw Error('Live update is missing its game identity.');
    }
    const previous=this.value;
    // A relay may lose an SSE event label. An unidentified legacy delta
    // cannot replace a known scene; wait for an authoritative snapshot.
    if(!partial&&previous&&incoming.status==='ready'&&!Object.hasOwn(incoming,'level_revision')){this.recover();return previous;}
    if(previous&&Number.isFinite(incoming.server_time)&&incoming.server_time<previous.server_time)return previous;
    if(partial&&(!previous||(wrapped&&(!sameScene(previous,incoming)||previous.run_id!==incoming.run_id)))){this.recover();return previous;}
    const value=partial?{...previous,...incoming}:{...incoming};
    // Keep published scene data across ordinary updates, including relays
    // that deliver an update as a plain message. Never reuse another map.
    if(previous&&sameScene(previous,value)){
      for(const key of sceneFields)if(!Object.hasOwn(incoming,key))value[key]=previous[key];
    }else if(partial&&!Object.hasOwn(incoming,'level')){
      for(const key of sceneFields)delete value[key];
    }
    this.value=value;
    this.apply(value);
    if(this.needsLevel())this.recover();
    return value;
  }
  needsLevel(){return this.value?.status==='ready'&&this.value.virtual_play&&!hasLevel(this.value.level);}
  recover(){
    if(this.pending)return this.pending;
    if(Date.now()<this.retryAt)return Promise.resolve();
    const requested=this.value;
    this.pending=Promise.resolve().then(()=>this.load()).then(fresh=>{
      const latest=this.value;
      // A delayed recovery may add geometry to a newer frame of the same
      // run, but must not roll a team back into a previous run or map.
      if(latest&&requested&&(latest.run_id!==requested.run_id||!sameScene(latest,requested)))return;
      if(!fresh||typeof fresh!=='object'||Array.isArray(fresh)||!['ready','unavailable'].includes(fresh.status))throw Error('Invalid recovered game state.');
      if(fresh.status==='ready'&&fresh.virtual_play&&!hasLevel(fresh.level))throw Error('Gamemaster has not published the level yet. Retrying…');
      if(latest&&fresh.server_time<latest.server_time){
        if(fresh.run_id!==latest.run_id||!sameScene(fresh,latest))return;
        const merged={...fresh,...latest};
        for(const key of sceneFields)if(Object.hasOwn(fresh,key)&&latest[key]==null)merged[key]=fresh[key];
        this.value=merged;
      }else this.value=fresh;
      this.apply(this.value);
    }).catch(error=>this.error(error)).finally(()=>{this.pending=null;this.retryAt=Date.now()+2000;});
    return this.pending;
  }
}
MobileGameState.hasLevel=hasLevel;
root.MobileGameState=MobileGameState;
if(typeof module!=='undefined')module.exports=MobileGameState;
})(typeof window==='undefined'?globalThis:window);
