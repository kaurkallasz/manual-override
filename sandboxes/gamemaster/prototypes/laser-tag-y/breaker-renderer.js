/* Presentation only: Game owns poses, flight, damage and shielding. */
(function (global) {
  'use strict';
  function pose(enemy, time) {
    const combat = enemy.combat;
    if (combat?.variant !== 'archer') return null;
    if (combat.state === 'aim') {
      const duration = Number(combat.release_at) - Number(combat.started_at);
      return time - Number(combat.started_at) < duration * .45 ? 4 : 5;
    }
    if (combat.state === 'recover') return time - Number(combat.last_shot_at) < .18 ? 6 : 7;
    return Math.floor(time * 8 + Number(enemy.id || 0)) % 4;
  }
  function frames(image, makeCanvas = () => document.createElement('canvas')) {
    const result = [];
    const width = image.naturalWidth / 4, height = image.naturalHeight / 2;
    if (!Number.isFinite(width) || !Number.isFinite(height) || width < 1 || height < 1) return result;
    for (let i = 0; i < 8; i++) {
      const frame = makeCanvas();
      frame.width = frame.height = 256;
      const ctx = frame.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(image, i % 4 * width, Math.floor(i / 4) * height, width, height, 0, 0, 256, 256);
      result.push(frame);
    }
    return result;
  }
  function fallback(ctx, enemy, x, y, size) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(Number(enemy.facing_y || 0), Number(enemy.facing_x || 0)) - Math.PI / 2);
    ctx.strokeStyle = '#ee3a48'; ctx.lineWidth = Math.max(2, size * .1);
    ctx.beginPath();ctx.moveTo(-size * .23, -size * .15);ctx.lineTo(size * .23, -size * .15);ctx.stroke();
    ctx.strokeStyle = '#dfad67';ctx.lineWidth = 1.8;
    ctx.beginPath();ctx.arc(0, size * .05, size * .34, 0, Math.PI);ctx.stroke();
    ctx.beginPath();ctx.moveTo(-size * .34, size * .05);ctx.lineTo(size * .34, size * .05);ctx.stroke();
    ctx.restore();
  }
  function arrows(ctx, state, time) {
    const flights = state.enemy_arrows || [];
    ctx.save();ctx.lineWidth = 1.7;ctx.strokeStyle = '#f4dca2';ctx.beginPath();
    const feathers = [];
    for (const shot of flights) {
      const duration = Number(shot.impact_at) - Number(shot.launch_at);
      if (!(duration > 0) || time < shot.launch_at || time > Number(shot.impact_at) + .08) continue;
      const p = Math.max(0, Math.min(1, (time - shot.launch_at) / duration));
      const dx = shot.target_x - shot.origin_x, dy = shot.target_y - shot.origin_y;
      const length = Math.hypot(dx, dy) || 1, ux = dx / length, uy = dy / length;
      const x = shot.origin_x + dx * p, y = shot.origin_y + dy * p;
      ctx.moveTo(x - ux * 13, y - uy * 13);ctx.lineTo(x, y);
      ctx.moveTo(x - ux * 4 - uy * 2, y - uy * 4 + ux * 2);ctx.lineTo(x, y);
      ctx.lineTo(x - ux * 4 + uy * 2, y - uy * 4 - ux * 2);
      feathers.push([x - ux * 11, y - uy * 11, ux, uy]);
    }
    ctx.stroke();ctx.strokeStyle = '#ff4055';ctx.lineWidth = 2.5;ctx.beginPath();
    for (const [x, y, ux, uy] of feathers) {
      ctx.moveTo(x - ux * 3 - uy * 3, y - uy * 3 + ux * 3);ctx.lineTo(x, y);
      ctx.lineTo(x - ux * 3 + uy * 3, y - uy * 3 - ux * 3);
    }
    ctx.stroke();
    for (const hit of (state.enemy_arrow_impacts || []).slice(-64)) {
      const age = time - hit.at;
      if (age < 0 || age > .35) continue;
      ctx.globalAlpha = 1 - age / .35;
      ctx.strokeStyle = hit.kind === 'blocked' ? '#a6eaff' : '#ff7c58';ctx.lineWidth = 1.5;
      const radius = 3 + age * 17;
      ctx.beginPath();ctx.moveTo(hit.x-radius, hit.y);ctx.lineTo(hit.x+radius, hit.y);
      ctx.moveTo(hit.x, hit.y-radius);ctx.lineTo(hit.x, hit.y+radius);ctx.stroke();
    }
    ctx.restore();
  }
  const api = {version: 1, pose, frames, fallback, arrows};
  global.BreakerRenderer = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window === 'undefined' ? globalThis : window);
