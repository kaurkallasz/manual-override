# Photon Level

## L4 companion anchors

Layout revision 19 retains all sixteen authored sockets and their marker/primary
positions. Each socket has the authored boolean `l4_companion_enabled`; codes
47, 48, 50 and 54 in the middle line are false. The other twelve are true.
Level publishes an additive `companion` descriptor on each runtime/display socket:
`contract: photon.level.companion`, integer `version: 1`, and `eligible`.
Eligible descriptors also contain gameplay `x/y`, optical `visual_x/visual_y`,
and `pod_size: 96`. Anchors are across the existing marker, computed from its
authored side, gap and rotation. They are not additional placement sockets.

The parser checks companion bounds and clearance against all primary pods,
other companions and marker squares, including the core. Editor saves invoke
that parser before atomic replacement, rejecting collisions without changing
the saved map. Geometry updates are still deferred by Game during active runs.
Older compatible levels can omit the descriptor and have no companions.

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
Repository-boundary smoke test: `.venv/bin/python -m unittest discover -s tests -p test_photon_module_isolation.py`.

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
  `photon.level.runtime` version 2: the parsed path graph, routes, sockets,
  marker geometry, blockers, ring topology, map properties, a renderer-neutral
  `photon.visual-scene` version 1 projection, and waves as plain JSON-compatible
  values. Consumers receive stable art IDs and transforms, never source-file
  paths, Tiled GIDs, or tileset interpretation work.
  The additive `presentation` field carries `photon.level.assets` v1 below.
- Optional `runtime_status()` publishes `photon.level.runtime` v2 health,
  revision and presentation metadata without copying runtime geometry or waves.
  Health and layout revisions are immediate; artwork is revalidated within
  250 ms. Source reload invalidates that cache. Returned descriptors are isolated
  copies, and direct `presentation_assets()` reads remain fresh.
- `GET /api/tiled-map` publishes the editable TMJ with tileset references
  rewritten to Photon Level's own HTTP asset boundary.
- `waves_document()` and `GET /api/waves` publish the authored wave document.
- `GET /api/events` emits the small level snapshot with Server-Sent Events.

Invalid source data produces an explicit `unavailable` output. Contract names
and integer versions are checked by consumers; incompatible versions fail in
the consumer without preventing unrelated hub modules from running.

### Two-entry row-barrier layout

Layout revision 18 adds `runtime_version: 2`, `enabled_spawn_groups`, and four
`row_barriers` descriptors. A row contains `row_id`, three stable `socket_ids`,
`opening_side`, horizontal endpoints `ax/ay/bx/by`, and `blocked_edges`.
The hidden editable Row Barriers layer owns those relationships and geometry.
The top/bottom outer rows open on the right; the two inner rows open on the
left. The middle four sockets are independent of the row mechanic.

Only `top_outer` and `bottom_outer` spawn, both from the left boundary. The
former inner entrances are junctions; westbound middle-lane edges and explicit
left-turn junctions provide the winding route. Wave totals and release times
are preserved, with previous top/bottom weights combined respectively.
All sixteen sockets remain usable, with `max_structures: 16` and an enemy cap
of 1,000. No road bitmap assets were changed.

Parsing and candidate layout edits validate membership, row bands, opening
clearance, geometric edge crossings, and both entrances in all sixteen powered
row combinations. Malformed rows or inconsistent spawn/wave data fail closed.
`tools/validate_photon_map.py` audits the modular construction for the current
contract; the historical skill's four-spawn/eight-structure assumptions do not
apply to this v2 layout. The independent generic `photon.level` contract stays
at version 2, and the art/scene contracts stay at version 1.

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

## LTZ upgrade art

The `photon.level.assets` v1 descriptor includes `tower/{type}/upgrade/{2,3,4}`
for Machine Gun, Flamethrower, Mortar and Tesla Coil, plus `field/upgrade-atlas`.
Files and image-generation provenance belong to `assets/upgrades/`. Tower atlases
contain a stationary base in the left cell and rotating head in the right cell.
Y removes the magenta matte and caches 256-pixel layers at load time. The field
atlas has three horizontal rows rendered with additive compositing. Missing
upgrade textures fall back to the existing base/head art.
