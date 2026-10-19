import {CameraStudioClient} from './camera-client.js';
import {AI_RANGES, validAISettings, validAISnapshot, overlayBoxes, drawBoxes} from './ai-overlay.js';
import './firmware.js';
const hubClient = new CameraStudioClient(new URL('./',location.href).pathname);
let events = null, lastAIStamp = 0, lastControlId = 0;
const $ = id => document.getElementById(id);
const definitions = [
  ['Exposure', 'LIGHT & MOTION', [
    ['aec','Auto exposure','toggle'],['ae_level','Exposure compensation','range',-5,5,'Active with auto exposure.'],
    ['aec_value','Manual exposure','range',1,1000,'Sensor row periods; the duration depends on the capture mode.'],
    ['agc','Auto gain','toggle'],['agc_gain','Manual gain','range',1,64,'Higher gain brightens the image and adds noise.'],
    ['aec2','Night mode','toggle',0,1,'Allows longer exposure in darkness and may reduce frame rate.']]],
  ['Colour & tone', 'WHITE BALANCE', [
    ['brightness','Brightness','range',-3,3],['contrast','Contrast','range',-3,3],['saturation','Saturation','range',-4,4],
    ['awb','White-balance processing','toggle'],['wb_mode','White balance','select',['Auto','Sunny','Cloudy','Office / fluorescent','Home / incandescent']],
    ['special_effect','Colour effect','select',['None','Negative','Grayscale','Red tint','Green tint','Blue tint','Sepia']]]],
  ['Detail & correction', 'SENSOR PROCESSING', [
    ['sharpness','Sharpness','range',-3,3],['denoise','Noise reduction','range',0,8,'0 disables denoising.'],
    ['raw_gma','Gamma correction','toggle'],['lenc','Lens-shading correction','toggle'],
    ['bpc','Black-pixel correction','toggle'],['wpc','White-pixel correction','toggle']]],
  ['Orientation & output', 'FRAME SETTINGS', [
    ['hmirror','Horizontal mirror','toggle'],['vflip','Vertical flip','toggle'],
    ['quality','JPEG compression','range',8,63,'Lower = more detail / larger frames. Higher = less USB traffic.'],
    ['colorbar','Sensor colour bars','toggle',0,1,'Replaces the scene with a test pattern.']]]
];
const inputs = new Map();
let values = null, busy = false, stream = null, videoBusy = false, lastFrameAt = 0, firmwareBusy = false;
let port = null, connecting = false;
let aiData=null, aiAvailable=false, aiReceivedAt=0, aiTransitMs=0;
const aiInputs=new Map();
const presetKey = 'hhh:mcam1:preset-v1';
let recording = null, recordTimer = null, recordStream = null, sharedFrame = null;
let hasPreset = false;
try { hasPreset = !!localStorage.getItem(presetKey); } catch { /* Storage can be disabled. */ }
function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }

