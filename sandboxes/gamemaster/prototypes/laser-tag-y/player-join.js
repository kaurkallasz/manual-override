(() => {
  const host = document.getElementById('playerJoin');
  if (!host) return;
  const cards = document.getElementById('playerJoinCards');
  const status = document.getElementById('playerJoinStatus');
  const address = document.getElementById('playerJoinAddress');
  const regenerate = document.getElementById('regeneratePlayerCodes');
  const copyField = document.getElementById('playerJoinCopy');
  const endpoint = location.pathname.split('/p/')[0] + '/api/player-join';
  const management = location.pathname.split('/p/')[0] + '/api/player-sessions';
  const resetButton = document.getElementById('cleanResetPlayers');
  const resetStatus = document.getElementById('playerResetStatus');
  const rows = document.getElementById('playerConnectionRows');
  let timer = null, busy = false, resetBusy = false, resetBlocked = false, pendingId = null;
  let connections = null, generation, ready = false, resetMessage = '';
  const pendingKey = 'ltz-clean-reset-operation';
  try { pendingId = sessionStorage.getItem(pendingKey); } catch (_) {}
  function remember(value) {
    pendingId = value;
    try { if (value) sessionStorage.setItem(pendingKey, value);else sessionStorage.removeItem(pendingKey); } catch (_) {}
  }
  function hideCodes() {
    clearTimeout(timer);cards.hidden = true;cards.replaceChildren();copyField.hidden = true;copyField.value = '';address.textContent = '';
  }
  function buttons() {
    regenerate.disabled = busy || resetBusy || resetBlocked;
    resetButton.disabled = resetBusy || !ready;
    resetButton.textContent = resetBusy ? 'Resetting…' : pendingId ? 'Retry clean reset' : 'Clean reset';
  }
  function showConnections(data) {
    if (data.contract !== 'hub.player-sessions' || data.version !== 1 || !Array.isArray(data.rows)) throw Error('Player connections unavailable.');
    ready = !data.unavailable;
    const wasBlocked = resetBlocked;
    resetBlocked = data.blocked;
    if (data.reset) remember(data.reset.id);
    else if (pendingId && data.generation === pendingId) {
      remember(null);resetMessage = 'Clean reset complete. Players can scan the fresh codes to join.';
    }
    if (resetBlocked) {
      hideCodes();status.textContent = 'Join codes are unavailable until Clean reset finishes.';
    } else if (wasBlocked || generation !== undefined && generation !== data.generation) load();
    generation = data.generation;
    const connected = data.rows.filter(row => !row.revoked && row.status !== 'disconnected').length;
    const error = data.reset?.error || data.error;
    resetStatus.dataset.error = String(!!error);
    resetStatus.textContent = error ? `${error}${resetBlocked ? ' Access remains blocked. Retry clean reset when resolved.' : ''}`
      : resetBlocked ? 'Clean reset in progress. Player access is blocked.' : resetMessage || `${connected} player browser${connected === 1 ? '' : 's'} connected.`;
    const content = data.rows.slice().reverse().map(row => {
      const tr = document.createElement('tr');tr.dataset.team = row.team;tr.dataset.ended = String(row.revoked);
      const age = Math.max(0, Math.floor(Date.now() / 1000 - row.last_seen));
      for (const text of [row.team === 'green' ? 'Green' : 'Purple', row.player_name, row.ip, row.status,
        age < 5 ? 'Now' : age < 60 ? `${age}s ago` : `${Math.floor(age / 60)}m ago`]) {
        const td = document.createElement('td');td.textContent = text;tr.append(td);
      }
      return tr;
    });
    if (!content.length) {
      const tr = document.createElement('tr'), td = document.createElement('td');td.colSpan = 5;td.textContent = 'No player sessions yet.';tr.append(td);content.push(tr);
    }
    rows.replaceChildren(...content);buttons();
  }
  function openConnections() {
    if (connections || document.hidden) return;
    connections = new EventSource(management + '/events');
    connections.onmessage = event => {
      try { showConnections(JSON.parse(event.data)); }
      catch (error) { ready = false;resetStatus.textContent = error.message;buttons(); }
    };
    connections.onerror = () => { ready = false;resetStatus.textContent = 'Reconnecting to player sessions…';buttons(); };
  }
  resetButton.onclick = async () => {
    if (resetBusy || !ready) return;
    if (!pendingId) remember('clean-' + Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2,'0')).join(''));
    const operation = pendingId;
    resetBusy = true;resetBlocked = true;resetMessage = '';hideCodes();buttons();
    resetStatus.textContent = 'Disconnecting players, stopping controls and resetting the game…';
    status.textContent = 'Waiting for Clean reset to finish…';
    try {
      const response = await fetch(management + '/clean-reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({operation_id:operation})});
      const data = await response.json();
      if (!response.ok || !data.ok) throw Error(data.error || 'Clean reset failed.');
      remember(null);resetBlocked = false;resetMessage = 'Clean reset complete. Players can scan the fresh codes to join.';
      resetStatus.textContent = resetMessage;resetStatus.dataset.error = 'false';await load();
    } catch (error) {
      // The POST response may be lost after a successful commit. Reconcile
      // before offering Retry so a network error cannot start another reset.
      try {
        const current = await fetch(management, {cache:'no-store'});
        if (current.ok) showConnections(await current.json());
      } catch (_) {}
      if (generation === operation) {
        remember(null);resetBlocked = false;resetMessage = 'Clean reset complete. Players can scan the fresh codes to join.';
        resetStatus.textContent = resetMessage;resetStatus.dataset.error = 'false';await load();
      } else {
        if (!pendingId) remember(operation);
        resetStatus.textContent = `${error.message} Retry uses the same reset operation.`;resetStatus.dataset.error = 'true';
      }
    } finally { resetBusy = false;buttons(); }
  };

  async function copyLink(url) {
    try {
      if (!navigator.clipboard?.writeText) throw Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      status.textContent = 'Join link copied.';
    } catch (_) {
      // LAN HTTP may not expose the Clipboard API; offer a selectable link.
      copyField.hidden = false;
      copyField.value = url;
      copyField.focus();
      copyField.select();
      status.textContent = 'Copy the selected join link.';
    }
  }

  function render(data) {
    if (data.contract !== 'hub.player-join' || data.version !== 1 || data.status !== 'ready'
        || !Array.isArray(data.links) || data.links.length !== 2
        || !Number.isFinite(data.expires_at) || data.expires_at * 1000 <= Date.now()) {
      throw Error('Join codes unavailable. Regenerate codes to try again.');
    }
    const nodes = ['green', 'purple'].map(team => {
      const link = data.links.find(item => item.team === team);
      const url = link && new URL(link.url);
      if (!link || !['http:', 'https:'].includes(url.protocol)
          || url.pathname !== `/s/${team}/login` || !url.hash.startsWith('#join=')
          || !link.qr?.startsWith('data:image/png;base64,')) throw Error('Invalid team join link.');
      const card = document.createElement('article');
      card.className = 'player-join-card';card.dataset.team = team;
      const title = document.createElement('h3');title.textContent = team === 'green' ? 'Green' : 'Purple';
      const image = document.createElement('img');image.src = link.qr;
      image.alt = `Scan to join ${title.textContent} Mobile LTZ`;image.width = 280;image.height = 280;
      const help = document.createElement('p');help.textContent = 'Mobile LTZ · automatic sign-in';
      const copy = document.createElement('button');copy.type = 'button';copy.textContent = 'Copy join link';
      copy.onclick = () => copyLink(link.url);
      card.append(title, image, help, copy);
      return card;
    });
    cards.replaceChildren(...nodes);cards.hidden = false;
    host.dataset.error = 'false';
    address.textContent = `Game server: ${data.origin}`;
    status.textContent = `Codes valid until ${new Date(data.expires_at * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}. Regenerating replaces both join links.`;
    timer = setTimeout(() => load(), Math.max(0, data.expires_at * 1000 - Date.now()) + 50);
  }

  async function load(rotate = false) {
    if (busy || resetBlocked) return;
    busy = true;regenerate.disabled = true;clearTimeout(timer);
    // Hide potentially stale links while checking, including after a restart.
    cards.hidden = true;cards.replaceChildren();copyField.hidden = true;copyField.value = '';
    address.textContent = '';status.textContent = rotate ? 'Generating new join codes…' : 'Loading team join codes…';
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(endpoint, {
        method: rotate ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal,
        ...(rotate ? {headers:{'Content-Type':'application/json'}, body:'{}'} : {}),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Join codes unavailable.');
      if (!resetBlocked) render(data);
    } catch (error) {
      host.dataset.error = 'true';
      status.textContent = controller.signal.aborted ? 'Loading timed out. Regenerate codes to try again.' : error.message;
    } finally { clearTimeout(timeout);busy = false;buttons(); }
  }

  regenerate.onclick = () => load(true);
  window.addEventListener('pageshow', event => { if (event.persisted) { load();openConnections(); } });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { load();openConnections(); } else { connections?.close();connections = null; } });
  window.addEventListener('pagehide', () => { clearTimeout(timer);copyField.value = '';connections?.close();connections = null; });
  load();openConnections();
})();
