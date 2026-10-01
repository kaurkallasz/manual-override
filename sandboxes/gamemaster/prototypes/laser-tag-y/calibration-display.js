/* Presentation only: mount the target screen published by the calibration owner. */
window.CalibrationDisplay={create(host,root){
 const layer=document.createElement('section');layer.className='calibrationDisplayLayer';layer.hidden=true;
 layer.innerHTML='<iframe id="calibrationDisplay" title="Auto PP Cal 2 targets" tabindex="-1" hidden></iframe><p role="status"></p>';
 host.append(layer);const frame=layer.querySelector('iframe'),message=layer.querySelector('p');
 return {update(state){
  const journey=state.journey,active=journey?.phase==='calibration';layer.hidden=!active;host.classList.toggle('calibrationDisplayActive',active);
  if(!active){frame.removeAttribute('src');frame.hidden=true;return;}
  const display=journey.calibration_display;
  const ready=display?.contract==='hhh.playfield.display'&&Number.isInteger(display.version)&&display.version===1&&display.status==='ready'&&display.path===root+'/p/playfield-areas/screen';
  frame.hidden=!ready;
  const path=ready?display.path+'?presentation=1':null;
  if(ready&&frame.getAttribute('src')!==path)frame.src=path;
  if(!ready)frame.removeAttribute('src');
  message.hidden=ready;message.textContent=journey.error||display?.error||'Loading Auto PP Cal 2 targets…';
 }};
}};
