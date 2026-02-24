# E1M1 (Doom map) JSON schema

This document describes the JSON output of the WAD→JSON tool (`doom_jq/tools/wad2json.py`). Field names and semantics match the Doom source `doomdata.h` structs where applicable.

## Top-level keys

| Key        | Type  | Description |
|------------|-------|-------------|
| `vertexes` | array | Map vertices (mapvertex_t). |
| `linedefs` | array | Line definitions (maplinedef_t). |
| `sidedefs` | array | Side definitions (mapsidedef_t). |
| `sectors`  | array | Sectors (mapsector_t). |
| `things`   | array | Things: players, monsters, items (mapthing_t). |
| `segs`     | array | BSP line segments (mapseg_t). |
| `ssectors` | array | Subsectors (mapsubsector_t). |
| `nodes`    | array | BSP nodes (mapnode_t). |

## mapvertex_t (vertexes[])

| Field | Type   | Description |
|-------|--------|-------------|
| `x`   | number | X coordinate (world units). |
| `y`   | number | Y coordinate (world units). |

## maplinedef_t (linedefs[])

| Field    | Type  | Description |
|----------|-------|-------------|
| `v1`     | number | Start vertex index. |
| `v2`     | number | End vertex index. |
| `flags`  | number | ML_BLOCKING (1), ML_BLOCKMONSTERS (2), ML_TWOSIDED (4), etc. |
| `special`| number | Line special. |
| `tag`    | number | Sector tag. |
| `sidenum`| [number, number] | Side indices; -1 if one-sided. |

## mapsidedef_t (sidedefs[])

| Field           | Type   | Description |
|-----------------|--------|-------------|
| `textureoffset` | number | Texture X offset. |
| `rowoffset`     | number | Texture Y offset. |
| `toptexture`    | string | Upper texture name (8 chars). |
| `bottomtexture`| string | Lower texture name. |
| `midtexture`    | string | Middle texture name. |
| `sector`        | number | Front sector index. |

## mapsector_t (sectors[])

| Field          | Type   | Description |
|----------------|--------|-------------|
| `floorheight`  | number | Floor height (world units). |
| `ceilingheight`| number | Ceiling height. |
| `floorpic`     | string | Floor flat name. |
| `ceilingpic`   | string | Ceiling flat name. |
| `lightlevel`   | number | Light level (0–255). |
| `special`      | number | Sector special. |
| `tag`          | number | Sector tag. |

## mapthing_t (things[])

| Field | Type   | Description |
|-------|--------|-------------|
| `x`   | number | X position. |
| `y`   | number | Y position. |
| `angle` | number | Facing angle (0–359; 0 = east). |
| `type`  | number | Thing type: 1 = player 1 start, 2 = player 2, etc. |
| `options` | number | Skill / multiplayer flags. |

## mapseg_t (segs[])

| Field    | Type   | Description |
|----------|--------|-------------|
| `v1`     | number | Start vertex index. |
| `v2`     | number | End vertex index. |
| `angle`  | number | Angle. |
| `linedef`| number | Linedef index. |
| `side`   | number | Side (0 or 1). |
| `offset` | number | Offset along linedef. |

## mapsubsector_t (ssectors[])

| Field      | Type   | Description |
|------------|--------|-------------|
| `numsegs`  | number | Number of segs in this subsector. |
| `firstseg` | number | Index of first seg in segs[]. |

## mapnode_t (nodes[])

| Field     | Type     | Description |
|-----------|----------|-------------|
| `x`, `y`  | number   | Partition line start. |
| `dx`, `dy`| number   | Partition line delta. |
| `bbox`    | [[4]]    | Bounding box per child [right, left, top, bottom]. |
| `children`| [number] | Child node indices; high bit (0x8000) = subsector. |

## Validation

- All top-level keys must be present and be arrays.
- For E1M1 level load, at least one `things[]` entry must have `type == 1` (player 1 start).
