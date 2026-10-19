export const AI_RANGES = {enabled:[0,1],confidence:[10,95],nms:[10,90],max_fps:[1,10],max_boxes:[1,10],stale_ms:[200,3000]};

export function validAISettings(settings) {
  return !!settings && Object.keys(settings).every(key => Object.hasOwn(AI_RANGES,key)) &&
    Object.entries(AI_RANGES).every(([key,[lo,hi]]) => Number.isInteger(settings[key]) && settings[key]>=lo && settings[key]<=hi);
}

export function validAISnapshot(data) {
  const label=value=>typeof value==='string' && value.length>0 && value.length<=64 && !/[\x00-\x1f]/.test(value);
  return data?.kind==='ai' && data.protocol===1 && label(data.model) && label(data.class_name) &&
    validAISettings(data.settings) && ['ready','disabled','loading','error','waiting_for_video','waiting_for_detection'].includes(data.state) &&
    Number.isInteger(data.frame_seq) && data.frame_seq>=0 && data.frame_seq<=4294967295 && Number.isInteger(data.epoch) && data.epoch>0 && data.epoch<=4294967295 &&
    Number.isInteger(data.width) && data.width>=0 && data.width<=640 && Number.isInteger(data.height) && data.height>=0 && data.height<=480 &&
    (data.state!=='ready' || (data.width>0 && data.height>0 && data.frame_seq>0 && data.age_ms>=0)) &&
    Number.isInteger(data.age_ms) && data.age_ms>=-1 && Array.isArray(data.boxes) && data.boxes.length<=10 &&
    data.boxes.every(b => b && typeof b==='object' && (!Object.hasOwn(b,'class_name') || label(b.class_name)) && ['x','y','w','h','score'].every(k => Number.isInteger(b[k])) &&
      b.x>=0 && b.y>=0 && b.w>0 && b.h>0 && b.x+b.w<=10000 && b.y+b.h<=10000 && b.score>=0 && b.score<=100);
}

// The UVC stream and CDC results have separate host delivery times. Render only
// recent, matching-size results; these are deliberately not called frame-exact.
export function overlayBoxes(data, {width,height,now,receivedAt,transitMs=0}) {
  if (!validAISnapshot(data) || data.state!=='ready' || !data.settings.enabled || !data.frame_seq ||
      width!==data.width || height!==data.height || data.age_ms<0 || !Number.isFinite(receivedAt) ||
      !Number.isFinite(now) || !Number.isFinite(transitMs) || transitMs<0 || now<receivedAt ||
      data.age_ms+transitMs+now-receivedAt>data.settings.stale_ms) return [];
  return data.boxes.slice(0,data.settings.max_boxes).map(b => ({
    x:b.x*width/10000,y:b.y*height/10000,w:b.w*width/10000,h:b.h*height/10000,score:b.score,class_name:b.class_name || data.class_name,
  }));
}

export function drawBoxes(context, boxes, width, height, labels=true) {
  context.save();
  const font=Math.max(11,Math.round(width/40));
  context.font=`600 ${font}px -apple-system, sans-serif`;
  context.lineWidth=Math.max(2,width/240); context.textBaseline='top';
  for (const b of boxes) {
    context.strokeStyle='#c4ef8a'; context.strokeRect(b.x,b.y,b.w,b.h);
    if (!labels) continue;
    const label=`${b.class_name || 'Object'} ${b.score}%`, labelWidth=Math.min(width,context.measureText(label).width+8);
    const x=Math.max(0,Math.min(b.x,width-labelWidth)), y=Math.max(0,Math.min(b.y-font-7,height-font-7));
    context.fillStyle='#c4ef8a'; context.fillRect(x,y,labelWidth,font+6);
    context.fillStyle='#14200e'; context.fillText(label,x+4,y+3);
  }
  context.restore();
}