function controlsEnabled() {
  const enabled = !!values && !!port && !busy && !connecting && !firmwareBusy;
  for (const [name, input] of inputs) {
    input.disabled = !enabled || (name === 'aec_value' && values.aec === 1) ||
      (name === 'ae_level' && values.aec === 0) || (name === 'agc_gain' && values.agc === 1) ||
      (name === 'wb_mode' && values.awb === 0);
  }
  for (const id of ['refresh','savePreset','defaults']) $(id).disabled = !enabled;
  $('loadPreset').disabled = !enabled || !hasPreset;
  $('connect').disabled = busy || connecting || firmwareBusy;
  $('aiEnabled').disabled = $('aiDefaults').disabled = !enabled || !aiAvailable;
  for (const input of aiInputs.values()) input.disabled = !enabled || !aiAvailable;
  videoButtons();
}
function videoButtons() {
  $('preview').disabled = videoBusy || firmwareBusy;
  $('camera').disabled = true; $('mode').disabled = videoBusy || firmwareBusy;
  $('recover').disabled = videoBusy || connecting || busy || firmwareBusy;
}
for (const [title, subtitle, defs] of definitions) {
  const details = document.createElement('details'); details.className = 'group'; details.open = title === 'Exposure' || title === 'Colour & tone';
  const summary = document.createElement('summary');
  const text = document.createElement('span'); text.textContent = title;
  const small = document.createElement('small'); small.textContent = subtitle; text.append(small); summary.append(text); details.append(summary);
  const fieldset = document.createElement('fieldset'); fieldset.setAttribute('aria-label', title);
  for (const [name,label,type,min,max,hint] of defs) {
    const row = document.createElement('div'); row.className = `control ${type}`;
    const top = document.createElement('div'); top.className = 'control-top';
    const lab = document.createElement('label'); lab.htmlFor = name; lab.textContent = label; top.append(lab);
    const input = document.createElement(type === 'select' ? 'select' : 'input'); input.id = name; input.disabled = true;
    if (type === 'toggle') { input.type = 'checkbox'; input.className = 'switch'; top.append(input); }
    else if (type === 'range') {
      input.type = 'range'; input.min = min; input.max = max; input.step = 1; input.value = Math.max(min,0);
      const output = document.createElement('output'); output.id = `${name}-value`; output.htmlFor = name; output.textContent = '—'; top.append(output);
      input.addEventListener('input', () => { output.textContent = input.value; });
    } else { min.forEach((name,index) => input.add(new Option(name,index))); }
    row.append(top); if (type !== 'toggle') row.append(input);
    if (hint) { const p = document.createElement('p'); p.className = 'hint'; p.id = `${name}-hint`; p.textContent = hint; input.setAttribute('aria-describedby',p.id); row.append(p); }
    input.addEventListener('change', () => applyControl(name, type === 'toggle' ? Number(input.checked) : Number(input.value)));
    inputs.set(name,input); fieldset.append(row);
  }
  details.append(fieldset); $('groups').append(details);
}
function render(data) {
  if (data.protocol !== 1 || data.sensor !== 'OV3660' || !data.values) throw new Error('This camera needs the controls-v1 firmware.');
  values = data.values;
  if (Number.isInteger(data.exposure_max) && data.exposure_max > 0) inputs.get('aec_value').max = data.exposure_max;
  for (const [name,input] of inputs) {
    if (!Number.isInteger(values[name])) throw new Error(`Camera did not report ${name}.`);
    if (input.type === 'checkbox') input.checked = !!values[name];
    else { input.value = values[name]; const output = $(`${name}-value`); if (output) output.textContent = values[name]; }
  }
  $('firmware').textContent = `${data.sensor} · ${data.fw}`;
  $('connection').textContent = 'USB controls connected'; $('connection').classList.add('connected');
  controlsEnabled();
}
function command(action, namespace='ctrl') {
  const [op,name,value] = action.split(' ');
  return hubClient[namespace==='ai'?'ai':'control'](op,name,value === undefined ? undefined : Number(value));
}
function markDisconnected() {
  clearAI(); aiAvailable=false; aiStatus('Connect USB controls to check for AI firmware.');
  values = null; $('connection').textContent = 'Controls disconnected'; $('connection').classList.remove('connected');
  $('connect').innerHTML = 'Connect USB controls <span>↗</span>'; $('firmware').textContent = 'Awaiting camera';
  for (const [name] of inputs) { const output = $(`${name}-value`); if(output) output.textContent = '—'; }
  controlsEnabled();
}
async function disconnect() {
  try { await hubClient.disconnect(); }
  finally { port = null; markDisconnected(); }
}
$('connect').addEventListener('click',async () => {
  connecting = true; controlsEnabled();
  try {
    if (port) { await disconnect(); message('USB controls disconnected.'); return; }
    const data = await command('get'); port = {bridge:true}; render(data);
    $('connect').textContent = 'Disconnect USB controls';
    await probeAI();
    message('XIAO sensor controls connected. Changes are confirmed by the camera.');
  } catch (error) { port = null; markDisconnected(); message(error.message,true); }
  finally { connecting = false; controlsEnabled(); }
});
async function action(fn, success) {
  if (busy || !values || !port || firmwareBusy) return;
  busy = true; controlsEnabled();
  try { await fn(); message(success); }
  catch (error) {
    message(error.message,true);
    try { render(await command('get')); } catch { await disconnect(); }
  } finally { busy = false; controlsEnabled(); }
}
function applyControl(name,value) { return action(async () => { clearAI(); render(await command(`set ${name} ${value}`)); },`${document.querySelector(`label[for="${name}"]`).textContent} applied.`); }
$('refresh').addEventListener('click',() => action(async () => { render(await command('get')); await probeAI(); },'Read current settings from the camera.'));
$('defaults').addEventListener('click',() => action(async () => { clearAI(); render(await command('reset')); },'Image settings reset to firmware defaults.'));
$('savePreset').addEventListener('click',() => {
  try { localStorage.setItem(presetKey,JSON.stringify({version:1,sensor:'OV3660',values,ai:aiAvailable?aiData?.settings:undefined,overlay:$('aiOverlay').checked,labels:$('aiLabels').checked})); hasPreset = true; controlsEnabled(); message('Image and available AI settings saved in this browser. Load after a power cycle to restore.'); }
  catch { message('Browser storage is unavailable. The preset could not be saved.',true); }
});
$('loadPreset').addEventListener('click',() => action(async () => {
  clearAI();
  const preset = JSON.parse(localStorage.getItem(presetKey));
  if (preset?.version !== 1 || preset.sensor !== 'OV3660' || !preset.values) throw new Error('Saved preset is not compatible.');
  const v = preset.values;
  if (preset.ai && (!validAISettings(preset.ai) || !aiAvailable)) throw new Error('This preset needs compatible ai-v1 firmware and valid AI settings.');
  for (const [name,input] of inputs) {
    if (!Number.isInteger(v[name])) throw new Error(`Invalid preset value: ${name}`);
    const min = input.type === 'range' ? Number(input.min) : 0;
    const max = input.type === 'range' ? Number(input.max) : input.type === 'checkbox' ? 1 : input.options.length-1;
    if (!((name === 'aec_value' && v.aec) || (name === 'agc_gain' && v.agc)) && (v[name] < min || v[name] > max)) throw new Error(`Preset ${name} is outside this mode’s range. Switch to the saved capture mode first.`);
  }
  // Auto modes first; manual values only make sense with automatic control off.
  const order = ['aec','agc','awb',...Array.from(inputs.keys()).filter(n => !['aec','agc','awb'].includes(n))];
  for (const name of order) {
    if ((name === 'aec_value' && v.aec) || (name === 'agc_gain' && v.agc)) continue;
    render(await command(`set ${name} ${v[name]}`));
  }
  if (preset.ai) for (const [name,value] of Object.entries(preset.ai)) await setAI(name,value);
  if (typeof preset.overlay==='boolean') $('aiOverlay').checked=preset.overlay;
  if (typeof preset.labels==='boolean') $('aiLabels').checked=preset.labels;
},'Saved preset applied to the camera.'));
function clearPreview() {
  clearAI(); stopRecording();
  stream = null; sharedFrame = null;
  $('sharedPreview').removeAttribute('src'); $('sharedPreview').hidden = true;
  $('placeholder').hidden = false; $('preview').textContent = 'Start preview'; $('videoState').textContent = 'PREVIEW OFF';
  $('liveDot').style.background = ''; $('snapshot').disabled = $('record').disabled = $('fullscreen').disabled = true;
  $('cadence').textContent = 'Waiting for frames'; $('frameSize').textContent = '— × —';
}
async function capture(action) {
  return hubClient.json('/api/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,mode:$('mode').value})},true);
}
async function startPreview() {
  if(videoBusy || firmwareBusy) return;
  videoBusy=true; videoButtons(); clearPreview();
  message('Connecting XIAO video… First use builds the native capture helper.');
  try { await capture('start'); message('Waiting for XIAO video frames…'); }
  catch(error) { message(error.message,true); }
  finally {videoBusy=false;videoButtons();}
}
$('preview').addEventListener('click',async()=>{
  if(!stream) return startPreview();
  videoBusy=true;videoButtons();
  try {await capture('stop');clearPreview();message('XIAO preview stopped.');}
  catch(error) {message(error.message,true);}
  finally {videoBusy=false;videoButtons();}
});
$('mode').addEventListener('change',()=>{if(stream) void startPreview();});
$('recover').addEventListener('click',()=>startPreview());
function subscribe() {
  if(events || document.hidden) return;
  events=new EventSource(`${hubClient.base}/api/events`);
  events.onmessage=event=>{
    const data=JSON.parse(event.data), camera=data.camera;
    if(firmwareBusy!==!!data.firmware_busy) {
      firmwareBusy=!!data.firmware_busy;
      if(firmwareBusy) {clearPreview();port=null;markDisconnected();message('Firmware flashing in progress. Camera controls are paused.');}
      controlsEnabled();
    }
    if(camera.status==='ready' && camera.preview) {
      const wasLive=!!stream, changed=sharedFrame?.frame_id!==camera.frame_id;
      sharedFrame=camera; stream={hub:true}; lastFrameAt=performance.now();
      $('sharedPreview').hidden=false;
      if(changed) $('sharedPreview').src=camera.preview;
      $('placeholder').hidden=true; $('preview').textContent='Stop preview';
      $('snapshot').disabled=$('record').disabled=$('fullscreen').disabled=false;
      $('frameSize').textContent=`${camera.width} × ${camera.height}`;
      $('cadence').textContent=`${camera.fps.toFixed(1)} fps captured · ${camera.target_fps} fps target`;
      $('videoState').textContent='LIVE';$('liveDot').style.background='var(--green)';
      if(!videoBusy) $('mode').value=camera.mode;
      if(!wasLive) {
        message('XIAO preview is live.');
        if(port && !busy && !connecting) void action(async()=>render(await command('get')),'XIAO preview and sensor controls are ready.');
      }
    } else {
      if(stream) clearPreview();
      $('cadence').textContent=camera.error || 'Camera unavailable';
      $('videoState').textContent=camera.running?'CONNECTING':'PREVIEW OFF';
    }
    if(data.controls?.status==='ready' && data.controls.id!==lastControlId && !busy && !connecting) {
      lastControlId=data.controls.id;port={bridge:true};render(data.controls);$('connect').textContent='Disconnect USB controls';
    } else if(!data.controls && port && !busy && !connecting) {port=null;markDisconnected();}
    if(data.ai?.transport_status==='ready' && data.ai.received_at!==lastAIStamp && !busy && !connecting) {
      lastAIStamp=data.ai.received_at;renderAI(data.ai);
    } else if(data.ai?.error && data.ai.transport_status!=='ready') {clearAI();aiAvailable=false;aiStatus(data.ai.error,true);controlsEnabled();}
  };
  events.onerror=()=>{clearPreview();message('MCAM1 connection lost. Reconnecting to the hub…',true);};
}
$('sharedPreview').addEventListener('error',()=>{clearPreview();message('The preview image could not be decoded.',true);});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden && !recording) {events?.close();events=null;clearPreview();}
  else subscribe();
});
window.addEventListener('pagehide',()=>{events?.close();events=null;clearPreview();});
subscribe();videoButtons();
$('fullscreen').addEventListener('click',() => $('sharedPreview').parentElement.requestFullscreen().catch(e => message(e.message,true)));
function download(blob,extension) {
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url;
  a.download = `xiao-${new Date().toISOString().replaceAll(':','-')}.${extension}`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
}
$('snapshot').addEventListener('click',async () => {
    try {
      const still = await hubClient.captureStill();
      if ($('aiOverlay').checked && aiAvailable) {
        const image=await createImageBitmap(still.blob);
        const canvas=document.createElement('canvas'); canvas.width=still.width; canvas.height=still.height;
        const context=canvas.getContext('2d'); context.drawImage(image,0,0); image.close();
        paintDetections(context,canvas.width,canvas.height);
        const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
        if (!blob) throw new Error('Could not encode the annotated still.');
        download(blob,'png');
      } else download(still.blob,'jpg');
      message(`Captured ${still.width} × ${still.height} still · frame ${still.frameId}.`);
    }
    catch(error) { message(error.message,true); }
});
setInterval(()=>{
  if(stream && performance.now()-lastFrameAt>2000) {clearPreview();message('No fresh video frames. Reconnect the camera.',true);}
},1000);

