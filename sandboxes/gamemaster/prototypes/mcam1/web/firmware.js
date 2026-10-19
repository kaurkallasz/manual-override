const $ = id => document.getElementById(id);
const base = new URL('./', location.href).pathname.replace(/\/$/, '');
let state = null, devices = [], stream = null, pending = false, connected = false;
let logText = '', renderedLog = '', renderedBundle = '';
async function json(path, options) {
  const response = await fetch(`${base}/api/firmware/${path}`, {cache:'no-store', ...options});
  const text = await response.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`Firmware request failed (${response.status}). Check the hub connection and upload size.`); }
  if (!response.ok) throw new Error(data.error || `Firmware request failed (${response.status})`);
  return data;
}
const post = data => ({method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
function selectedDevice() { return devices.find(d => d.token === $('fwDevice').value); }
function selectedBundle() { return [state?.builtin, state?.upload].find(b => b?.id === $('fwBundle').value); }
function note(text, error=false) { $('fwActionMessage').textContent=text; $('fwActionMessage').classList.toggle('error',error); }
function enable() {
  const running=state?.job?.status==='running', locked=pending || running || !connected;
  for (const id of ['fwUpload','fwFile','fwBundle','fwRefresh','fwRelease','fwDevice','fwBoard','fwConfirm']) $(id).disabled=locked;
  const target=selectedDevice();
  $('fwFlash').disabled=locked || !!state?.error || !selectedBundle() || !target?.flashable ||
    !$('fwBoard').checked || $('fwConfirm').value!==`XIAO ${target.serial}`;
  $('fwDownloadLog').disabled=!logText;
}
function renderBundle() {
  const b=selectedBundle();
  const signature=JSON.stringify(b || state?.error || null);
  if(signature===renderedBundle) return;
  renderedBundle=signature;
  $('fwBundleInfo').replaceChildren();
  if (!b) { $('fwBundleInfo').textContent=state?.error || 'No validated bundle selected.'; return; }
  const items=[`${b.revision} · ${(b.application_bytes/1048576).toFixed(2)} MiB application`,
    b.ai ? `AI: ${b.ai.model} · classes: ${b.ai.classes.join(', ')}` : 'No AI model declared',
    'ESP32-S3 · OV3660 · 8MB flash / 8MB PSRAM', 'Bootloader + 4 MiB factory partition + application'];
  for (const text of items) { const p=document.createElement('p'); p.textContent=text; $('fwBundleInfo').append(p); }
  const hash=document.createElement('code');hash.textContent=`Application SHA-256: ${b.application_sha256}`;$('fwBundleInfo').append(hash);
}
function render(data) {
  state=data;
  const select=$('fwBundle'), previous=select.value;
  const bundles=[data.builtin,data.upload].filter(Boolean);
  if ([...select.options].map(o=>o.value).join(',')!==bundles.map(b=>b.id).join(',')) {
    select.replaceChildren();
    for (const b of bundles) select.add(new Option(`${b.id==='builtin'?'Bundled':'Uploaded'} ${b.revision}`,b.id));
  }
  if ([...select.options].some(o=>o.value===previous)) select.value=previous;
  renderBundle();
  const job=data.job || {status:'idle'}, running=job.status==='running';
  $('fwStatus').textContent=data.error ? 'Utility unavailable' : running ? 'USB RESERVED · FLASHING' : 'READY · ESPTOOL 5.4';
  $('fwProgress').hidden=!running;
  const names={idle:'No flash job started',running:`${job.phase || 'Starting'} · ${job.revision} → ${job.target?.serial}`,
    done:`Flash verified · ${job.revision} → ${job.target?.serial}`,error:`Flash failed · ${job.target?.serial || ''}`};
  $('fwJobStatus').textContent=names[job.status] || 'Firmware state unavailable';
  logText=(job.log || []).join('\n');
  if (logText!==renderedLog) {
    renderedLog=logText;$('fwLog').textContent=logText || 'The flash log will appear here.';
    $('fwLog').scrollTop=$('fwLog').scrollHeight;
  }
  if (data.error) note(data.error,true);
  else if (running) note('Flashing in progress. Keep USB connected and the hub running.');
  else if (job.status==='done') note('Flash verified. Press RESET or replug USB, then reconnect controls and start preview to check camera operation.');
  else if (job.status==='error') note(job.error || 'Flash failed. Re-enter download mode and retry.',true);
  enable();
}
function targetChanged() {
  $('fwConfirm').value='';$('fwBoard').checked=false;
  const target=selectedDevice();
  $('fwConfirmation').textContent=target ? `XIAO ${target.serial}` : 'Select a device first';
  $('fwDeviceInfo').textContent=target ? `${target.description} · ${target.port} · USB ${target.serial}. ${target.flashable ? 'ESP USB serial/JTAG port; verify the physical XIAO board and enter download mode.' : 'Camera firmware is running. Enter BOOT + RESET, then refresh and select its new port.'}` : 'USB identity alone cannot distinguish an Atom from a XIAO. Select the physical camera you put in download mode.';
  enable();
}
async function refreshDevices() {
  const data=await json('devices');devices=data.devices;
  const previous=$('fwDevice').value;$('fwDevice').replaceChildren(new Option('Choose a USB device…',''));
  for (const d of devices) $('fwDevice').add(new Option(`${d.description} · ${d.serial}${d.flashable?'':' · enter download mode'}`,d.token));
  if (devices.some(d=>d.token===previous)) $('fwDevice').value=previous;
  else targetChanged();
  if (!devices.length) note('No ESP USB devices found on the hub. Connect the XIAO and refresh.');
  enable();
}
async function action(fn) {
  if (pending) return;
  pending=true;enable();
  try { await fn(); } catch(error) {note(error.message,true);}
  finally {pending=false;enable();}
}
$('fwBundle').addEventListener('change',()=>{renderBundle();enable();});
$('fwDevice').addEventListener('change',targetChanged);
for (const id of ['fwConfirm','fwBoard']) $(id).addEventListener('input',enable);
$('fwRefresh').addEventListener('click',()=>action(refreshDevices));
$('fwUpload').addEventListener('click',()=>action(async()=>{
  const file=$('fwFile').files[0];
  if (!file || !file.name.toLowerCase().endsWith('.zip')) throw new Error('Choose a complete firmware ZIP. Raw model and .bin files need packaging first.');
  if (file.size>32*1048576) throw new Error('Firmware ZIP exceeds 32 MiB.');
  $('fwUploadMessage').textContent='Checking images, hashes and partition layout…';
  const form=new FormData();form.append('bundle',file);
  try {
    const upload=await json('upload',{method:'POST',body:form});
    render({...state,upload});$('fwBundle').value=upload.id;renderBundle();
    $('fwUploadMessage').textContent=`Validated ${upload.revision}. Ready to select a target; nothing flashed.`;
    note('Upload validated. Select and confirm the camera to install it.');
  } catch(error) { $('fwUploadMessage').textContent=error.message;throw error; }
}));
$('fwRelease').addEventListener('click',()=>action(async()=>{
  for (const [path,data] of [['capture',{action:'stop'}],['disconnect',{}]]) {
    const response=await fetch(`${base}/api/${path}`,post(data));
    if(!response.ok) {const result=await response.json();throw new Error(result.error || 'Could not release camera');}
  }
  note('Camera USB released. Put the target in BOOT + RESET download mode, then refresh devices.');
}));
$('fwFlash').addEventListener('click',()=>action(async()=>{
  const data=await json('flash',post({bundle_id:$('fwBundle').value, device_token:$('fwDevice').value, confirmation:$('fwConfirm').value}));
  $('fwConfirm').value='';$('fwBoard').checked=false;render(data);
}));
$('fwDownloadLog').addEventListener('click',()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(state.job,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=`mcam1-flash-${state.job.id || 'log'}.json`;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
function subscribe() {
  if(stream || document.hidden) return;
  stream=new EventSource(`${base}/api/firmware/events`);
  stream.onmessage=event=>{connected=true;render(JSON.parse(event.data));};
  stream.onerror=()=>{connected=false;$('fwStatus').textContent='HUB CONNECTION LOST';note('Connection lost. A server-side flash may still be running; reconnect before retrying.',true);enable();};
}
document.addEventListener('visibilitychange',()=>{
  if(document.hidden) {stream?.close();stream=null;connected=false;enable();}
  else {subscribe();void action(refreshDevices);}
});
window.addEventListener('pagehide',()=>{stream?.close();stream=null;});
subscribe();enable();void action(refreshDevices);
