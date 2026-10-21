/* Relative video predictions and independently labelled motion distances. */
(function(root){
  'use strict';
  const median=values=>{const v=[...values].sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;};
  function grid(points,width,height,size=12,relative=false){
    const columns=Math.ceil(width/size),rows=Math.ceil(height/size),groups=new Map(),cells=[];
    for(const p of points||[]){
      const distance=relative?p.relative_depth:p.distance_mm??p.depth_mm;
      if(![p.x,p.y,distance].every(Number.isFinite)||p.x<0||p.x>=1||p.y<0||p.y>=1||(relative?(distance<0||distance>1):(distance<20||distance>3000)))continue;
      const x=Math.floor(p.x*width/size),y=Math.floor(p.y*height/size),key=y*columns+x;
      if(!groups.has(key))groups.set(key,{x,y,values:[],views:[]});groups.get(key).values.push(distance);groups.get(key).views.push(Number.isInteger(p.views)?p.views:0);
    }
    for(const group of groups.values()){
      const distance=median(group.values);
      // Do not blend the foreground and background at an object boundary.
      if(Math.max(...group.values)-Math.min(...group.values)>(relative?.25:Math.max(8,distance*.12)))continue;
      cells.push({x:group.x*size,y:group.y*size,width:Math.min(size,width-group.x*size),height:Math.min(size,height-group.y*size),distance,views:Math.min(...group.views)});
    }
    return {cells,columns,rows,size,coverage:cells.length/(columns*rows)};
  }
  function color(distance,near,far){return `hsl(${10+230*Math.max(0,Math.min(1,(distance-near)/(far-near)))} 88% 56%)`;}
  function paint(context,map,width,height,near,far,background=null){
    context.fillStyle='#0a1019';context.fillRect(0,0,width,height);
    if(background){context.save();context.globalAlpha=.35;context.drawImage(background,0,0,width,height);context.restore();}
    context.strokeStyle='#1b2938';context.lineWidth=.5;
    for(let y=0;y<height;y+=map.size)for(let x=0;x<width;x+=map.size)context.strokeRect(x+.5,y+.5,Math.min(map.size,width-x)-1,Math.min(map.size,height-y)-1);
    for(const cell of map.cells){
      const x=cell.x+1,y=cell.y+1,w=cell.width-2,h=cell.height-2;
      context.fillStyle=color(cell.distance,near,far);context.fillRect(x,y,w,h);
      context.fillStyle='#ffffff50';context.fillRect(x,y,w,1.5);context.fillRect(x,y,1,h);
      context.fillStyle='#00000050';context.fillRect(x,y+h-1.5,w,1.5);context.fillRect(x+w-1,y,1,h);
      if(w>=9&&h>=9){context.beginPath();context.ellipse(x+w/2,y+h/2,w*.19,h*.16,0,0,Math.PI*2);context.fillStyle='#ffffff30';context.fill();}
    }
  }
  function relativePoints(data,dw,dh,width,height){
    if(!data||data.length!==dw*dh)return [];
    const samples=Array.from(data).filter(Number.isFinite).sort((a,b)=>a-b);
    if(samples.length<12)return [];
    const low=samples[Math.floor(samples.length*.02)],high=samples[Math.floor(samples.length*.98)];
    if(high-low<1e-6)return [];
    const points=[];
    for(let y=4;y<height;y+=8)for(let x=4;x<width;x+=8){
      const inverse=data[Math.min(dh-1,Math.floor(y/height*dh))*dw+Math.min(dw-1,Math.floor(x/width*dw))];
      if(Number.isFinite(inverse))points.push({x:x/width,y:y/height,inverse,relative_depth:Math.max(0,Math.min(1,(high-inverse)/(high-low)))});
    }
    return points;
  }
  function motionScale(data,dw,dh,anchors){
    // Fit inverse prediction to inverse axial depth on this exact frame only.
    let pairs=(anchors||[]).flatMap(p=>{
      const inverse=data[Math.min(dh-1,Math.max(0,Math.floor(p.y*dh)))*dw+Math.min(dw-1,Math.max(0,Math.floor(p.x*dw)))];
      return Number.isFinite(inverse)&&Number.isFinite(p.depth_mm)&&p.depth_mm>=20&&p.depth_mm<=1200?[[inverse,1/p.depth_mm]]:[];
    });
    if(pairs.length<20)return null;
    const fit=rows=>{const mx=rows.reduce((s,p)=>s+p[0],0)/rows.length,my=rows.reduce((s,p)=>s+p[1],0)/rows.length;
      let xx=0,xy=0;for(const [x,y]of rows){xx+=(x-mx)**2;xy+=(x-mx)*(y-my);}const slope=xy/xx;return {slope,offset:my-slope*mx};};
    let line=fit(pairs);
    for(let i=0;i<2;i++){
      const residuals=pairs.map(([x,y])=>Math.abs((line.slope*x+line.offset-y)/y));
      const cutoff=Math.max(.08,median(residuals)*2.5);
      pairs=pairs.filter((_,j)=>residuals[j]<=cutoff);if(pairs.length<20)return null;line=fit(pairs);
    }
    const ys=pairs.map(p=>p[1]),xs=pairs.map(p=>p[0]),spread=Math.max(...ys)-Math.min(...ys);
    const error=median(pairs.map(([x,y])=>Math.abs((line.slope*x+line.offset-y)/y)));
    if(!Number.isFinite(line.slope)||line.slope<=0||spread<median(ys)*.12||error>.15||pairs.length<(anchors?.length||0)*.6)return null;
    return {...line,min:Math.min(...xs),max:Math.max(...xs),anchors:pairs.length,error};
  }
  async function workerMain(forceCPU=false){
    let estimator=null, RawImage=null,processing=false;
    const report=message=>self.postMessage(message);
    try{
      const runtime=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/transformers.min.js');
      RawImage=runtime.RawImage;runtime.env.allowLocalModels=false;
      runtime.env.backends.onnx.wasm.numThreads=1;
      const options={revision:'4472b7362082ad9968fee890ca0f1e5aca36b93d',progress_callback:p=>{if(p.status==='progress')report({type:'loading',progress:Math.round(p.progress||0)});}};
      let gpu=false;try{gpu=!forceCPU&&!!(await navigator.gpu?.requestAdapter());}catch{}
      report({type:'loading',progress:0});
      try{estimator=await runtime.pipeline('depth-estimation','onnx-community/depth-anything-v2-small',{...options,device:gpu?'webgpu':'wasm',dtype:gpu?'fp32':'q8'});}
      catch(error){if(!gpu)throw error;estimator=await runtime.pipeline('depth-estimation','onnx-community/depth-anything-v2-small',{...options,device:'wasm',dtype:'q8'});gpu=false;}
      // 294 is a multiple of the model's 14-pixel patch size, suitable for MCAM1.
      estimator.processor.image_processor.size={width:294,height:294};
      report({type:'ready',device:gpu?'GPU':'CPU'});
    }catch(error){report({type:'error',error:'Video depth could not load: '+error.message});return;}
    self.onmessage=async({data:job})=>{
      if(processing){report({type:'busy',id:job.id});return;}processing=true;
      try{
        const result=await estimator(await RawImage.read(job.preview));
        const tensor=result.predicted_depth,dims=tensor.dims,values=Float32Array.from(tensor.data);
        self.postMessage({type:'result',id:job.id,width:dims.at(-1),height:dims.at(-2),values},[values.buffer]);
      }catch(error){report({type:'error',id:job.id,error:'Video depth failed: '+error.message});}
      finally{processing=false;}
    };
  }
  root.DepthBricks={grid,color,paint,relativePoints,motionScale,workerMain};
  if(typeof module!=='undefined')module.exports=root.DepthBricks;
})(typeof window==='undefined'?globalThis:window);