function stopRecording() {
  if (recording && recording.state !== 'inactive') recording.stop();
  clearInterval(recordTimer); recordTimer = null;
  recordStream?.getTracks().forEach(t => t.stop()); recordStream = null;
  $('record').textContent = 'Record video'; $('record').classList.remove('recording');
}
$('record').addEventListener('click',() => {
  if(recording) { stopRecording(); message('Recording stopped. Saving the video download.'); return; }
  if(!stream) return;
  if(!window.MediaRecorder) { message('Video recording is unavailable in this browser.',true); return; }
  try {
    const canvas = document.createElement('canvas');
    canvas.width = sharedFrame.width;
    canvas.height = sharedFrame.height;
    if (!canvas.width || !canvas.height) throw new Error('Wait for a video frame before recording.');
    const context = canvas.getContext('2d');
    const draw = () => {
      context.drawImage($('sharedPreview'),0,0,canvas.width,canvas.height);
      paintDetections(context,canvas.width,canvas.height);
    };
    draw(); const source = canvas.captureStream(30); recordStream = source;
    recordTimer = setInterval(()=>{try {draw();} catch(error) {stopRecording();message(error.message,true);}},1000/30);
    const mimeType = ['video/webm;codecs=vp8','video/webm','video/mp4'].find(t => MediaRecorder.isTypeSupported(t));
    if(!mimeType) throw new Error('No supported video recording format.');
    const chunks = []; let total = 0, recordingStarted = performance.now();
    recording = new MediaRecorder(source,{mimeType,videoBitsPerSecond:2500000});
    recording.ondataavailable = event => {
      if(event.data.size) { chunks.push(event.data); total += event.data.size; }
      if(total > 128*1024*1024 || performance.now()-recordingStarted > 5*60*1000) { stopRecording(); message('Recording saved at the five-minute / 128 MB limit.'); }
    };
    recording.onstop = () => { const blob = new Blob(chunks,{type:mimeType}); recording = null; if(blob.size) download(blob,mimeType.includes('mp4')?'mp4':'webm'); };
    recording.onerror = event => { stopRecording(); message(event.error?.message || 'Recording failed.',true); };
    recording.start(1000); $('record').textContent = 'Stop & save video'; $('record').classList.add('recording');
    message('Recording locally. Stop to save the video (maximum five minutes / 128 MB).');
  } catch(error) { stopRecording(); recording = null; message(error.message,true); }
});

