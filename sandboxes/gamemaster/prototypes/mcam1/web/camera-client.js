/** Browser adapter for hhh.camera.controls / hhh.camera.still, both version 1.
 * The server owns capture. No camera or robot connection is opened by import.
 */
export class CameraStudioClient {
  constructor(base) { this.base = base.replace(/\/$/, ''); }
  async json(path, options, allowUnavailable=false) {
    const response = await fetch(`${this.base}${path}`, {cache:'no-store', ...options});
    const data = await response.json();
    if (!response.ok || (!allowUnavailable && data.status === 'unavailable')) throw new Error(data.error || `Camera unavailable (${response.status})`);
    return data;
  }
  async control(action = 'get', name, value) {
    const data = await this.json('/api/controls', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action,name,value})});
    if (data.contract !== 'hhh.camera.controls' || data.version !== 1 || data.status !== 'ready') throw new Error('Unsupported camera controls contract');
    return data;
  }
  async frame() {
    const data = await this.json('/api/frame');
    if (data.contract !== 'hhh.camera.still' || data.version !== 1 || data.status !== 'ready' || data.source !== 'camera') throw new Error('Unsupported still-image contract');
    return data;
  }
  async ai(action='get',name,value) {
    const data=await this.json('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,name,value})},true);
    if (data.contract!=='hhh.camera.detections' || data.version!==1 || data.transport_status!=='ready' || !['ready','unavailable'].includes(data.status)) throw new Error('Unsupported camera detections contract');
    return data;
  }
  async captureStill() {
    const response = await fetch(`${this.base}/api/still`, {cache:'no-store'});
    if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Still unavailable'); }
    if (response.headers.get('X-Camera-Contract') !== 'hhh.camera.still' || response.headers.get('X-Camera-Version') !== '1') throw new Error('Unsupported still-image contract');
    const metadata = {width:Number(response.headers.get('X-Camera-Width')), height:Number(response.headers.get('X-Camera-Height')), capturedAt:Number(response.headers.get('X-Camera-Captured-At')), frameId:Number(response.headers.get('X-Camera-Frame-Id')), corrected:false};
    if (!(metadata.width > 0 && metadata.height > 0 && Number.isFinite(metadata.capturedAt))) throw new Error('Invalid still-image metadata');
    return {blob:await response.blob(), ...metadata};
  }
  async disconnect() { await this.json('/api/disconnect', {method:'POST',keepalive:true}, true); }
}
