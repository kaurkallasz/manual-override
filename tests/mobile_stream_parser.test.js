const assert=require('node:assert/strict');
const {FetchEventSource}=require('../sandboxes/green/prototypes/mobile-ltz/network.js');
(async()=>{
 const frames=[];let requestOptions;
 const wire=new TextEncoder().encode(': heartbeat\r\ndata: {"name":"🧟"}\r\n\r\nevent: update\ndata: {"a":\ndata: 1}\n\ndata: {"truncated":');
 global.fetch=async(url,options)=>{
  requestOptions=options;
  return new Response(new ReadableStream({start(controller){for(let i=0;i<wire.length;i+=3)controller.enqueue(wire.slice(i,i+3));controller.close();}}),{headers:{'Content-Type':'text/event-stream'}});
 };
 await new Promise(resolve=>{
  const source=new FetchEventSource('https://example.test/live/events?token=fixture');
  source.onmessage=e=>frames.push(JSON.parse(e.data));
  source.addEventListener('update',e=>frames.push(JSON.parse(e.data)));
  source.onerror=()=>{source.close();resolve();};
 });
 assert.deepEqual(frames,[{name:'🧟'},{a:1}]);
 assert.equal(requestOptions.headers['ngrok-skip-browser-warning'],'1');
 assert.equal(requestOptions.credentials,'omit');
 assert.ok(requestOptions.signal.aborted);
 let badEvents=0;
 global.fetch=async()=>new Response('<html>warning</html>',{headers:{'Content-Type':'text/html'}});
 await new Promise(resolve=>{const source=new FetchEventSource('https://example.test/live/events');source.onmessage=()=>badEvents++;source.onerror=()=>{source.close();resolve();};});
 assert.equal(badEvents,0);
 console.log('Streaming UTF-8, split/CRLF/multiline events, truncated tails, HTML rejection and cancellation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
