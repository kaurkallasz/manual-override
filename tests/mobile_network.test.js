const assert=require('node:assert/strict');
const {readJson}=require('../sandboxes/green/prototypes/mobile-ltz/network.js');
const response=(body,status=200)=>({status,ok:status<400,text:async()=>body,json(){throw Error('Do not use Safari Response.json');}});
(async()=>{
  assert.deepEqual(await readJson(response('{"status":"ready"}')),{status:'ready'});
  await assert.rejects(readJson(response('<html>Gateway timeout</html>',504)),/invalid response \(HTTP 504\)/);
  await assert.rejects(readJson(response('{"level":')),/invalid response/);
  await assert.rejects(readJson(response('null')),/invalid response/);
  await assert.rejects(readJson(response('[]')),/invalid response/);
  await assert.rejects(readJson(response('{"error":"Session expired"}',409)),/Session expired/);
  await assert.rejects(readJson({status:200,text:async()=>{throw Error('disconnected');}}),/interrupted/);
  console.log('JSON, HTML errors, truncated responses, invalid payloads and disconnect handling passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
