# Photon Level

Photon Level owns one authored content package: geometry, waves, and static
artwork (map components, towers, enemies, combat effects, and ArUco codes). It does not
know about cameras, robots, gameplay state, damage, live-game rendering, or a
sibling's files. Its own authoring preview is part of level editing.

## Authoring preview

The Level tab draws the existing `photon.visual-scene` v1 in authored layer
order using its shared local images: terrain, roads, static decorations,
core artwork, and activation staging. It never displays the hidden concept
reference. Placement art is replaced by editable owner-colored square outlines,
center crosses, and labels. Optional overlays show ArUco codes (38 and 40–55)
and enemy routes. These are authoring aids, not live gameplay.

`GET /api/editor` is a module-local `photon.level.editor` v1 view: one revision,
the existing level/scene projection, local asset URLs, and socket marker resize
vectors. The browser draws supplied transforms; it does not parse TMJ or copy
marker-placement rules. Translation and size edits keep marker geometry aligned
with the server projection, while marker footprints remain fixed. Canvas and
pointer coordinates share the authored dimensions at any displayed size.

Drag a placement or its marker, or edit X/Y/size inputs. Changes remain local
until **Validate & publish all 16 sockets** succeeds through the existing
authenticated, revision-checked layout endpoint. A rejected save retains the
draft. Reloading a dirty layout asks before discarding it. Only placements are
editable in this tab; other authored layers remain editable in Tiled.

The preview requires no Board, Game, or Y module. Its ArUco PNGs are the same
local files used for live presentation; no OpenCV runtime dependency
is added. Missing artwork or an invalid source produces an explicit unavailable
preview instead of a deceptively complete schematic. Existing public Level and
runtime contract versions are unchanged; the runtime bundle gains an optional
versioned presentation descriptor.

Smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_level_editor.py`.

## Input

Its only runtime mutation is `update_layout(sockets, expected_revision=...)` or
authenticated `POST /api/layout`. The input must contain every one of the 16
stable socket IDs, integer center coordinates, and a size from 96 through 208
pixels. Editing is an optimistic, complete replacement: a stale expected
revision is rejected and no partial layout is accepted.

Photon Level validates socket identity, ArUco IDs 40–55, marker and playfield
bounds, marker/turret overlap, spacing, linked gate geometry, route reachability,
ring topology, and the complete candidate TMJ before one atomic file replace.

## Output

- `level_snapshot()` and `GET /api/level` publish `photon.level` version 2: a
  small generic educational-game projection with dimensions, paths, sockets,
  revision, and discoverable map/wave endpoints.
- `runtime_bundle()` and `GET /api/runtime` publish
  `photon.level.runtime` version 1: the parsed path graph, routes, sockets,
  marker geometry, blockers, ring topology, map properties, a renderer-neutral
  `photon.visual-scene` version 1 projection, and waves as plain JSON-compatible
  values. Consumers receive stable art IDs and transforms, never source-file
  paths, Tiled GIDs, or tileset interpretation work.
  The additive `presentation` field carries `photon.level.assets` v1 below.
- `GET /api/tiled-map` publishes the editable TMJ with tileset references
  rewritten to Photon Level's own HTTP asset boundary.
- `waves_document()` and `GET /api/waves` publish the authored wave document.
- `GET /api/events` emits the small level snapshot with Server-Sent Events.

Invalid source data produces an explicit `unavailable` output. Contract names
and integer versions are checked by consumers; incompatible versions fail in
the consumer without preventing unrelated hub modules from running.

## Owned state and assets

The canonical files are local to this module:

- `assets/tiled/levels/z-pixel-first-map.tmj`
- `assets/tiled/levels/z-pixel-first-map.waves.json`
- `assets/tiled/tilesets/*.tsj`
- the normalized modular PNG components referenced by those tilesets
- `assets/tiled/photon-crane.tiled-project`

The map remains an editable modular Tiled project. A visible flattened style
reference is forbidden. The extracted production map must continue to pass the
modular validator, native Tiled round-trip, native raster render, and the
Laser Tag Z parity fixture.

The standalone Photon Art module has been merged here. Identical images share
one file; no per-map runtime copies or sibling filesystem reads are needed.
The original Laser Tag Z and its assets remain untouched.

## Static presentation contract

`runtime_bundle().presentation`, `presentation_assets()`, and `GET /api/assets`
publish `photon.level.assets` integer version 1. The Level tab's **Artwork**
page (`/art`) browses that same manifest; it is not another module.

- `status`: `ready` or `unavailable`; `error` explains missing/invalid content.
- `base`: an HTTP path relative to the sandbox mount, currently
  `/p/photon-level/assets`. Prefix it once with the current sandbox mount
  (for example `/s/gamemaster`), not with a module's filesystem location.
- `assets`: stable ID to relative URL, e.g. `marker/40`, `tower/mortar/base`,
  `enemy/grunt/1`, `effect/mortar-impact`, and `map/roads/junction-cross`.
  Scene IDs are resolved from Level's own authored tilesets, not a copied map
  filename table. The editor and runtime resolve to the same image files.
- Each URL has `?v=<SHA-256 of file bytes>`; `revision` fingerprints the manifest.
  File metadata is checked on reads; unchanged files are not rehashed. Changed
  artwork updates its URL and revision without changing gameplay geometry.
- File responses revalidate (`no-cache`), not permanent `immutable`: old version
  URLs are not promises that Level stores historical bytes. Missing files are
  omitted and make content explicitly unavailable; remaining files and Canvas
  fallbacks can still render. No image bytes travel in snapshots or SSE.

Photon Game validates and forwards this descriptor in its own output. Y gets
all state and asset references from Game, then fetches the supplied image URLs.
Game does not serve, parse, or render artwork. Art-only updates can be adopted
during a run; a pending geometry revision and its associated scene/manifest
are deferred together until setup/reset.

Smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_content.py`.

## Independence rule

A future Photon Level repository may change its implementation and dependencies
without knowledge of a game or presenter, provided its published contract
versions retain their documented meaning. A breaking output change requires a
new integer version; it must not silently reinterpret an existing version.
