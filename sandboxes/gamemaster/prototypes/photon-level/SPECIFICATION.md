# Photon Level

Photon Level owns authored playfield geometry and wave definitions. It does not
know about cameras, robots, gameplay state, damage, rendering, or a sibling's
files.

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
  marker geometry, blockers, ring topology, map properties, and waves as plain
  JSON-compatible values. Consumers receive values, never source-file paths.
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

## Independence rule

A future Photon Level repository may change its implementation and dependencies
without knowledge of a game or presenter, provided its published contract
versions retain their documented meaning. A breaking output change requires a
new integer version; it must not silently reinterpret an existing version.
