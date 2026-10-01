/* Idempotency receipts, not authentication tokens. Works on HTTP mobile origins. */
(function(root){
 'use strict';
 let sequence=0;
 function operationId(){
  if(typeof root.crypto?.randomUUID==='function')return root.crypto.randomUUID();
  if(typeof root.crypto?.getRandomValues==='function'){
   const bytes=new Uint8Array(16);root.crypto.getRandomValues(bytes);
   return 'ltz:'+Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');
  }
  return `ltz:${Date.now().toString(36)}:${++sequence}:${Math.random().toString(36).slice(2)}:${Math.random().toString(36).slice(2)}`;
 }
 root.LtzOperationId=operationId;
 if(typeof module==='object'&&module.exports)module.exports=operationId;
})(globalThis);
