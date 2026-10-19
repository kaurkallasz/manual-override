/* Game owns occupancy/destruction; Board diagnostics supply overlay positions only. */
(function (root) {
  'use strict';
  function create({container, markerOverlay, camera, status, command}) {
    const entries = new Map();
    let state = null, facts = null, markers = null, connected = false, busy = false, message = '';
    function button(text, label) {
      const node = document.createElement('button');
      node.type = 'button'; node.textContent = text; node.setAttribute('aria-label', label);
      return node;
    }
    const validPoint = value => Array.isArray(value) && value.length === 2 && value.every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1);
    function position(entry, tag, matrix, box) {
      const point = ([x, y]) => new DOMPoint(x * markers.width, y * markers.height).matrixTransform(matrix);
      const corners = Array.isArray(tag.corners) && tag.corners.length === 4 && tag.corners.every(validPoint) ? tag.corners.map(point) : [point(tag.camera)];
      const bounds = {left: Math.min(...corners.map(p => p.x)) - box.left, right: Math.max(...corners.map(p => p.x)) - box.left,
        top: Math.min(...corners.map(p => p.y)) - box.top, bottom: Math.max(...corners.map(p => p.y)) - box.top};
      const visible = bounds.right >= 0 && bounds.left <= box.width && bounds.bottom >= 0 && bounds.top <= box.height;
      entry.root.hidden = !visible;
      if (!visible) return;
      const cy = (bounds.top + bounds.bottom) / 2;
      const place = (node, x, y) => {
        node.style.left = Math.max(2, Math.min(box.width - node.offsetWidth - 2, x)) + 'px';
        node.style.top = Math.max(2, Math.min(box.height - node.offsetHeight - 2, y)) + 'px';
      };
      const atomWidth = entry.choices.offsetWidth, atomHeight = entry.choices.offsetHeight;
      // Keep the code itself clear; near a cropped edge, use the space below it.
      place(entry.choices, bounds.left - atomWidth - 7,
        bounds.left < atomWidth + 9 ? bounds.bottom + 7 : cy - atomHeight / 2);
      place(entry.remove, bounds.right + 7,
        bounds.right + entry.remove.offsetWidth + 9 > box.width ? bounds.bottom + 7 : cy - entry.remove.offsetHeight / 2);
    }
    function render() {
      if (!state || !facts) return;
      const visible = !state.virtual_play && state.journey?.phase !== 'calibration'
        && !container.parentElement.classList.contains('calibration-camera') && markers?.ready
        && !camera.hidden && !markerOverlay.hidden && markers.width > 0 && markers.height > 0;
      container.hidden = !visible;
      status.hidden = true;
      if (!visible) return;
      const matrix = markerOverlay.getScreenCTM(), box = container.getBoundingClientRect();
      if (!matrix || !box.width || !box.height) { container.hidden = true; return; }
      const descriptor = state.turret_controls;
      const compatible = descriptor?.contract === 'photon.game.turret-controls' && descriptor.version === 1;
      const records = new Map((compatible ? descriptor.sockets : []).map(item => [item.socket_id, item]));
      const physicalAtoms = new Set([...records.values()].filter(item => item.atom_source === 'physical').map(item => item.atom_id));
      const reason = !connected || state.status !== 'ready' ? 'Waiting for live game state.'
        : !compatible ? 'Turret controls unavailable: update Photon Game.'
        : !['setup', 'running'].includes(state.phase) ? 'Continue before changing turrets.' : '';
      status.textContent = busy ? 'Applying gamefield control…' : message || reason;
      status.hidden = !status.textContent;
      const tags = new Map((markers.tags || []).filter(tag => validPoint(tag.camera)).map(tag => [tag.id, tag]));
      const targets = (state.level?.sockets || []).filter(socket => tags.has(Number(socket.aruco_id)));
      const core = state.core_sequence || {}, coreControls = compatible && descriptor.core;
      if (coreControls && tags.has(coreControls.aruco_id)) {
        targets.push({socket_id: 'core_38', aruco_id: coreControls.aruco_id, core: true});
      }
      const valid = new Set(targets.map(socket => String(socket.socket_id || socket.id)));
      for (const [sid, entry] of entries) if (!valid.has(sid)) { entry.root.remove(); entries.delete(sid); }
      for (const socket of targets) {
        const sid = String(socket.socket_id || socket.id), tag = tags.get(Number(socket.aruco_id)), isCore = !!socket.core;
        const record = isCore ? coreControls : records.get(sid);
        const controlReason = reason || (isCore ? coreControls.blocked_reason : '');
        const tower = (state.towers || []).find(item => String(item.socket_id) === sid);
        const inactive = !!(tower?.destroyed || tower?.deactivated);
        let entry = entries.get(sid);
        if (!entry) {
          const item = document.createElement('div'); item.className = 'turret-overlay-target'; item.dataset.turretSocket = sid;
          item.setAttribute('role', 'group'); item.setAttribute('aria-label', `ArUco ${socket.aruco_id} controls`);
          const choices = document.createElement('div'); choices.className = 'turret-overlay-atoms';
          const remove = button('X', isCore ? 'Clear first core layer at ArUco 38' : `Destroy turret at ArUco ${socket.aruco_id}`);
          remove.className = 'turret-overlay-destroy'; remove.dataset.destroyTurret = sid;
          remove.onclick = () => send(isCore ? {action: 'operator_core', atom_tag_id: null}
            : {action: 'operator_turret', socket_id: sid, activation: 'deactivated'});
          item.append(choices, remove); container.append(item);
          entry = {root: item, choices, remove, atoms: new Map()}; entries.set(sid, entry);
        }
        const atoms = new Set(facts.loadout.map(role => role.atom_tag_id));
        for (const [id, node] of entry.atoms) if (!atoms.has(id)) { node.remove(); entry.atoms.delete(id); }
        for (const role of facts.loadout) {
          const id = role.atom_tag_id;
          let node = entry.atoms.get(id);
          if (!node) {
            node = button(String(id), `Atom ${id} on ArUco ${socket.aruco_id}`); node.dataset.turretAtom = String(id);
            node.onclick = () => {
              if (isCore) { send({action: 'operator_core', atom_tag_id: id}); return; }
              send({action: 'operator_atom', socket_id: sid, atom_tag_id: id});
            };
            entry.choices.append(node); entry.atoms.set(id, node);
          }
          const team = Object.entries(state.movable_piece_codes || {}).find(([, ids]) => ids.includes(id))?.[0] || '';
          const layer = isCore ? core.first_atom_tag_id === id ? 1 : core.second_atom_tag_id === id ? 2 : 0 : 0;
          const selected = isCore ? !!layer : record?.atom_id === id, physical = !isCore && record?.atom_source === 'physical';
          node.className = 'turret-overlay-atom ' + team;
          node.setAttribute('aria-pressed', String(selected));
          node.dataset.source = selected ? isCore ? (layer === 1 ? core.first_source : core.second_source) : record.atom_source : '';
          const eventGame=state.event_game||state.next_loadouts?.saved_games?.active;
          const locked=eventGame?.atoms?.green&&eventGame.level<4&&!Object.values(eventGame.atoms).some(a=>a.tag===id);
          node.disabled = locked || busy || !!controlReason || !record || physical || physicalAtoms.has(id);
          node.title = (locked?'Second Atom unlocks at L4.':'') || controlReason || (physical || physicalAtoms.has(id)
            ? `${selected ? 'Physical · ' + id + '. ' : ''}Physical detection takes priority.`
            : isCore ? layer ? `Core layer ${layer} · ${node.dataset.source}`
              : core.stage === 'first_tag' ? 'Activate second core layer · opposing team required' : 'Activate first core layer'
              : `${role.label} · ${!tower ? 'Activate turret' : inactive ? 'Rebuild turret' : 'Replenish turret'} · no Atom boost`);
        }
        entry.remove.setAttribute('aria-pressed', String(isCore ? coreControls.cleared : !!tower?.destroyed));
        entry.remove.disabled = busy || !!reason || !record || (isCore ? !coreControls.can_clear : !tower || tower.destroyed);
        entry.remove.title = reason || (isCore ? coreControls.can_clear ? 'Clear the first layer and restart core activation' : controlReason || 'No core layer to clear'
          : tower?.destroyed ? 'Turret destroyed' : tower ? 'Destroy this turret' : 'No turret at this ArUco');
        position(entry, tag, matrix, box);
      }
    }
    async function send(data) {
      if (busy) return;
      busy = true; message = ''; render();
      try { await command(data); }
      catch (error) { message = error.message; }
      finally { busy = false; render(); }
    }
    const resize = new ResizeObserver(render);
    resize.observe(container.parentElement);
    const stop = event => event.stopPropagation();
    container.addEventListener('pointerdown', stop);
    container.addEventListener('click', stop);
    return {
      update(next, gameFacts, detected) { state = next; facts = gameFacts; markers = detected; render(); },
      connected() { connected = true; },
      disconnected() { connected = false; message = ''; render(); },
      destroy() { resize.disconnect(); container.replaceChildren(); entries.clear(); container.removeEventListener('pointerdown', stop); container.removeEventListener('click', stop); },
    };
  }
  root.YTurretControls = {create};
})(typeof window === 'undefined' ? globalThis : window);
