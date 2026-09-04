/* Presentation-local observability. No fetch, discovery, polling or game state. */
(function (root) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const definitions = {
    authored: ["Authored content", "Ultimate source · files", "Editable map, tilesets, waves, sprites and ArUco images."],
    level: ["Photon Level", "Content owner", "Parsed map and artwork references."],
    files: ["Image files", "URLs supplied by Game", "Level-owned terrain, sprites, effects and marker images."],
    camera: ["Physical camera", "Ultimate source · sensor", "Captured pixels of the real board and its tags."],
    webcam: ["Webcam", "Camera acquisition", "Frames, detected tag IDs, corners and frame time."],
    preview: ["Board video preview", "Display-only branch", "Corrected video → Board tab only."],
    lens: ["Lens calibration", "Ultimate source · saved data", "Measured camera matrix and distortion coefficients."],
    correction: ["Camera Calibration", "Lens correction", "Corrected tag coordinates and corrected video."],
    board: ["Photon Board", "Physical observation owner", "Corrected tags + arm state; optional calibrated diagnostics."],
    game: ["Photon Game", "Y’s only live state source", "Simulation, timers, turrets, enemies and effects."],
    y: ["Laser Tag Y", "This presentation", "Canvas, HUD and controls. External screen uses the same source."],
    robots: ["Dobot MG400 arms", "Ultimate source · hardware", "Green / purple arms: measured pose and robot feedback."],
    relay: ["Dobot Relay", "Existing robot-control owner", "Arm feedback, pump state and commanded target."],
    settings: ["Game settings", "Game-owned input", "Saved operator choices and built-in defaults."],
    cal2: ["Arm calibration", "Ultimate source · saved data", "Auto PP Cal 2: six-point mapping, height and parallax."],
    pickup: ["Auto Pickup / Cal 2", "Calibration + report owner", "Camera ↔ arm-mm projection; separate LTX stage reports."],
    players: ["Player LTX / operator", "Ultimate source · intent", "Authenticated stage reports and robot-control intent."],
  };
  // Explicit presentation layout, not a discovery registry. Each owner remains independent.
  const positions = {authored:[0,0],level:[1,0],files:[2,0],camera:[0,1],webcam:[1,1],preview:[2,1],
    lens:[0,2],correction:[1,2],board:[2,2],game:[3,2],y:[4,2],robots:[0,3],relay:[1,3],settings:[3,3],
    cal2:[0,4],pickup:[1,4],players:[0,5]};
  const edges = [
    ["authored","level","reported",["Map + art","owned files"]],
    ["level","files","reported",["Static URLs","image bytes"]],
    ["level","game","reported",["Map + waves","+ art URLs"],"top"],
    ["camera","webcam","reported",["Frames","pixels"]],
    ["webcam","correction","reported",["Frames + tags"]],
    ["lens","correction","reported",["Lens model"]],
    ["correction","preview","reported",["Video only","on demand"]],
    ["correction","board","reported",["Corrected","tags"]],
    ["webcam","board","reported",["IDs + time"],"metadata"],
    ["robots","relay","reported",["Feedback","pose / I/O"]],
    ["relay","board","reported",["Arm state"]],
    ["cal2","pickup","reported",["Saved","measurements"]],
    ["players","pickup","reported",["Stage intent","not outcome"]],
    ["players","relay","reported",["Control intent"],"control"],
    ["players","game","reported",["Game commands","virtual / run"],"operator"],
    ["board","pickup","reported",["Corrected tags","+ arm poses"],"projection"],
    ["pickup","board","reported",["mm projection","+ stage reports"],"diagnostics"],
    ["board","game","reported",["Tags + arms","+ input health"]],
    ["settings","game","reported",["Validated","settings"]],
    ["game","y","live",["Snapshot + SSE","live state"]],
    ["files","y","image",["Image files","on demand"],"images"],
  ];
  function model(state, telemetry, now) {
    const compatible = state?.contract === "photon.game" && state.version === 2;
    const recent = compatible && !["error","reconnecting"].includes(telemetry.connection)
      && telemetry.receivedAt !== null && now - telemetry.receivedAt < 3000;
    const streaming = recent && telemetry.connection === "open" && telemetry.eventAt !== null && now - telemetry.eventAt < 3000;
    const status = input => !recent ? {text:"Last report / feed unavailable", tone:"muted"}
      : !input ? {text:"Not reported by Game", tone:"muted"}
      : {text:`Game reports: ${input.status || "unknown"}`, tone:input.status === "ready" ? "good" : "warn"};
    const level = status(state?.inputs?.level), board = status(state?.inputs?.board);
    const ready = recent && state.status === "ready";
    const art = telemetry.assets;
    const age = telemetry.receivedAt === null ? null : Math.max(0, (now - telemetry.receivedAt) / 1000);
    const upstream=state?.inputs?.board?.upstream;
    const reportAge=typeof state?.server_time==='number' && typeof upstream?.reported_at==='number'
      ? Math.max(0,state.server_time-upstream.reported_at)+(age || 0) : null;
    const reportRecent=recent && reportAge!==null && reportAge<3;
    if(state?.virtual_play){board.text="Not used · virtual play";board.tone="muted";}
    else if(upstream?.reported_at && !reportRecent){board.text=`Last Game report: ${state?.inputs?.board?.status || 'unknown'}`;board.tone="muted";}
    const inputStatus=(name, diagnostic=false)=>{
      const input=(diagnostic?upstream?.tracking?.inputs:upstream?.inputs)?.[name];
      if(!input)return {text:"Not reported by Board",tone:"muted"};
      if(!reportRecent)return {text:`Last report: ${input.status || "unknown"}`,tone:"muted"};
      return {text:`Board reports: ${input.status || "unknown"}`,tone:input.status==="ready"?"good":input.status==="simulated"?"muted":"warn"};
    };
    const origin={text:"Origin · not monitored",tone:"muted"};
    return {
      recent, streaming, ready, level, board, age, reportAge, reportRecent,
      authored:origin,camera:origin,lens:origin,robots:origin,cal2:origin,players:origin,
      webcam:inputStatus('webcam'),correction:inputStatus('camera_calibration'),relay:inputStatus('relay'),
      pickup:inputStatus('cal2_projection',true),
      preview:{text:"Route only · feed not opened here",tone:"muted"},
      settings:{text:state?.configuration?.status==='ready'&&recent?"Game reports: ready":"Not reported / last-known",tone:recent&&state?.configuration?.status==='ready'?"good":"muted"},
      health: streaming ? "SSE receiving" : recent ? "Snapshot received · SSE not live" : "Feed unavailable / stale",
      game: {text:!compatible ? "Waiting for compatible Game output" : !recent ? "Last-known state only" : state.status === "ready" ? `${state.paused?"Paused":state.phase || "Ready"} · wave ${state.wave ?? "—"}` : state.error || "Game unavailable", tone:ready?"good":"warn"},
      files: {text:!art ? "No image requests observed yet" : `${art.loaded} loaded · ${art.pending} pending · ${art.failed} failed`, tone:art?.failed?"bad":art?.pending?"warn":art?.loaded?"good":"muted"},
      y: {text:ready ? `${state.virtual_play?"Virtual":"Physical"} · ${state.towers?.length ?? "—"} turrets · ${state.active_enemies ?? state.enemies?.length ?? "—"} enemies` : "Waiting / last-known display", tone:ready?"good":"muted"},
      imageFlow: Boolean(art?.requested && (art.pending > 0 || (telemetry.assetAt !== null && now - telemetry.assetAt < 900))),
    };
  }
  function create({dialog, openButton, closeButton, motionButton, graph, health, received, details, self, sandboxRoot = ""}) {
    let state = null, selected = "game", timer = null, destroyed = false, opened = false;
    const telemetry = {receivedAt:null, eventAt:null, connection:"connecting", events:0, via:"none", assets:null, assetAt:null, error:null};
    const nodes = {}, wires = [];
    const make = (tag, text, cls) => {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
    const svg = (tag, attrs) => {const el=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,String(value));return el;};
    const lines = svg("svg", {class:"df-wires", "aria-hidden":"true"});
    const defs = svg("defs", {});
    for(const [name,color] of [["reported","#64829d"],["live","#7df3d7"],["image","#ffc879"]]) {
      const marker=svg("marker",{id:`${dialog.id}-${name}`,viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:6,markerHeight:6,orient:"auto-start-reverse"});
      marker.append(svg("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:color}));defs.append(marker);
    }
    lines.append(defs);graph.append(lines);
    for(const [key,[title,kind,description]] of Object.entries(definitions)) {
      const node=make("button",undefined,`df-node df-${key}`);node.type="button";node.dataset.node=key;
      node.style.gridColumn=String(positions[key][0]*2+1);node.style.gridRow=String(positions[key][1]+1);
      const value=make("span","Waiting…","df-node-state");
      node.append(make("span",kind,"df-node-kind"),make("span",title,"df-node-title"),make("span",description,"df-node-description"),value);
      node.onclick=()=>{selected=key;render();};graph.append(node);nodes[key]={node,value};
    }
    for(const [from,to,type,label,route] of edges) {
      const path=svg("path",{class:`df-wire ${type}`,"marker-end":`url(#${dialog.id}-${type})`});
      const particles=svg("path",{class:`df-particles ${type}`});
      const text=svg("text",{class:"df-edge-label"});
      label.forEach((line,index)=>{const span=svg("tspan",{dy:index?14:0});span.textContent=line;text.append(span);});
      path.dataset.from=from;path.dataset.to=to;
      lines.append(path,particles,text);wires.push({from,to,type,route,path,particles,text});
    }
    function drawWires() {
      if(!dialog.open || destroyed)return;
      const rect=graph.getBoundingClientRect();
      lines.setAttribute("viewBox",`0 0 ${rect.width} ${rect.height}`);
      const box=key=>{const r=nodes[key].node.getBoundingClientRect();return {left:r.left-rect.left,right:r.right-rect.left,top:r.top-rect.top,bottom:r.bottom-rect.top,width:r.width,height:r.height};};
      wires.forEach(wire=>{
        const a=box(wire.from),b=box(wire.to);let d,x,y;
        if(wire.route==='top') {
          x=b.left+b.width/2;y=18;
          d=`M ${a.left+a.width/2} ${a.top} V ${y} H ${x} V ${b.top}`;
        } else if(wire.route==='images') {
          x=b.left+b.width/2;y=a.top+a.height/2;
          d=`M ${a.right} ${y} H ${x} V ${b.top}`;
          x=(a.right+x)/2;y-=12;
        } else if(wire.route==='control') {
          x=(a.right+b.left)/2-14;y=a.top-20;
          d=`M ${a.right} ${a.top+a.height/2} H ${x} V ${b.bottom+15} H ${b.left+b.width/2} V ${b.bottom}`;
        } else if(wire.route==='projection') {
          x=a.left+a.width*.65;y=b.bottom+20;
          d=`M ${x} ${a.bottom} V ${y} H ${b.left+b.width*.7} V ${b.bottom}`;
        } else if(wire.route==='operator') {
          x=b.left-22;y=a.top+a.height/2;
          d=`M ${a.right} ${y} H ${x} V ${b.top+b.height*.8} H ${b.left}`;
          y-=12;
        } else if(Math.abs(a.left-b.left)<1) {
          x=a.left+a.width/2;y=(a.bottom+b.top)/2;
          const down=b.top>a.top,sy=down?a.bottom:a.top,ty=down?b.top:b.bottom;
          y=(sy+ty)/2;
          d=`M ${x} ${sy} V ${ty}`;
        } else {
          const port={metadata:.18,diagnostics:.88},sy=a.top+a.height/2,ty=b.top+b.height*(port[wire.route] || .5);
          x=(a.right+b.left)/2;y=(sy+ty)/2-10;
          d=`M ${a.right} ${sy} C ${x} ${sy}, ${x} ${ty}, ${b.left} ${ty}`;
        }
        wire.path.setAttribute("d",d);wire.particles.setAttribute("d",d);
        wire.text.setAttribute("x",x);wire.text.setAttribute("y",y);for(const child of wire.text.children)child.setAttribute("x",x);
      });
    }
    function renderDetails(m) {
      const level=state?.level, art=state?.presentation, board=state?.inputs?.board;
      const endpoint=path=>self+path;
      const upstream=board?.upstream;
      const report=(key,diagnostic=false)=>{
        const item=(diagnostic?upstream?.tracking?.inputs:upstream?.inputs)?.[key];
        return item?`${item.status} · ${item.contract || 'contract not supplied'}${item.version?` v${item.version}`:''}${item.error?` · ${item.error}`:''}`:'Not reported by Board';
      };
      const provenance=m.reportAge===null?'No timestamped Board report supplied. This is a declared route, not a hardware health check.':
        `Board → Game → Y · Game read Board ${m.reportAge.toFixed(1)} s ago. ${m.reportRecent?'Last reported status, not an independent hardware check.':'Historical report; not live.'}${state?.virtual_play?' Virtual play does not use physical Board input.':''}`;
      const rows={
        authored:[['Origin','Photon Level owns the editable TMJ/TSJ map, authored waves, terrain, static decorations, sprites and ArUco images.'],['Route','Authored files → Level runtime bundle → Game; Level serves static images at the URLs forwarded by Game.'],['Boundary','Y receives a display projection and URLs. It never parses map files or reads the repository.']],
        camera:[['Origin','The configured physical camera observes the real playfield and printed tags. Webcam acquires its frames and detects ArUco IDs/corners.'],['Two branches','Tag observations → Camera Calibration → Board → Game → Y. Pixels → corrected video → Board preview only.'],['Health','Device identity and live camera connection are not supplied to Y. Webcam health is only the forwarded Board input report.']],
        webcam:[['Source','Physical camera frames → Webcam acquisition and ArUco detector.'],['Output','tag_snapshot() · hhh.webcam.tags v1: tags, detections, visible_ids, width, height, frame_at. Board passes tags into lens correction; raw IDs and timing remain Board inputs.'],['Report',report('webcam')],['Provenance',provenance]],
        lens:[['Origin','Calibration pattern captures produce the camera matrix and distortion coefficients saved by Camera Calibration in its own calibration.json.'],['Use','Corrects image pixels and marker coordinates. This is lens calibration, not arm millimetre calibration.'],['Boundary','Only the owning module reads these coefficients; they are not copied to Board, Game or Y.']],
        correction:[['Inputs','Webcam frames/detections + the module-owned lens calibration. Board supplies tag sets to the correction function.'],['Output','corrected_tag_snapshot(tags, detections) · hhh.camera-correction v1. Corrected pixel/normalized positions, corners, rotation and dimensions.'],['Video branch','The existing corrected-stream endpoint is consumed by Board’s preview. No video bytes enter Game or Y.'],['Report',report('camera_calibration')],['Provenance',provenance]],
        robots:[['Origin','The green and purple Dobot MG400 arms supply measured pose, enabled/connection and feedback state to the existing relay.'],['Important distinction','A commanded target is intent; a feedback pose is observation. Pump state alone does not prove a tag was picked up.'],['Health','Y does not connect to a robot or infer that both arms are connected from a ready relay API.']],
        relay:[['Inputs','MG400 hardware feedback plus existing authenticated player/gamemaster commands. This diagram never sends commands.'],['Output','arms_snapshot() · hhh.relay.arms v1: per-side pose, target, control_mode, pump_mode, connected, enabled and feedback_at.'],['Route','Relay → Board → Game. Only the relay owns robot actuation; Board reads observations and Y draws Game output.'],['Report',report('relay')],['Provenance',provenance]],
        cal2:[['Origin','Auto PP Cal 2 measurements are saved by Auto Pickup in its own auto-calibration-2.json.'],['Information','Six-point camera/arm mapping and raised-tag height/parallax calibration. Camera lens coefficients are a separate dataset.'],['Boundary','The Auto Pickup owner performs the projection. No calibration file or transform is copied to Game or Y.']],
        pickup:[['Inputs','Board supplies corrected tags and arm poses to tracking_projection(tags, arms); Auto Pickup applies its own saved Cal 2 measurements.'],['Projection output','hhh.cal2.projection v1 → Board: camera ↔ each arm’s millimetre frame, projected TCP/base and distance evidence. Used by Board diagnostics, not combat decisions.'],['Separate intent output','tracking_intent_snapshot() · hhh.controller.intent v1: authenticated Player LTX stage/operation/tag/target reports. Intent is not observed completion.'],['Projection report',report('cal2_projection',true)],['Intent report',report('controller_intent',true)],['Provenance',provenance]],
        players:[['Origin','The existing Player LTX controller reports its stages/operations through Auto Pickup and sends robot intent through the existing relay path; gamemaster takeover uses that relay too.'],['Two routes','Stage reports → Auto Pickup → Board diagnostics. Control intent → Dobot Relay; observed arm feedback returns through Board.'],['Y commands','Virtual placement, aiming, Start and pause from Y go to Game validation instead; they are not robot commands.']],
        preview:[['Route','Physical camera → Webcam → Camera Calibration corrected video → Board tab preview.'],['Information','Read-only corrected MJPEG pixels, aligned with Board overlays. Board resolves the existing preview_snapshot() / hhh.camera-preview v1 route.'],['Not a Game input','The preview is an on-demand display branch. This window does not open it, measure its frames, or claim it is connected. Simulation does not display live video.']],
        settings:[['Origin','Game-owned data/settings.json plus built-in defaults and operator changes from the Photon Game settings tab.'],['Output','photon.game.settings v1 in configuration; Game validates changes and freezes active-run settings.'],['Virtual alternative','Y’s operator commands can provide virtual placement/aiming instead of physical Board observations. Board can separately provide explicitly simulated observations.'],['Boundary','Y receives configuration, not a settings file. This diagnostic window edits nothing.']],
        level:[
          ["Connection","Level → Game → Y. Upstream status is reported by Game, not independently inspected."],
          ["Information",`level: dimensions, paths, sockets, core and visual scene. Wave summary: configuration.authored_wave_enemy_counts. Artwork URLs: presentation.`],
          ["Last received",level?`${level.name} · ${level.width} × ${level.height} · ${level.sockets?.length ?? 0} sockets · ${level.scene?.layers?.length ?? 0} visual layers` : "No level projection received"],
          ["Status",state?.inputs?.level?.error || (state?.inputs?.level?.pending_revision ? `Revision ${state.inputs.level.revision}; revision ${state.inputs.level.pending_revision} waits for reset` : m.level.text)],
        ],
        board:[
          ["Connection","Board → Game. Y receives the resulting gameplay and inputs.board status, not raw tracking or camera video."],
          ["Information","Normalized tags and arm observations feed physical play. Cal 2 projections and LTX intent feed Board’s optional diagnostics; raw tracking, calibration values and camera video stay out of Game/Y."],
          ["Source health","The bounded upstream input-health summary is forwarded through Game, from its existing Board read. No extra sampling."],
          ["Provenance",provenance],
          ["Last report",board?`Status: ${board.status} · source: ${board.source || "not supplied"} · revision: ${board.revision ?? "not supplied"}`:"No Board report in Game output"],
          ["Status",board?.error || (state?.virtual_play?"Virtual play does not require Board. Upstream report may describe its last read.":m.board.text)],
        ],
        game:[
          ["Browser input",`${endpoint("/api/state")}\n${endpoint("/api/events")}`],
          ["Server source","Y’s server adapter forwards Game.game_snapshot() and Game.game_events(). No extra diagnostic requests."],
          ["Information","phase, paused, wave, enemies, towers, projectiles, effects, core_sequence, level, configuration, presentation and input health (including inputs.board.upstream)"],
          ["Observed feed",`${telemetry.events} SSE messages this page session · latest input: ${telemetry.via}${m.age===null?"":` · ${m.age.toFixed(1)} s ago`}`],
          ["Status",telemetry.error || state?.error || m.health],
        ],
        files:[
          ["File source",art?.base ? sandboxRoot+art.base : "No asset base received from Game"],
          ["Information",`${Object.keys(art?.assets || {}).length} declared asset IDs: terrain, roads, turrets, enemies, effects and ArUco images. Bytes are not in SSE.`],
          ["Revision",art?.revision || "Not supplied"],
          ["Observed loads",m.files.text+". Counts are Image load completions in this page, including browser cache; not measured network throughput."],
          ["Latest file",telemetry.assets?.last_url || "No file requested yet"],
          ["Status",art?.error || telemetry.assets?.last_error || "Image files are requested only when needed, using Game’s supplied URLs."],
        ],
        y:[
          ["Presentation",`${state?.virtual_play?"Virtual":"Physical"} mode · ${state?.paused?"paused":state?.phase || "waiting"}`],
          ["Draws","Map and ArUco markers; turret/enemy sprites and combat effects; wave, health and ring-immunity HUD."],
          ["Operator input",`${endpoint("/api/command")} → Game validates intent. This window sends no commands.`],
          ["External screen",`${endpoint("/screen")} uses the same Game contract. Its connection is not monitored by this window.`],
          ["Status",m.ready?"Rendering received Game output; Y does not decide gameplay.":"Live feed unavailable. Displayed values may be last-known."],
        ],
      }[selected];
      const list=make("dl");for(const [name,value] of rows)list.append(make("dt",name),make("dd",value));
      details.replaceChildren(make("h3",definitions[selected][0]+" · connection details"),list);
    }
    function render() {
      if(!dialog.open || destroyed)return;
      const m=model(state,telemetry,performance.now());
      health.textContent=m.health;health.dataset.tone=m.streaming?"good":m.recent?"warn":"bad";
      received.textContent=`${telemetry.events} SSE messages · ${m.age===null?"no snapshot received":`last input ${m.age.toFixed(1)} s ago`}`;
      for(const key of Object.keys(nodes)){const item=m[key];nodes[key].value.textContent=item.text;nodes[key].value.dataset.tone=item.tone;nodes[key].node.setAttribute("aria-pressed",String(selected===key));}
      for(const wire of wires){wire.path.dataset.tone=wire.type==="reported"?m[wire.from].tone:wire.type==="live"?(m.streaming?"good":"bad"):m.files.tone;wire.particles.dataset.active=String(wire.type==="live"?m.streaming:wire.type==="image"?m.imageFlow:false);}
      renderDetails(m);drawWires();
    }
    const observer=new ResizeObserver(drawWires);observer.observe(graph);
    function focusNode(key) {
      const scroller=graph.parentElement, node=nodes[key]?.node;
      if(!scroller || !node)return;
      const r=node.getBoundingClientRect(),s=scroller.getBoundingClientRect();
      scroller.scrollTo({top:scroller.scrollTop+r.top-s.top-(s.height-r.height)/2,
        left:scroller.scrollLeft+r.left-s.left-(s.width-r.width)/2,behavior:'instant'});
      selected=key;render();
    }
    const closed=()=>{clearInterval(timer);timer=null;openButton.focus();};
    dialog.addEventListener("close",closed);
    openButton.onclick=()=>{dialog.showModal();render();if(!opened){focusNode('game');opened=true;}if(timer===null)timer=setInterval(render,500);};
    closeButton.onclick=()=>dialog.close();
    motionButton.onclick=()=>{const paused=dialog.classList.toggle("df-still");motionButton.textContent=paused?"Resume motion":"Pause motion";motionButton.setAttribute("aria-pressed",String(paused));};
    return {
      snapshot(value, via="snapshot") {
        state=value;telemetry.via=via;
        if(value?.contract!=="photon.game" || value.version!==2){telemetry.error=value?.error || "Incompatible Game output";telemetry.connection="error";render();return;}
        telemetry.receivedAt=performance.now();telemetry.error=null;
        if(via==="SSE"){telemetry.eventAt=telemetry.receivedAt;telemetry.events++;telemetry.connection="open";}
        render();
      },
      connection(status,error=null){telemetry.connection=status;telemetry.error=error;if(status!=="open")telemetry.eventAt=null;render();},
      assets(value){telemetry.assets={...value};telemetry.assetAt=performance.now();render();},
      focus:focusNode,
      destroy(){destroyed=true;clearInterval(timer);observer.disconnect();dialog.removeEventListener("close",closed);if(dialog.open)dialog.close();},
    };
  }
  root.YDataFlow = {create, model, positions, edges};
})(globalThis);
