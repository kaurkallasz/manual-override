/* Saved measurements are owned by Cal 2. This panel only previews camera
   coordinates and forwards an explicit Apply command through Photon Game. */
window.CalibrationHistory={create({root,overlay,image,read,apply,onPreview}){
  const side=root.querySelector('[data-history-side]'),select=root.querySelector('[data-history-select]');
  const preview=root.querySelector('[data-history-preview]'),save=root.querySelector('[data-history-apply]');
  const refresh=root.querySelector('[data-history-refresh]'),status=root.querySelector('[data-history-status]'),cameraNotice=root.querySelector('[data-history-camera]');
  let history=null,show=false,busy=false,loading=false,state=null,generation=0,signature='',lastPhase=null,camera=null,received=0;
  const chosen=()=>history?.rows.find(row=>row.id===(select.value==='latest'?history.latest_id:select.value));
  const date=value=>Number.isFinite(value)?new Date(value*1000).toLocaleString():'Undated';
  function cameraFresh(){
    const now=Date.now()/1000,fresh=value=>Number.isFinite(value)&&now-value>=-.25&&now-value<1.5;
    return camera?.contract==='photon.board.tracking'&&camera.version===1&&camera.status==='ready'&&camera.source==='camera'
      &&camera.coordinate_space==='corrected-camera-normalized'&&fresh(received)&&fresh(camera.sampled_at)&&fresh(camera.frame_at);
  }
  function render(){
    const row=chosen(),ready=!!row?.applicable;
    preview.disabled=loading||!ready;preview.setAttribute('aria-pressed',String(show));
    preview.textContent=show?'Hide preview':'Preview on camera';
    save.disabled=loading||busy||!ready||state?.status!=='ready'||state?.phase==='running';
    side.disabled=select.disabled=refresh.disabled=busy;
    const cameraReady=cameraFresh();
    cameraNotice.hidden=!show||cameraReady&&!image.hidden;
    cameraNotice.textContent='Preview paused · waiting for a fresh corrected camera image.';
    const hidden=loading||!show||!ready||!cameraReady||image.hidden||!image.naturalWidth||!image.naturalHeight;
    overlay.toggleAttribute('hidden',hidden);
    const key=JSON.stringify([hidden,row?.id,side.value,image.naturalWidth,image.naturalHeight]);
    if(key===signature)return;signature=key;overlay.replaceChildren();
    if(hidden)return;
    const w=image.naturalWidth,h=image.naturalHeight,size=Math.max(w,h)/90;
    overlay.setAttribute('viewBox',`0 0 ${w} ${h}`);
    overlay.style.color=side.value==='green'?'#62ffa5':'#d5a2ff';
    const add=(name,attrs,text)=>{const node=document.createElementNS('http://www.w3.org/2000/svg',name);for(const[k,v]of Object.entries(attrs))node.setAttribute(k,String(v));if(text!=null)node.textContent=text;overlay.append(node);return node};
    const stroke={fill:'none',stroke:'currentColor','stroke-width':2,'vector-effect':'non-scaling-stroke'};
    // Stored coordinates are canonical corrected-camera coordinates for BOTH
    // arms. Purple's player viewport rotation must not be applied here.
    for(const point of Object.values(row.draft.points)){
      const x=point.camera.u*w,y=point.camera.v*h;
      add('rect',{...stroke,x:x-size,y:y-size,width:size*2,height:size*2,'data-saved-marker':point.marker});
      add('path',{...stroke,d:`M ${x-size*.5} ${y} H ${x+size*.5} M ${x} ${y-size*.5} V ${y+size*.5}`});
      add('text',{x:x+size*1.3,y:y-size*.6,'font-size':size*1.2},String(point.marker));
    }
    for(const point of Object.values(row.draft.parallax_points)){
      const x=point.raised.u*w,y=point.raised.v*h;
      add('line',{...stroke,x1:point.ground.u*w,y1:point.ground.v*h,x2:x,y2:y,'stroke-dasharray':'4 4'});
      add('circle',{...stroke,cx:x,cy:y,r:size*.65,'stroke-dasharray':'4 3','data-saved-raised':point.marker});
      add('text',{x:x+size,y:y+size*1.8,'font-size':size*.95},`${point.marker} +3 cm`);
    }
  }
  function describe(prefix=''){
    const row=chosen();
    status.textContent=prefix+(row?`${side.options[side.selectedIndex].text} · ${date(row.saved_at)}${row.active?' · Applied':''}. ${row.applicable?'Six square ground targets; four dashed raised-tag points.':row.error}`:'No complete saved calibration available.');
    if(state?.phase==='running')status.textContent+=' End the game before applying.';
  }
  async function reload(reset=false){
    const token=++generation,selection=select.value,team=side.value;loading=true;render();
    try{
      const value=await read(team);
      if(token!==generation)return;
      if(value?.contract!=='hhh.cal2.history'||value.version!==1||value.status!=='ready'||!Array.isArray(value.rows))throw Error(value?.error||'Saved calibration history unavailable');
      history=value;select.replaceChildren(new Option('Latest complete calibration · default','latest'));
      for(const row of value.rows){const option=new Option(`${date(row.saved_at)}${row.active?' · Applied':''}${row.applicable?'':' · Incomplete'}`,row.id);select.append(option)}
      const desired=reset?value.selection:selection;
      select.value=desired==='latest'||value.rows.some(row=>row.id===desired)?desired:'latest';
      signature='';describe();
    }catch(error){if(token!==generation)return;history=null;status.textContent=error.message;}
    finally{if(token===generation){loading=false;render();}}
  }
  side.onchange=()=>reload(true);
  select.onchange=()=>{describe();render()};
  preview.onclick=()=>{show=!show;onPreview();render()};
  refresh.onclick=()=>reload();
  save.onclick=async()=>{
    if(save.disabled)return;busy=true;status.textContent='Applying calibration…';render();
    const value={action:'calibration_apply',side:side.value,id:select.value,expected_revision:history.rig_revision};
    try{await apply(value);await reload();describe('Calibration applied. Reconnect the player controls. ')}
    catch(error){status.textContent=`Calibration not applied: ${error.message}`;}
    finally{busy=false;render()}
  };
  image.addEventListener('load',render);
  return {
    isPreview:()=>show,
    cameraFresh,
    render,
    camera(value){camera=value;received=Date.now()/1000;render()},
    update(value){state=value;const phase=value?.journey?.phase;if(lastPhase==='calibration'&&phase!=='calibration'&&!busy)reload();lastPhase=phase;render()},
    load:()=>reload(true),
    destroy(){generation++;image.removeEventListener('load',render);side.onchange=select.onchange=preview.onclick=refresh.onclick=save.onclick=null;overlay.replaceChildren()},
  };
}};
