const {test}=require('node:test'),assert=require('node:assert/strict');
const Presence=require('../shared/ltz_ui/marker-presence.js');
test('brief loss retains display only, expiry is measured from the actual sighting',()=>{
 const p=new Presence(),read=(tags,now,extra={})=>p.update(tags,{now,identity:'camera1',ready:true,...extra});
 assert.equal(read([{id:100,seen_at:10,x:.4}],10)[0].visible,true);
 const held=read([],10.7)[0];assert.equal(held.x,.4);assert.equal(held.visible,false);assert.equal(held.recent,true);
 assert.equal(read([{id:100,seen_at:10,x:.4}],10.9).length,1);
 assert.equal(read([],11.01).length,0);
 read([{id:100,seen_at:12}],12);
 assert.equal(read([],12.1,{rejected:[100]}).length,0);
 read([{id:100,seen_at:12.2}],12.2);
 assert.equal(read([],12.3,{identity:'camera2'}).length,0);
 read([{id:100,seen_at:12.4}],12.4);
 assert.equal(read([],12.5,{ready:false}).length,0);
 assert.equal(read([],12.6).length,0);
});
