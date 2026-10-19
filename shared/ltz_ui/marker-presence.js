/* Display continuity only. Never supplies calibration, pickup or buff evidence. */
(function(root){
'use strict';
class LTZMarkerPresence {
 constructor(){this.tags=new Map();this.identity=null;}
 clear(){this.tags.clear();this.identity=null;}
 update(tags,{now,identity,ready,rejected=[]}){
  if(!ready||!Number.isFinite(now)){this.clear();return [];}
  if(identity!==this.identity){this.clear();this.identity=identity;}
  const forbidden=new Set(rejected),visible=new Set();
  for(const id of forbidden)this.tags.delete(id);
  for(const tag of tags){
   if(!Number.isInteger(tag.id)||forbidden.has(tag.id)||!Number.isFinite(tag.seen_at)
      ||now-tag.seen_at < -.25||now-tag.seen_at>1)continue;
   const old=this.tags.get(tag.id);
   if(!old||tag.seen_at>=old.seen_at)this.tags.set(tag.id,{...tag});
   visible.add(tag.id);
  }
  for(const [id,tag] of this.tags)if(now-tag.seen_at>1)this.tags.delete(id);
  return [...this.tags.values()].sort((a,b)=>a.id-b.id)
   .map(tag=>({...tag,visible:visible.has(tag.id),recent:true}));
 }
}
root.LTZMarkerPresence=LTZMarkerPresence;
if(typeof module!=='undefined'&&module.exports)module.exports=LTZMarkerPresence;
})(typeof window==='undefined'?globalThis:window);
