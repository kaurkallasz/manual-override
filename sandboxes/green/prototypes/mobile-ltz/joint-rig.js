/* Version 01 technical-contour rig. Pure motion/geometry also exported for tests. */
(function(root){
'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),rad=d=>d*Math.PI/180;
const delta=(a,b)=>((a-b+540)%360)-180;
const limits=[[ -25,85 ],[ -25,105 ]];
// Preserve the robot's existing clockwise/decreasing J1 convention on a fixed dial.
function baseDialAngle(value,bounds){return 90-180*(clamp(value,...bounds)-bounds[0])/(bounds[1]-bounds[0]);}
function baseDialValue(angle,bounds){return bounds[1]-(clamp(angle,-90,90)+90)/180*(bounds[1]-bounds[0]);}
function sliderBounds(bounds,center,fine){
 const [lo,hi]=bounds;if(!fine)return [lo,hi];
 const span=(hi-lo)/10,start=clamp(center-span/2,lo,hi-span);
 return [start,start+span];
}
function displayAngles(confirmed,preview,bounds){
 const values=[...confirmed];
 if(Array.isArray(preview)&&preview.length===3&&preview.every(Number.isFinite))for(let i=1;i<3;i++)values[i]=clamp(preview[i],...bounds[i-1]);
 return values;
}
// Calibrated sketch zeroes; J3 is an absolute forearm angle, not relative to J2.
function pose(j2,j3){
 const shoulder={x:0,y:0},a=-120+j2,b=185+j3;
 const elbow={x:180*Math.cos(rad(a)),y:180*Math.sin(rad(a))};
 const wrist={x:elbow.x+175*Math.cos(rad(b)),y:elbow.y+175*Math.sin(rad(b))};
 return {shoulder,elbow,wrist,head:{x:wrist.x,y:wrist.y+42},a,b};
}
// Include trigonometric extrema, not just limit endpoints. This frame stays fixed
// throughout a gesture, including at the ends of both independent joint sweeps.
function layout(width,height,bounds,zoom=1){
 const angles=(lo,hi)=>{const out=[lo,hi];for(let v=Math.ceil(lo/90)*90;v<hi;v+=90)out.push(v);return out;};
 const a=angles(-120+bounds[0][0],-120+bounds[0][1]),b=angles(185+bounds[1][0],185+bounds[1][1]);
 const xs=[0],ys=[0];
 for(const v of a){const x=180*Math.cos(rad(v)),y=180*Math.sin(rad(v));xs.push(x);ys.push(y);for(const w of b){xs.push(x+175*Math.cos(rad(w)));ys.push(y+175*Math.sin(rad(w)),y+175*Math.sin(rad(w))+51);}}
 const minX=Math.min(...xs)-24,maxX=Math.max(...xs)+24,minY=Math.min(...ys)-24,maxY=Math.max(...ys);
 const pad=30,scale=zoom*Math.max(.01,Math.min((width-2*pad)/(maxX-minX),(height-68)/(maxY-minY)));
 return {scale,x:width/2-(minX+maxX)*scale/2,y:height-38-maxY*scale,w:width,h:height,zoom};
}
// Two cascaded low-pass stages keep both position and velocity continuous as
// telemetry arrives. Exact integration is independent of the display frame rate.
// Presentation only: never feed this delayed value back into arm commands.
class IndicatorMotion{
 constructor(){this.reset();}
 reset(value=null){this.value=this.follow=Number.isFinite(value)?value:null;return this.value;}
 step(target,dt,enabled=true){
  if(!Number.isFinite(target))return this.reset();
  if(!enabled||this.value===null||!Number.isFinite(dt)||dt<0||dt>.25)return this.reset(target);
  const elapsed=dt/.09,decay=Math.exp(-elapsed),offset=this.follow-target;
  this.value=target+(this.value-target+offset*elapsed)*decay;
  this.follow=target+offset*decay;
  return this.value;
 }
}
// Align the stationary shoulder guide with the control panel edge. Never follow
// a moving elbow or telemetry packet; only layout/limit changes can reframe it.
function alignRight(frame,bounds,rightEdge=frame.w-8){
 const s=frame.scale,r=Math.min(43*frame.zoom,frame.h*.19*frame.zoom,180*s*.42);
 const maxCos=(lo,hi)=>Math.ceil(lo/360)*360<=hi?1:Math.max(Math.cos(rad(lo)),Math.cos(rad(hi)));
 const mid=(bounds[0][0]+bounds[0][1])/2,edge=r*maxCos(mid-210,mid-30);
 return {...frame,x:rightEdge-edge};
}
class Motion{
 constructor(){this.cancel();}
 request(axis,current,desired){if(this.axis!==axis)this.begin(axis,current,0,0,0);this.desired=desired;this.moved=true;}
 begin(axis,value,angle,x,y){this.axis=axis;this.value=value;this.desired=value;this.last=angle;this.start={x,y};this.moved=false;this.age=0;}
 move(angle,x,y,fine){if(this.axis==null)return;if(!this.moved&&Math.hypot(x-this.start.x,y-this.start.y)<4)return;this.moved=true;this.desired+=delta(angle,this.last)*(this.axis===1?-1:1)*(fine?.15:.5);this.last=angle;}
 step(dt,confirmed,bounds){if(this.axis==null||!this.moved)return null;dt=clamp(dt,0,.05);this.age+=dt;const speed=12*Math.min(1,this.age/.2);this.desired=clamp(this.desired,...bounds);const low=Math.max(bounds[0],confirmed-1.2),high=Math.min(bounds[1],confirmed+1.2);if(Math.abs(this.value-confirmed)>6){this.cancel();return null;}if(this.value<low-.00001||this.value>high+.00001)return null;const next=clamp(this.value+clamp(this.desired-this.value,-speed*dt,speed*dt),low,high);if(Math.abs(next-this.value)<.00001)return null;this.value=next;return next;}
 cancel(){this.axis=null;this.moved=false;this.age=0;}
}
// User-selected goals are separate from both issued commands and telemetry.
// Each axis retains its goal when the other slider is edited or packets arrive.
class JointControls{
 constructor(){this.motions=[null,new Motion(),new Motion()];this.goals=[null,null,null];this.selected=null;}
 request(axis,current,desired){if(![1,2].includes(axis)||!Number.isFinite(current)||!Number.isFinite(desired))return;this.goals[axis]=desired;this.motions[axis].request(axis,current,desired);this.selected=axis;}
 value(axis,fallback){return this.goals[axis]??fallback;}
 commanded(axis,fallback){return this.goals[axis]===null?fallback:this.motions[axis].value;}
 get moving(){return this.motions.slice(1).some(m=>m.axis!==null);}
 get activeAxis(){return this.motions[this.selected]?.axis??this.motions.slice(1).find(m=>m.axis!==null)?.axis??null;}
 preview(fallback){if(this.goals.slice(1).every(v=>v===null))return null;return fallback.map((v,i)=>i?this.value(i,v):v);}
 step(dt,confirmed,bounds){
  const changed=[];
  for(const axis of [1,2]){
   const motion=this.motions[axis];if(motion.axis===null)continue;
   const next=motion.step(dt,confirmed[axis],bounds[axis-1]);
   if(motion.axis===null){this.goals[axis]=null;continue;}
   this.goals[axis]=motion.desired;
   if(next!==null)changed.push([axis,next]);
   if(Math.abs(motion.desired-motion.value)<.00001)motion.cancel();
  }
  return changed;
 }
 cancel(){for(const axis of [1,2]){this.motions[axis].cancel();this.goals[axis]=null;}this.selected=null;}
}
function mount(host,options){
 let shown=null,lastTime=0,raf=0,destroyed=false,previewing=false;
 host.innerHTML=`<svg class="jointRigSvg" aria-label="MG400 arm position" role="img">
 <g class="rigDrawing" fill="none" stroke="white" stroke-linejoin="round" stroke-linecap="round">
 <path class="rigStem" d="M-15 0 L-15 500 M15 0 L15 500 M-10 0 L-10 500"/>
 <g class="rigShoulder"><path class="rigContour" d="M0 -20 C35 -22 135 -16 175 -19 Q196 -14 194 0 Q194 19 175 20 L32 25 Q-20 27 -22 0 Q-21 -20 0 -20Z"/><path class="rigDetail" d="M20 -14 L160 -12 M24 16 L157 13 M35 22 L151 18 M40 -11 L143 -10 L143 9 L40 12Z"/><circle r="16"/><circle r="12" class="rigDetail"/><circle cx="180" r="17"/><circle cx="180" r="13" class="rigDetail"/></g>
 <g class="rigForearm"><path class="rigContour" d="M0 -19 Q-20 -17 -20 0 Q-19 19 0 19 L135 17 Q163 21 175 12 Q190 0 176 -14 L30 -23Z"/><path class="rigDetail" d="M24 -17 L128 -12 L142 -6 L142 8 L30 12Z M26 16 L147 12 M12 -20 L35 -28 L140 -20 L166 -15"/><circle r="15"/><circle r="11" class="rigDetail"/><circle cx="175" r="13"/><circle cx="175" r="9" class="rigDetail"/></g>
 <g class="rigTool"><path class="rigContour" d="M-11 0 L-11 18 L11 18 L11 0 M-13 20 H13 V27 H-13Z M-9 29 H9 V43 H-9Z M-4 44 V51 H4 V44"/><path class="rigDetail" d="M-8 7 H8 M-7 23 H7 M0 31 V41"/></g>
 </g><g class="rigGonio rigGonio2"></g><g class="rigGonio rigGonio3"></g>
 <g class="rigActual" fill="none" stroke-linecap="round" stroke-linejoin="round"><path class="rigActualJ2"/><path class="rigActualJ3"/></g>
 </svg><span class="rigCaption">Arm position</span>`;
 const svg=host.querySelector('svg'),g2=host.querySelector('.rigGonio2'),g3=host.querySelector('.rigGonio3'),caption=host.querySelector('.rigCaption');
 const elements={shoulder:host.querySelector('.rigShoulder'),forearm:host.querySelector('.rigForearm'),tool:host.querySelector('.rigTool'),stem:host.querySelector('.rigStem'),actual2:host.querySelector('.rigActualJ2'),actual3:host.querySelector('.rigActualJ3')};
 let frame=null,currentPose=pose(-5,-5),latest=null,layoutKey='',drawKey='';
 function fit(bounds,rightEdge){
  const rect=host.getBoundingClientRect(),edge=Number.isFinite(rightEdge)?rightEdge-(rect.left||0):rect.width-8;
  frame=alignRight(layout(rect.width,rect.height,bounds,2),bounds,edge);
  // Keep the original shoulder height above the slider dock. Expanded virtual
  // sweeps may change the drawing scale, but must not lift its stationary base.
  frame.y=layout(rect.width,rect.height,limits,2).y;
  svg.setAttribute('viewBox',`0 0 ${rect.width} ${rect.height}`);drawKey='';
 }
 const screen=p=>({x:frame.x+p.x*frame.scale,y:frame.y+p.y*frame.scale});
 function protractor(group,p,angle,value,bounds,axis){
  const c=screen(p),r=Math.min(43*frame.zoom,frame.h*.19*frame.zoom,180*frame.scale*.42),activeAxis=options.activeAxis?.()===axis;
  // A 180-degree instrument centered on the configured sweep. Numeric labels remain real joint angles.
  const mid=(bounds[0]+bounds[1])/2,start=mid-90,sweep=1;
  const bearing=v=>axis===1?-120+v:185+v;
  const polar=(v,radius)=>({x:c.x+radius*Math.cos(rad(bearing(v))),y:c.y+radius*Math.sin(rad(bearing(v)))});
  const first=polar(start,r),last=polar(start+180,r),zero=polar(0,r);
  let content=`<path d="M${first.x} ${first.y} A${r} ${r} 0 0 ${sweep} ${last.x} ${last.y}" class="gonioArc"/><path d="M${c.x} ${c.y} L${zero.x} ${zero.y}" class="gonioBaseline"/>`;
  const lo=polar(bounds[0],r),hi=polar(bounds[1],r);content+=`<path d="M${lo.x} ${lo.y} A${r} ${r} 0 0 ${sweep} ${hi.x} ${hi.y}" class="gonioRange"/>`;
  for(let v=Math.ceil(start/5)*5;v<=start+180;v+=5){const major=v%15===0,from=polar(v,r),to=polar(v,r-(major?7:3));content+=`<path class="gonioTick" d="M${from.x} ${from.y} L${to.x} ${to.y}"/>`;if(v%45===0){const label=polar(v,r+10);content+=`<text x="${clamp(label.x,12,frame.w-12)}" y="${Math.min(frame.h-8,label.y+3)}">${v}°</text>`;}}
  const needle=polar(clamp(value,start,start+180),r-9);content+=`<path class="gonioNeedle" d="M${c.x} ${c.y} L${needle.x} ${needle.y}"/><circle class="gonioCenter" cx="${c.x}" cy="${c.y}" r="2"/><text class="gonioValue" x="${c.x}" y="${Math.min(frame.h-8,c.y+24)}">J${axis+1} ${value.toFixed(options.precision?.()?2:1)}°</text>`;
  const requested=latest?.targets?.[axis];if(Number.isFinite(requested)&&Math.abs(requested-value)>.2){const q=polar(requested,r-4);content+=`<circle class="gonioTarget" cx="${q.x}" cy="${q.y}" r="3"/>`;}
  group.innerHTML=content;group.classList.toggle('active',activeAxis);
 }
 function draw(values,bounds){
  currentPose=pose(values[1],values[2]);
  const confirmed=latest?.joints,validActual=Array.isArray(confirmed)&&confirmed.length===3&&confirmed.every(Number.isFinite);
  const actual=validActual?pose(confirmed[1],confirmed[2]):currentPose;
  const p=currentPose,s=frame.scale,base=screen(p.shoulder),e=screen(p.elbow),w=screen(p.wrist),h=screen(p.head);
  svg.setAttribute('aria-label',`${previewing?'Target preview':'Arm position'}: shoulder ${values[1].toFixed(1)} degrees, elbow ${values[2].toFixed(1)} degrees`);
  caption.textContent=previewing?'White: target · Red: actual':'Red: actual arm position';
  elements.shoulder.setAttribute('transform',`translate(${base.x} ${base.y}) rotate(${p.a}) scale(${s})`);
  elements.forearm.setAttribute('transform',`translate(${e.x} ${e.y}) rotate(${p.b}) scale(${s})`);
  elements.tool.setAttribute('transform',`translate(${w.x} ${w.y}) scale(${s})`);
  elements.stem.setAttribute('transform',`translate(${base.x} ${base.y}) scale(${s})`);
  protractor(g2,p.shoulder,p.a,values[1],bounds[0],1);protractor(g3,p.elbow,p.b,values[2],bounds[1],2);
  if(validActual){
   const a=screen(actual.shoulder),b=screen(actual.elbow),c=screen(actual.wrist);
   elements.actual2.setAttribute('d',`M${a.x} ${a.y} L${b.x} ${b.y}`);
   elements.actual3.setAttribute('d',`M${b.x} ${b.y} L${c.x} ${c.y}`);
   host.querySelector('.rigActual').setAttribute('aria-label',`Actual J2 ${confirmed[1].toFixed(1)} degrees, J3 ${confirmed[2].toFixed(1)} degrees`);
  }else{elements.actual2.setAttribute('d','');elements.actual3.setAttribute('d','');}
 }
 function tick(time){if(destroyed)return;const dt=Math.min(.05,(time-lastTime)/1000||0);lastTime=time;latest=options.state();const valid=Array.isArray(latest?.joints)&&latest.joints.length===3&&latest.joints.every(Number.isFinite)&&Array.isArray(latest?.limits)&&latest.limits.length===3&&latest.limits.every(b=>Array.isArray(b)&&b.length===2&&b.every(Number.isFinite)&&b[0]<b[1]&&b[0]>=-360&&b[1]<=360);const enabled=options.available()&&valid;host.classList.toggle('unavailable',!enabled);
  const bounds=[1,2].map(i=>valid?latest.limits[i]:limits[i-1]),rightEdge=options.rightEdge?.();const key=host.clientWidth+','+host.clientHeight+JSON.stringify(bounds)+','+rightEdge;if(key!==layoutKey){layoutKey=key;fit(bounds,rightEdge);}
  const preview=enabled?options.previewTargets?.():null;
  previewing=Array.isArray(preview)&&preview.length===3&&preview.every(Number.isFinite);
  if(valid){if(!shown)shown=[...latest.joints];const destination=displayAngles(latest.joints,preview,bounds);for(let i=1;i<3;i++)shown[i]+=(destination[i]-shown[i])*(1-Math.exp(-dt/.075));}
  const values=shown||[-80,-5,-5];const nextDraw=values.map(v=>v.toFixed(2)).join(',')+','+previewing+','+options.activeAxis?.()+','+options.precision?.()+','+(latest?.targets||[]).join(',')+','+(latest?.joints||[]).map(v=>Number(v).toFixed(2)).join(',');if(nextDraw!==drawKey){drawKey=nextDraw;draw(values,bounds);}raf=requestAnimationFrame(tick);
 }
 raf=requestAnimationFrame(tick);
 return {destroy(){destroyed=true;cancelAnimationFrame(raf);}};
}
const api={pose,layout,alignRight,Motion,IndicatorMotion,JointControls,delta,displayAngles,sliderBounds,baseDialAngle,baseDialValue,mount};if(typeof module==='object'&&module.exports)module.exports=api;else root.MobileJointRig=api;
})(typeof globalThis==='object'?globalThis:this);
