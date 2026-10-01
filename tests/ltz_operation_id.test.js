const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../shared/mobile_ltz/operation-id.js'),'utf8');
test('HTTP browser without randomUUID uses getRandomValues receipts',()=>{
 let calls=0;
 const context=vm.createContext({crypto:{getRandomValues(bytes){bytes.fill(++calls);return bytes;}}});
 vm.runInContext(source,context);
 const first=context.LtzOperationId(),second=context.LtzOperationId();
 assert.notEqual(first,second);assert.match(first,/^ltz:[a-f0-9]{32}$/);assert.equal(calls,2);
});
test('browser without Web Crypto still produces valid distinct operation IDs',()=>{
 for(const crypto of [undefined,{}]){
  const context=vm.createContext({crypto});vm.runInContext(source,context);
  const ids=Array.from({length:1000},()=>context.LtzOperationId());
  assert.equal(new Set(ids).size,1000);assert(ids.every(id=>id.length<=160&&/^[a-zA-Z0-9_:.-]+$/.test(id)));
 }
});
test('native UUID remains supported',()=>{
 const context=vm.createContext({crypto:{randomUUID:()=> 'native-receipt'}});vm.runInContext(source,context);
 assert.equal(context.LtzOperationId(),'native-receipt');
});
