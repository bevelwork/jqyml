#!/usr/bin/env python3
"""
Export E1M1 (or other Doom map) from a WAD file to JSON.
Matches doomdata.h lump order and struct layout (little-endian).
Usage:
  python wad2json.py path/to/doom1.wad [--map E1M1]   -> stdout
  python wad2json.py --write-minimal                   -> writes doom_jq/data/e1m1.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path


# Lump order after map label (doomdata.h ML_*)
MAP_LUMP_NAMES = [
    "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS",
    "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP",
]


def read_wad_header(f):
    """Read WAD header: id(4), numlumps(4), infotableofs(4)."""
    buf = f.read(12)
    if len(buf) < 12:
        raise ValueError("WAD file too short")
    id_ = buf[:4]
    if id_ not in (b"IWAD", b"PWAD"):
        raise ValueError(f"Invalid WAD id: {id_!r}")
    numlumps, infotableofs = struct.unpack("<II", buf[4:12])
    return numlumps, infotableofs


def read_directory(f, infotableofs, numlumps):
    """Each entry: filepos(4), size(4), name(8)."""
    f.seek(infotableofs)
    entries = []
    for _ in range(numlumps):
        buf = f.read(16)
        if len(buf) < 16:
            raise ValueError("Truncated directory")
        filepos, size = struct.unpack("<II", buf[:8])
        name = buf[8:16].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        entries.append({"filepos": filepos, "size": size, "name": name})
    return entries


def find_map_lumps(entries, map_name):
    """Return (start_index, list of (name, filepos, size)) for map lumps."""
    for i, e in enumerate(entries):
        if e["name"] == map_name:
            # Next lumps must be THINGS, LINEDEFS, ...
            lumps = []
            for j, want in enumerate(MAP_LUMP_NAMES):
                k = i + 1 + j
                if k >= len(entries) or entries[k]["name"] != want:
                    raise ValueError(f"Map {map_name}: expected lump {want} at index {k}")
                lumps.append((want, entries[k]["filepos"], entries[k]["size"]))
            return lumps
    raise ValueError(f"Map {map_name} not found in WAD")


def parse_vertexes(data):
    """mapvertex_t: short x, short y (4 bytes each)."""
    out = []
    for i in range(0, len(data), 4):
        if i + 4 > len(data):
            break
        x, y = struct.unpack("<hh", data[i : i + 4])
        out.append({"x": x, "y": y})
    return out


def parse_linedefs(data):
    """maplinedef_t: v1, v2, flags, special, tag, sidenum[2] (7 shorts = 14 bytes)."""
    out = []
    for i in range(0, len(data), 14):
        if i + 14 > len(data):
            break
        v1, v2, flags, special, tag, s0, s1 = struct.unpack("<hhhhhhh", data[i : i + 14])
        out.append({"v1": v1, "v2": v2, "flags": flags, "special": special, "tag": tag, "sidenum": [s0, s1]})
    return out


def parse_sidedefs(data):
    """mapsidedef_t: textureoffset(2), rowoffset(2), toptexture(8), bottomtexture(8), midtexture(8), sector(2) = 30 bytes."""
    out = []
    for i in range(0, len(data), 30):
        if i + 30 > len(data):
            break
        to, ro = struct.unpack("<hh", data[i : i + 4])
        top = data[i + 4 : i + 12].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        bot = data[i + 12 : i + 20].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        mid = data[i + 20 : i + 28].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        sec, = struct.unpack("<h", data[i + 28 : i + 30])
        out.append({"textureoffset": to, "rowoffset": ro, "toptexture": top, "bottomtexture": bot, "midtexture": mid, "sector": sec})
    return out


def parse_sectors(data):
    """mapsector_t: floorheight(2), ceilingheight(2), floorpic(8), ceilingpic(8), lightlevel(2), special(2), tag(2) = 26 bytes."""
    out = []
    for i in range(0, len(data), 26):
        if i + 26 > len(data):
            break
        fh, ch = struct.unpack("<hh", data[i : i + 4])
        fpic = data[i + 4 : i + 12].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        cpic = data[i + 12 : i + 20].split(b"\x00")[0].decode("ascii", errors="replace").strip()
        light, special, tag = struct.unpack("<hhh", data[i + 20 : i + 26])
        out.append({"floorheight": fh, "ceilingheight": ch, "floorpic": fpic, "ceilingpic": cpic, "lightlevel": light, "special": special, "tag": tag})
    return out


def parse_things(data):
    """mapthing_t: x, y, angle, type, options (5 shorts = 10 bytes)."""
    out = []
    for i in range(0, len(data), 10):
        if i + 10 > len(data):
            break
        x, y, angle, type_, options = struct.unpack("<hhhhh", data[i : i + 10])
        out.append({"x": x, "y": y, "angle": angle, "type": type_, "options": options})
    return out


def parse_segs(data):
    """mapseg_t: v1, v2, angle, linedef, side, offset (6 shorts = 12 bytes)."""
    out = []
    for i in range(0, len(data), 12):
        if i + 12 > len(data):
            break
        v1, v2, angle, linedef, side, offset = struct.unpack("<hhhhhh", data[i : i + 12])
        out.append({"v1": v1, "v2": v2, "angle": angle, "linedef": linedef, "side": side, "offset": offset})
    return out


def parse_ssectors(data):
    """mapsubsector_t: numsegs(2), firstseg(2) = 4 bytes."""
    out = []
    for i in range(0, len(data), 4):
        if i + 4 > len(data):
            break
        numsegs, firstseg = struct.unpack("<hh", data[i : i + 4])
        out.append({"numsegs": numsegs, "firstseg": firstseg})
    return out


def parse_nodes(data):
    """mapnode_t: x, y, dx, dy (4 shorts), bbox[2][4] (8 shorts), children[2] (2 ushorts) = 28 bytes."""
    out = []
    for i in range(0, len(data), 28):
        if i + 28 > len(data):
            break
        x, y, dx, dy = struct.unpack("<hhhh", data[i : i + 8])
        bbox = list(struct.unpack("<hhhhhhhh", data[i + 8 : i + 24]))
        # bbox is [2][4]: right, left, top, bottom for each child
        children = list(struct.unpack("<HH", data[i + 24 : i + 28]))
        out.append({"x": x, "y": y, "dx": dx, "dy": dy, "bbox": [bbox[:4], bbox[4:8]], "children": children})
    return out


def export_map(f, map_name):
    """Read WAD from file f, export map_name to a JSON-serializable dict."""
    numlumps, infotableofs = read_wad_header(f)
    entries = read_directory(f, infotableofs, numlumps)
    lumps = find_map_lumps(entries, map_name)

    result = {}
    for name, filepos, size in lumps:
        f.seek(filepos)
        data = f.read(size)
        if name == "VERTEXES":
            result["vertexes"] = parse_vertexes(data)
        elif name == "LINEDEFS":
            result["linedefs"] = parse_linedefs(data)
        elif name == "SIDEDEFS":
            result["sidedefs"] = parse_sidedefs(data)
        elif name == "SECTORS":
            result["sectors"] = parse_sectors(data)
        elif name == "THINGS":
            result["things"] = parse_things(data)
        elif name == "SEGS":
            result["segs"] = parse_segs(data)
        elif name == "SSECTORS":
            result["ssectors"] = parse_ssectors(data)
        elif name == "NODES":
            result["nodes"] = parse_nodes(data)
        # REJECT and BLOCKMAP omitted from JSON for now (optional for rendering)
    return result


def minimal_e1m1():
    """Return minimal E1M1-like JSON (one room, one player start) for tests without a WAD."""
    # One square room: 4 vertexes, 4 linedefs, 4 sidedefs, 1 sector, 1 thing (player 1).
    return {
        "vertexes": [
            {"x": 0, "y": 0},
            {"x": 256, "y": 0},
            {"x": 256, "y": 256},
            {"x": 0, "y": 256},
        ],
        "linedefs": [
            {"v1": 0, "v2": 1, "flags": 1, "special": 0, "tag": 0, "sidenum": [0, -1]},
            {"v1": 1, "v2": 2, "flags": 1, "special": 0, "tag": 0, "sidenum": [1, -1]},
            {"v1": 2, "v2": 3, "flags": 1, "special": 0, "tag": 0, "sidenum": [2, -1]},
            {"v1": 3, "v2": 0, "flags": 1, "special": 0, "tag": 0, "sidenum": [3, -1]},
        ],
        "sidedefs": [
            {"textureoffset": 0, "rowoffset": 0, "toptexture": "-", "bottomtexture": "-", "midtexture": "STARTAN1", "sector": 0},
            {"textureoffset": 0, "rowoffset": 0, "toptexture": "-", "bottomtexture": "-", "midtexture": "STARTAN1", "sector": 0},
            {"textureoffset": 0, "rowoffset": 0, "toptexture": "-", "bottomtexture": "-", "midtexture": "STARTAN1", "sector": 0},
            {"textureoffset": 0, "rowoffset": 0, "toptexture": "-", "bottomtexture": "-", "midtexture": "STARTAN1", "sector": 0},
        ],
        "sectors": [
            {"floorheight": 0, "ceilingheight": 128, "floorpic": "FLOOR0_1", "ceilingpic": "CEIL3_2", "lightlevel": 160, "special": 0, "tag": 0},
        ],
        "things": [
            {"x": 128, "y": 128, "angle": 90, "type": 1, "options": 7},
        ],
        "segs": [
            {"v1": 0, "v2": 1, "angle": 0, "linedef": 0, "side": 0, "offset": 0},
            {"v1": 1, "v2": 2, "angle": 16384, "linedef": 1, "side": 0, "offset": 0},
            {"v1": 2, "v2": 3, "angle": 32768, "linedef": 2, "side": 0, "offset": 0},
            {"v1": 3, "v2": 0, "angle": 49152, "linedef": 3, "side": 0, "offset": 0},
        ],
        "ssectors": [
            {"numsegs": 4, "firstseg": 0},
        ],
        "nodes": [],
    }


def validate_schema(obj):
    """Check required keys and types. Returns (True, None) or (False, error_msg)."""
    required = ["vertexes", "linedefs", "sidedefs", "sectors", "things", "segs", "ssectors", "nodes"]
    for key in required:
        if key not in obj:
            return False, f"Missing key: {key}"
        if not isinstance(obj[key], list):
            return False, f"{key} must be a list"
    # Spot-check thing type 1 present for player spawn
    things = obj.get("things", [])
    if not any(t.get("type") == 1 for t in things):
        return False, "No player 1 start (thing type 1) in things"
    return True, None


def main():
    ap = argparse.ArgumentParser(description="Export Doom map from WAD to JSON")
    ap.add_argument("wad", nargs="?", help="Path to WAD file (e.g. doom1.wad)")
    ap.add_argument("--map", default="E1M1", help="Map name (default E1M1)")
    ap.add_argument("--write-minimal", action="store_true", help="Write minimal e1m1.json to doom_jq/data/ (no WAD)")
    ap.add_argument("--validate", metavar="JSON", help="Validate a JSON file against schema; exit 0 iff valid")
    args = ap.parse_args()

    if args.validate:
        path = Path(args.validate)
        if not path.is_file():
            print(f"Error: not a file: {path}", file=sys.stderr)
            return 1
        with open(path) as f:
            data = json.load(f)
        ok, err = validate_schema(data)
        if not ok:
            print(f"Invalid: {err}", file=sys.stderr)
            return 1
        print("OK", file=sys.stderr)
        return 0

    if args.write_minimal:
        data = minimal_e1m1()
        out_path = Path(__file__).resolve().parent.parent / "data" / "e1m1.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as out:
            json.dump(data, out, indent=2)
        print(f"Wrote {out_path}", file=sys.stderr)
        return 0

    if not args.wad:
        ap.error("WAD path required (or use --write-minimal)")
    wad_path = Path(args.wad)
    if not wad_path.is_file():
        print(f"Error: not a file: {wad_path}", file=sys.stderr)
        return 1

    with open(wad_path, "rb") as f:
        try:
            data = export_map(f, args.map)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    ok, err = validate_schema(data)
    if not ok:
        print(f"Schema validation: {err}", file=sys.stderr)
        return 1

    json.dump(data, sys.stdout, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