(() => {
  'use strict';
  if(typeof document==='undefined')return;
  const $=id=>document.getElementById(id), canvas=$('video'), context=canvas.getContext('2d');
  let state=null, draft=null, dirty=false, select=null, dragging=null, lastEvent=0, stream=null, imageKey='', generation=0, image=null;
  let brickMap=null, near=30, far=300, lastMeasured=null, travelSamples=[];
  let videoEnabled=true, autoStarted=false, worker=null, workerURL=null, workerReady=false, busy=false, pending=null, aiFrame=null, jobId=0, queuedKey='';
  let workerInfo='Video depth starts automatically from the MCAM1 feed.', loadTimer=null;
  const fields={horizontal_fov_deg:'fov',frame_delay_ms:'delay',timing_uncertainty_ms:'uncertainty',min_baseline_mm:'baseline'};
  const vectors={camera_offset_mm:['cameraX','cameraY','cameraZ'],contact_offset_mm:['contactX','contactY','contactZ'],mount_rpy_deg:['roll','pitch','yaw']};
  const checks={follows_tool_rotation:'followsRotation',mounting_confirmed:'mountConfirmed',timing_confirmed:'timingConfirmed'};
  const api=name=>new URL('api/'+name,location.href);
  const num=(v,d=1)=>Number.isFinite(v)?v.toFixed(d):'—';
  function measuredFrame(){
    const m=state?.measurement,age=m?state.observed_at-(m.captured_at_estimate??m.received_at):Infinity;
    return m&&age>=0&&age<=.5&&state.motion&&state.running&&!state.error&&(state.config.mounting_confirmed||m.method==='automatic_motion')?m:null;
  }
  function motionReason(){
    if(!videoEnabled||state?.running===false)return 'Analysis paused. Press Start analysis to resume.';
    if(!state?.camera)return 'MCAM1 video is unavailable. Start its preview in the MCAM1 tab.';
    if(state.error)return state.error;
    if(!state.motion)return 'Fresh feedback from the selected arm is unavailable.';
    if(!state.automatic_motion_supported)return 'Motion depth needs the updated server. Restart the hub when the match has finished.';
    return state.message||'Waiting for measured camera movement.';
  }
  function motionProgress(){
    if(!state?.motion)return '';
    const pose=state.motion.pose;
    const travel=Math.max(0,...travelSamples.map(sample=>Math.hypot(...pose.slice(0,3).map((p,i)=>p-sample.pose[i]))));
    const mode=state.config.mounting_confirmed?'Configured mount':'Automatic camera direction';
    return `${mode} · ${num(travel)} mm from recent views · ${num(state.motion.speed_mm_s)} mm/s · needs ${state.config.min_baseline_mm}–40 mm with steady orientation`;
  }
  function motionMap(){
    const fresh=measuredFrame();
    if(fresh)return fresh;
    // A frozen map is presentation only, paired with its original image. It
    // never supplies current clearance, AI scale or the public measurement.
    const age=lastMeasured?state?.observed_at-(lastMeasured.captured_at_estimate??lastMeasured.received_at):Infinity;
    return videoEnabled&&state?.running&&state.camera&&state.motion&&!state.error&&age>=0&&age<=300?lastMeasured:null;
  }
  function showMotionStatus(){
    const fresh=videoEnabled?measuredFrame():null;
    const shown=$('view').value==='motion'?motionMap():fresh, fusion=shown?.fusion;
    $('fusionState').textContent=!videoEnabled||state?.running===false?'Paused':shown&&!fresh?'Last measured map':fusion?.state==='refined'?'Motion refined':shown?'Collecting viewpoints':'Waiting for measurements';
    const evidence=fusion?`${fusion.combined_points} features combined · up to ${fusion.max_views} viewpoints · ${fusion.rejected_observations} conflicting observations rejected in the captured frame`:'';
    $('fusionDetail').textContent=shown?(evidence||'Distance samples from measured arm travel'):motionReason();
    $('motionProgress').textContent=motionProgress();
    $('refinementStatus').textContent=motionReason();
    $('depthDetail').textContent=shown?`${num(shown.baseline_mm)} mm of measured travel over ${shown.interval_ms} ms. ${shown!==fresh?'This frozen map belongs to the displayed camera reference; it is not a current clearance measurement.':'Repeated agreeing observations refine these distances.'}`:$('view').value==='motion'?'Motion depth needs the same stationary scene features in multiple views. The head and a held Atom move with the camera and have no useful parallax.':'Video predicts relative near/far depth, including visible head and Atom surfaces. Their predicted depth is not a measured grip or ground clearance.';
  }
  function stopWorker(){
    worker?.terminate();worker=null;workerReady=false;busy=false;pending=null;queuedKey='';
    clearTimeout(loadTimer);if(workerURL)URL.revokeObjectURL(workerURL);workerURL=null;
  }
  function startWorker(){
    if(worker||!videoEnabled||!state?.camera||document.hidden)return;
    workerInfo='Loading video depth model… The first visit downloads model files; video stays in this browser.';
    try{
      workerURL=URL.createObjectURL(new Blob(['('+DepthBricks.workerMain.toString()+')()'],{type:'text/javascript'}));
      worker=new Worker(workerURL,{type:'module'});
      loadTimer=setTimeout(()=>{stopWorker();workerInfo='Video depth download timed out. Check the connection and retry.';draw();},120000);
      worker.onerror=event=>{stopWorker();workerInfo='Video depth could not start: '+(event.message||'browser worker unavailable');draw();};
      worker.onmessage=({data})=>{
        if(data.type==='loading'){workerInfo=`Loading video depth model… ${data.progress}% of current file. Video stays in this browser.`;draw();return;}
        if(data.type==='ready'){clearTimeout(loadTimer);workerReady=true;workerInfo=`Video depth ready · ${data.device} · estimates run in this browser`;schedulePrediction();draw();return;}
        if(data.type==='error'){stopWorker();workerInfo=data.error;draw();return;}
        if(data.type==='busy'&&pending?.id===data.id){pending=null;busy=false;queuedKey='';setTimeout(schedulePrediction,250);return;}
        if(data.type!=='result'||!pending||data.id!==pending.id)return;
        const job=pending;pending=null;busy=false;
        if(videoEnabled&&state?.camera&&!document.hidden&&job.side===state.config.side&&performance.now()-job.started<15000){
          let points=DepthBricks.relativePoints(data.values,data.width,data.height,job.width,job.height);
          const fit=job.measurement?DepthBricks.motionScale(data.values,data.width,data.height,job.measurement.points):null;
          let kind='relative';
          if(fit){
            const lens=job.config.intrinsics?.matrix,f=job.width/(2*Math.tan(job.config.horizontal_fov_deg*Math.PI/360));
            const fx=lens?.[0][0]||f,fy=lens?.[1][1]||f,cx=lens?.[0][2]??job.width/2,cy=lens?.[1][2]??job.height/2;
            const metric=points.flatMap(p=>{const inv=fit.slope*p.inverse+fit.offset,z=1/inv;
              if(p.inverse<fit.min||p.inverse>fit.max||!(z>=20&&z<=1200))return [];
              return [{...p,depth_mm:z,distance_mm:z*Math.hypot((p.x*job.width-cx)/fx,(p.y*job.height-cy)/fy,1)}];});
            if(metric.length>points.length*.5){points=metric;kind='video_motion';}
          }
          aiFrame={bitmap:job.bitmap,points,kind,measured:false,distanceKind:kind==='relative'?'relative':'lens_to_point',receivedAt:job.receivedAt,completed:performance.now(),fit:kind==='video_motion'?fit:null};
          $('brickReadout').textContent=kind==='relative'?'Point at a brick to compare nearer and farther surfaces.':'Point at a brick to read its estimated distance.';
          present();
        }
        setTimeout(schedulePrediction,100);
      };
    }catch(error){stopWorker();workerInfo='Video depth could not start: '+error.message;}
  }
  function schedulePrediction(){
    if(!videoEnabled||document.hidden||!state?.camera||['live','motion'].includes($('view').value))return;
    if(!worker){if(!workerInfo.includes('could not')&&!workerInfo.includes('failed')&&!workerInfo.includes('timed out'))startWorker();return;}
    if(!workerReady||busy)return;
    const m=measuredFrame(),frame=m||state.camera,key=frame.frame_id+':'+frame.received_at;
    if(key===queuedKey)return;
    queuedKey=key;busy=true;
    const job={id:++jobId,preview:frame.preview,width:frame.width||state.camera.width,height:frame.height||state.camera.height,receivedAt:frame.received_at,measurement:m,config:state.config,side:state.config.side,started:performance.now()};
    pending=job;const bitmap=new Image();job.bitmap=bitmap;
    bitmap.onload=()=>{if(pending?.id===job.id&&worker)worker.postMessage({id:job.id,preview:job.preview});};
    bitmap.onerror=()=>{if(pending?.id===job.id){pending=null;busy=false;workerInfo='Camera frame could not be decoded.';}};
    bitmap.src=job.preview;
  }
  function markDirty(){dirty=true;$('dirty').textContent='Unsaved setup changes';}
  function loadConfig(c){
    draft=structuredClone(c);$('side').value=c.side;
    for(const [key,id] of Object.entries(fields))$(id).value=c[key];
    for(const [key,ids] of Object.entries(vectors))ids.forEach((id,i)=>$(id).value=c[key][i]);
    for(const [key,id] of Object.entries(checks))$(id).checked=c[key];
    $('surfaceValues').value=c.surface_roi?.join(', ')||'';$('atomValues').value=c.atom_roi?.join(', ')||'';
    dirty=false;$('dirty').textContent='Video depth works without setup. These settings improve precision and enable calibrated clearance.';
  }
  function readRegion(text){if(!text.trim())return null;const a=text.split(/[\s,]+/).map(Number);if(a.length!==4||!a.every(Number.isFinite))throw Error('Region needs X, Y, width and height');return a;}
  function readConfig(){
    const c=structuredClone(draft);c.side=$('side').value;
    for(const [key,id] of Object.entries(fields))c[key]=Number($(id).value);
    for(const [key,ids] of Object.entries(vectors))c[key]=ids.map(id=>Number($(id).value));
    for(const [key,id] of Object.entries(checks))c[key]=$(id).checked;
    c.surface_roi=readRegion($('surfaceValues').value);c.atom_roi=readRegion($('atomValues').value);return c;
  }
  async function post(name,data){
    const response=await fetch(api(name),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const value=await response.json();if(!response.ok)throw Error(value.error||'Request failed');return value;
  }
  function unavailable(message){
    state=null;lastEvent=0;$('run').disabled=true;
    $('status').textContent=message;$('clearance').textContent='—';$('planeAge').textContent='No current surface estimate';
    $('attachment').textContent='Unknown';$('attachmentDetail').textContent='Fresh movement evidence is required';
    $('speed').textContent='—';$('motionDetail').textContent='No current feedback';$('pointCount').textContent='—';$('fitError').textContent='—';
    $('fusionState').textContent='Unavailable';$('fusionDetail').textContent='Fresh observations are required before showing refinement.';
    $('motionProgress').textContent='';
    image=aiFrame=lastMeasured=null;travelSamples=[];pending=null;busy=false;queuedKey='';imageKey='';generation++;draw();$('frameInfo').textContent='No current video';
  }
  function apply(s){
    if(s.contract!=='hhh.mcam1.depth'||s.version!==1||!s.config)throw Error('Incompatible depth stream');
    if(state&&(JSON.stringify(state.config)!==JSON.stringify(s.config)||state.camera?.width!==s.camera?.width||state.camera?.height!==s.camera?.height||state.motion?.epoch!==s.motion?.epoch||s.camera?.frame_id<state.camera?.frame_id||s.camera?.received_at<state.camera?.received_at)){
      aiFrame=lastMeasured=null;travelSamples=[];pending=null;busy=false;queuedKey='';image=null;imageKey='';generation++;
    }
    state=s;lastEvent=performance.now();$('run').disabled=false;if(!draft||!dirty)loadConfig(s.config);
    if(!videoEnabled||!s.running||!s.camera||!s.motion||s.error){lastMeasured=null;travelSamples=[];}
    else{
      if(measuredFrame())lastMeasured=measuredFrame();
      const stamp=s.motion.feedback_at??s.observed_at;
      travelSamples=travelSamples.filter(sample=>stamp-sample.stamp>=0&&stamp-sample.stamp<=4);
      if(!travelSamples.length||travelSamples.at(-1).stamp!==stamp)travelSamples.push({stamp,pose:s.motion.pose});
      if(travelSamples.length>160)travelSamples.shift();
    }
    $('run').textContent=videoEnabled?'Pause analysis':'Start analysis';$('runState').textContent=(videoEnabled?'Automatic video depth · ':'Paused · ')+s.config.side+' arm';
    $('status').textContent=videoEnabled?(s.measurement?'Arm motion is supplying distance samples.':'Video-only depth needs no setup. Move the camera with a steady orientation to refine distance.'):'Analysis paused';$('status').classList.remove('bad');
    $('clearance').textContent=Number.isFinite(s.clearance_if_held_mm)?'≈ '+num(s.clearance_if_held_mm)+' mm':'—';
    $('planeAge').textContent=s.plane?'Surface update '+num(s.plane_age_ms/1000,1)+' s ago · upright Atom assumption':'No current surface estimate';
    const labels={moves_with_head:'Moves with head',relative_motion:'Relative movement',unknown:'Unknown'};
    $('attachment').textContent=labels[s.attachment?.state]||'Unknown';$('attachmentDetail').textContent=s.attachment?.reason||'Fresh movement evidence is required';
    $('speed').textContent=s.motion?num(s.motion.speed_mm_s)+' mm/s':'—';
    $('motionDetail').textContent=s.motion?s.motion.phase+' · TCP Z '+num(s.motion.pose[2])+' mm':'Waiting for selected arm feedback';
    $('lensQuality').textContent=s.config.intrinsics?'Calibrated · '+num(s.config.intrinsics.rms,2)+' px RMS':'Nominal '+s.config.horizontal_fov_deg+'° view';
    $('mountQuality').textContent=s.config.mounting_confirmed?'Operator measured':'Automatic · no setup needed';
    $('timingQuality').textContent=(s.config.timing_confirmed?'Measured delay':'Unverified delay')+' · '+s.config.frame_delay_ms+' ms';
    $('pointCount').textContent=s.measurement?.points?.length??'—';$('fitError').textContent=s.plane?num(s.plane.rms_mm,2)+' mm residual':'No screen plane';
    $('samples').textContent=s.lens_samples+' views collected';
    if(!autoStarted){autoStarted=true;if(!s.running)post('analysis',{running:true}).catch(error=>{$('refinementStatus').textContent=error.message;});}
    schedulePrediction();
    present();
  }
  function present(){
    showMotionStatus();
    if(!state?.camera){image=null;imageKey='';generation++;draw();return;}
    const fresh=measuredFrame(),m=$('view').value==='motion'?motionMap():fresh,preferMeasured=$('view').value==='motion'||m?.fusion?.state==='refined';
    if(videoEnabled&&$('view').value!=='live'&&!preferMeasured&&aiFrame&&performance.now()-aiFrame.completed<10000&&state.observed_at-aiFrame.receivedAt<15){
      image=aiFrame;imageKey='ai:'+aiFrame.receivedAt;generation++;canvas.width=image.bitmap.naturalWidth;canvas.height=image.bitmap.naturalHeight;
      $('frameInfo').textContent=(image.kind==='relative'?'AI relative depth':'AI depth scaled by arm motion')+' · frame '+num(Math.max(0,state.observed_at-aiFrame.receivedAt),1)+' s old';draw();return;
    }
    const age=m?state.observed_at-(m.captured_at_estimate??m.received_at):Infinity;
    const depth=videoEnabled&&$('view').value!=='live'&&m;
    const key=(depth?'depth:':'live:')+(depth?m.frame_id:state.camera.frame_id)+':'+(depth?m.received_at:state.camera.received_at);
    const frozen=!!depth&&!fresh;
    $('frameInfo').textContent=depth?(frozen?'Last measured map · '+num(age,1)+' s old · frozen snapshot':(m.fusion?.state==='refined'?'Motion refined · ':'Measured depth · ')+Math.round(age*1000)+' ms old'):$('view').value==='live'?'Live MCAM1 · '+state.camera.width+' × '+state.camera.height:'Live camera · no measured depth yet';
    if(key===imageKey){if(image)image.frozen=frozen;draw();return;}
    imageKey=key;const token=++generation;const next=new Image();
    if(!depth&&image){image={...image,points:[],measured:false};draw();}
    next.onload=()=>{if(token!==generation)return;image={bitmap:next,points:depth?m.points:[],kind:depth?'motion':'waiting',measured:!!depth,frozen,distanceKind:depth?m.distance_kind:null};canvas.width=next.naturalWidth;canvas.height=next.naturalHeight;if(depth)$('brickReadout').textContent='Point at a brick to read its distance.';draw();};
    next.onerror=()=>{if(token!==generation)return;image=null;draw();};next.src=depth?m.preview:state.camera.preview;
  }
  function draw(){
    context.clearRect(0,0,canvas.width,canvas.height);$('noVideo').hidden=!!image;
    const depthMode=$('view').value!=='live';
    const relative=image?.kind==='relative',approximate=relative||image?.kind==='video_motion',waiting=!image?.points?.length;
    brickMap=DepthBricks.grid(image?.points,canvas.width,canvas.height,Number($('brickSize').value),relative);
    const motionView=$('view').value==='motion';
    $('videoDepthStatus').textContent=motionView?'Motion measurements use the video and measured arm travel. AI predictions are shown in Depth bricks.':workerInfo;
    $('retryDepth').hidden=motionView||workerReady||!!worker;
    const relativeScale=relative||waiting;
    $('near').hidden=$('far').hidden=$('fitRange').hidden=relativeScale;
    $('nearTitle').textContent=relativeScale?'Nearer':'Near (mm)';$('farTitle').textContent=relativeScale?'Farther':'Far (mm)';
    canvas.dataset.bricks=String(depthMode?brickMap.cells.length:0);
    $('depthLegend').hidden=!depthMode;$('reference').hidden=!depthMode||!image||waiting;
    $('referenceLabel').textContent=image?.frozen?'Camera reference · frozen with the last measured map':'Camera reference · same frame as the map';
    $('depthNotice').hidden=!depthMode||!image||brickMap.cells.length>0;
    $('coverage').textContent=`${brickMap.cells.length} ${approximate?'estimated':'measured'} bricks · ${num(brickMap.coverage*100,0)}% image coverage`;
    $('fitRange').disabled=!brickMap.cells.length;
    if(!brickMap.cells.length)$('brickReadout').textContent='No measured distance at unknown cells.';
    $('depthAxis').textContent=motionView&&waiting?'No measured distances yet':relativeScale?'Relative depth · AI estimate, no millimetre scale':image?.kind==='video_motion'?'Estimated distance · AI fitted to arm-motion samples':image?.distanceKind==='lens_to_point'?'Distance from camera lens':'Camera forward depth';
    $('depthNoticeTitle').textContent=motionView?'Waiting for motion measurements':'Preparing video depth';
    $('depthReason').textContent=!videoEnabled?'Analysis paused. Press Start analysis to resume.':motionView?motionReason():workerInfo;
    if(!image)return;
    if(depthMode){
      DepthBricks.paint(context,brickMap,canvas.width,canvas.height,relative?0:near,relative?1:far,$('view').value==='overlay'||(motionView&&waiting)?image.bitmap:null);
      const reference=$('referenceVideo');reference.width=canvas.width;reference.height=canvas.height;reference.getContext('2d').drawImage(image.bitmap,0,0);
    }else context.drawImage(image.bitmap,0,0);
    function box(r,color){if(!r)return;context.strokeStyle=color;context.lineWidth=2;context.strokeRect(r[0]*canvas.width,r[1]*canvas.height,r[2]*canvas.width,r[3]*canvas.height);}
    box(draft?.surface_roi,'#69dfd0');box(draft?.atom_roi,'#e5b9ff');
    if(dragging)box(rect(dragging.start,dragging.end),'#ffffff');
  }
  function rect(a,b){return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1])];}
  function point(event){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}
  function selection(kind){select=kind;if(kind){$('view').value='live';present();}$('surfaceSelect').classList.toggle('active',kind==='surface_roi');$('atomSelect').classList.toggle('active',kind==='atom_roi');canvas.parentElement.classList.toggle('selecting',!!kind);$('selectionHint').textContent=kind?'Drag a rectangle on the camera image, then save setup.':'Regions selected. Save setup to apply changes.';}
  canvas.addEventListener('pointerdown',e=>{if(!select||!image||!draft)return;dragging={start:point(e),end:point(e)};canvas.setPointerCapture(e.pointerId);draw();});
  canvas.addEventListener('pointermove',e=>{if(dragging){dragging.end=point(e);draw();}else if($('view').value!=='live'){const [u,v]=point(e),x=u*canvas.width,y=v*canvas.height,cell=brickMap?.cells.find(c=>x>=c.x&&x<c.x+c.width&&y>=c.y&&y<c.y+c.height);$('brickReadout').textContent=cell?(image?.kind==='relative'?(cell.distance<.33?'Nearer':cell.distance>.66?'Farther':'Middle depth')+' · relative AI estimate':'≈ '+num(cell.distance)+' mm · '+$('depthAxis').textContent.toLowerCase()+(cell.views?' · '+cell.views+' viewpoints':'')):'Unknown depth at this cell';}});
  canvas.addEventListener('pointerup',e=>{if(!dragging)return;const r=rect(dragging.start,point(e));dragging=null;if(r[2]>=.04&&r[3]>=.04){draft[select]=r.map(v=>Math.round(v*10000)/10000);$(select==='surface_roi'?'surfaceValues':'atomValues').value=draft[select].join(', ');markDirty();selection(null);}else $('actionStatus').textContent='Select a region at least 4% wide and high.';draw();});
  canvas.addEventListener('pointercancel',()=>{dragging=null;draw();});
  $('surfaceSelect').onclick=()=>selection('surface_roi');$('atomSelect').onclick=()=>selection('atom_roi');
  $('clearRegions').onclick=()=>{if(!draft)return;draft.surface_roi=draft.atom_roi=null;$('surfaceValues').value=$('atomValues').value='';markDirty();draw();};
  $('view').onchange=()=>{present();schedulePrediction();};
  $('retryDepth').onclick=()=>{stopWorker();workerInfo='Retrying video depth…';startWorker();draw();};
  $('brickSize').onchange=draw;
  function setRange(){const a=Number($('near').value),b=Number($('far').value);if(!Number.isFinite(a)||!Number.isFinite(b)||a<20||b>3000||b<=a){$('brickReadout').textContent='Use a range from 20 to 3000 mm with Far greater than Near.';return;}near=a;far=b;draw();}
  $('near').onchange=$('far').onchange=setRange;
  $('fitRange').onclick=()=>{if(!brickMap?.cells.length)return;const values=brickMap.cells.map(c=>c.distance);$('near').value=Math.max(20,Math.floor(Math.min(...values)-5));$('far').value=Math.min(3000,Math.ceil(Math.max(...values)+5));setRange();};
  $('setup').addEventListener('input',markDirty);$('side').onchange=()=>{markDirty();$('mountConfirmed').checked=false;$('dirty').textContent='Arm changed: verify mounting and save setup before analysing this arm.';};
  $('setup').onsubmit=async e=>{e.preventDefault();$('save').disabled=true;try{const result=await post('config',readConfig());loadConfig(result.config);$('actionStatus').textContent='Setup saved. Previous depth observations cleared.';}catch(error){$('actionStatus').textContent=error.message;}finally{$('save').disabled=false;}};
  $('run').onclick=async()=>{videoEnabled=!videoEnabled;if(!videoEnabled){aiFrame=lastMeasured=null;travelSamples=[];pending=null;busy=false;image=null;imageKey='';queuedKey='';generation++;}else schedulePrediction();present();try{apply(await post('analysis',{running:videoEnabled}));}catch(error){$('actionStatus').textContent='Video mode changed; motion refinement: '+error.message;}};
  for(const button of document.querySelectorAll('[data-lens]'))button.onclick=async()=>{button.disabled=true;try{if(dirty)throw Error('Save setup before lens calibration');const result=await post('lens',{action:button.dataset.lens,columns:Number($('columns').value),rows:Number($('rows').value),square_mm:Number($('square').value)});apply(result);$('actionStatus').textContent=button.dataset.lens==='capture'?'Board view captured. Change position and tilt for the next sample.':'Lens calibration updated.';}catch(error){$('actionStatus').textContent=error.message;}finally{button.disabled=false;}};
  function connect(){if(document.hidden)return;stream=new EventSource(api('events'));stream.onmessage=e=>{try{apply(JSON.parse(e.data));}catch(error){unavailable(error.message);}};stream.onerror=()=>unavailable('Depth stream disconnected; reconnecting…');}
  document.addEventListener('visibilitychange',()=>{stream?.close();stream=null;if(document.hidden)unavailable('Preview paused while hidden');else connect();});
  window.addEventListener('pagehide',()=>{stream?.close();stopWorker();});
  setInterval(()=>{if(lastEvent&&performance.now()-lastEvent>1000)unavailable('Depth updates are stale; waiting for fresh observations');},250);
  connect();
})();
