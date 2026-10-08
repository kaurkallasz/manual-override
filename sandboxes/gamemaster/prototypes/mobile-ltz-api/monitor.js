'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const sides = ['green', 'purple'];
  let channel = 'generated', frozen = false, busy = false, loadedKey = '', currentSample = null;
  const hints = {
    generated: 'The full player projection before SSE fields are omitted. Size is its compact JSON representation; the HTTP or SSE serialization can differ.',
    sse: 'The actual JSON envelope in the last sampled outgoing SSE frame. Update packets omit unchanged scene data; snapshot packets contain the full scene. Size includes SSE framing.',
    http: 'The last sampled non-stream HTTP response. JSON bodies are shown; images and files show content type and body size only.'
  };
  const number = (value, digits = 1) => Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : '—';
  const bytes = value => !Number.isFinite(value) ? '—' : value < 1024 ? `${number(value, 0)} B` : value < 1048576 ? `${number(value / 1024)} KiB` : `${number(value / 1048576)} MiB`;
  const clock = stamp => stamp ? new Date(stamp * 1000).toLocaleTimeString() : '—';
  const age = stamp => stamp ? `${number(Math.max(0, Date.now() / 1000 - stamp))}s ago` : 'No traffic yet';
  const historySeconds = 15, maxSampleGap = 2.5, history = [];
  const charts = [
    {key: 'generated', label: 'Generated', unit: 'states/s', minimum: 1},
    {key: 'packets', label: 'SSE packets', unit: 'packets/s', minimum: 1},
    {key: 'bandwidth', label: 'Outgoing body', unit: 'KiB/s', minimum: 1, help: 'SSE and HTTP body bytes combined'},
    {key: 'build', label: 'Mean build', unit: 'ms', minimum: .1},
    {key: 'connections', label: 'Active streams', unit: 'connections', minimum: 1, step: true},
    {key: 'issues', label: 'Delivery issues', unit: 'issues/s', minimum: 1, help: 'HTTP errors, failed streams and unavailable generated states combined'}
  ];
  let baseline = null, clockAnchor = null, selectedTime = null;
  for (const chart of charts) {
    const row = document.createElement('div'); row.className = 'timeline-row';
    row.innerHTML = `<div class="timeline-label"><h3>${chart.label}</h3><div class="timeline-values"><span data-team="green">—</span><span data-team="purple">—</span></div><small class="timeline-scale"></small></div>
      <svg class="timeline-plot" viewBox="0 0 1000 64" preserveAspectRatio="none" role="img" aria-label="${chart.label}: collecting history">
        <path class="timeline-grid" d="M0 4H1000 M0 60H1000 M1 4V60 M333.333 4V60 M666.667 4V60 M999 4V60"/>
        <path class="timeline-series" data-side="green"/><path class="timeline-series" data-side="purple"/>
        <path class="timeline-cursor"/>
      </svg>`;
    if (chart.help) row.querySelector('h3').title = chart.help;
    $('timeline').append(row); chart.row = row; chart.svg = row.querySelector('svg');
  }
  function recordHistory(value) {
    const stamp = value.sampled_at;
    if (!Number.isFinite(stamp)) return;
    if (baseline && (baseline.started_at !== value.started_at || stamp < baseline.sampled_at)) {
      history.length = 0; baseline = null; selectedTime = null;
    }
    clockAnchor = {stamp, received: performance.now()};
    const elapsed = baseline ? stamp - baseline.sampled_at : 0;
    // Selection changes can request another refresh before the next regular poll.
    if (baseline && elapsed < .75) return;
    const sample = {at: stamp, teams: {}};
    for (const side of sides) {
      const team = value.teams[side], previous = baseline?.teams[side];
      if (!team) continue;
      const valid = previous && elapsed <= maxSampleGap && team.generated >= previous.generated && team.sse_bytes >= previous.sse_bytes;
      const delta = key => valid ? Math.max(0, team[key] - previous[key]) : null;
      const rate = key => valid ? delta(key) / elapsed : null;
      const builds = delta('generated');
      sample.teams[side] = {
        generated: rate('generated'), packets: valid ? (delta('sse_snapshots') + delta('sse_updates')) / elapsed : null,
        bandwidth: valid ? (delta('sse_bytes') + delta('http_bytes')) / elapsed / 1024 : null,
        build: builds > 0 ? Math.max(0, (team.build_mean_ms * team.generated - previous.build_mean_ms * previous.generated) / builds) : null,
        connections: team.active_streams,
        issues: valid ? (delta('http_errors') + delta('stream_errors') + delta('generated_unavailable')) / elapsed : null
      };
    }
    history.push(sample); baseline = value;
    renderHistory();
  }
  function renderHistory() {
    if (!clockAnchor) return;
    const end = clockAnchor.stamp + (performance.now() - clockAnchor.received) / 1000, start = end - historySeconds;
    while (history.length && history[0].at < start) history.shift();
    const selected = selectedTime === null ? history.at(-1) : history.reduce((best, item) =>
      !best || Math.abs(item.at - selectedTime) < Math.abs(best.at - selectedTime) ? item : best, null);
    const fresh = selected && (selectedTime !== null || end - selected.at <= maxSampleGap);
    const x = stamp => (stamp - start) / historySeconds * 1000;
    for (const chart of charts) {
      const values = history.flatMap(item => sides.map(side => item.teams[side]?.[chart.key])).filter(Number.isFinite);
      const peak = Math.max(chart.minimum, ...values);
      const ceiling = Math.ceil(peak / (10 ** Math.floor(Math.log10(peak)))) * (10 ** Math.floor(Math.log10(peak)));
      const y = value => 60 - value / ceiling * 56;
      const descriptions = [];
      for (const side of sides) {
        let path = '', previous = null;
        for (const item of history) {
          const value = item.teams[side]?.[chart.key];
          if (!Number.isFinite(value)) { previous = null; continue; }
          const point = `${x(item.at).toFixed(2)},${y(value).toFixed(2)}`;
          path += !previous || item.at - previous.at > maxSampleGap ? `M${point}` : chart.step ? `H${x(item.at).toFixed(2)}V${y(value).toFixed(2)}` : `L${point}`;
          previous = item;
        }
        chart.svg.querySelector(`[data-side="${side}"]`).setAttribute('d', path);
        const text = number(fresh ? selected.teams[side]?.[chart.key] : null, chart.key === 'build' ? 2 : 1);
        chart.row.querySelector(`[data-team="${side}"]`).textContent = text;
        descriptions.push(`${side} ${text} ${chart.unit}`);
      }
      chart.row.querySelector('.timeline-scale').textContent = `0–${number(ceiling, 2)} ${chart.unit}`;
      chart.svg.setAttribute('aria-label', `${chart.label}, last 15 seconds: ${descriptions.join(', ')}`);
      chart.svg.querySelector('.timeline-cursor').setAttribute('d', selectedTime !== null && selected ? `M${x(selected.at).toFixed(2)} 4V60` : '');
    }
    $('timelineTime').textContent = !fresh ? 'Waiting for fresh measurements…' :
      `${selectedTime === null ? 'Latest' : 'Inspecting'} ${clock(selected.at)} · ${number(Math.max(0, end - selected.at))} s ago`;
  }
  $('timeline').onpointermove = event => {
    const rect = charts[0].svg.getBoundingClientRect();
    if (!clockAnchor || event.clientX < rect.left) return;
    const end = clockAnchor.stamp + (performance.now() - clockAnchor.received) / 1000;
    selectedTime = end - historySeconds + Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)) * historySeconds;
    renderHistory();
  };
  $('timeline').onpointerleave = () => { selectedTime = null; renderHistory(); };
  $('timeline').onkeydown = event => {
    if (!['ArrowLeft', 'ArrowRight', 'Escape'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Escape') selectedTime = null;
    else if (history.length) {
      const index = selectedTime === null ? history.length - 1 : history.reduce((best, item, i) =>
        Math.abs(item.at - selectedTime) < Math.abs(history[best].at - selectedTime) ? i : best, 0);
      selectedTime = history[Math.max(0, Math.min(history.length - 1, index + (event.key === 'ArrowLeft' ? -1 : 1)))].at;
    }
    renderHistory();
  };
  for (const side of sides) {
    const card = document.createElement('article');
    card.className = 'team'; card.dataset.side = side;
    card.innerHTML = `<div class="team-heading"><h2>${side === 'green' ? 'Green' : 'Purple'}</h2><span class="age" data-value="age">No traffic yet</span></div>
      <div class="metrics"><div class="metric"><strong data-value="generated_hz">—</strong><span>Generated / s</span></div>
      <div class="metric"><strong data-value="emitted_hz">—</strong><span>SSE packets / s</span></div>
      <div class="metric"><strong data-value="active_streams">0</strong><span>Active streams</span></div>
      <div class="metric"><strong data-value="emitted_bytes_per_s">—</strong><span>SSE body / s</span></div></div>
      <dl class="details">${[
        ['build', 'Build · last / mean / peak'], ['generated', 'States generated'],
        ['packets', 'Snapshots / updates / pings'], ['sse_bytes', 'SSE bytes emitted'],
        ['http', 'HTTP responses / errors'], ['http_bytes', 'HTTP response bytes'],
        ['unavailable', 'Unavailable states'], ['connections', 'Opened / closed / failed']
      ].map(([key, label]) => `<div><dt>${label}</dt><dd data-value="${key}">—</dd></div>`).join('')}</dl>`;
    $('teams').append(card);
  }
  function renderStats(value) {
    recordHistory(value);
    for (const side of sides) {
      const team = value.teams[side]; if (!team) continue;
      const card = document.querySelector(`.team[data-side="${side}"]`);
      const values = {
        age: age(team.last_emitted_at || team.last_generated_at),
        generated_hz: number(team.generated_hz), emitted_hz: number(team.emitted_hz),
        active_streams: number(team.active_streams, 0), emitted_bytes_per_s: bytes(team.emitted_bytes_per_s),
        build: `${number(team.build_last_ms)} / ${number(team.build_mean_ms)} / ${number(team.build_max_ms)} ms`,
        generated: number(team.generated, 0), sse_bytes: bytes(team.sse_bytes),
        packets: `${team.sse_snapshots} / ${team.sse_updates} / ${team.sse_pings}`,
        http: `${team.http_responses} / ${team.http_errors}`, http_bytes: bytes(team.http_bytes),
        unavailable: number(team.generated_unavailable, 0),
        connections: `${team.opened_streams} / ${team.closed_streams} / ${team.stream_errors}`
      };
      for (const [key, text] of Object.entries(values)) card.querySelector(`[data-value="${key}"]`).textContent = text;
    }
    const fragment = document.createDocumentFragment();
    for (const item of value.recent.slice(0, 20)) {
      const row = document.createElement('tr');
      const cells = [clock(item.at), item.side, item.route || item.kind.replaceAll('_', ' '), item.action || '—',
        item.status ?? '—', bytes(item.bytes), Number.isFinite(item.duration_ms) ? `${number(item.duration_ms)} ms` : '—'];
      cells.forEach((text, i) => {
        const cell = document.createElement('td'); cell.textContent = text;
        if (i === 1) cell.dataset.team = item.side;
        if (i === 4 && item.status >= 400) cell.className = 'bad';
        row.append(cell);
      });
      fragment.append(row);
    }
    if (!fragment.childNodes.length) {
      const row = document.createElement('tr'), cell = document.createElement('td');
      cell.colSpan = 7; cell.textContent = 'No player requests or stream connections observed yet.'; row.append(cell); fragment.append(row);
    }
    $('activity').replaceChildren(fragment);
    $('startedAt').textContent = `Recording since ${new Date(value.started_at * 1000).toLocaleString()}`;
    $('updatedAt').textContent = `Updated ${clock(value.sampled_at)}`;
    $('connectionStatus').textContent = '● Live · read only';
    $('connectionStatus').style.color = '';
    $('error').hidden = !value.observer_errors;
    $('error').textContent = value.observer_errors ? `${value.observer_errors} monitoring errors recorded. Player delivery remains independent; check server logs.` : '';
  }
  function renderSample(sample) {
    currentSample = sample || null;
    $('download').disabled = !sample;
    $('fields').replaceChildren();
    if (!sample) {
      $('sampleMeta').textContent = 'No payload sampled yet. Open a player page to generate traffic.';
      $('payload').textContent = 'Waiting for player traffic…'; return;
    }
    $('sampleMeta').textContent = `${sample.kind.toUpperCase()} · ${bytes(sample.body_bytes)} · sampled ${clock(sample.captured_at)}${sample.route ? ` · ${sample.route}` : ''}${sample.truncated ? ' · preview truncated' : ''}`;
    const scrollTop = $('payload').scrollTop, scrollLeft = $('payload').scrollLeft;
    $('payload').textContent = sample.preview;
    $('payload').scrollTop = scrollTop; $('payload').scrollLeft = scrollLeft;
    for (const field of sample.fields || []) {
      const row = document.createElement('tr');
      [field.name, bytes(field.bytes), field.items ?? '—'].forEach((text, i) => {
        const cell = document.createElement('td'); cell.textContent = text;
        if (i === 0) { cell.className = 'field-name'; cell.title = field.name; }
        row.append(cell);
      });
      $('fields').append(row);
    }
  }
  async function get(query = '') {
    const response = await fetch(`api/monitor${query}`, {cache: 'no-store'});
    if (!response.ok) throw Error(`Diagnostics unavailable (HTTP ${response.status}). Game Master access is required.`);
    const value = await response.json();
    if (value.contract !== 'mobile.delivery-diagnostics' || value.version !== 1) throw Error('Unexpected diagnostics response.');
    return value;
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const value = await get(); renderStats(value);
      const side = $('team').value, selectedChannel = channel;
      const meta = value.teams[side]?.samples[selectedChannel];
      const key = `${side}:${selectedChannel}:${meta?.captured_at ?? 'none'}`;
      if (!frozen && key !== loadedKey) {
        const detail = meta ? await get(`?side=${side}&channel=${selectedChannel}&payloads=1`) : null;
        if (!frozen && side === $('team').value && selectedChannel === channel) {
          renderSample(detail?.teams[side]?.samples[selectedChannel]); loadedKey = key;
        }
      }
    } catch (error) {
      $('error').hidden = false; $('error').textContent = error.message;
      $('connectionStatus').textContent = '● Disconnected · retrying';
      $('connectionStatus').style.color = '#ffa890';
    } finally { busy = false; }
  }
  function selectChannel(next = channel) {
    channel = next; frozen = false; loadedKey = '';
    $('freeze').textContent = 'Freeze payload'; $('freeze').setAttribute('aria-pressed', 'false');
    for (const tab of document.querySelectorAll('[data-channel]')) {
      const selected = tab.dataset.channel === channel;
      tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
    }
    $('payloadPanel').setAttribute('aria-labelledby', `tab-${channel}`);
    $('channelHelp').textContent = hints[channel]; renderSample(null); refresh();
  }
  for (const tab of document.querySelectorAll('[data-channel]')) {
    tab.onclick = () => selectChannel(tab.dataset.channel);
    tab.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const keys = Object.keys(hints), index = keys.indexOf(channel);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
      selectChannel(keys[next]); $(`tab-${keys[next]}`).focus();
    };
  }
  $('team').onchange = () => selectChannel();
  $('freeze').onclick = () => {
    frozen = !frozen; $('freeze').textContent = frozen ? 'Resume payload' : 'Freeze payload';
    $('freeze').setAttribute('aria-pressed', String(frozen)); if (!frozen) refresh();
  };
  $('download').onclick = () => {
    if (!currentSample) return;
    const url = URL.createObjectURL(new Blob([currentSample.preview], {type: 'text/plain;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url;
    link.download = `mobile-${$('team').value}-${channel}-${Math.floor(currentSample.captured_at)}.txt`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  $('channelHelp').textContent = hints[channel]; refresh(); setInterval(refresh, 1000); setInterval(renderHistory, 250);
})();
