// One authenticated presence stream for the outer player page, including when
// the controller itself is nested in dashboard iframes.
(() => {
  if (window.top !== window || window.hhhPlayerSession) return;
  window.hhhPlayerSession = true;
  const team = document.currentScript.dataset.team;
  if (!['green', 'purple'].includes(team)) return;
  const root = `/s/${team}`;
  let stream = null, checking = false, ended = false, retry = null;
  function close() { stream?.close();stream = null;clearTimeout(retry); }
  function end() {
    if (ended) return;
    ended = true;close();
    location.replace(`${root}/login?ended=1&next=${encodeURIComponent(root + '/p/mobile-ltz/')}`);
  }
  async function check() {
    if (checking || ended || document.hidden) return;
    checking = true;
    try {
      const response = await fetch(`${root}/api/meta`, {cache:'no-store'});
      if (response.status === 401 || response.redirected) { end();return; }
      if (response.ok && !stream) open();
    } catch (_) { /* A network outage is not proof of revocation. */ }
    finally {
      checking = false;
      if (!stream && !ended && !document.hidden) retry = setTimeout(check, 3000);
    }
  }
  function open() {
    if (ended || document.hidden || stream) return;
    stream = new EventSource(`${root}/api/player-session/events`);
    stream.onmessage = event => { if (JSON.parse(event.data).active === false) end(); };
    stream.onerror = () => { close();check(); };
  }
  document.addEventListener('visibilitychange', () => { if (document.hidden) close();else check(); });
  window.addEventListener('pagehide', close);
  window.addEventListener('pageshow', check);
  open();
})();
