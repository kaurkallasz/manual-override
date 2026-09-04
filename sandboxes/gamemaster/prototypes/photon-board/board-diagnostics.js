(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const self = location.pathname.replace(/\/$/, "");
  const url = path => self + path;
  const NS = "http://www.w3.org/2000/svg";
  let current = null, receivedAt = 0, previewOn = false, previewFailed = false, initialized = false;
  let settings = null, settingsDirty = false, settingsBusy = false;
  let settingsRequestError = "";
  const settingKeys = ["near_xy_mm", "near_z_mm", "unique_margin_mm", "stale_s"];
  const targetsOpen = {green:true,purple:true};
  const stageNames = {visible:"Visible", unknown:"Unknown", near_arm:"Near arm", pickup_suspected:"Pickup suspected",
    likely_carried:"Likely carried", release_observed:"Release signal", placement_stable:"Placement stable"};
  function showSettings(value, force = false) {
    if(value?.contract!=="photon.board.settings" || value.version!==1) return;
    settings = value;
    for(const key of settingKeys) {
      $(key).min = value.bounds[key].min; $(key).max = value.bounds[key].max;
      $("default_"+key).textContent = `Default: ${value.defaults[key]}${key==="stale_s"?" s":" mm"}`;
      if(force || !settingsDirty) $(key).value = value.settings[key];
    }
    $("settingsFields").disabled = settingsBusy;
    $("saveSettings").disabled = settingsBusy;
    $("defaultSettings").disabled = settingsBusy;
    $("settingsError").textContent = settingsRequestError || value.error || "";
    if(!settingsDirty) $("settingsStatus").textContent = "Saved diagnostic values. Apply to change; defaults stay available.";
  }
  function markSettingsDirty() {
    settingsDirty = true;
    settingsRequestError = "";
    $("settingsStatus").textContent = "Unsaved changes — Apply settings to use them.";
  }
  $("settingsForm").oninput = markSettingsDirty;
  $("defaultSettings").onclick = () => {
    if(!settings || settingsBusy) return;
    for(const key of settingKeys) $(key).value = settings.defaults[key];
    markSettingsDirty();
  };
  $("settingsForm").onsubmit = async event => {
    event.preventDefault();
    if(!settings || settingsBusy) return;
    settingsBusy = true;
    $("settingsFields").disabled = $("saveSettings").disabled = $("defaultSettings").disabled = true;
    $("settingsError").textContent = "";
    settingsRequestError = "";
    try {
      const values = Object.fromEntries(settingKeys.map(key => [key, Number($(key).value)]));
      const response = await fetch(url("/api/settings"), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({settings:values})});
      const result = await response.json();
      if(!response.ok || !result.ok) throw Error(result.error || "Settings were not saved");
      settingsDirty = false;
      showSettings(result.output, true);
      $("settingsStatus").textContent = "Settings saved. New diagnostic evidence starts with the next sample.";
    } catch(error) { settingsRequestError = error.message; $("settingsError").textContent = error.message; }
    finally { settingsBusy = false; $("settingsFields").disabled = $("saveSettings").disabled = $("defaultSettings").disabled = false; }
  };
  function element(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
  function svg(tag, attrs, text) { const node = document.createElementNS(NS, tag); for (const [k,v] of Object.entries(attrs)) node.setAttribute(k, String(v)); if(text !== undefined) node.textContent = text; $("overlay").append(node); return node; }
  const mm = value => Number.isFinite(value) ? Math.round(value) : "—";
  function meter(reading, considered) {
    const available = reading.status !== "unavailable" && reading.status !== "stale" && Number.isFinite(reading.xy_mm);
    const row = element("div", undefined, "ltxDistanceMeter" + (available && reading.near && considered ? " ready" : ""));
    row.append(element("span", `#${reading.id}${considered ? " · CONSIDERED" : reading.requested ? " · requested" : ""}`, "ltxDistanceLabel"));
    row.append(element("span", available ? `XY ${mm(reading.xy_mm)} · Z ${mm(reading.z_mm)} mm` : reading.status === "stale" ? "last seen / stale" : "unavailable", "ltxDistanceValue"));
    const bar = element("span", undefined, "ltxDistanceTrack");
    bar.setAttribute("role", "meter"); bar.setAttribute("aria-label", `Tag ${reading.id} proximity`);
    bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(available ? reading.fill : 0));
    const lit = available ? Math.round(24 * reading.fill / 100) : 0;
    for (let i=0; i<24; i++) bar.append(element("span", undefined, "ltxDistanceSegment" + (i<lit ? " lit" : "")));
    row.append(bar);
    row.title = reading.error || `${reading.visible ? "Currently visible" : "Last seen"} · ${reading.age_s ?? "—"} s · proximity is diagnostic, not release permission`;
    return row;
  }
  function renderArms(data) {
    const cards = [];
    for (const side of ["green", "purple"]) {
      const arm = data.arms?.[side] || {}, card = element("section", undefined, "panel arm-card");
      const head = element("div", undefined, "arm-head");
      head.append(element("h2", `${side.toUpperCase()} ARM`, side), element("small", arm.status === "ready" ? `Pump ${arm.pump_mode}` : "Unavailable", arm.status === "ready" ? "" : "bad")); card.append(head);
      const detail = element("div", undefined, "arm-detail");
      const summary = arm.carried_tag != null ? `Likely carrying #${arm.carried_tag}` : arm.ambiguous ? "Ambiguous · no unique tag" : arm.considered_tag != null ? `Considering tag #${arm.considered_tag}` : "No tag uniquely considered";
      detail.append(element("div", summary, arm.ambiguous ? "bad" : ""));
      if (arm.pose) detail.append(element("div", `TCP ${arm.pose.slice(0,3).map(mm).join(" / ")} mm · age ${arm.feedback_age_s ?? "—"} s`, "muted"));
      const report = arm.controller;
      detail.append(element("div", report ? `Controller: ${report.stage.replaceAll("_", " ")}${report.stale ? " (stale report)" : " (reported)"}` : "Controller stage: no report", "muted"));
      if (report?.operation_id) detail.title = `Operation ${report.operation_id}; tag #${report.physical_tag ?? "?"}; target #${report.target_marker ?? "?"}`;
      if(arm.error) detail.append(element("div",arm.error,"bad")); card.append(detail);
      const candidates = element("div", undefined, "ltxDistanceMeters");
      candidates.append(element("div", "Tag → arm consideration", "meter-title"));
      for (const reading of arm.candidates || []) candidates.append(meter(reading, reading.considered));
      if(!arm.candidates?.length) candidates.append(element("div", arm.calibration_error || "Waiting for fresh raised-tag observations", "meter-note"));
      candidates.append(element("div", "Green = uniquely near. Orange = another candidate. No release command.", "meter-note")); card.append(candidates);
      const targets = element("details"); targets.open = targetsOpen[side];
      targets.ontoggle = () => {if(targets.isConnected) targetsOpen[side] = targets.open;};
      targets.append(element("summary", "Arm → physical targets"));
      const targetMeters = element("div", undefined, "ltxDistanceMeters");
      for (const reading of (arm.targets || []).slice(0,3)) targetMeters.append(meter(reading, false));
      if(!arm.targets?.length) targetMeters.append(element("div", "No calibrated target observations", "meter-note"));
      targetMeters.append(element("div", "Nearest / requested markers · calibrated Z estimate; excludes player-local fine tuning.", "meter-note"));
      targets.append(targetMeters); card.append(targets);
      const command = arm.command_distance;
      card.append(element("div", command ? `Commanded destination: XY ${mm(command.xy_mm)} · Z ${mm(command.z_mm)} mm` : arm.command_distance_error || "Commanded destination: unavailable", "meter-note"));
      cards.push(card);
    }
    $("arms").replaceChildren(...cards);
  }
  function renderOverlay(data) {
    const w = 1000, h = w * (data.height > 0 && data.width > 0 ? data.height / data.width : 9/16);
    $("scene").style.aspectRatio = `${w}/${h}`; $("overlay").setAttribute("viewBox", `0 0 ${w} ${h}`);
    $("overlay").replaceChildren(); $("scene").dataset.stale = String(data.status !== "ready");
    for (const tag of data.tags || []) {
      const [u,v] = tag.camera || []; if(!Number.isFinite(u)||!Number.isFinite(v)) continue;
      const x=u*w,y=v*h, color=tag.visible?tag.kind==="movable"?"#b6ff3a":"#c9dbd0":"#718375";
      if(tag.corners?.length===4) svg("polygon",{points:tag.corners.map(p=>`${p[0]*w},${p[1]*h}`).join(" "),fill:"none",stroke:color,"stroke-width":2,"stroke-dasharray":tag.visible?"none":"4 4"});
      else svg("rect",{x:x-13,y:y-13,width:26,height:26,fill:"#0a100e88",stroke:color,"stroke-width":2,"stroke-dasharray":tag.visible?"none":"4 4"});
      svg("text",{x:x+17,y:y+5,"font-size":14},`#${tag.id}`);
    }
    for(const [side,arm] of Object.entries(data.arms || {})) {
      if(data.status !== "ready" || !arm.tcp_camera || !arm.base_camera) continue;
      const [u,v]=arm.tcp_camera,[bu,bv]=arm.base_camera;
      // SVG clips to the exact same corrected-frame rectangle as the video.
      svg("line",{x1:bu*w,y1:bv*h,x2:u*w,y2:v*h,stroke:"#ff6464","stroke-width":9,"stroke-dasharray":"8 8"});
      svg("circle",{cx:u*w,cy:v*h,r:10,fill:"#ff6464",stroke:"#08110e","stroke-width":3});
      svg("text",{x:Math.max(8,Math.min(820,u*w+18)),y:Math.max(20,Math.min(h-10,v*h-15)),"font-size":15},`${side.toUpperCase()} TCP`);
      const target=arm.targets?.[0];
      if(target?.camera) svg("line",{x1:u*w,y1:v*h,x2:target.camera[0]*w,y2:target.camera[1]*h,stroke:"#f5a623","stroke-width":2,"stroke-dasharray":"6 5"});
      const tag=(data.tags||[]).find(t=>t.id===arm.considered_tag);
      if(tag) svg("line",{x1:u*w,y1:v*h,x2:tag.camera[0]*w,y2:tag.camera[1]*h,stroke:"#54e68e","stroke-width":3});
    }
  }
  function renderTable(data) {
    const rows=[];
    for(const tag of data.tags || []) {
      if(tag.kind!=="movable"&&!$("markers").checked) continue;
      const row=element("tr"); row.append(element("td",`#${tag.id}`),element("td",tag.visible?"Visible":Number.isFinite(tag.age_s)?`Last seen ${tag.age_s}s ago`:"Last known / stale"));
      const stage=element("td");stage.append(element("span",stageNames[tag.stage]||tag.stage,"stage"+(tag.stage==="placement_stable"?" good":tag.stage==="unknown"?" bad":"")));
      row.append(stage,element("td",tag.arm||"—"),element("td",tag.target_id!=null?`#${tag.target_id}`:"—"),element("td",`${tag.confidence} · ${tag.evidence}`)); rows.push(row);
    }
    if(!rows.length){const row=element("tr"),td=element("td","No movable tags observed. IDs 100+ identify raised hardware tags; enable fixed markers to see other detections.");td.colSpan=6;row.append(td);rows.push(row);}
    $("tagRows").replaceChildren(...rows);
  }
  function renderPreview(data) {
    const enabled=$("camera").checked && data.source==="camera" && data.status==="ready";
    if(enabled&&!previewOn){$("feed").src=url("/api/preview");previewOn=true;}
    if(!enabled&&previewOn){$("feed").removeAttribute("src");previewOn=false;previewFailed=false;}
    $("feed").hidden=!enabled||previewFailed;
    $("cameraMessage").textContent=data.source==="simulation"?"SIMULATED OBSERVATIONS · no live camera or controller intent":previewFailed?"Corrected camera preview unavailable; toggle camera to retry":!enabled?"Coordinate overlay · camera off or evidence unavailable":"Lens-corrected frame · unrotated · projected TCP, not full arm geometry";
  }
  function show(data) {
    if(data?.contract!=="photon.board.tracking"||data.version!==1){fail("Incompatible Photon Board tracking output");return;}
    current=data; receivedAt=performance.now();
    showSettings(data.configuration);
    if(!initialized){$("enabled").checked=data.source==="simulation";initialized=true;}
    $("status").textContent=`${data.source==="simulation"?"SIMULATION": "PHYSICAL"} · ${data.status.toUpperCase()}`;
    $("status").className="badge"+(data.status!=="ready"?" bad":"");
    $("inputs").replaceChildren(...Object.entries(data.inputs||{}).map(([key,value])=>element("span",`${key.replaceAll("_"," ")}: ${value.status}`,value.status==="unavailable"?"bad":"")));
    $("errors").textContent=(data.errors||[]).join("\n");
    const limits=data.limits;
    if(limits)$("limits").textContent=`Near: XY ≤ ${limits.near_xy_mm} mm / Z ≤ ${limits.near_z_mm} mm · unique margin ${limits.unique_margin_mm} mm · stale after ${limits.stale_s}s. Diagnostic thresholds, not game or safety rules.`;
    $("out").textContent=JSON.stringify(data,null,2);
    renderArms(data);renderOverlay(data);renderTable(data);renderPreview(data);
  }
  function fail(message) {
    $("status").textContent="DISCONNECTED · EVIDENCE UNAVAILABLE";$("status").className="badge bad";
    $("errors").textContent=message;
    if(current){current={...current,status:"unavailable",arms:{},tags:current.tags.map(t=>({...t,visible:false,age_s:null,stage:"unknown",arm:null,target_id:null,confidence:"unknown",evidence:"Stream disconnected; historical position only"}))};renderArms(current);renderOverlay(current);renderTable(current);renderPreview(current);}
    $("inputs").replaceChildren(element("span","Input health unknown while disconnected","bad"));
  }
  $("camera").onchange=()=>current&&renderPreview(current);
  $("markers").onchange=()=>current&&renderTable(current);
  $("feed").onerror=()=>{previewFailed=true;if(current)renderPreview(current);};
  $("apply").onclick=async()=>{
    $("simulationError").textContent="";$("apply").disabled=true;
    try{const input=JSON.parse($("simulation").value);const response=await fetch(url("/api/simulation"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...input,enabled:$("enabled").checked})});const value=await response.json();if(!response.ok)throw Error(value.error||"Simulation failed");show(value.output.tracking);}catch(error){$("simulationError").textContent=error.message;}finally{$("apply").disabled=false;}
  };
  fetch(url("/api/diagnostics")).then(r=>r.json()).then(show).catch(error=>fail(error.message));
  const stream=new EventSource(url("/api/events"));
  stream.onmessage=event=>{try{show(JSON.parse(event.data).tracking);}catch(error){fail(error.message);}};
  stream.onerror=()=>fail("Board event stream disconnected. Waiting for reconnection…");
  setInterval(()=>{if(receivedAt&&performance.now()-receivedAt>1600)fail("No fresh Board samples. Cached meters and arm associations cleared.");},500);
  window.addEventListener("pagehide",()=>{stream.close();$("feed").removeAttribute("src");});
})();