function aiStatus(text,error=false) { $('aiStatus').textContent=text; $('aiStatus').classList.toggle('error',error); }
function clearAI() {
  aiReceivedAt=NaN;
  const canvas=$('aiOverlayCanvas'); canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height); canvas.hidden=true;
}
function renderAI(data,transitMs=0) {
  if (!validAISnapshot(data)) throw new Error('Invalid on-device detection reply.');
  aiData=data; aiAvailable=true; aiReceivedAt=performance.now(); aiTransitMs=transitMs;
  $('aiModel').textContent=data.model;
  $('aiEnabled').checked=!!data.settings.enabled;
  for (const [name,input] of aiInputs) {
    if (document.activeElement!==input) { input.value=data.settings[name]; $(`ai-${name}-value`).textContent=data.settings[name]; }
  }
  const states={disabled:'Detection paused on device.',loading:'Loading model on ESP32-S3…',
    waiting_for_video:'Start a camera preview to supply frames to the on-device model.',
    waiting_for_detection:'Waiting for a fresh on-device detection.',ready:`${data.boxes.length} detections · ${data.class_name} · inference on ESP32-S3`,
    error:`On-device AI unavailable: ${String(data.error || 'unknown error').replaceAll('_',' ')}`};
  aiStatus(states[data.state],data.state==='error');
  $('aiTiming').textContent=data.frame_seq ? `${data.inference_ms} ms inference · ${data.decode_ms} ms JPEG decode · ${data.age_ms} ms result age · ${data.processed} frames analysed` : 'Waiting for device measurements.';
  controlsEnabled();
}
async function probeAI() {
  const started=performance.now();
  try { renderAI(await command('get','ai'),performance.now()-started); }
  catch(error) { aiAvailable=false; aiData=null; clearAI(); aiStatus(error.message,true); controlsEnabled(); }
}
async function setAI(name,value) {
  clearAI(); const started=performance.now();
  renderAI(await command(`set ${name} ${value}`,'ai'),performance.now()-started);
}
for (const [name,label,hint] of [
  ['confidence','Confidence threshold (%)','Higher values reject uncertain detections.'],
  ['nms','Overlap threshold (%)','Lower values suppress more overlapping boxes.'],
  ['max_fps','Maximum detections per second','A rate limit, not a guaranteed inference speed.'],
  ['max_boxes','Maximum detections shown','The detection protocol supports up to ten result boxes.'],
  ['stale_ms','Hide results older than (ms)','Includes capture, decoding, inference and reply age.']
]) {
  const row=document.createElement('div'); row.className='control';
  const top=document.createElement('div'); top.className='control-top';
  const lab=document.createElement('label'); lab.htmlFor=`ai-${name}`; lab.textContent=label;
  const output=document.createElement('output'); output.id=`ai-${name}-value`; output.textContent='—';
  const input=document.createElement('input'); input.id=`ai-${name}`; input.type='range';
  [input.min,input.max]=AI_RANGES[name]; input.step=name==='stale_ms'?100:1; input.disabled=true;
  input.setAttribute('aria-describedby',`ai-${name}-hint`);
  const detail=document.createElement('p'); detail.className='hint'; detail.id=`ai-${name}-hint`; detail.textContent=hint;
  input.addEventListener('input',()=>{output.textContent=input.value;});
  input.addEventListener('change',()=>action(()=>setAI(name,Number(input.value)),`${label} applied on the ESP32-S3.`));
  top.append(lab,output); row.append(top,input,detail); $('aiSettings').append(row); aiInputs.set(name,input);
}
$('aiEnabled').addEventListener('change',()=>action(()=>setAI('enabled',Number($('aiEnabled').checked)),'Detection setting applied on the ESP32-S3.'));
$('aiDefaults').addEventListener('click',()=>action(async()=>{clearAI();renderAI(await command('reset','ai'));},'On-device detection settings reset.'));
function paintDetections(context,width,height) {
  if (!$('aiOverlay').checked || !aiAvailable || !stream) return;

  const boxes=overlayBoxes(aiData,{width,height,now:performance.now(),receivedAt:aiReceivedAt,transitMs:aiTransitMs});
  drawBoxes(context,boxes,width,height,$('aiLabels').checked);
}
function paintOverlay() {
  const canvas=$('aiOverlayCanvas');
  const width=sharedFrame?.width, height=sharedFrame?.height;
  if (stream && width && height && $('aiOverlay').checked && aiAvailable) {
    if (canvas.width!==width || canvas.height!==height) {canvas.width=width;canvas.height=height;}
    canvas.hidden=false; const context=canvas.getContext('2d'); context.clearRect(0,0,width,height); paintDetections(context,width,height);
  } else canvas.hidden=true;
  requestAnimationFrame(paintOverlay);
}
requestAnimationFrame(paintOverlay);
