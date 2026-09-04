/* Photon Level's local authoring preview. No game or sibling-module inputs. */
"use strict";

function markerForSocket(socket, original) {
  const deltaSize = socket.size - original.size;
  return {
    x: original.marker_x + socket.x - original.x + deltaSize * original.marker_resize_x,
    y: original.marker_y + socket.y - original.y + deltaSize * original.marker_resize_y,
    size: original.marker_size,
    id: socket.aruco_id,
  };
}

function mapPoint(clientX, clientY, rect, width, height) {
  return { x: (clientX - rect.left) * width / rect.width,
    y: (clientY - rect.top) * height / rect.height };
}

function drawSceneItem(ctx, item, images) {
  ctx.save();
  if (item.kind === "sprite") {
    ctx.translate(item.origin_x, item.origin_y);
    ctx.rotate((item.rotation_degrees || 0) * Math.PI / 180);
    const destination = [item.draw_x, item.draw_y, item.width, item.height];
    if (item.source) ctx.drawImage(images.get(item.asset_id), ...item.source, ...destination);
    else ctx.drawImage(images.get(item.asset_id), ...destination);
  } else if (item.kind === "activation_zone") {
    ctx.fillStyle = "#ff9f4326";
    ctx.strokeStyle = "#ff9f43";
    ctx.lineWidth = 3;
    ctx.fillRect(item.x, item.y, item.width, item.height);
    ctx.strokeRect(item.x, item.y, item.width, item.height);
  } else if (item.kind === "atom_start") {
    ctx.fillStyle = item.owner === "green" ? "#35d07f" : "#c084fc";
    ctx.beginPath();
    ctx.arc(item.x, item.y, 15, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#061018";
    ctx.font = "bold 13px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(item.atom_tag_id), item.x, item.y);
  } else {
    throw new Error(`Unsupported preview item: ${item.kind}`);
  }
  ctx.restore();
}

// Pure display geometry is also executable by the module's Node smoke test.
if (typeof module !== "undefined") module.exports = { markerForSocket, mapPoint, drawSceneItem };

if (typeof document !== "undefined") {
  const canvas = document.querySelector("#map"), ctx = canvas.getContext("2d");
  const list = document.querySelector("#sockets"), status = document.querySelector("#status");
  const save = document.querySelector("#save"), reload = document.querySelector("#reload");
  const confirmReload = document.querySelector("#confirm-reload");
  const discard = document.querySelector("#discard"), keep = document.querySelector("#keep");
  const placements = document.querySelector("#placements"), markers = document.querySelector("#markers");
  const routes = document.querySelector("#routes");
  let level = null, original = new Map(), images = new Map(), revision = 0;
  let drag = null, selected = null, dirty = false, busy = false;

  function setStatus(text, error = false) {
    status.textContent = text;
    status.style.color = error ? "#ff837a" : "#b6ff3a";
  }

  function setBusy(value) {
    busy = value;
    save.disabled = value || !level;
    reload.disabled = value;
    discard.disabled = value;
    keep.disabled = value;
    list.querySelectorAll("input").forEach(input => { input.disabled = value; });
  }

  function drawMarker(marker) {
    ctx.drawImage(images.get(`marker/${marker.id}`), marker.x - marker.size / 2,
      marker.y - marker.size / 2, marker.size, marker.size);
    label(`A${marker.id}`, marker.x, marker.y + marker.size / 2 + 14);
  }

  function label(text, x, y) {
    ctx.font = "bold 16px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const width = ctx.measureText(text).width + 10;
    ctx.fillStyle = "#071018e8";
    ctx.fillRect(x - width / 2, y - 11, width, 22);
    ctx.fillStyle = "#f4f8ff";
    ctx.fillText(text, x, y);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!level) return;
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#030609";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const layer of level.scene.layers) {
      ctx.save();
      ctx.globalAlpha = layer.opacity ?? 1;
      for (const item of layer.items) drawSceneItem(ctx, item, images);
      ctx.restore();
    }
    if (routes.checked) {
      ctx.save();
      ctx.strokeStyle = "#ffe59b";
      ctx.lineWidth = 3;
      ctx.setLineDash([10, 8]);
      for (const points of Object.values(level.paths)) {
        ctx.beginPath();
        points.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y));
        ctx.stroke();
      }
      ctx.restore();
    }
    if (placements.checked) {
      for (const socket of level.sockets) {
        const color = socket.owner === "purple" ? "#cf99ff"
          : socket.owner === "green" ? "#59f6a5" : "#ffe59b";
        ctx.strokeStyle = socket.id === selected ? "#fff" : color;
        ctx.fillStyle = `${color}18`;
        ctx.lineWidth = socket.id === selected ? 4 : 2;
        const left = socket.x - socket.size / 2, top = socket.y - socket.size / 2;
        ctx.fillRect(left, top, socket.size, socket.size);
        ctx.strokeRect(left, top, socket.size, socket.size);
        ctx.beginPath();
        ctx.moveTo(socket.x - 10, socket.y); ctx.lineTo(socket.x + 10, socket.y);
        ctx.moveTo(socket.x, socket.y - 10); ctx.lineTo(socket.x, socket.y + 10);
        ctx.stroke();
        label(`${socket.id} · A${socket.aruco_id}`, socket.x, top + 14);
      }
    }
    if (markers.checked) {
      for (const socket of level.sockets) drawMarker(markerForSocket(socket, original.get(socket.id)));
      const core = level.core;
      drawMarker({ x: core.marker_x, y: core.marker_y, size: core.marker_size, id: 38 });
    }
  }

  function markDirty() {
    dirty = true;
    confirmReload.hidden = true;
    draw();
    setStatus(`Unsaved changes · based on revision ${revision}`);
  }

  function renderRows() {
    list.replaceChildren();
    for (const socket of level.sockets) {
      const row = document.createElement("div");
      row.className = `socket${socket.id === selected ? " selected" : ""}`;
      const name = document.createElement("span");
      name.textContent = `${socket.id.replace("socket_", "S")} · A${socket.aruco_id}`;
      row.append(name);
      for (const key of ["x", "y", "size"]) {
        const input = document.createElement("input");
        input.type = "number";
        input.step = "1";
        input.min = key === "size" ? "96" : "0";
        input.max = String(key === "size" ? 208 : key === "x" ? level.width : level.height);
        input.value = socket[key];
        input.setAttribute("aria-label", `${socket.id} ${key}`);
        input.onfocus = () => { selected = socket.id; draw(); };
        input.onchange = () => {
          if (!input.checkValidity() || input.value === "") {
            input.reportValidity();
            input.value = socket[key];
            return;
          }
          socket[key] = Number(input.value);
          markDirty();
        };
        row.append(input);
      }
      list.append(row);
    }
  }

  async function load() {
    confirmReload.hidden = true;
    setBusy(true);
    setStatus("Loading authored graphics…");
    try {
      const response = await fetch("api/editor", { cache: "no-store" });
      const next = await response.json();
      if (!response.ok || next.status !== "ready") throw new Error(next.error || "Level unavailable");
      if (next.contract !== "photon.level.editor" || next.version !== 1
          || next.level?.scene?.contract !== "photon.visual-scene" || next.level.scene.version !== 1) {
        throw new Error("Incompatible level preview contract");
      }
      const loaded = new Map(await Promise.all(Object.entries(next.assets).map(([id, url]) => (
        new Promise((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve([id, image]);
          image.onerror = () => reject(new Error(`Artwork unavailable: ${id}`));
          image.src = url;
        })
      ))));
      images = loaded;
      level = next.level;
      original = new Map(level.sockets.map(socket => [socket.id, { ...socket }]));
      revision = next.revision;
      canvas.width = level.width;
      canvas.height = level.height;
      dirty = false;
      selected = null;
      renderRows();
      draw();
      setStatus(`Authored map · revision ${revision}`);
    } catch (error) {
      level = null;
      list.replaceChildren();
      draw();
      setStatus(`Preview unavailable: ${error.message}`, true);
    } finally {
      setBusy(false);
    }
  }

  const pointer = event => mapPoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), level.width, level.height);
  canvas.onpointerdown = event => {
    if (!level || busy || event.button !== 0 || drag) return;
    const point = pointer(event);
    const candidates = level.sockets.map(socket => {
      const marker = markerForSocket(socket, original.get(socket.id));
      const onMarker = markers.checked && Math.abs(point.x - marker.x) <= marker.size / 2
        && Math.abs(point.y - marker.y) <= marker.size / 2;
      const onPlacement = placements.checked && Math.abs(point.x - socket.x) <= socket.size / 2
        && Math.abs(point.y - socket.y) <= socket.size / 2;
      return { socket, hit: onMarker || onPlacement, distance: onMarker ? 0 : Math.hypot(point.x - socket.x, point.y - socket.y) };
    }).filter(item => item.hit).sort((a, b) => a.distance - b.distance);
    if (!candidates.length) return;
    const socket = candidates[0].socket;
    selected = socket.id;
    drag = { id: socket.id, pointerId: event.pointerId, dx: socket.x - point.x, dy: socket.y - point.y };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("dragging");
    renderRows(); draw();
  };
  canvas.onpointermove = event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const point = pointer(event), socket = level.sockets.find(item => item.id === drag.id);
    socket.x = Math.round(Math.max(0, Math.min(level.width, point.x + drag.dx)));
    socket.y = Math.round(Math.max(0, Math.min(level.height, point.y + drag.dy)));
    renderRows(); markDirty();
  };
  function endDrag(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    canvas.classList.remove("dragging");
    draw();
  }
  canvas.onpointerup = endDrag;
  canvas.onpointercancel = endDrag;
  canvas.onlostpointercapture = endDrag;
  for (const control of [placements, markers, routes]) control.onchange = draw;
  reload.onclick = () => { if (dirty) confirmReload.hidden = false; else load(); };
  discard.onclick = () => load();
  keep.onclick = () => { confirmReload.hidden = true; };
  window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
  save.onclick = async () => {
    if (!level || busy) return;
    setBusy(true);
    setStatus("Validating layout…");
    try {
      const response = await fetch("api/layout", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_revision: revision,
          sockets: level.sockets.map(({ socket_id, x, y, size }) => ({ socket_id, x, y, size })) }),
      });
      const body = await response.json();
      if (!response.ok || !body.ok) throw new Error(body.error || "Layout rejected");
      await load();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      setBusy(false);
    }
  };
  load();
}
