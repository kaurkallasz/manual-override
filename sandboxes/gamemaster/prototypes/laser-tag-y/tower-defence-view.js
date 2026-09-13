(function (global) {
  "use strict";

  const WIDTH = 1696;
  const HEIGHT = 960;
  const LIVE_POD_SIZE = 112;
  const TOWER_VISUAL_SIZE = 88;
  const UPGRADED_HEAD_LIFT = 14;
  const UPGRADED_HEAD_SCALE = 0.9;
  const ENEMY_VISUAL_SCALE = 2;
  const FRAME_INTERVAL_MS = 1000 / 60;
  const TOWER_HEALTH_BAR_WIDTH = 68;
  const TOWER_DAMAGE_FLASH_S = 0.45;
  const TOWER_ACTIVATION_FRAMES = 72;
  const TOWER_ACTIVATION_FPS = 24;
  const TOWER_ACTIVATION_DURATION_S = 3;
  const TOWER_REPLENISH_PULSE_S = 0.35;
  const ARUCO_FIELD_CLEARANCE = 20;
  const CORE_MARKER_VISUAL_SIZE = 116;
  const FORCE_FIELD_ZAP_DURATION_S = 0.5;
  const MACHINE_GUN_MUZZLE_FORWARD = 36;
  const MACHINE_GUN_MUZZLE_HALF_GAP = 7;
  const FLAMETHROWER_PATH_SEGMENTS = 18;
  const FLAMETHROWER_TRAIL_LAG_S = 0.48;
  const FLAMETHROWER_MUZZLE_OFFSET = 35;
  const FLAMETHROWER_PILOT_LAG_S = 0.08;
  const TESLA_DISCHARGE_FLASH_S = 0.16;
  const AIM_HANDLE_RADIUS = 17;
  const TOWER_CORNER_OFFSETS = Object.freeze([
    Object.freeze([-44, -44]),
    Object.freeze([44, -44]),
    Object.freeze([-44, 44]),
    Object.freeze([44, 44]),
  ]);
  const EFFECT_QUALITY_PROFILES = Object.freeze({
    full: Object.freeze({
      name: "full",
      targetFps: 60,
      trailSamples: 7,
      burnFrameDivisor: 1,
      flameSegments: 18,
      machineGunBullets: 4,
      lightningLayers: 3,
      lightningStepPx: 22,
      mortarImpactSprites: 8,
      towerSmokePuffs: 3,
      towerEmberScale: 1,
      destructionDebris: 8,
      teslaIdleArcScale: 1,
      shadowScale: 1,
    }),
    reduced: Object.freeze({
      name: "reduced",
      targetFps: 60,
      trailSamples: 5,
      burnFrameDivisor: 1,
      flameSegments: 12,
      machineGunBullets: 3,
      lightningLayers: 2,
      lightningStepPx: 28,
      mortarImpactSprites: 6,
      towerSmokePuffs: 2,
      towerEmberScale: 0.7,
      destructionDebris: 6,
      teslaIdleArcScale: 0.75,
      shadowScale: 0.35,
    }),
    dense: Object.freeze({
      name: "dense",
      targetFps: 60,
      trailSamples: 2,
      burnFrameDivisor: 2,
      flameSegments: 9,
      machineGunBullets: 2,
      lightningLayers: 2,
      lightningStepPx: 38,
      mortarImpactSprites: 4,
      towerSmokePuffs: 1,
      towerEmberScale: 0.45,
      destructionDebris: 4,
      teslaIdleArcScale: 0.5,
      shadowScale: 0,
    }),
  });

  function effectQualityForEnemyCount(enemyCount) {
    const count = Math.max(0, Number(enemyCount) || 0);
    if (count >= 800) return EFFECT_QUALITY_PROFILES.dense;
    if (count >= 400) return EFFECT_QUALITY_PROFILES.reduced;
    return EFFECT_QUALITY_PROFILES.full;
  }

  // Pixel budgets bound memory even when the Gamemaster changes sprite sizes.
  function rasterCache(maxPixels) {
    const entries = new Map();
    let pixels = 0;
    return {
      get: key => entries.get(key),
      has: key => entries.has(key),
      clear() { entries.clear(); pixels = 0; },
      set(key, canvas) {
        const cost = canvas.width * canvas.height;
        if (cost > maxPixels) return;
        while (entries.size && (pixels + cost > maxPixels || entries.size >= 512)) {
          const oldest = entries.keys().next().value;
          const removed = entries.get(oldest);
          pixels -= removed.width * removed.height;
          entries.delete(oldest);
        }
        entries.set(key, canvas);
        pixels += cost;
      },
      get pixels() { return pixels; },
    };
  }

  function towerTypeLabel(value) {
    const words = String(value || "").replaceAll("_", " ").trim();
    return words ? words[0].toUpperCase() + words.slice(1) : "Unknown";
  }

  function snapshotReceiver(apply) {
    const fields = ["level", "presentation", "configuration", "settings", "loadout", "force_field_blockers", "row_barrier_geometry"];
    let baseline = null;
    return {
      full(value) {
        baseline = Object.fromEntries(fields.filter(key => Object.hasOwn(value, key)).map(key => [key, value[key]]));
        apply(value);
      },
      update(value) {
        if (!baseline) throw new Error("Game update arrived before a complete snapshot");
        apply({...baseline, ...value});
      },
    };
  }

  function gameFacts(gameState) {
    const sequence = gameState?.core_sequence || {};
    const finiteInteger = (value) => {
      if (!['number', 'string'].includes(typeof value) || String(value).trim() === "") {
        return null;
      }
      const number = Number(value);
      return Number.isSafeInteger(number) ? number : null;
    };
    const loadout = gameState?.loadout && typeof gameState.loadout === "object"
      && !Array.isArray(gameState.loadout)
      ? Object.entries(gameState.loadout).map(([atomTagId, towerType]) => ({
        atom_tag_id: finiteInteger(atomTagId),
        tower_type: typeof towerType === "string" ? towerType : "",
        label: towerTypeLabel(towerType),
      })).filter((entry) => entry.atom_tag_id != null && entry.tower_type)
      : [];
    loadout.sort((a, b) => a.atom_tag_id - b.atom_tag_id);
    return {
      loadout,
      atom_ids: loadout.map((entry) => entry.atom_tag_id),
      socket_count: Array.isArray(gameState?.level?.sockets)
        ? gameState.level.sockets.length : 0,
      core_marker_id: finiteInteger(sequence.marker_id),
      ring_min_turrets: finiteInteger(sequence.ring_min_turrets),
      ring_max_turrets: finiteInteger(sequence.ring_max_turrets),
    };
  }

  function aimControl(value) {
    const control = value?.control || value;
    if (!control || typeof control !== "object") return null;
    const start = Number(control.range_at_spread_0);
    const end = Number(control.range_at_spread_1);
    return Number.isFinite(start) && Number.isFinite(end)
      ? control
      : null;
  }

  function controlValue(control, name, spread) {
    const start = Number(control?.[`${name}_at_spread_0`]);
    const end = Number(control?.[`${name}_at_spread_1`]);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return NaN;
    const amount = Math.max(0, Math.min(1, Number(spread) || 0));
    return start + (end - start) * amount;
  }

  function towerAimDistance(control, spread) {
    const geometry = aimControl(control);
    return geometry ? controlValue(geometry, "range", spread) : NaN;
  }

  function towerAimFromPoint(
    control, towerX, towerY, pointerX, pointerY, currentAngleDegrees = 0,
  ) {
    const geometry = aimControl(control);
    if (!geometry) return null;
    const dx = Number(pointerX) - Number(towerX);
    const dy = Number(pointerY) - Number(towerY);
    const distance = Math.hypot(dx, dy);
    const start = Number(geometry.range_at_spread_0);
    const end = Number(geometry.range_at_spread_1);
    const spread = Math.max(0, Math.min(1,
      Math.abs(end - start) < 0.000001 ? 0 : (distance - start) / (end - start)
    ));
    const pointerAngle = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
    return {
      angle: geometry.directional === false
        ? ((Number(currentAngleDegrees) % 360) + 360) % 360
        : pointerAngle,
      spread,
      distance: towerAimDistance(geometry, spread),
    };
  }

  function boundedVisualAge(receivedAt, now, connected, frozenAge = 0, maximum = 0.5) {
    const limit = Math.max(0, Number(maximum) || 0);
    const age = connected
      ? Math.max(0, Number(now) - Number(receivedAt)) / 1000
      : Math.max(0, Number(frozenAge) || 0);
    return Math.min(limit, age);
  }

  function targetingHandlePoint(tower, targeting) {
    const angle = Number(targeting.angle || 0);
    const distance = Number(targeting.range || 0);
    return {
      x: Number(tower.x) + Math.cos(angle) * distance,
      y: Number(tower.y) + Math.sin(angle) * distance,
    };
  }

  function fixedMarkerVisualSize(width, height = width) {
    return Math.max(42, Math.min(104, Math.round(Math.min(width, height) * 0.37)));
  }

  function permanentTurretMarkerOffset(side, turretSize, markerSize, gap = 0) {
    const direction = Math.sign(Number(side) || 0);
    if (!direction) return 0;
    return direction * (
      Number(turretSize) / 2
      + Number(markerSize) / 2
      + Number(gap || 0)
    );
  }

  function machineGunMuzzlePoints(x, y, angle, scale = 1) {
    const forwardX = Math.cos(angle);
    const forwardY = Math.sin(angle);
    const normalX = -forwardY;
    const normalY = forwardX;
    const centerX = Number(x) + forwardX * MACHINE_GUN_MUZZLE_FORWARD * scale;
    const centerY = Number(y) + forwardY * MACHINE_GUN_MUZZLE_FORWARD * scale;
    return [-1, 1].map((side) => ({
      x: centerX + normalX * MACHINE_GUN_MUZZLE_HALF_GAP * side * scale,
      y: centerY + normalY * MACHINE_GUN_MUZZLE_HALF_GAP * side * scale,
    }));
  }

  function machineGunFireLines(x, y, angle, targetX, targetY, scale = 1) {
    return machineGunMuzzlePoints(x, y, angle, scale).map((muzzle) => ({
      ax: muzzle.x,
      ay: muzzle.y,
      bx: Number(targetX),
      by: Number(targetY),
    }));
  }

  function flamethrowerNozzlePoint(x, y, angle, scale = 1) {
    return {
      x: Number(x) + Math.cos(angle) * FLAMETHROWER_MUZZLE_OFFSET * scale,
      y: Number(y) + Math.sin(angle) * FLAMETHROWER_MUZZLE_OFFSET * scale,
    };
  }

  function advancedWeaponCharge(snapshotCharge, chargeDuration, elapsed) {
    const initial = Math.max(0, Math.min(1, Number(snapshotCharge) || 0));
    const duration = Math.max(0.001, Number(chargeDuration) || 1);
    return Math.max(0, Math.min(1, initial + Math.max(0, Number(elapsed) || 0) / duration));
  }

  function towerLinkMultiplierLabel(tower) {
    const linkedTurretCount = Math.max(1, Math.round(Number(tower.linked_turret_count) || 1));
    const snapshotMultiplier = Number(tower.link_multiplier);
    const linkMultiplier = Number.isFinite(snapshotMultiplier) ? snapshotMultiplier : null;
    return {
      linkedTurretCount,
      linkMultiplier,
      label: linkMultiplier == null
        ? "×—"
        : `×${linkMultiplier.toFixed(2).replace(/0$/, "")}`,
    };
  }

  function towerHealthBarMetrics(tower, visualTime) {
    const maximum = Math.max(1, Number(tower.max_hp || 1));
    const healthRatio = Math.max(0, Math.min(1, Number(tower.hp || 0) / maximum));
    const damagedAt = tower.last_damage_at == null ? NaN : Number(tower.last_damage_at);
    const damageAge = Number(visualTime) - damagedAt;
    const damageAlpha = Number.isFinite(damageAge) && damageAge >= 0 && damageAge <= TOWER_DAMAGE_FLASH_S
      ? 1 - damageAge / TOWER_DAMAGE_FLASH_S
      : 0;
    const damageAmount = Math.max(0, Number(tower.last_damage_amount || 0));
    return {
      healthRatio,
      fillWidth: TOWER_HEALTH_BAR_WIDTH * healthRatio,
      damageAlpha,
      damageNotchWidth: damageAlpha > 0 && damageAmount > 0
        ? Math.max(1, Math.min(TOWER_HEALTH_BAR_WIDTH, TOWER_HEALTH_BAR_WIDTH * damageAmount / maximum))
        : 0,
    };
  }

  function normalizedKeepOut(keepOut, padding = 0) {
    const left = Number.isFinite(Number(keepOut.left))
      ? Number(keepOut.left)
      : Number(keepOut.x) - Number(keepOut.halfWidth ?? keepOut.halfSize ?? 0);
    const right = Number.isFinite(Number(keepOut.right))
      ? Number(keepOut.right)
      : Number(keepOut.x) + Number(keepOut.halfWidth ?? keepOut.halfSize ?? 0);
    const top = Number.isFinite(Number(keepOut.top))
      ? Number(keepOut.top)
      : Number(keepOut.y) - Number(keepOut.halfHeight ?? keepOut.halfSize ?? 0);
    const bottom = Number.isFinite(Number(keepOut.bottom))
      ? Number(keepOut.bottom)
      : Number(keepOut.y) + Number(keepOut.halfHeight ?? keepOut.halfSize ?? 0);
    if (![left, right, top, bottom].every(Number.isFinite)) return null;
    return {
      markerId: Number(keepOut.markerId ?? keepOut.marker_id),
      left: Math.min(left, right) - padding,
      right: Math.max(left, right) + padding,
      top: Math.min(top, bottom) - padding,
      bottom: Math.max(top, bottom) + padding,
    };
  }

  function segmentRectangleInterval(ax, ay, bx, by, rectangle) {
    const dx = bx - ax;
    const dy = by - ay;
    let enter = 0;
    let exit = 1;
    const boundaries = [
      [-dx, ax - rectangle.left],
      [dx, rectangle.right - ax],
      [-dy, ay - rectangle.top],
      [dy, rectangle.bottom - ay],
    ];
    for (const [direction, distance] of boundaries) {
      if (Math.abs(direction) <= 1e-9) {
        if (distance < 0) return null;
        continue;
      }
      const ratio = distance / direction;
      if (direction < 0) enter = Math.max(enter, ratio);
      else exit = Math.min(exit, ratio);
      if (enter > exit) return null;
    }
    return [Math.max(0, enter), Math.min(1, exit)];
  }

  function fieldSegmentsOutsideKeepOuts(ax, ay, bx, by, keepOuts) {
    let visibleIntervals = [[0, 1]];
    for (const keepOut of keepOuts) {
      const blocked = segmentRectangleInterval(ax, ay, bx, by, keepOut);
      if (!blocked || blocked[1] - blocked[0] <= 1e-9) continue;
      const nextIntervals = [];
      for (const [start, end] of visibleIntervals) {
        if (blocked[1] <= start || blocked[0] >= end) {
          nextIntervals.push([start, end]);
          continue;
        }
        if (blocked[0] > start + 1e-9) {
          nextIntervals.push([start, Math.min(end, blocked[0])]);
        }
        if (blocked[1] < end - 1e-9) {
          nextIntervals.push([Math.max(start, blocked[1]), end]);
        }
      }
      visibleIntervals = nextIntervals;
      if (!visibleIntervals.length) break;
    }
    return visibleIntervals.map(([start, end]) => ({
      start,
      end,
      ax: ax + (bx - ax) * start,
      ay: ay + (by - ay) * start,
      bx: ax + (bx - ax) * end,
      by: ay + (by - ay) * end,
    }));
  }

  function circleOverlapsKeepOut(x, y, radius, keepOut) {
    const nearestX = Math.max(keepOut.left, Math.min(x, keepOut.right));
    const nearestY = Math.max(keepOut.top, Math.min(y, keepOut.bottom));
    return Math.hypot(x - nearestX, y - nearestY) <= radius;
  }

  function createTowerDefenceView(options) {
    const sandboxRoot = String(options.sandboxRoot || "").replace(/\/$/, "");
    let assetRoot = "";
    let assetPaths = {};
    let assetRevision = null;
    let assetGeneration = 0;
    let assetLoads = {requested:0, loaded:0, failed:0, pending:0, last_url:null, last_error:null};
    const mapCanvas = options.mapCanvas;
    const gameCanvas = options.gameCanvas;
    if (!mapCanvas || !gameCanvas) {
      throw new Error("Tower Defense view requires mapCanvas and gameCanvas");
    }

    const images = new Map();
    const gameImages = new Map();
    const sceneImages = new Map();
    const markerImages = new Map();
    const tintedEffectCache = new Map();
    const enemySpriteCache = rasterCache(3 * 1024 * 1024);
    const effectRasterCache = rasterCache(2 * 1024 * 1024);
    const enemyGlowCache = rasterCache(4 * 1024 * 1024);
    const scaledImageIds = new WeakMap();
    let nextScaledImageId = 0;
    let visualStateCache = null;
    let enemiesByIdCache = null;
    const fieldGeometryCache = new Map();
    let geometrySignature = "";
    let bruteScale = null;
    const enemyTrailHistory = new Map();
    const towerRenderAngles = new Map();
    let socketRecordCache = null;
    let socketRecordMapCache = null;
    let staticFieldKeepOutCache = null;
    let level = null;
    let levelRevision = null;
    let state = null;
    let stateReceivedAt = performance.now();
    let feedConnected = false;
    let frozenVisualAge = 0;
    let nextGameRenderAt = null;
    let lastGameRenderAt = null;
    let adaptiveQuality = 0;
    let slowFrameTime = 0;
    let healthyFrameTime = 0;
    let renderStats = {fps: 0, drawMs: 0, frameMs: 0, quality: "full"};
    let profilingFrames = 0;
    let profilingTotals = {};
    let fpsSampleStartedAt = performance.now();
    let fpsRenderedFrames = 0;
    let animationFrame = 0;
    let destroyed = false;
    let selectedTowerId = null;
    const towerAimPreview = new Map();
    let gameImagesStarted = false;

    mapCanvas.width = WIDTH;
    mapCanvas.height = HEIGHT;
    gameCanvas.width = WIDTH;
    gameCanvas.height = HEIGHT;
    function reportFps(fps) {
      try { options.onFps?.(fps); }
      catch (error) { console.warn("FPS monitor unavailable", error); }
    }
    function resetFpsSample() {
      fpsSampleStartedAt = performance.now();
      fpsRenderedFrames = 0;
      nextGameRenderAt = null;
      lastGameRenderAt = null;
      slowFrameTime = healthyFrameTime = 0;
      reportFps(null);
    }
    document.addEventListener?.("visibilitychange", resetFpsSample);
    function reportAssetLoads() {
      // Optional presentation diagnostics must never interrupt drawing.
      try { options.onAssetStatus?.({...assetLoads, base:assetRoot, revision:assetRevision}); }
      catch(error) { console.warn("Asset diagnostics unavailable", error); }
    }
    function loadImage(url) {
      if (!url) return Promise.reject(new Error("asset unavailable"));
      if (images.has(url)) return images.get(url);
      const promise = new Promise((resolve, reject) => {
        const generation = assetGeneration;
        const image = new Image();
        assetLoads.requested++; assetLoads.pending++; assetLoads.last_url=url;
        reportAssetLoads();
        image.onload = () => {
          if(generation !== assetGeneration) { reject(new Error("superseded asset request")); return; }
          assetLoads.loaded++; assetLoads.pending--; assetLoads.last_url=url;
          reportAssetLoads(); resolve(image);
        };
        image.onerror = () => {
          if (generation === assetGeneration) {
            assetLoads.failed++; assetLoads.pending--; assetLoads.last_url=url;
            assetLoads.last_error=`Artwork failed to load: ${url}`;
            reportAssetLoads();
            const report = options.onAssetError || console.warn;
            report(`Artwork failed to load: ${url}`);
          }
          reject(new Error(`asset failed: ${url}`));
        };
        image.src = url;
      });
      images.set(url, promise);
      return promise;
    }

    function setPresentation(value) {
      const valid = value?.contract === "photon.level.assets" && value.version === 1;
      const next = valid ? value : {};
      const revision = JSON.stringify([next.base, next.revision, next.status]);
      if (revision === assetRevision) return false;
      assetRevision = revision;
      assetGeneration += 1;
      assetRoot = next.base ? sandboxRoot + String(next.base).replace(/\/$/, "") : "";
      assetPaths = next.assets || {};
      images.clear(); gameImages.clear(); sceneImages.clear(); markerImages.clear();
      tintedEffectCache.clear(); enemySpriteCache.clear(); effectRasterCache.clear(); enemyGlowCache.clear();
      gameImagesStarted = false;
      assetLoads = {requested:0, loaded:0, failed:0, pending:0, last_url:null, last_error:null};
      reportAssetLoads();
      return true;
    }

    function assetUrl(assetId) {
      const path = assetPaths[String(assetId)];
      return assetRoot && path ? `${assetRoot}/${String(path).replace(/^\//, "")}` : "";
    }

    function towerRuntimeImagePath(type, layer) {
      return assetUrl(`tower/${type}/${layer}`);
    }

    function enemyImagePath(type, frame) {
      return assetUrl(`enemy/${type}/${frame}`);
    }

    function combatEffectPath(name) {
      return assetUrl(`effect/${name}`);
    }

    async function loadGameImages() {
      if (gameImagesStarted || !assetRoot) return;
      gameImagesStarted = true;
      const pending = [];
      for (const assetId of Object.keys(assetPaths)) {
        const upgrade = assetId.match(/^tower\/([^/]+)\/upgrade\/([234])$/);
        if (upgrade) {
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            if (!image) return;
            // Decode the two-cell art once, removing its magenta matte and borders.
            const cell = Math.floor(image.naturalWidth / 2);
            for (const [index, layer] of ['base', 'head'].entries()) {
              const raw = document.createElement('canvas');
              raw.width = cell - 8; raw.height = image.naturalHeight - 8;
              const ctx = raw.getContext('2d', {willReadFrequently: true});
              ctx.drawImage(image, index * cell + 4, 4, raw.width, raw.height, 0, 0, raw.width, raw.height);
              const pixels = ctx.getImageData(0, 0, raw.width, raw.height);
              let left = raw.width, top = raw.height, right = -1, bottom = -1;
              for (let p = 0; p < pixels.data.length; p += 4) {
                const r = pixels.data[p], g = pixels.data[p + 1], b = pixels.data[p + 2];
                if (r > g * 1.6 + 25 && b > g * 1.6 + 25) pixels.data[p + 3] = 0;
                if (pixels.data[p + 3] && layer === 'base') {
                  const x = (p / 4) % raw.width, y = Math.floor(p / 4 / raw.width);
                  left = Math.min(left, x); right = Math.max(right, x);
                  top = Math.min(top, y); bottom = Math.max(bottom, y);
                }
              }
              ctx.putImageData(pixels, 0, 0);
              const texture = document.createElement('canvas');
              texture.width = texture.height = 256;
              if (layer === 'base' && right >= left && bottom >= top) {
                // Fill the existing 88 px sprite box with the pedestal, not atlas padding.
                // Its front armor stays below the raised gun, exposing every tier color.
                const width = right - left + 1, height = bottom - top + 1;
                const scale = Math.min(84 / width, 72 / height);
                const w = width * scale, h = height * scale;
                const toTexture = 256 / TOWER_VISUAL_SIZE;
                texture.getContext('2d').drawImage(raw, left, top, width, height,
                  (TOWER_VISUAL_SIZE / 2 - w / 2) * toTexture,
                  (TOWER_VISUAL_SIZE / 2 + 36 - h) * toTexture,
                  w * toTexture, h * toTexture);
              } else {
                texture.getContext('2d').drawImage(raw, 0, 0, 256, 256);
              }
              raw.width = raw.height = 1;
              gameImages.set(`tower:${upgrade[1]}:${layer}:${upgrade[2]}`, texture);
            }
          }));
          continue;
        }
        if (assetId === 'field/upgrade-atlas') {
          pending.push(loadImage(assetUrl(assetId)).then(image => {
            if (!image) return;
            for (let tier = 2; tier <= 4; tier++) {
              const texture = document.createElement('canvas');
              texture.width = 512; texture.height = 96;
              texture.getContext('2d').drawImage(image, 0, (tier - 2) * image.naturalHeight / 3,
                image.naturalWidth, image.naturalHeight / 3, 0, 0, 512, 96);
              gameImages.set(`field:${tier}`, texture);
            }
          }));
          continue;
        }
        let match = assetId.match(/^tower\/([^/]+)\/(base|head|activation)$/);
        if (match) {
          const [, type, layer] = match;
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            gameImages.set(`tower:${type}:${layer}`, image);
          }));
          continue;
        }
        if (assetId === "tower/socket-cover") {
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            gameImages.set("tower:socket-cover", image);
          }));
          continue;
        }
        match = assetId.match(/^enemy\/([^/]+)\/(\d+)$/);
        if (match) {
          const [, type, frame] = match;
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            gameImages.set(`enemy:${type}:${frame}`, image);
          }));
          continue;
        }
        match = assetId.match(/^effect\/(.+)$/);
        if (match) {
          const effect = match[1];
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            gameImages.set(`effect:${effect}`, image);
          }));
          continue;
        }
        match = assetId.match(/^marker\/(\d+)$/);
        if (match) {
          const markerId = Number(match[1]);
          pending.push(loadImage(assetUrl(assetId)).then((image) => {
            markerImages.set(markerId, image);
          }));
        }
      }
      await Promise.allSettled(pending);
      visualStateCache = null;
    }

    async function loadSceneImages(scene) {
      const assetIds = new Set();
      for (const layer of scene?.layers || []) {
        for (const item of layer.items || []) {
          if (item.kind === "sprite" && item.asset_id) assetIds.add(String(item.asset_id));
        }
      }
      await Promise.allSettled([...assetIds].map((assetId) => (
        loadImage(assetUrl(`map/${assetId}`)).then((image) => {
          sceneImages.set(assetId, image);
        })
      )));
    }

    function socketMarkerVisualSize() {
      const configured = Number(state?.aruco_code_footprint_px);
      return Number.isFinite(configured) ? configured : fixedMarkerVisualSize(208);
    }

    function drawMarker(context, x, y, size, id) {
      const left = Math.round(x - size / 2);
      const top = Math.round(y - size / 2);
      const marker = markerImages.get(Number(id));
      if (marker) {
        context.save();
        context.imageSmoothingEnabled = false;
        context.drawImage(marker, left, top, size, size);
        context.restore();
        return;
      }
      context.save();
      context.fillStyle = "#f4f8ff";
      context.fillRect(left, top, size, size);
      context.strokeStyle = "#071018";
      context.lineWidth = Math.max(4, size * 0.08);
      context.strokeRect(left + 2, top + 2, size - 4, size - 4);
      context.fillStyle = "#071018";
      context.font = `900 ${Math.max(13, Math.round(size * 0.24))}px ui-monospace`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(String(id), x, y);
      context.restore();
    }

    function drawSocketMarkers(context) {
      for (const socket of socketRecords()) {
        drawMarker(context, socket.marker_x, socket.marker_y, socket.marker_size, socket.aruco_id);
      }
    }

    function centralCoreCenter() {
      const x = Number(level?.core?.x);
      const y = Number(level?.core?.y);
      if (Number.isFinite(x) && Number.isFinite(y)) return { x, y };
      const paths = Object.values(level?.paths || {});
      const endpoints = paths.map((path) => path[path.length - 1]).filter(Boolean);
      if (!endpoints.length) return { x: 880, y: 480 };
      return {
        x: endpoints.reduce((sum, point) => sum + Number(point[0]), 0) / endpoints.length,
        y: endpoints.reduce((sum, point) => sum + Number(point[1]), 0) / endpoints.length,
      };
    }

    function coreMarkerRecord() {
      const center = centralCoreCenter();
      const configured = Number(state?.core_aruco_code_footprint_px);
      return {
        x: Number.isFinite(Number(level?.core?.marker_x))
          ? Number(level.core.marker_x) : center.x,
        y: Number.isFinite(Number(level?.core?.marker_y))
          ? Number(level.core.marker_y) : center.y,
        size: Number.isFinite(Number(level?.core?.marker_size))
          ? Number(level.core.marker_size)
          : Number.isFinite(configured) ? configured : CORE_MARKER_VISUAL_SIZE,
      };
    }

    function renderCoreMarkerOverlay(context, gameState) {
      const stage = String(gameState.core_sequence?.stage || "locked");
      if (!["first_tag", "ring_ready"].includes(stage)) return;
      const markerId = gameFacts(gameState).core_marker_id;
      if (markerId == null) return;
      const record = coreMarkerRecord();
      drawMarker(context, record.x, record.y, record.size, markerId);
    }

    function drawSceneItem(context, item) {
      if (item.kind === "sprite") {
        const image = sceneImages.get(String(item.asset_id));
        if (!image) return;
        context.save();
        context.translate(Number(item.origin_x), Number(item.origin_y));
        context.rotate(Number(item.rotation_degrees || 0) * Math.PI / 180);
        const destination = [
          Number(item.draw_x), Number(item.draw_y),
          Number(item.width), Number(item.height),
        ];
        if (Array.isArray(item.source) && item.source.length === 4) {
          context.drawImage(image, ...item.source.map(Number), ...destination);
        } else {
          context.drawImage(image, ...destination);
        }
        context.restore();
        return;
      }
      if (item.kind === "activation_zone") {
        context.fillStyle = "#ff9f4326";
        context.strokeStyle = "#ff9f43";
        context.lineWidth = 3;
        context.fillRect(Number(item.x), Number(item.y), Number(item.width), Number(item.height));
        context.strokeRect(Number(item.x), Number(item.y), Number(item.width), Number(item.height));
        return;
      }
      if (item.kind === "atom_start") {
        context.fillStyle = item.owner === "green" ? "#35d07f" : "#c084fc";
        context.beginPath();
        context.arc(Number(item.x), Number(item.y), 15, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = "#061018";
        context.font = "900 13px ui-monospace";
        context.textAlign = "center";
        context.fillText(String(item.atom_tag_id), Number(item.x), Number(item.y) + 5);
      }
    }

    function renderMapFallback(context) {
      if (!level) return;
      context.fillStyle = "#0b1717";
      context.fillRect(0, 0, WIDTH, HEIGHT);
      context.strokeStyle = "#355750";
      context.lineWidth = 38;
      context.lineCap = "round";
      context.lineJoin = "round";
      for (const path of Object.values(level.paths || {})) {
        context.beginPath();
        path.forEach((point, index) => {
          if (index) context.lineTo(Number(point[0]), Number(point[1]));
          else context.moveTo(Number(point[0]), Number(point[1]));
        });
        context.stroke();
      }
      context.strokeStyle = "#507b70";
      context.lineWidth = 3;
      for (const socket of socketRecords()) {
        context.strokeRect(
          socket.x - socket.size / 2,
          socket.y - socket.size / 2,
          socket.size,
          socket.size,
        );
      }
      const core = centralCoreCenter();
      context.fillStyle = "#132929";
      context.strokeStyle = "#b6ff3a";
      context.lineWidth = 4;
      context.fillRect(core.x - 72, core.y - 72, 144, 144);
      context.strokeRect(core.x - 72, core.y - 72, 144, 144);
    }

    function renderMap() {
      if (!level) return;
      const context = mapCanvas.getContext("2d");
      context.clearRect(0, 0, WIDTH, HEIGHT);
      const scene = level.scene;
      if (
        scene?.contract === "photon.visual-scene"
        && Number(scene.version) === 1
        && Array.isArray(scene.layers)
      ) {
        const sceneSprites = scene.layers.flatMap((layer) => (
          (layer.items || []).filter((item) => item.kind === "sprite")
        ));
        if (sceneSprites.some((item) => !sceneImages.has(String(item.asset_id)))) {
          renderMapFallback(context);
        } else {
          context.fillStyle = "#030609";
          context.fillRect(0, 0, WIDTH, HEIGHT);
        }
        context.imageSmoothingEnabled = false;
        for (const layer of scene.layers) {
          context.save();
          context.globalAlpha = Number(layer.opacity ?? 1);
          for (const item of layer.items || []) drawSceneItem(context, item);
          context.restore();
        }
      } else {
        renderMapFallback(context);
      }
      const marker = coreMarkerRecord();
      const markerId = gameFacts(state).core_marker_id;
      if (markerId != null) drawMarker(context, marker.x, marker.y, marker.size, markerId);
    }

    function visualSimulationTime(now, gameState) {
      const serverTime = Number(gameState.sim_time || 0);
      const advancing = gameState.phase === "running" && !gameState.paused;
      return serverTime + (advancing
        ? boundedVisualAge(stateReceivedAt, now, feedConnected, frozenVisualAge)
        : 0);
    }

    function visualRuntimeTime(now, gameState) {
      return Number(gameState.runtime_time || 0)
        + boundedVisualAge(stateReceivedAt, now, feedConnected, frozenVisualAge);
    }

    function renderCoreHealth(context, gameState) {
      const center = centralCoreCenter();
      const ratio = Math.max(0, Math.min(1, Number(gameState.core_hp) / Math.max(1, Number(gameState.core_max_hp))));
      const percent = Math.round(ratio * 100);
      const width = 144;
      const height = 15;
      const x = center.x - width / 2;
      const y = center.y + 54;
      const color = ratio > 0.5 ? "#35d07f" : ratio > 0.2 ? "#ffb347" : "#ff5367";
      context.save();
      context.shadowColor = "#000";
      context.shadowBlur = 6;
      context.fillStyle = "#05080de8";
      context.fillRect(x - 3, y - 3, width + 6, height + 6);
      context.fillStyle = "#301017";
      context.fillRect(x, y, width, height);
      context.fillStyle = color;
      context.fillRect(x, y, width * ratio, height);
      context.strokeStyle = "#dceaff";
      context.lineWidth = 2;
      context.strokeRect(x, y, width, height);
      context.shadowBlur = 0;
      context.fillStyle = "#fff";
      context.font = "900 11px ui-monospace,monospace";
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(`CORE ${percent}%`, center.x, y + height / 2 + 0.5);
      context.restore();
    }

    function enemyVisualScale(enemyType) {
      if (enemyType !== "brute") return 1;
      const scale = Number(state?.settings?.brute_size_multiplier);
      return Number.isFinite(scale) && scale > 0 ? scale : 56 / 44;
    }

    function enemyVisualSize(enemyType) {
      return 44 / 3 * ENEMY_VISUAL_SCALE * enemyVisualScale(enemyType);
    }

    function cachedEnemySprite(enemyType, frame, facingX, facingY) {
      const directions = 16;
      const rotation = Math.atan2(facingY, facingX) - Math.PI / 2;
      const direction = ((Math.round(rotation / (Math.PI * 2) * directions) % directions) + directions) % directions;
      const drawSize = enemyVisualSize(enemyType);
      const key = `${enemyType}:${frame}:${direction}:${drawSize}`;
      if (enemySpriteCache.has(key)) return enemySpriteCache.get(key);
      const source = gameImages.get(`enemy:${enemyType}:${frame}`);
      if (!source) return null;
      const canvasSize = Math.ceil(drawSize * Math.SQRT2) + 2;
      const sprite = document.createElement("canvas");
      sprite.width = canvasSize;
      sprite.height = canvasSize;
      const spriteContext = sprite.getContext("2d");
      spriteContext.imageSmoothingEnabled = false;
      spriteContext.translate(canvasSize / 2, canvasSize / 2);
      spriteContext.rotate(direction / directions * Math.PI * 2);
      spriteContext.drawImage(source, -drawSize / 2, -drawSize / 2, drawSize, drawSize);
      enemySpriteCache.set(key, sprite);
      return sprite;
    }

    function drawEnemy(context, enemy, visualTime, extrapolationAge, effectQuality) {
      const frame = 1 + (Math.floor(visualTime * 8 + Number(enemy.id || 0)) % 4);
      const size = enemyVisualSize(enemy.enemy_type);
      const facingX = Number(enemy.facing_x ?? 0);
      const facingY = Number(enemy.facing_y ?? 1);
      const rawX = Number(enemy.x) + Number(enemy.vx || 0) * extrapolationAge;
      const rawY = Number(enemy.y) + Number(enemy.vy || 0) * extrapolationAge;
      const electrified = Number(enemy.electrocuted_until || 0) > visualTime;
      const intensity = Math.max(0, Math.min(1, Number(enemy.electrocution_intensity || 0)));
      const shake = electrified ? 2.5 + intensity * 3.5 : 0;
      const x = rawX + (electrified ? Math.sin(visualTime * 61 + Number(enemy.id)) * shake : 0);
      const y = rawY + (electrified ? Math.cos(visualTime * 47 + Number(enemy.id) * 1.7) * shake : 0);
      const sprite = cachedEnemySprite(enemy.enemy_type, frame, facingX, facingY);
      let history = [];
      if (electrified) {
        history = enemyTrailHistory.get(enemy.id) || [];
        if (!history.length || visualTime - history[history.length - 1].at >= 1 / 24) {
          history.push({ x: rawX, y: rawY, at: visualTime });
        }
        while (
          history.length > effectQuality.trailSamples
          || (history[0] && visualTime - history[0].at > 0.42)
        ) history.shift();
        enemyTrailHistory.set(enemy.id, history);
      }
      if (sprite) {
        if (electrified) {
          context.save();
          context.globalCompositeOperation = "lighter";
          for (let index = 0; index < history.length - 1; index += 1) {
            const trail = history[index];
            const alpha = (index + 1) / history.length * 0.16 * intensity;
            context.globalAlpha = alpha;
            context.drawImage(sprite, trail.x - sprite.width / 2, trail.y - sprite.height / 2);
          }
          context.globalAlpha = 0.65 + intensity * 0.35;
          // Applying a Canvas shadow for each enemy makes the browser rasterize
          // hundreds of glows every frame. Bake it with the orientation sprite.
          const glow = effectQuality.shadowScale > 0
            ? electrifiedSprite(sprite, Math.round((9 + intensity * 15) * effectQuality.shadowScale / 4) * 4)
            : sprite;
          context.drawImage(glow, x - glow.width / 2, y - glow.height / 2);
          context.restore();
        } else {
          context.drawImage(sprite, x - sprite.width / 2, y - sprite.height / 2);
        }
        if (Number(enemy.burn_until || 0) > visualTime) {
          // Lower detail slows the flicker animation; the burn cue stays
          // visible on every frame, including at the 60 FPS dense setting.
          const burnFrame = Math.floor(visualTime * 18 / effectQuality.burnFrameDivisor) * effectQuality.burnFrameDivisor;
          const flicker = 0.7 + 0.3 * Math.sin(burnFrame + Number(enemy.id));
          const flame = gameImages.get("effect:flame-burn");
          drawCombatEffect(context, flame, x, y - size * 0.45, size * 1.7, flicker);
        }
        return;
      }
      context.fillStyle = "#84c74a";
      context.beginPath();
      context.arc(x, y, size / 3, 0, Math.PI * 2);
      context.fill();
    }

    function towerPlacementId(tower) {
      return String(tower.placement_id || tower.socket_id);
    }

    function towerTargeting(tower) {
      const preview = towerAimPreview.get(String(tower.parent_placement_id || towerPlacementId(tower)));
      const targeting = tower.targeting || {};
      if (!preview) return targeting;
      const control = aimControl(targeting);
      if (!control) return targeting;
      const spread = Math.max(0, Math.min(1, Number(preview.spread)));
      const angleDegrees = control.directional === false
        ? Number(targeting.angle_degrees || 0)
        : Number(preview.angle);
      const angle = angleDegrees * Math.PI / 180;
      const range = towerAimDistance(control, spread);
      const result = {
        ...targeting, control, angle, angle_degrees: angleDegrees,
        spread, range,
      };
      const halfAngle = controlValue(control, "half_angle", spread);
      if (Number.isFinite(halfAngle)) result.half_angle = halfAngle;
      const blastRadius = controlValue(control, "blast_radius", spread);
      if (Number.isFinite(blastRadius)) result.blast_radius = blastRadius;
      if (control.target_point === true) {
        result.target_x = Number(tower.x) + Math.cos(angle) * range;
        result.target_y = Number(tower.y) + Math.sin(angle) * range;
      }
      return result;
    }

    function drawTargetingOverlay(context, tower) {
      if (tower.destroyed) return;
      const targeting = towerTargeting(tower);
      const selected = String(tower.parent_placement_id || towerPlacementId(tower)) === selectedTowerId;
      const color = tower.owner === "green" ? "53,208,127" : "192,132,252";
      context.save();
      context.strokeStyle = `rgba(${color},${selected ? 0.9 : 0.28})`;
      context.fillStyle = `rgba(${color},${selected ? 0.09 : 0.035})`;
      context.lineWidth = selected ? 2.5 : 1.25;
      context.setLineDash(selected ? [7, 5] : [4, 7]);
      if (tower.tower_type === "mortar") {
        const handle = targetingHandlePoint(tower, targeting);
        context.beginPath();
        context.moveTo(tower.x, tower.y);
        context.lineTo(handle.x, handle.y);
        context.stroke();
        context.beginPath();
        context.arc(handle.x, handle.y, targeting.blast_radius, 0, Math.PI * 2);
        context.fill();
        context.stroke();
      } else if (tower.tower_type === "tesla_coil") {
        context.beginPath();
        context.arc(tower.x, tower.y, Number(targeting.range || 0), 0, Math.PI * 2);
        context.fill();
        context.stroke();
        if (selected) {
          const handle = targetingHandlePoint(tower, targeting);
          context.beginPath();
          context.moveTo(tower.x, tower.y);
          context.lineTo(handle.x, handle.y);
          context.stroke();
        }
      } else {
        const half = Number(targeting.half_angle || 0) * Math.PI / 180;
        const angle = Number(targeting.angle || 0);
        const reach = Number(targeting.range || 0);
        context.beginPath();
        context.moveTo(tower.x, tower.y);
        context.lineTo(tower.x + Math.cos(angle - half) * reach, tower.y + Math.sin(angle - half) * reach);
        context.arc(tower.x, tower.y, reach, angle - half, angle + half);
        context.closePath();
        context.fill();
        context.stroke();
        context.beginPath();
        context.moveTo(tower.x, tower.y);
        context.lineTo(tower.x + Math.cos(angle) * reach, tower.y + Math.sin(angle) * reach);
        context.stroke();
      }
      context.restore();
    }

    function drawAimHandle(context, tower) {
      if (!tower || tower.destroyed || towerPlacementId(tower) !== selectedTowerId) return;
      const handle = targetingHandlePoint(tower, towerTargeting(tower));
      const color = tower.owner === "green" ? "#35d07f" : "#c084fc";
      context.save();
      context.setLineDash([]);
      context.shadowColor = "#36dfff";
      context.shadowBlur = 14;
      context.fillStyle = "#071018";
      context.strokeStyle = "#f4f8ff";
      context.lineWidth = 4;
      context.beginPath();
      context.arc(handle.x, handle.y, AIM_HANDLE_RADIUS, 0, Math.PI * 2);
      context.fill();
      context.stroke();
      context.shadowBlur = 0;
      context.fillStyle = color;
      context.beginPath();
      context.arc(handle.x, handle.y, 6, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }

    function drawCombatEffect(context, image, x, y, size, alpha = 1, rotation = 0, stretch = 1) {
      if (!image) return;
      // Rasterize common small effects at their destination size once. Large
      // continuously growing core effects bypass the bounded cache.
      const width = Math.max(1, Math.round(size * stretch));
      const height = Math.max(1, Math.round(size));
      const source = width <= 256 && height <= 256
        ? scaledImage(image, width, height) : image;
      context.save();
      context.globalAlpha = Math.max(0, Math.min(1, alpha));
      context.translate(x, y);
      context.rotate(rotation);
      context.drawImage(source, -size * stretch / 2, -size / 2, size * stretch, size);
      context.restore();
    }

    function scaledImage(image, width, height) {
      let id = scaledImageIds.get(image);
      if (id == null) { id = ++nextScaledImageId; scaledImageIds.set(image, id); }
      const key = `${id}:${width}:${height}`;
      let raster = effectRasterCache.get(key);
      if (raster) return raster;
      raster = document.createElement("canvas");
      raster.width = width; raster.height = height;
      const context = raster.getContext("2d");
      context.imageSmoothingEnabled = false;
      context.drawImage(image, 0, 0, width, height);
      effectRasterCache.set(key, raster);
      return raster;
    }

    function electrifiedSprite(sprite, blur) {
      let id = scaledImageIds.get(sprite);
      if (id == null) { id = ++nextScaledImageId; scaledImageIds.set(sprite, id); }
      const key = `${id}:${blur}`;
      let raster = enemyGlowCache.get(key);
      if (raster) return raster;
      const padding = Math.max(2, blur * 2);
      raster = document.createElement("canvas");
      raster.width = sprite.width + padding * 2;
      raster.height = sprite.height + padding * 2;
      const paint = raster.getContext("2d");
      paint.shadowColor = "#a96cff"; paint.shadowBlur = blur;
      paint.drawImage(sprite, padding, padding);
      enemyGlowCache.set(key, raster);
      return raster;
    }

    function tintedEffect(image, color) {
      if (!image) return null;
      const key = `${image.src}:${color}`;
      if (tintedEffectCache.has(key)) return tintedEffectCache.get(key);
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth || image.width;
      canvas.height = image.naturalHeight || image.height;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0);
      context.globalCompositeOperation = "source-in";
      context.fillStyle = color;
      context.fillRect(0, 0, canvas.width, canvas.height);
      tintedEffectCache.set(key, canvas);
      return canvas;
    }

    function drawCoreSequence(context, gameState, visualTime, foreground = false) {
      const sequence = gameState.core_sequence || {};
      const stage = String(sequence.stage || "locked");
      const center = { x: Number(sequence.x ?? 880), y: Number(sequence.y ?? 480) };
      const pulse = 0.82 + Math.sin(visualTime * 6) * 0.1;
      if (!foreground && stage === "ring_ready") {
        drawCombatEffect(context, gameImages.get("effect:core-ring-aura"), center.x, center.y, 210, pulse);
      }
      if (!foreground && stage === "first_tag") {
        const greenAura = tintedEffect(gameImages.get("effect:core-ring-aura"), "#49ff88");
        drawCombatEffect(context, greenAura, center.x, center.y, 220, pulse);
        context.save();
        context.strokeStyle = `rgba(73,255,136,${pulse})`;
        context.shadowColor = "#49ff88";
        context.shadowBlur = 22;
        context.lineWidth = 7;
        context.beginPath();
        context.arc(center.x, center.y, 74, 0, Math.PI * 2);
        context.stroke();
        context.restore();
      }
      if (foreground && ["detonating", "complete"].includes(stage)) {
        const progress = Math.max(0, Math.min(1, Number(sequence.detonation_progress || 0)));
        if (progress < 0.32) {
          const burstAlpha = Math.max(0, 1 - progress / 0.34);
          drawCombatEffect(
            context,
            gameImages.get("effect:core-detonation-burst"),
            center.x,
            center.y,
            190 + progress * 260,
            burstAlpha,
          );
        }
        if (progress > 0 && progress < 1) {
          const radius = Number(sequence.detonation_radius || 0);
          drawCombatEffect(
            context,
            gameImages.get("effect:core-purge-wave"),
            center.x,
            center.y,
            Math.max(80, radius * 2.12),
            Math.min(1, 0.45 + (1 - progress) * 0.5),
          );
        }
      }
    }

    function drawSheetFrame(context, image, frame, frames, x, y, width, height, alpha = 1) {
      if (!image) return;
      const sourceWidth = (image.naturalWidth || image.width) / frames;
      const sourceHeight = image.naturalHeight || image.height;
      const index = ((Math.floor(frame) % frames) + frames) % frames;
      context.save();
      context.globalAlpha = Math.max(0, Math.min(1, alpha));
      context.drawImage(
        image,
        index * sourceWidth,
        0,
        sourceWidth,
        sourceHeight,
        x - width / 2,
        y - height,
        width,
        height,
      );
      context.restore();
    }

    function drawAtlasFrame(context, image, frame, columns, rows, x, y, width, height, alpha = 1, rotation = 0) {
      if (!image) return;
      const sourceWidth = (image.naturalWidth || image.width) / columns;
      const sourceHeight = (image.naturalHeight || image.height) / rows;
      const count = columns * rows;
      const index = ((Math.floor(frame) % count) + count) % count;
      const column = index % columns;
      const row = Math.floor(index / columns);
      context.save();
      context.globalAlpha = Math.max(0, Math.min(1, alpha));
      context.translate(x, y);
      context.rotate(rotation);
      context.drawImage(
        image,
        column * sourceWidth,
        row * sourceHeight,
        sourceWidth,
        sourceHeight,
        -width / 2,
        -height / 2,
        width,
        height,
      );
      context.restore();
    }

    function angleDelta(angle, reference) {
      return (angle - reference + Math.PI * 3) % (Math.PI * 2) - Math.PI;
    }

    function flamethrowerVisualAngleAt(tower, visualTime) {
      const targeting = towerTargeting(tower);
      const half = Number(targeting.half_angle || 0) * Math.PI / 180;
      const phaseOffset = (Number(tower.aruco_id || 0) % 7) / 7;
      const phase = ((visualTime / 1.6 + phaseOffset) % 1 + 1) % 1;
      const oscillation = 4 * Math.abs(phase - 0.5) - 1;
      return Number(targeting.angle || 0) + half * oscillation;
    }

    function drawFlamethrowerPilotFlame(
      context, tower, visualTime, turretAngle, effectQuality
    ) {
      const delayedAngle = flamethrowerVisualAngleAt(
        tower,
        visualTime - FLAMETHROWER_PILOT_LAG_S,
      );
      const origin = towerHeadOrigin(tower, true);
      const nozzle = flamethrowerNozzlePoint(origin.x, origin.y, turretAngle, origin.scale);
      const nozzleX = nozzle.x;
      const nozzleY = nozzle.y;
      const directionX = Math.cos(delayedAngle);
      const directionY = Math.sin(delayedAngle);
      const normalX = -directionY;
      const normalY = directionX;
      const seed = Number(tower.aruco_id || 0) * 0.37;
      const flicker = Math.sin(visualTime * 31 + seed) * 0.85
        + Math.sin(visualTime * 47 + seed * 1.9) * 0.45;
      const length = 9.5 + flicker;
      const width = 2.8 + Math.sin(visualTime * 37 + seed) * 0.35;
      const tipX = nozzleX + directionX * length;
      const tipY = nozzleY + directionY * length;

      context.save();
      context.globalCompositeOperation = "lighter";
      context.shadowColor = "#159dff";
      context.shadowBlur = 8 * effectQuality.shadowScale;
      context.fillStyle = "#147dff";
      context.beginPath();
      context.moveTo(nozzleX + normalX * width, nozzleY + normalY * width);
      context.quadraticCurveTo(
        nozzleX + directionX * length * 0.46 + normalX * width * 0.72,
        nozzleY + directionY * length * 0.46 + normalY * width * 0.72,
        tipX,
        tipY,
      );
      context.quadraticCurveTo(
        nozzleX + directionX * length * 0.38 - normalX * width * 0.72,
        nozzleY + directionY * length * 0.38 - normalY * width * 0.72,
        nozzleX - normalX * width,
        nozzleY - normalY * width,
      );
      context.closePath();
      context.fill();

      context.shadowBlur = 4 * effectQuality.shadowScale;
      context.fillStyle = "#c9f7ff";
      context.beginPath();
      context.moveTo(nozzleX + normalX * width * 0.38, nozzleY + normalY * width * 0.38);
      context.quadraticCurveTo(
        nozzleX + directionX * length * 0.34,
        nozzleY + directionY * length * 0.34,
        nozzleX + directionX * length * 0.68,
        nozzleY + directionY * length * 0.68,
      );
      context.quadraticCurveTo(
        nozzleX + directionX * length * 0.28,
        nozzleY + directionY * length * 0.28,
        nozzleX - normalX * width * 0.38,
        nozzleY - normalY * width * 0.38,
      );
      context.closePath();
      context.fill();
      context.restore();
    }

    function drawCurvedFlame(context, tower, visualTime, alpha, effectQuality) {
      const image = gameImages.get("effect:flame-gasoline");
      if (!image) return;
      const currentAngle = flamethrowerVisualAngleAt(tower, visualTime);
      const reach = Number(towerTargeting(tower).range);
      if (!Number.isFinite(reach) || reach <= 0) return;
      const segmentCount = Math.max(
        1,
        Math.min(FLAMETHROWER_PATH_SEGMENTS, effectQuality.flameSegments),
      );
      const origin = towerHeadOrigin(tower);
      const segmentLength = Math.max(1, reach - FLAMETHROWER_MUZZLE_OFFSET * origin.scale) / segmentCount;
      const pulse = 0.94 + Math.sin(visualTime * 34) * 0.06;
      const points = [flamethrowerNozzlePoint(
        origin.x, origin.y, currentAngle, origin.scale,
      )];
      for (let index = 0; index < segmentCount; index += 1) {
        const progress = (index + 1) / segmentCount;
        const delayedAngle = flamethrowerVisualAngleAt(
          tower,
          visualTime - progress * FLAMETHROWER_TRAIL_LAG_S,
        );
        const flutter = Math.sin(visualTime * 18 - index * 0.72) * 0.065 * progress;
        const previous = points[points.length - 1];
        points.push({
          x: previous.x + Math.cos(delayedAngle + flutter) * segmentLength,
          y: previous.y + Math.sin(delayedAngle + flutter) * segmentLength,
        });
      }
      context.save();
      context.globalAlpha = Math.max(0, Math.min(1, alpha));
      context.shadowColor = "#ff6a16";
      context.shadowBlur = 7 * effectQuality.shadowScale;
      for (let index = segmentCount - 1; index >= 0; index -= 1) {
        const start = points[index];
        const end = points[index + 1];
        const angle = Math.atan2(end.y - start.y, end.x - start.x);
        const sourceX = Math.floor(image.width * index / segmentCount);
        const sourceRight = Math.ceil(image.width * (index + 1) / segmentCount);
        const destinationLength = Math.hypot(end.x - start.x, end.y - start.y) + 4;
        context.save();
        context.translate((start.x + end.x) / 2, (start.y + end.y) / 2);
        context.rotate(angle);
        context.drawImage(
          image,
          sourceX,
          0,
          Math.max(1, sourceRight - sourceX),
          image.height,
          -destinationLength / 2,
          -15 * pulse,
          destinationLength,
          30 * pulse,
        );
        context.restore();
      }
      context.restore();
    }

    function livePodVisualSize() {
      return LIVE_POD_SIZE;
    }

    function hasUpgradedTowerArt(tower) {
      return gameImages.has(`tower:${tower.tower_type}:head:${tower.upgrade_level}`)
        && gameImages.has(`tower:${tower.tower_type}:base:${tower.upgrade_level}`);
    }

    function towerHeadOrigin(tower, bodySpace = false) {
      const upgraded = hasUpgradedTowerArt(tower);
      const unitScale = bodySpace ? 1 : towerUnitScale(tower);
      return {x: Number(tower.x), y: Number(tower.y) - (upgraded ? UPGRADED_HEAD_LIFT * unitScale : 0),
        scale: (upgraded ? UPGRADED_HEAD_SCALE : 1) * unitScale};
    }

    function towerUnitScale(tower) {
      return tower.is_companion ? Number(tower.pod_size || 96) / LIVE_POD_SIZE : 1;
    }

    function towerVisualRecord(tower, socketsById) {
      if (tower.is_companion) return {...tower, x: Number(tower.visual_x), y: Number(tower.visual_y),
        visual_offset_x: Number(tower.visual_x) - Number(tower.x),
        visual_offset_y: Number(tower.visual_y) - Number(tower.y)};
      const socket = socketsById.get(String(tower.socket_id));
      const gameplayY = Number(tower.y);
      const opticalY = Number(socket?.marker_y);
      if (!Number.isFinite(gameplayY) || !Number.isFinite(opticalY)) return tower;
      return {
        ...tower,
        y: opticalY,
        visual_offset_y: opticalY - gameplayY,
      };
    }

    function towerVisualState(nextState, socketsById) {
      const towers = [...(nextState.towers || []), ...(nextState.companions || [])].map((tower) => (
        towerVisualRecord(tower, socketsById)
      ));
      const towersByPlacementId = new Map(towers.map((tower) => [
        towerPlacementId(tower),
        tower,
      ]));
      const projectiles = (nextState.projectiles || []).map((projectile) => {
        const tower = towersByPlacementId.get(String(projectile.tower_id));
        // Launch metadata keeps rounds stable through a downgrade/replacement.
        const offsetX = Number(projectile.origin_visual_offset_x ?? tower?.visual_offset_x ?? 0);
        const unitScale = projectile.origin_pod_size != null ? Number(projectile.origin_pod_size) / LIVE_POD_SIZE
          : tower ? towerUnitScale(tower) : 1;
        const upgraded = projectile.origin_upgrade_level != null ? Number(projectile.origin_upgrade_level) > 1
          : tower && hasUpgradedTowerArt(tower);
        const offsetY = Number(projectile.origin_visual_offset_y ?? tower?.visual_offset_y ?? 0)
          - (upgraded ? UPGRADED_HEAD_LIFT * unitScale : 0);
        if (!Number.isFinite(offsetY)) return projectile;
        return {
          ...projectile,
          origin_x: Number(projectile.origin_x) + offsetX,
          origin_y: Number(projectile.origin_y) + offsetY,
        };
      });
      return { ...nextState, towers, projectiles };
    }

    function towerActivationDuration(gameState = state) {
      const snapshotDuration = Number(gameState?.tower_activation_duration_s);
      if (Number.isFinite(snapshotDuration) && snapshotDuration > 0) return snapshotDuration;
      return TOWER_ACTIVATION_DURATION_S;
    }

    function towerActivationAge(tower, runtimeVisualTime) {
      const startedAt = Number(tower.activation_started_at);
      return Number.isFinite(startedAt) ? Number(runtimeVisualTime) - startedAt : Infinity;
    }

    function towerIsActivating(tower, runtimeVisualTime, gameState = state) {
      const age = towerActivationAge(tower, runtimeVisualTime);
      return !tower.destroyed && age >= 0 && age < towerActivationDuration(gameState);
    }

    function drawTowerActivation(context, tower, runtimeVisualTime, gameState = state) {
      if (!towerIsActivating(tower, runtimeVisualTime, gameState)) return false;
      const image = gameImages.get(`tower:${tower.tower_type}:activation`);
      if (!image) return false;
      const age = towerActivationAge(tower, runtimeVisualTime);
      const frame = Math.min(
        TOWER_ACTIVATION_FRAMES - 1,
        Math.floor(age * TOWER_ACTIVATION_FPS),
      );
      drawSheetFrame(
        context,
        image,
        frame,
        TOWER_ACTIVATION_FRAMES,
        tower.x,
        tower.y + LIVE_POD_SIZE / 2,
        LIVE_POD_SIZE,
        LIVE_POD_SIZE,
      );
      return true;
    }

    function drawTowerIdleStatus(context, tower, visualTime) {
      const phase = (Math.sin(visualTime * Math.PI * 1.5 + Number(tower.aruco_id || 0)) + 1) / 2;
      const color = tower.owner === "green" ? "53,208,127" : "192,132,252";
      context.save();
      context.fillStyle = `rgba(${color},${0.22 + phase * 0.34})`;
      for (const [dx, dy] of TOWER_CORNER_OFFSETS) {
        context.fillRect(tower.x + dx - 3, tower.y + dy - 3, 6, 6);
      }
      context.restore();
    }

    function drawTowerReplenishPulse(
      context, tower, runtimeVisualTime, effectQuality
    ) {
      const replenishedAt = Number(tower.replenished_at);
      const snapshotDuration = Number(state?.tower_replenish_pulse_s);
      const duration = Number.isFinite(snapshotDuration) && snapshotDuration > 0
        ? snapshotDuration
        : TOWER_REPLENISH_PULSE_S;
      const age = Number(runtimeVisualTime) - replenishedAt;
      if (!Number.isFinite(replenishedAt) || age < 0 || age > duration) return;
      const progress = age / duration;
      const envelope = Math.sin(progress * Math.PI);
      const color = tower.owner === "green" ? "53,208,127" : "192,132,252";
      context.save();
      context.strokeStyle = `rgba(${color},${envelope})`;
      context.shadowColor = `rgb(${color})`;
      context.shadowBlur = 18 * envelope * effectQuality.shadowScale;
      context.lineWidth = 3;
      context.beginPath();
      context.arc(tower.x, tower.y, 48 + progress * 15, 0, Math.PI * 2);
      context.stroke();
      context.fillStyle = `rgba(${color},${0.38 + envelope * 0.5})`;
      for (const [dx, dy] of TOWER_CORNER_OFFSETS) {
        context.fillRect(tower.x + dx - 5, tower.y + dy - 5, 10, 10);
      }
      context.restore();
    }

    function desiredTowerAngle(tower, visualTime) {
      if (tower.tower_type === "flamethrower") return flamethrowerVisualAngleAt(tower, visualTime);
      if (tower.tower_type === "tesla_coil") return 0;
      const firedAt = Number(tower.last_fire_at);
      if (tower.tower_type === "machine_gun" && Number.isFinite(firedAt) && visualTime - firedAt <= 0.32) {
        return Number(tower.facing_angle ?? tower.targeting?.angle ?? 0);
      }
      return Number(tower.targeting?.angle ?? tower.facing_angle ?? 0);
    }

    function smoothTowerAngle(tower, visualTime) {
      const id = towerPlacementId(tower);
      const desired = desiredTowerAngle(tower, visualTime);
      const previous = towerRenderAngles.has(id) ? towerRenderAngles.get(id) : desired;
      const response = tower.tower_type === "flamethrower" ? 1 : 0.24;
      const next = previous + angleDelta(desired, previous) * response;
      towerRenderAngles.set(id, next);
      return next;
    }

    function seededValue(seed) {
      const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
      return value - Math.floor(value);
    }

    function drawTeslaIdleCharge(context, tower, visualTime, effectQuality) {
      const firedAt = Number(tower.last_fire_at);
      const fireAge = visualTime - firedAt;
      if (
        Number.isFinite(firedAt)
        && fireAge >= 0
        && fireAge < TESLA_DISCHARGE_FLASH_S
      ) return;
      const snapshotTime = Number(state?.sim_time);
      const elapsed = Number.isFinite(snapshotTime)
        ? Math.max(0, visualTime - snapshotTime)
        : 0;
      const charge = advancedWeaponCharge(
        tower.weapon_charge,
        tower.charge_duration_s,
        elapsed,
      );
      if (charge <= 0.01) return;

      const towerSeed = Number(tower.aruco_id || 0) * 17.17;
      const frame = Math.floor(visualTime * (14 + charge * 10));
      const fluctuation = 0.76
        + 0.16 * Math.sin(visualTime * 19 + towerSeed)
        + 0.08 * Math.sin(visualTime * 37 + towerSeed * 1.7);
      const energy = Math.max(0.04, Math.min(1, charge * fluctuation));
      const {x, y} = towerHeadOrigin(tower, true);
      const outerRadius = 27;
      const terminalRadius = 8;

      context.save();
      context.globalCompositeOperation = "lighter";
      const haloRadius = Math.round(17 + charge * 8);
      const haloKey = `tesla-halo:${haloRadius}`;
      let halo = effectRasterCache.get(haloKey);
      if (!halo) {
        halo = document.createElement("canvas");
        halo.width = halo.height = 52;
        const paint = halo.getContext("2d");
        const gradient = paint.createRadialGradient(26, 26, 2, 26, 26, haloRadius);
        gradient.addColorStop(0, "rgba(244,249,255,0.32)");
        gradient.addColorStop(0.28, "rgba(76,219,255,0.25)");
        gradient.addColorStop(0.66, "rgba(142,83,255,0.12)");
        gradient.addColorStop(1, "rgba(70,110,255,0)");
        paint.fillStyle = gradient;
        paint.fillRect(0, 0, 52, 52);
        effectRasterCache.set(haloKey, halo);
      }
      context.globalAlpha = energy;
      context.drawImage(halo, x - 26, y - 26);

      const arcCount = Math.max(
        1,
        Math.round((1 + Math.floor(charge * 4)) * effectQuality.teslaIdleArcScale),
      );
      context.lineCap = "round";
      context.lineJoin = "round";
      for (let arc = 0; arc < arcCount; arc += 1) {
        const seed = towerSeed + frame * 13 + arc * 31;
        const angle = Math.PI * 2 * (
          arc / arcCount + seededValue(seed) * 0.16
        );
        const points = [];
        for (let step = 0; step <= 4; step += 1) {
          const progress = step / 4;
          const radius = outerRadius * (1 - progress)
            + terminalRadius * progress;
          const bend = (
            seededValue(seed + step * 7) - 0.5
          ) * 0.62 * Math.sin(progress * Math.PI);
          points.push({
            x: x + Math.cos(angle + bend) * radius,
            y: y + Math.sin(angle + bend) * radius,
          });
        }
        for (const [color, width, alpha] of [
          ["#7447ff", 3.8, 0.34],
          ["#43dcff", 2.1, 0.72],
          ["#f4fbff", 0.8, 0.95],
        ].slice(3 - effectQuality.lightningLayers)) {
          context.strokeStyle = color;
          context.lineWidth = width;
          context.globalAlpha = alpha * energy;
          context.shadowColor = color;
          context.shadowBlur = 7 * energy * effectQuality.shadowScale;
          context.beginPath();
          context.moveTo(points[0].x, points[0].y);
          for (let index = 1; index < points.length; index += 1) {
            context.lineTo(points[index].x, points[index].y);
          }
          context.stroke();
        }
      }

      context.globalAlpha = 0.5 + energy * 0.5;
      context.fillStyle = "#f4fbff";
      context.shadowColor = "#43dcff";
      context.shadowBlur = (8 + energy * 10) * effectQuality.shadowScale;
      context.beginPath();
      context.arc(x, y, 1.8 + energy * 2.2, 0, Math.PI * 2);
      context.fill();
      context.restore();
    }

    function drawLightning(
      context, ax, ay, bx, by, intensity, seed, visualTime, effectQuality
    ) {
      const dx = bx - ax;
      const dy = by - ay;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const normalX = -dy / distance;
      const normalY = dx / distance;
      const steps = Math.max(
        5,
        Math.min(13, Math.round(distance / effectQuality.lightningStepPx)),
      );
      const frameSeed = Math.floor(visualTime * 28);
      const points = [];
      for (let index = 0; index <= steps; index += 1) {
        const progress = index / steps;
        const envelope = Math.sin(progress * Math.PI);
        const jitter = (seededValue(seed * 71 + frameSeed * 17 + index * 13) - 0.5) * 22 * envelope;
        points.push([ax + dx * progress + normalX * jitter, ay + dy * progress + normalY * jitter]);
      }
      context.save();
      context.lineCap = "round";
      context.lineJoin = "round";
      context.shadowColor = "#a96cff";
      // The layered colored strokes supply the halo. Blurring each long bolt
      // repeatedly rasterizes its large bounding box and stalls compositing.
      context.shadowBlur = 0;
      const lightningLayers = [
        ["#7c35ff", 8 * intensity, 0.45],
        ["#ca8cff", 4 * intensity, 0.82],
        ["#f5f1ff", 1.7 * intensity, 1],
      ];
      for (const [color, width, alpha] of lightningLayers.slice(
        -effectQuality.lightningLayers
      )) {
        context.strokeStyle = color;
        context.lineWidth = Math.max(0.8, width);
        context.globalAlpha = alpha * intensity;
        context.beginPath();
        context.moveTo(points[0][0], points[0][1]);
        for (let index = 1; index < points.length; index += 1) context.lineTo(points[index][0], points[index][1]);
        context.stroke();
      }
      context.restore();
    }

    function drawMortarEffects(context, gameState, visualTime, effectQuality) {
      const shell = gameImages.get("effect:mortar-shell");
      for (const projectile of gameState.projectiles || []) {
        const launchAt = Number(projectile.launch_at);
        const impactAt = Number(projectile.impact_at);
        const progress = Math.max(0, Math.min(1, (visualTime - launchAt) / Math.max(0.01, impactAt - launchAt)));
        const groundX = Number(projectile.origin_x) + (Number(projectile.target_x) - Number(projectile.origin_x)) * progress;
        const groundY = Number(projectile.origin_y) + (Number(projectile.target_y) - Number(projectile.origin_y)) * progress;
        const arc = Math.sin(progress * Math.PI);
        const size = 20 + arc * 64;
        context.save();
        context.globalAlpha = 0.22 + (1 - arc) * 0.18;
        context.fillStyle = "#000";
        context.beginPath();
        context.ellipse(groundX, groundY + 8, 10 + arc * 20, 4 + arc * 8, 0, 0, Math.PI * 2);
        context.fill();
        context.restore();
        const angle = Math.atan2(Number(projectile.target_y) - Number(projectile.origin_y), Number(projectile.target_x) - Number(projectile.origin_x));
        drawCombatEffect(context, shell, groundX, groundY - arc * 92, size, 1, angle + Math.PI / 2, 0.66);
      }
      for (const impact of gameState.mortar_impacts || []) {
        const age = visualTime - Number(impact.impact_at);
        if (age < 0 || age > 0.9) continue;
        const radius = Number(impact.blast_radius || 80);
        for (let index = 0; index < effectQuality.mortarImpactSprites; index += 1) {
          const localAge = age - index * 0.055;
          if (localAge < 0 || localAge > 0.52) continue;
          const angle = seededValue(Number(impact.projectile_id) * 31 + index) * Math.PI * 2;
          const distance = Math.sqrt(seededValue(Number(impact.projectile_id) * 47 + index * 3)) * radius * 0.58;
          const x = Number(impact.x) + Math.cos(angle) * distance;
          const y = Number(impact.y) + Math.sin(angle) * distance;
          const alpha = Math.max(0, 1 - localAge / 0.52);
          drawCombatEffect(context, gameImages.get("effect:mortar-impact"), x, y, 55 + radius * 0.34, alpha, angle);
        }
      }
    }

    function drawTowerHealthEffects(context, tower, visualTime, effectQuality) {
      const maximum = Math.max(1, Number(tower.max_hp || 1));
      const ratio = Math.max(0, Math.min(1, Number(tower.hp || 0) / maximum));
      if (ratio >= 0.5 || tower.destroyed) return;
      const frame = Math.floor(visualTime * 8 + Number(tower.aruco_id || 0));
      const crackFrame = ratio < 0.1 ? 2 : ratio < 0.3 ? 1 : 0;
      const crackAlpha = 0.62 + Math.min(0.32, (0.5 - ratio) * 0.9);
      drawSheetFrame(
        context,
        gameImages.get("effect:tower-stress-cracks"),
        crackFrame,
        3,
        tower.x,
        tower.y + 44,
        92,
        92,
        crackAlpha,
      );
      if (ratio < 0.3) {
        const smokeSeverity = Math.min(1, (0.3 - ratio) / 0.3);
        for (let index = 0; index < effectQuality.towerSmokePuffs; index += 1) {
          const phase = ((visualTime * (0.48 + index * 0.045) + index * 0.31 + Number(tower.aruco_id || 0) * 0.017) % 1 + 1) % 1;
          const envelope = Math.sin(phase * Math.PI);
          const x = Number(tower.x) + 7 + phase * (34 + smokeSeverity * 18) + Math.sin(visualTime * 3 + index) * 4;
          const y = Number(tower.y) + 7 - phase * (62 + smokeSeverity * 28);
          const width = (84 + smokeSeverity * 34) * (0.82 + index * 0.08);
          const height = (108 + smokeSeverity * 42) * (0.82 + index * 0.08);
          const alpha = envelope * (0.36 + smokeSeverity * 0.5) * (1 - index * 0.1);
          drawSheetFrame(context, gameImages.get("effect:tower-smoke"), frame + index, 4, x, y, width, height, alpha);
        }
      }
      if (ratio < 0.1) {
        const fireSeverity = Math.min(1, (0.1 - ratio) / 0.1);
        const fireWidth = 90 + fireSeverity * 35;
        const fireHeight = 108 + fireSeverity * 32;
        context.save();
        const glow = context.createRadialGradient(tower.x, tower.y, 4, tower.x, tower.y, 46 + fireSeverity * 20);
        glow.addColorStop(0, `rgba(255,245,180,${0.32 + fireSeverity * 0.3})`);
        glow.addColorStop(0.45, `rgba(255,102,20,${0.18 + fireSeverity * 0.2})`);
        glow.addColorStop(1, "rgba(255,60,8,0)");
        context.fillStyle = glow;
        context.beginPath();
        context.arc(tower.x, tower.y, 66 + fireSeverity * 18, 0, Math.PI * 2);
        context.fill();
        context.restore();
        drawSheetFrame(context, gameImages.get("effect:tower-fire"), frame, 4, tower.x - 7, tower.y + 40, fireWidth, fireHeight, 0.82 + fireSeverity * 0.18);
        drawSheetFrame(context, gameImages.get("effect:tower-fire"), frame + 2, 4, tower.x + 12, tower.y + 32, fireWidth * 0.72, fireHeight * 0.82, 0.58 + fireSeverity * 0.24);
        const emberCount = Math.max(
          2,
          Math.round((4 + fireSeverity * 8) * effectQuality.towerEmberScale),
        );
        for (let index = 0; index < emberCount; index += 1) {
          const seed = Number(tower.aruco_id || 0) * 37 + index * 19;
          const phase = ((visualTime * (1.4 + seededValue(seed) * 1.2) + seededValue(seed + 1)) % 1 + 1) % 1;
          const x = tower.x + (seededValue(seed + 2) - 0.35) * (46 + fireSeverity * 32) + phase * 16;
          const y = tower.y + 20 - phase * (58 + seededValue(seed + 3) * 42);
          const size = 2 + seededValue(seed + 4) * (3 + fireSeverity * 3);
          context.fillStyle = phase < 0.55 ? "#fff2a8" : phase < 0.82 ? "#ff9c24" : "#ff4c12";
          context.globalAlpha = Math.sin(phase * Math.PI) * (0.65 + fireSeverity * 0.35);
          context.fillRect(x, y, size, size);
        }
        context.globalAlpha = 1;
      }
    }

    function drawTowerDestruction(context, tower, visualTime, effectQuality) {
      const age = visualTime - Number(tower.destroyed_at);
      if (!Number.isFinite(age) || age < 0 || age > 4.6) return;
      if (age <= 0.4) {
        const blastProgress = Math.max(0, Math.min(1, age / 0.4));
        drawSheetFrame(
          context,
          gameImages.get("effect:tower-destruction-blast"),
          Math.min(3, Math.floor(blastProgress * 4)),
          4,
          tower.x,
          tower.y + 82,
          122 + blastProgress * 52,
          122 + blastProgress * 52,
          1 - Math.max(0, (blastProgress - 0.72) / 0.28),
        );
      }
      const flightDuration = 1.1;
      const settledUntil = flightDuration + 3.0;
      const debrisAlpha = age <= settledUntil
        ? 1
        : Math.max(0, 1 - (age - settledUntil) / 0.5);
      const flight = Math.max(0, Math.min(1, age / flightDuration));
      const debris = gameImages.get("effect:tower-debris");
      for (let index = 0; index < effectQuality.destructionDebris; index += 1) {
        const seed = Number(tower.aruco_id || 0) * 101 + index * 43;
        const angle = seededValue(seed) * Math.PI * 2;
        const distance = 52 + seededValue(seed + 1) * 50;
        const landingX = Number(tower.x) + Math.cos(angle) * distance;
        const landingY = Number(tower.y) + Math.sin(angle) * distance * 0.72;
        const groundX = Number(tower.x) + (landingX - Number(tower.x)) * flight;
        const groundY = Number(tower.y) + (landingY - Number(tower.y)) * flight;
        const arc = Math.sin(flight * Math.PI) * (54 + seededValue(seed + 2) * 42);
        const scale = 1 + arc / 105;
        const baseSize = 24 + seededValue(seed + 3) * 13;
        context.save();
        context.globalAlpha = debrisAlpha * (0.16 + flight * 0.18);
        context.fillStyle = "#020304";
        context.beginPath();
        context.ellipse(groundX, groundY + 5, baseSize * 0.46, baseSize * 0.19, angle, 0, Math.PI * 2);
        context.fill();
        context.restore();
        drawAtlasFrame(
          context,
          debris,
          index,
          4,
          2,
          groundX,
          groundY - arc,
          baseSize * scale,
          baseSize * scale,
          debrisAlpha,
          angle + flight * (3.2 + seededValue(seed + 4) * 4.5),
        );
      }
    }

    function drawTowerFireEffect(
      context, tower, visualTime, enemiesById, effectQuality
    ) {
      const firedAt = Number(tower.last_fire_at);
      const target = tower.last_fire_target;
      if (!Number.isFinite(firedAt) || !target || tower.destroyed) return;
      const age = visualTime - firedAt;
      if (age < 0 || age > 0.58) return;
      const tx = Number(target.x);
      const ty = Number(target.y);
      if (tower.tower_type === "mortar") return;
      if (tower.tower_type === "tesla_coil") {
        let previous = towerHeadOrigin(tower);
        for (const link of tower.last_fire_chain || []) {
          const enemy = enemiesById.get(Number(link.enemy_id));
          const next = enemy ? { x: Number(enemy.x), y: Number(enemy.y) } : { x: Number(link.x), y: Number(link.y) };
          const intensity = Math.max(0.14, Number(link.intensity || 0) * (1 - age / 0.58));
          drawLightning(
            context,
            previous.x,
            previous.y,
            next.x,
            next.y,
            intensity,
            Number(link.enemy_id),
            visualTime,
            effectQuality,
          );
          drawCombatEffect(context, gameImages.get("effect:tesla-spark"), next.x, next.y, 32 + intensity * 23, intensity, visualTime * 2.2);
          previous = next;
        }
        return;
      }
      if (tower.tower_type === "flamethrower") {
        if (age > 0.34) return;
        drawCurvedFlame(
          context, tower, visualTime, 1 - age / 0.62, effectQuality
        );
        return;
      }
      if (tower.tower_type === "machine_gun" && age <= 0.24) {
        const origin = towerHeadOrigin(tower);
        const liveTarget = enemiesById.get(Number(target.enemy_id));
        const targetX = liveTarget ? Number(liveTarget.x) : tx;
        const targetY = liveTarget ? Number(liveTarget.y) : ty;
        const fireAngle = Math.atan2(
          targetY - Number(tower.y), targetX - Number(tower.x)
        );
        const fireLines = machineGunFireLines(
          origin.x,
          origin.y,
          fireAngle,
          targetX,
          targetY,
          origin.scale,
        );
        for (let barrel = 0; barrel < fireLines.length; barrel += 1) {
          const line = fireLines[barrel];
          const dx = line.bx - line.ax;
          const dy = line.by - line.ay;
          const lineAngle = Math.atan2(dy, dx);
          drawCombatEffect(
            context,
            gameImages.get("effect:machine-gun-impact"),
            line.ax,
            line.ay,
            23,
            0.9,
            lineAngle,
          );
          for (let index = 0; index < effectQuality.machineGunBullets; index += 1) {
            const progress = (
              (visualTime * 8.5 + index * 0.245 + barrel * 0.08) % 1 + 1
            ) % 1;
            const x = line.ax + dx * progress;
            const y = line.ay + dy * progress;
            drawCombatEffect(
              context,
              gameImages.get("effect:machine-gun-bullet"),
              x,
              y,
              10,
              0.95 - index * 0.09,
              lineAngle,
              2.8,
            );
          }
        }
        drawCombatEffect(
          context,
          gameImages.get("effect:machine-gun-impact"),
          targetX,
          targetY,
          42,
          1 - age / 0.24,
          fireAngle,
        );
      }
    }

    function arucoFieldKeepOuts(extraKeepOuts = []) {
      if (staticFieldKeepOutCache && !extraKeepOuts.length) {
        return staticFieldKeepOutCache;
      }
      const clearance = Number.isFinite(Number(
        state?.force_field_marker_clearance_px
      ))
        ? Number(state.force_field_marker_clearance_px)
        : ARUCO_FIELD_CLEARANCE;
      const coreMarkerSize = Number.isFinite(Number(
        state?.core_aruco_code_footprint_px
      ))
        ? Number(state.core_aruco_code_footprint_px)
        : CORE_MARKER_VISUAL_SIZE;
      if (!staticFieldKeepOutCache) {
        const staticKeepOuts = socketRecords().map((socket) => ({
          markerId: socket.aruco_id,
          x: socket.marker_x,
          y: socket.marker_y,
          halfSize: socket.marker_size / 2,
        }));
        const core = coreMarkerRecord();
        const coreMarkerId = gameFacts(state).core_marker_id;
        staticKeepOuts.push({
          markerId: coreMarkerId,
          x: core.x,
          y: core.y,
          halfSize: Math.max(coreMarkerSize, core.size) / 2,
        });
        staticFieldKeepOutCache = staticKeepOuts
          .map((keepOut) => normalizedKeepOut(keepOut, clearance))
          .filter(Boolean);
      }
      if (!extraKeepOuts.length) return staticFieldKeepOutCache;
      return staticFieldKeepOutCache.concat(
        extraKeepOuts
          .map((keepOut) => normalizedKeepOut(keepOut, clearance))
          .filter(Boolean)
      );
    }

    function drawRowBarriers(context, gameState, runtimeTime) {
      const states = gameState.row_barriers || [];
      const keepOuts = arucoFieldKeepOuts();
      context.save();
      context.lineCap = 'butt';
      context.shadowBlur = 0;
      for (const row of gameState.row_barrier_geometry || []) {
        const status = states.find(item => item.row_id === row.row_id);
        if (!status) continue;
        const powered = status.powered === true;
        const breakAge = status.changed_at == null ? Infinity : runtimeTime - status.changed_at;
        const breaking = !powered && breakAge >= 0 && breakAge < 0.8;
        const color = breaking ? '#ff6577' : powered ? '#ffd166' : '#a49b7d';
        const key = `row:${row.ax},${row.ay},${row.bx},${row.by}`;
        let segments = fieldGeometryCache.get(key);
        if (!segments) {
          segments = fieldSegmentsOutsideKeepOuts(row.ax, row.ay, row.bx, row.by, keepOuts);
          if (fieldGeometryCache.size >= 256) fieldGeometryCache.clear();
          fieldGeometryCache.set(key, segments);
        }
        context.strokeStyle = color;
        context.setLineDash(powered ? [] : [8, 12]);
        context.globalAlpha = breaking ? 1 - breakAge / 0.8 : powered ? 0.9 : 0.2;
        context.lineWidth = powered ? 6 : 2;
        for (const segment of segments) {
          context.beginPath();
          context.moveTo(segment.ax, segment.ay);
          context.lineTo(segment.bx, segment.by);
          context.stroke();
        }
        context.globalAlpha = 1;
        context.setLineDash([]);
        context.fillStyle = color;
        context.font = 'bold 13px monospace';
        context.textAlign = row.opening_side === 'right' ? 'right' : 'left';
        const labelX = row.opening_side === 'right' ? row.bx - 12 : row.ax + 12;
        context.fillText(`ROW ${status.active_count}/3${breaking ? ' · BROKEN' : ''}`, labelX, row.ay + 44);
        if (powered) {
          const gapX = row.opening_side === 'right' ? row.bx + 80 : row.ax - 80;
          const direction = row.ay < HEIGHT / 2 ? 1 : -1;
          context.lineWidth = 3;
          context.beginPath();
          context.moveTo(gapX, row.ay - direction * 16);
          context.lineTo(gapX, row.ay + direction * 16);
          context.moveTo(gapX - 7, row.ay + direction * 7);
          context.lineTo(gapX, row.ay + direction * 16);
          context.lineTo(gapX + 7, row.ay + direction * 7);
          context.stroke();
        }
      }
      context.restore();
    }

    function drawForceFields(
      context, gameState, visualTime, effectQuality, extraKeepOuts = []
    ) {
      context.save();
      context.lineCap = "round";
      const keepOuts = arucoFieldKeepOuts(extraKeepOuts);
      const forceFieldVisuals = Array.isArray(gameState.connections)
        ? gameState.connections.filter((field) => field.visible === true)
        : Array.isArray(gameState.force_field_visuals)
          ? gameState.force_field_visuals.filter((field) => field.visible !== false)
          : gameState.gates || [];
      for (const gate of forceFieldVisuals) {
        const durability = Math.max(0, Math.min(1, 1 - Number(gate.hits || 0) / Math.max(1, Number(gate.capacity || 1))));
        const pulse = 0.62 + 0.28 * Math.sin(visualTime * 5);
        const preview = gate.visual_state === "preview";
        const provisional = Boolean(gate.provisional);
        const broken = Boolean(gate.broken) || gate.visual_state === "broken";
        const invulnerable = Boolean(gate.invulnerable);
        context.strokeStyle = preview ? `rgba(54,223,255,${pulse * 0.68})` : broken ? `rgba(255,83,103,${pulse * 0.7})` : invulnerable ? `rgba(255,255,255,${pulse})` : durability > 0.5 ? `rgba(54,223,255,${pulse})` : durability > 0.2 ? `rgba(255,179,71,${pulse})` : `rgba(255,83,103,${pulse})`;
        context.shadowColor = preview ? "#36dfff" : invulnerable ? "#ffffff" : durability > 0.5 ? "#36dfff" : durability > 0.2 ? "#ffb347" : "#ff5367";
        context.shadowBlur = 0;
        context.lineWidth = broken ? 3 : provisional ? 4 : preview ? 6 : Number(gate.visual_width_px || 8);
        context.setLineDash(broken ? [12, 13] : provisional ? [18, 8] : []);
        const ax = Number(gate.ax);
        const ay = Number(gate.ay);
        const bx = Number(gate.bx);
        const by = Number(gate.by);
        const fieldLength = Math.hypot(bx - ax, by - ay);
        const key = `${ax},${ay},${bx},${by}`;
        let segments = extraKeepOuts.length ? null : fieldGeometryCache.get(key);
        if (!segments) {
          segments = fieldSegmentsOutsideKeepOuts(ax, ay, bx, by, keepOuts);
          if (!extraKeepOuts.length) {
            if (fieldGeometryCache.size >= 256) fieldGeometryCache.clear();
            fieldGeometryCache.set(key, segments);
          }
        }
        for (const segment of segments) {
          context.lineDashOffset = -fieldLength * segment.start;
          context.beginPath();
          context.moveTo(segment.ax, segment.ay);
          context.lineTo(segment.bx, segment.by);
          if (effectQuality.shadowScale > 0) {
            const width = context.lineWidth;
            context.globalAlpha = 0.16 * effectQuality.shadowScale;
            context.lineWidth = width + 8;
            context.stroke();
            context.globalAlpha = 1;
            context.lineWidth = width;
          }
          context.stroke();
          const ribbon = gameImages.get(`field:${gate.upgrade_level}`);
          if (ribbon && !broken && !provisional && !preview) {
            const length = Math.hypot(segment.bx - segment.ax, segment.by - segment.ay);
            const width = Number(gate.visual_width_px || 8) * 2;
            context.save();
            context.translate(segment.ax, segment.ay);
            context.rotate(Math.atan2(segment.by - segment.ay, segment.bx - segment.ax));
            context.globalCompositeOperation = 'screen';
            context.globalAlpha = invulnerable ? 1 : Math.max(.25, durability);
            context.drawImage(ribbon, 0, -width / 2, length, width);
            context.restore();
          }
        }
      }
      for (const impact of gameState.force_field_impacts || []) {
        const impactAge = visualTime - Number(impact.at);
        if (
          !Number.isFinite(impactAge)
          || impactAge < 0
          || impactAge > FORCE_FIELD_ZAP_DURATION_S
        ) continue;
        const impactX = Number(impact.contact_x);
        const impactY = Number(impact.contact_y);
        const impactSize = 72;
        const impactTouchesMarker = keepOuts.some((keepOut) => (
          circleOverlapsKeepOut(impactX, impactY, impactSize / 2, keepOut)
        ));
        if (impactTouchesMarker) continue;
        drawCombatEffect(
          context,
          gameImages.get("effect:force-field-impact"),
          impactX,
          impactY,
          impactSize,
          1 - impactAge / FORCE_FIELD_ZAP_DURATION_S,
        );
      }
      context.restore();
    }

    function drawForceFieldSkeletonZaps(
      context, gameState, visualTime, extrapolationAge, enemiesById,
      effectQuality
    ) {
      const skeleton = gameImages.get("effect:force-field-zap-skeleton");
      if (!skeleton) return;
      for (const impact of gameState.force_field_impacts || []) {
        const age = visualTime - Number(impact.at);
        if (
          !Number.isFinite(age)
          || age < 0
          || age > FORCE_FIELD_ZAP_DURATION_S
        ) continue;
        const enemy = enemiesById.get(Number(impact.enemy_id));
        const x = enemy
          ? Number(enemy.x) + Number(enemy.vx || 0) * extrapolationAge
          : Number(impact.enemy_x);
        const y = enemy
          ? Number(enemy.y) + Number(enemy.vy || 0) * extrapolationAge
          : Number(impact.enemy_y);
        const facingX = Number(enemy?.facing_x ?? impact.facing_x ?? 0);
        const facingY = Number(enemy?.facing_y ?? impact.facing_y ?? 1);
        const rotation = Math.atan2(facingY, facingX) - Math.PI / 2;
        const enemyType = String(enemy?.enemy_type || impact.enemy_type || "grunt");
        const baseSize = 31 * ENEMY_VISUAL_SCALE * enemyVisualScale(enemyType);
        const pulse = 1 + Math.sin(visualTime * 48 + Number(impact.enemy_id)) * 0.06;
        const alpha = Math.max(0, 1 - age / FORCE_FIELD_ZAP_DURATION_S);
        context.save();
        context.globalCompositeOperation = "lighter";
        context.globalAlpha = alpha;
        context.shadowColor = "#36dfff";
        context.shadowBlur = (12 + alpha * 12) * effectQuality.shadowScale;
        context.translate(x, y);
        context.rotate(rotation);
        context.drawImage(
          skeleton,
          -baseSize * pulse / 2,
          -baseSize * pulse / 2,
          baseSize * pulse,
          baseSize * pulse,
        );
        context.restore();
      }
    }

    function renderGame(now = performance.now()) {
      if (destroyed) return false;
      const profile = Boolean(options.onPerformance);
      let passStartedAt = profile ? performance.now() : 0;
      function markPass(name) {
        if (!profile) return;
        const at = performance.now();
        profilingTotals[name] = (profilingTotals[name] || 0) + at - passStartedAt;
        passStartedAt = at;
      }
      const context = gameCanvas.getContext("2d");
      context.clearRect(0, 0, WIDTH, HEIGHT);
      if (!state || !level) return false;
      const enemies = state.enemies || [];
      const enemyCount = Number(state.active_enemies || enemies.length || 0);
      const qualityIndex = Math.max(adaptiveQuality, enemyCount >= 800 ? 2 : enemyCount >= 400 ? 1 : 0);
      const effectQuality = [EFFECT_QUALITY_PROFILES.full, EFFECT_QUALITY_PROFILES.reduced, EFFECT_QUALITY_PROFILES.dense][qualityIndex];
      renderStats.quality = effectQuality.name;
      const enemiesById = enemiesByIdCache || (enemiesByIdCache = new Map(enemies.map(enemy => [Number(enemy.id), enemy])));
      const socketsById = socketRecordMap();
      const visualState = visualStateCache || (visualStateCache = towerVisualState(state, socketsById));
      context.imageSmoothingEnabled = false;
      const visualTime = visualSimulationTime(now, state);
      const runtimeVisualTime = visualRuntimeTime(now, state);
      const extrapolationAge = state.phase === "running" && !state.paused
        ? boundedVisualAge(stateReceivedAt, now, feedConnected, frozenVisualAge, 0.14)
        : 0;
      for (const tower of visualState.towers || []) {
        if (!towerIsActivating(tower, runtimeVisualTime, visualState)) {
          drawTargetingOverlay(context, tower);
        }
      }
      drawCoreSequence(context, state, visualTime, false);
      drawRowBarriers(context, state, runtimeVisualTime);
      drawForceFields(context, state, visualTime, effectQuality);
      markPass("fieldMs");
      for (const tower of visualState.towers || []) {
        context.save();
        const unitScale = towerUnitScale(tower);
        context.translate(tower.x, tower.y);
        context.scale(unitScale, unitScale);
        context.translate(-tower.x, -tower.y);
        if (tower.destroyed) {
          drawTowerDestruction(context, tower, visualTime, effectQuality);
          context.restore();
          continue;
        }
        if (drawTowerActivation(context, tower, runtimeVisualTime, visualState)) { context.restore(); continue; }
        const socket = socketsById.get(String(tower.socket_id));
        const coverSize = livePodVisualSize(socket);
        const cover = gameImages.get("tower:socket-cover");
        if (cover) context.drawImage(cover, tower.x - coverSize / 2, tower.y - coverSize / 2, coverSize, coverSize);
        const base = gameImages.get(`tower:${tower.tower_type}:base:${tower.upgrade_level}`) || gameImages.get(`tower:${tower.tower_type}:base`);
        const head = gameImages.get(`tower:${tower.tower_type}:head:${tower.upgrade_level}`) || gameImages.get(`tower:${tower.tower_type}:head`);
        if (base) context.drawImage(base, tower.x - TOWER_VISUAL_SIZE / 2, tower.y - TOWER_VISUAL_SIZE / 2, TOWER_VISUAL_SIZE, TOWER_VISUAL_SIZE);
        else {
          context.fillStyle = tower.owner === "green" ? "#1f6e49" : "#624184";
          context.beginPath();
          context.arc(tower.x, tower.y, TOWER_VISUAL_SIZE / 2, 0, Math.PI * 2);
          context.fill();
        }
        if (head) {
          const angle = smoothTowerAngle(tower, visualTime);
          const pulse = tower.tower_type === "tesla_coil" ? 1 + Math.sin(visualTime * 8) * 0.035 : 1;
          const idleBob = Math.round(Math.sin(
            visualTime * Math.PI * 1.5 + Number(tower.aruco_id || 0),
          ));
          const origin = towerHeadOrigin(tower, true);
          const headSize = TOWER_VISUAL_SIZE * origin.scale;
          context.save();
          context.translate(origin.x, origin.y + idleBob);
          context.rotate(angle + Math.PI / 2);
          context.scale(pulse, pulse);
          context.drawImage(head, -headSize / 2, -headSize / 2, headSize, headSize);
          context.restore();
          if (tower.tower_type === "flamethrower") {
            drawFlamethrowerPilotFlame(
              context, tower, visualTime, angle, effectQuality
            );
          }
        } else {
          const angle = smoothTowerAngle(tower, visualTime);
          context.save();
          context.translate(tower.x, tower.y);
          context.rotate(angle);
          context.strokeStyle = "#dce9f5";
          context.lineWidth = 10;
          context.beginPath();
          context.moveTo(0, 0);
          context.lineTo(38, 0);
          context.stroke();
          context.restore();
        }
        if (tower.tower_type === "tesla_coil") {
          drawTeslaIdleCharge(context, tower, visualTime, effectQuality);
        }
        drawTowerIdleStatus(context, tower, visualTime);
        context.fillStyle = tower.owner === "green" ? "#35d07f" : "#c084fc";
        context.beginPath();
        context.arc(tower.x, tower.y + 38, 11, 0, Math.PI * 2);
        context.fill();
        context.fillStyle = "#071018";
        context.font = "900 9px ui-monospace";
        context.textAlign = "center";
        context.fillText(String(tower.is_companion ? "C" : tower.atom_tag_id), tower.x, tower.y + 41);
        const linkBonus = towerLinkMultiplierLabel(tower);
        context.fillStyle = "rgba(4,11,18,0.88)";
        context.fillRect(tower.x - 21, tower.y - 70, 42, 15);
        context.strokeStyle = linkBonus.linkMultiplier == null
          ? "#dce9f5"
          : linkBonus.linkMultiplier > 1
          ? "#36dfff"
          : linkBonus.linkMultiplier < 1
            ? "#ffb347"
            : "#dce9f5";
        context.lineWidth = 1;
        context.strokeRect(tower.x - 21, tower.y - 70, 42, 15);
        context.fillStyle = context.strokeStyle;
        context.font = "900 11px ui-monospace";
        context.fillText(linkBonus.label, tower.x, tower.y - 59);
        const health = towerHealthBarMetrics(tower, visualTime);
        context.fillStyle = "#240b10";
        context.fillRect(tower.x - 34, tower.y - 51, TOWER_HEALTH_BAR_WIDTH, 6);
        context.fillStyle = health.healthRatio > 0.5 ? "#35d07f" : health.healthRatio > 0.2 ? "#ffb347" : "#ff5367";
        context.fillRect(tower.x - 34, tower.y - 51, health.fillWidth, 6);
        if (health.damageAlpha > 0) {
          const notchX = tower.x - 34 + Math.max(
            0,
            Math.min(
              TOWER_HEALTH_BAR_WIDTH - health.damageNotchWidth,
              health.fillWidth,
            ),
          );
          context.fillStyle = `rgba(255,179,71,${0.72 + health.damageAlpha * 0.28})`;
          context.fillRect(notchX, tower.y - 51, health.damageNotchWidth, 6);
          context.save();
          context.strokeStyle = `rgba(255,83,103,${health.damageAlpha * 0.9})`;
          context.shadowColor = "#ff5367";
          context.shadowBlur = (8 + health.damageAlpha * 8)
            * effectQuality.shadowScale;
          context.lineWidth = 2;
          context.beginPath();
          context.arc(tower.x, tower.y, TOWER_VISUAL_SIZE / 2 + 4, 0, Math.PI * 2);
          context.stroke();
          context.restore();
        }
        drawTowerHealthEffects(context, tower, visualTime, effectQuality);
        drawTowerReplenishPulse(
          context, tower, runtimeVisualTime, effectQuality
        );
        context.restore();
      }
      markPass("towerMs");
      for (const enemyId of enemyTrailHistory.keys()) {
        const enemy = enemiesById.get(Number(enemyId));
        if (!enemy || Number(enemy.electrocuted_until || 0) <= visualTime) {
          enemyTrailHistory.delete(enemyId);
        }
      }
      for (const enemy of enemies) {
        drawEnemy(
          context, enemy, visualTime, extrapolationAge, effectQuality
        );
      }
      markPass("enemyMs");
      drawForceFieldSkeletonZaps(
        context,
        state,
        visualTime,
        extrapolationAge,
        enemiesById,
        effectQuality,
      );
      drawMortarEffects(context, visualState, visualTime, effectQuality);
      for (const tower of visualState.towers || []) {
        drawTowerFireEffect(
          context, tower, visualTime, enemiesById, effectQuality
        );
      }
      drawCoreSequence(context, state, visualTime, true);
      renderCoreHealth(context, state);
      drawAimHandle(
        context,
        (visualState.towers || []).find((tower) => (
          towerPlacementId(tower) === selectedTowerId
        )),
      );
      drawSocketMarkers(context, state);
      renderCoreMarkerOverlay(context, state);
      markPass("combatMs");
      profilingFrames += 1;
      return true;
    }

    function gameRenderLoop(now) {
      if (destroyed) return;
      if (!document.hidden && (nextGameRenderAt == null || now + 0.5 >= nextGameRenderAt)) {
        // Preserve the fractional deadline; never draw catch-up bursts after a
        // delayed callback. The tolerance avoids floating-point refresh skips.
        const deadline = nextGameRenderAt ?? now;
        nextGameRenderAt = deadline + Math.max(1, Math.floor((now + 0.5 - deadline) / FRAME_INTERVAL_MS) + 1) * FRAME_INTERVAL_MS;
        const frameMs = lastGameRenderAt == null ? FRAME_INTERVAL_MS : now - lastGameRenderAt;
        lastGameRenderAt = now;
        const started = performance.now();
        const drawn = renderGame(now);
        const drawMs = performance.now() - started;
        if (drawn) {
          fpsRenderedFrames += 1;
          const weight = Math.min(frameMs, 100);
          if (drawMs > 18 || frameMs > 25) {
            slowFrameTime += weight; healthyFrameTime = 0;
          } else {
            slowFrameTime = Math.max(0, slowFrameTime - weight);
            healthyFrameTime = drawMs < 10 && frameMs < 21 ? healthyFrameTime + weight : 0;
          }
          if (slowFrameTime >= 400) { adaptiveQuality = Math.min(2, adaptiveQuality + 1); slowFrameTime = 0; }
          if (healthyFrameTime >= 5000) { adaptiveQuality = Math.max(0, adaptiveQuality - 1); healthyFrameTime = 0; }
          renderStats.drawMs = drawMs; renderStats.frameMs = frameMs;
        }
      }
      const sampledAt = performance.now();
      const elapsed = sampledAt - fpsSampleStartedAt;
      if (!document.hidden && elapsed >= 1000) {
        renderStats.fps = Math.round(fpsRenderedFrames * 1000 / elapsed);
        reportFps(renderStats.fps);
        if (options.onPerformance) {
          const passes = Object.fromEntries(Object.entries(profilingTotals).map(([key, total]) => [key, total / Math.max(1, profilingFrames)]));
          try { options.onPerformance({...renderStats, ...passes, cacheBytes: 4 * (enemySpriteCache.pixels + effectRasterCache.pixels + enemyGlowCache.pixels)}); }
          catch (error) { console.warn("Render diagnostics unavailable", error); }
        }
        profilingFrames = 0; profilingTotals = {};
        fpsRenderedFrames = 0;
        fpsSampleStartedAt = sampledAt;
      }
      animationFrame = global.requestAnimationFrame(gameRenderLoop);
    }

    function applyState(nextState) {
      state = nextState;
      visualStateCache = null;
      enemiesByIdCache = null;
      const nextGeometry = JSON.stringify([state?.aruco_code_footprint_px, state?.core_aruco_code_footprint_px, state?.force_field_marker_clearance_px]);
      if (nextGeometry !== geometrySignature) { geometrySignature = nextGeometry; invalidateSocketGeometry(); }
      if (bruteScale !== state?.settings?.brute_size_multiplier) {
        bruteScale = state?.settings?.brute_size_multiplier;
        enemySpriteCache.clear(); enemyGlowCache.clear();
      }
      const placements = new Set([...(state?.towers || []), ...(state?.companions || [])].map(towerPlacementId));
      for (const id of towerRenderAngles.keys()) if (!placements.has(id)) towerRenderAngles.delete(id);
      for (const id of towerAimPreview.keys()) if (!placements.has(id)) towerAimPreview.delete(id);
      stateReceivedAt = performance.now();
      frozenVisualAge = 0;
      const assetsChanged = setPresentation(nextState?.presentation);
      const nextRevision = Number(nextState?.level_revision);
      if (
        nextState?.level
        && (assetsChanged || !level || !Number.isFinite(nextRevision) || nextRevision !== levelRevision)
      ) setLevel(nextState.level, nextRevision);
    }

    function invalidateSocketGeometry() {
      socketRecordCache = null;
      socketRecordMapCache = null;
      staticFieldKeepOutCache = null;
      fieldGeometryCache.clear();
      visualStateCache = null;
    }

    function setLevel(nextLevel, revision = null) {
      if (
        !nextLevel
        || !Number.isFinite(Number(nextLevel.width))
        || !Number.isFinite(Number(nextLevel.height))
        || !nextLevel.paths
        || !Array.isArray(nextLevel.sockets)
      ) throw new Error("Photon Game level projection is invalid");
      level = nextLevel;
      levelRevision = Number.isFinite(Number(revision)) ? Number(revision) : null;
      invalidateSocketGeometry();
      Promise.all([loadGameImages(), loadSceneImages(nextLevel.scene)]).then(() => {
        if (destroyed) return;
        renderMap();
      });
      renderMap();
      return level;
    }

    function socketRecords() {
      if (socketRecordCache) return socketRecordCache;
      const markerSize = socketMarkerVisualSize();
      socketRecordCache = (level?.sockets || []).map((socket) => {
        const x = Number(socket.x);
        const y = Number(socket.y);
        const size = Number(socket.size || Number(socket.radius) * 2 || 208);
        return {
          socket_id: String(socket.socket_id || socket.id),
          owner: String(socket.owner || ""),
          aruco_id: Number(socket.aruco_id),
          x,
          y,
          marker_x: Number.isFinite(Number(socket.marker_x))
            ? Number(socket.marker_x) : x,
          marker_y: Number.isFinite(Number(socket.marker_y))
            ? Number(socket.marker_y) : y,
          marker_size: Number.isFinite(Number(socket.marker_size))
            ? Number(socket.marker_size) : markerSize,
          size,
        };
      });
      socketRecordMapCache = new Map(socketRecordCache.map((socket) => [
        String(socket.socket_id), socket,
      ]));
      return socketRecordCache;
    }

    function socketRecordMap() {
      if (!socketRecordMapCache) socketRecords();
      return socketRecordMapCache;
    }

    function socketAtPoint(x, y) {
      return socketRecords()
        .filter((socket) => (
          Math.abs(socket.x - x) <= socket.size / 2
          && Math.abs(socket.y - y) <= socket.size / 2
        ))
        .sort((a, b) => Math.hypot(a.x - x, a.y - y) - Math.hypot(b.x - x, b.y - y))[0] || null;
    }

    function towerAtPoint(x, y) {
      const units = [...(state?.towers || []), ...(state?.companions || [])]
        .map(unit => towerVisualRecord(unit, socketRecordMap()))
        .filter(unit => Math.abs(unit.x - x) <= LIVE_POD_SIZE * towerUnitScale(unit) / 2
          && Math.abs(unit.y - y) <= LIVE_POD_SIZE * towerUnitScale(unit) / 2);
      const hit = units.sort((a,b) => Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0];
      return hit ? (state.towers || []).find(unit => towerPlacementId(unit) === String(hit.parent_placement_id || towerPlacementId(hit))) : null;
    }

    function markerAtPoint(x, y) {
      return socketRecords()
        .filter((socket) => (
          Math.abs(socket.marker_x - x) <= socket.marker_size / 2
          && Math.abs(socket.marker_y - y) <= socket.marker_size / 2
        ))
        .sort((a, b) => (
          Math.hypot(a.marker_x - x, a.marker_y - y)
          - Math.hypot(b.marker_x - x, b.marker_y - y)
        ))[0] || null;
    }

    function coreAtPoint(x, y) {
      const center = centralCoreCenter();
      const markerId = gameFacts(state).core_marker_id;
      return Math.hypot(center.x - x, center.y - y) <= 78
        ? { socket_id: markerId == null ? "core" : `core_${markerId}`, aruco_id: markerId, x: center.x, y: center.y, size: 156 }
        : null;
    }

    function selectTower(placementId) {
      selectedTowerId = placementId == null ? null : String(placementId);
    }

    function previewTowerAim(placementId, angle, spread) {
      if (placementId == null) return;
      towerAimPreview.set(String(placementId), { angle: Number(angle), spread: Number(spread) });
    }

    function clearTowerAimPreview(placementId) {
      if (placementId == null) return;
      towerAimPreview.delete(String(placementId));
    }

    function selectedAimTower(placementId = selectedTowerId) {
      if (placementId == null) return null;
      const tower = (state?.towers || []).find((candidate) => (
        towerPlacementId(candidate) === String(placementId)
      )) || null;
      return tower ? towerVisualRecord(tower, socketRecordMap()) : null;
    }

    function aimHandle(placementId = selectedTowerId) {
      const tower = selectedAimTower(placementId);
      if (!tower || tower.destroyed) return null;
      const targeting = towerTargeting(tower);
      const point = targetingHandlePoint(tower, targeting);
      return {
        placement_id: towerPlacementId(tower),
        tower_type: String(tower.tower_type),
        tower_x: Number(tower.x),
        tower_y: Number(tower.y),
        x: point.x,
        y: point.y,
        radius: AIM_HANDLE_RADIUS,
        angle: Number(targeting.angle_degrees || 0),
        spread: Number(targeting.spread || 0),
      };
    }

    function aimFromPoint(placementId, x, y) {
      const tower = selectedAimTower(placementId);
      if (!tower || tower.destroyed) return null;
      const targeting = towerTargeting(tower);
      return towerAimFromPoint(
        targeting.control,
        tower.x,
        tower.y,
        x,
        y,
        targeting.angle_degrees,
      );
    }

    function setFeedConnected(connected) {
      const next = Boolean(connected);
      const now = performance.now();
      if (!next && feedConnected) {
        frozenVisualAge = boundedVisualAge(
          stateReceivedAt, now, true, frozenVisualAge,
        );
      } else if (next && !feedConnected && frozenVisualAge > 0) {
        stateReceivedAt = now - frozenVisualAge * 1000;
      }
      feedConnected = next;
    }

    animationFrame = global.requestAnimationFrame(gameRenderLoop);

    return {
      applyState,
      destroy() {
        destroyed = true;
        if (animationFrame) global.cancelAnimationFrame(animationFrame);
        document.removeEventListener?.("visibilitychange", resetFpsSample);
        enemySpriteCache.clear(); effectRasterCache.clear(); enemyGlowCache.clear(); tintedEffectCache.clear();
        enemyTrailHistory.clear(); towerRenderAngles.clear(); towerAimPreview.clear();
      },
      get level() {
        return level;
      },
      get levelReady() {
        return Boolean(level);
      },
      setLevel,
      renderGame,
      renderMap,
      selectTower,
      previewTowerAim,
      clearTowerAimPreview,
      aimHandle,
      aimFromPoint,
      setFeedConnected,
      coreAtPoint,
      markerAtPoint,
      socketAtPoint,
      towerAtPoint,
      socketRecords,
    };
  }

  global.TowerDefenceView = {
    create: createTowerDefenceView,
    HEIGHT,
    WIDTH,
    geometry: {
      ARUCO_FIELD_CLEARANCE,
      advancedWeaponCharge,
      boundedVisualAge,
      effectQualityForEnemyCount,
      fieldSegmentsOutsideKeepOuts,
      fixedMarkerVisualSize,
      flamethrowerNozzlePoint,
      machineGunFireLines,
      machineGunMuzzlePoints,
      normalizedKeepOut,
      permanentTurretMarkerOffset,
      targetingHandlePoint,
      towerAimDistance,
      towerAimFromPoint,
      towerHealthBarMetrics,
      towerLinkMultiplierLabel,
    },
    presentation: {
      gameFacts,
      snapshotReceiver,
      towerTypeLabel,
    },
  };
})(typeof window === "undefined" ? globalThis : window);
