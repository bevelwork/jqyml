# Doom in jq — Milestone Plan

**Scope:** Local-only (no website, no jq.bevel.work). Target **main menu** and **first level** (E1M1) only. **Input:** keyboard only; no mouse support.  
**Reference:** `doom/linuxdoom-1.10` (id Software Linux Doom 1.10).

High-level flow in the reference:
- **Entry:** `i_main.c` → `D_DoomMain()` → inits → `D_DoomLoop()` (never returns).
- **Loop:** `I_StartFrame` → `TryRunTics` (events, `G_BuildTiccmd`, `M_Ticker`, `G_Ticker`) → `D_Display` (by `gamestate`: level = `R_RenderPlayerView` + status; demoscreen = `D_PageDrawer`).
- **Menu:** `M_Responder` / `M_Ticker` / `M_Drawer`; `menu_t` + `menuitem_t`; main → New Game → Episode → Skill → Start.
- **Level:** WAD lumps (e.g. `E1M1`: VERTEXES, LINEDEFS, SIDEDEFS, SECTORS, NODES, SSECTORS, SEGS, THINGS); `P_SetupLevel`; renderer uses BSP (`r_bsp.c`), segs (`r_segs.c`), planes (`r_plane.c`), things (`r_things.c`).

jq is used for **state + logic**; a **Python host** (pipeline glue) handles I/O: display, input, timing, and optionally WAD reading (or we pre-convert E1M1 to JSON).

Every milestone includes a **Tests / regression** step: list and add tests (e.g. jq unit/snapshot, Python runner, schema checks) and run them locally or in CI to protect against regressions.

---

## Phase 1 — Runner and display

### 1.0 — Wire up rendering a visualization
- **Goal:** A local runner that can display output produced by jq.
- **Tasks:**
  - Add a Python host (e.g. `doom_jq/runner.py`) that: runs jq with a “frame” filter, reads JSON from stdout, and renders it.
  - Define a minimal “frame” schema (e.g. `{ "width": 320, "height": 200, "pixels": "base64..." }` or `{ "draw": [ {"rect": [x,y,w,h], "color": "#rrggbb"}, ... ] }`).
  - Implement one jq script that outputs a single static frame (e.g. solid color or a simple pattern).
  - **Tests / regression:** List and add tests: e.g. jq script given no input yields valid frame JSON (schema check or snapshot); runner exits 0 when given that frame. Run in CI or `make test` to protect against regressions.
- **Reference:** `v_video.c` / `i_video.c` (screen buffer, dimensions); `doomdef.h` (`SCREENWIDTH` 320, `SCREENHEIGHT` 200).
- **Deliverable:** Run `python doom_jq/runner.py` (or similar) and see one static image from jq.
- **Status:** Done.
- **Notes:** Frame schema is `{ "width": 320, "height": 200, "draw": [ {"rect": [x,y,w,h], "color": "#rrggbb"}, ... ] }`. Implemented in `doom_jq/jq/frame.jq`; `doom_jq/runner.py` runs jq, validates frame, exits 0. Snapshot test: `doom_jq/tests/frame_static.expected`; `make test-doom-jq-frame`. The site serves `/doom` (HTML + canvas) and uses the same frame format over WebSocket `/doom/ws` or POST `/doom/tic`.

### 1.1 — Simple game loop and display (e.g. bouncing box)
- **Goal:** A ticking game loop where jq receives state + input and returns next state + frame.
- **Tasks:**
  - Python loop: each “tic” or “frame”: pass `{ "state": <prev>, "input": { "keys": [], "dt": ... } }` into jq (e.g. via subprocess and stdin); jq outputs `{ "state": <next>, "frame": <frame> }`.
  - Implement in jq: state = e.g. `{ "x", "y", "vx", "vy" }`; update position; clamp to screen; output `frame` with one rectangle (bouncing box).
  - Python renders `frame` and optionally caps tic rate (e.g. 35 tics/s like `TICRATE` in `doomdef.h`).
  - **Tests / regression:** List and add tests: e.g. jq given initial state + empty input yields next state + frame; N tics from fixed initial state produce known final state (snapshot or golden file). Runner test: one full tic round-trip. Run in CI or `make test`.
- **Reference:** `D_DoomLoop`, `TryRunTics`, `G_Ticker`, `D_Display`; fixed timestep idea from `d_main.c`.
- **Deliverable:** A box that moves and bounces, driven entirely by jq state updates.
- **Status:** Done.
- **Notes:** `doom_jq/jq/loop.jq` implements one tic: input `{ "state", "input": { "keys": [] } }` → output `{ "state", "frame" }` (bouncing box). Runner supports `--loop --headless`. Snapshot: `doom_jq/tests/loop_one_tic.expected`; `make test-doom-jq-loop`, `make test-doom-jq-runner`. Web client sends state+keys over WebSocket and draws returned frame each tick.

### 1.2 — Input handling and schema
- **Goal:** Python captures key events and passes them into jq; jq can branch on “menu” vs “game” at a high level.
- **Tasks:**
  - Python: map keyboard to a small `input` object, e.g. `{ "keys": ["Up","Down","Enter","Escape"] }`. No mouse support; keyboard only.
  - Extend state schema with e.g. `"mode": "menu" | "game"` so later we can have menu vs level behavior.
  - **Tests / regression:** List and add tests: jq state transitions for key sequences (e.g. Up/Down changes `selected`, Enter toggles `mode`); snapshot or assertion on output state. Run in CI or `make test`.
- **Reference:** `D_ProcessEvents`, `M_Responder`, `G_Responder`; `d_event.h` event types.
- **Deliverable:** Keys change something visible (e.g. a counter or the box direction) and mode can be switched.
- **Status:** Done.
- **Notes:** Input schema `{ "keys": ["Up","Down","Left","Right", ... ] }` is used in `loop.jq` and by the runner/web client. Arrow keys and WASD mapped in `doom.jqx` script and in runner (keyboard only). Explicit `mode` (menu/game) is left for Phase 2 when menu state is added.

---

## Phase 2 — Main menu

### 2.0 — Menu state and item list
- **Goal:** Menu state in jq: list of items, current selection index, and which menu “screen” we’re on.
- **Tasks:**
  - Represent main menu as JSON: e.g. `{ "screen": "main", "items": ["New Game","Options","Read This","Quit DOOM"], "selected": 0 }`.
  - jq: on input `Up`/`Down`, update `selected`; on `Enter`, either run item action or push a new screen (e.g. New Game → episode select).
  - Output “frame” as menu text or simple list of strings + cursor position so Python can draw a text/blocky menu.
  - **Tests / regression:** List and add tests: jq menu state for sequences (Up/Down/Enter) — e.g. selected index wraps, Enter on “Quit DOOM” sets quit flag; frame contains expected items and cursor. Snapshot or golden output for a short key sequence. Run in CI or `make test`.
- **Reference:** `m_menu.c` — `menu_t`, `menuitem_t`, `currentMenu`, `itemOn`; main menu items and `M_NewGame`, `M_QuitDOOM`, etc.
- **Deliverable:** Navigate main menu (up/down, enter) and see selection change; Quit exits.
- **Status:** Done.
- **Notes:** Menu state and items in `doom_jq/jq/menu.jq` and `doom_jq/jq/game.jq`: main items New Game, Options, Read This, Quit DOOM. Up/Down wrap selection; Enter on New Game goes to episode screen. Frame has `menu: { lines, selected }` for client to draw. Web client draws menu with `>>` cursor; Quit sets `state.quit` and client stops tick loop. Snapshot tests: `game_menu_initial.expected`, `make test-doom-jq-game`.

### 2.1 — Episode and skill selection (New Game path)
- **Goal:** New Game → Episode → Skill → “Start game” (to first level).
- **Tasks:**
  - Add screens: `episode` (E1–E3 for shareware; we can restrict to E1), `skill` (e.g. Baby / Easy / Normal / Hard / Nightmare — we can do a subset).
  - State: `screen`, `items`, `selected`, and e.g. `episode`, `skill` when starting.
  - On “Start” from skill screen: set `mode: "game"`, `episode: 1`, `map: 1`, `skill: <chosen>`, and clear menu stack.
  - **Tests / regression:** List and add tests: jq flow New Game → E1 → Skill → Start yields state with `mode: "game"`, `episode: 1`, `map: 1`, and chosen skill; episode/skill screens show correct items and selection. Snapshot tests for full path. Run in CI or `make test`.
- **Reference:** `M_NewGame` → `M_Episode` → `M_ChooseSkill` → `M_StartGame`; `startepisode`, `startmap`, `startskill` in `d_main.c`.
- **Deliverable:** From main menu, choose New Game → E1 → Skill → Start; Python switches to “game” mode with episode 1, map 1.
- **Status:** Done.
- **Notes:** Episode screen (E1–E3) and skill screen (Baby, Easy, Normal, Hard, Nightmare) in `game.jq`. Enter on episode selects episode and goes to skill; Enter on skill sets `mode: "game"`, `episode`, `map: 1`, `skill` (index), and initial `game` state (bouncing box). First game frame is emitted on transition. Snapshots: `game_newgame_episode.expected`, `game_episode_skill.expected`; `make test-doom-jq-game`.

### 2.2 — Menu drawing (optional: patches / look and feel)
- **Goal:** Menu looks more like Doom (optional: use patch names or simple graphics instead of plain text).
- **Tasks:**
  - If we have a way to load patches (e.g. from a small JSON atlas or pre-baked sprites): jq outputs draw commands with patch names or image IDs for title and menu items.
  - Otherwise: keep text/blocky but match layout (centered, spacing) and cursor (e.g. “>>” or a simple sprite).
  - Python draws according to jq output.
  - **Tests / regression:** List and add tests: jq frame output for main (and episode/skill) menus has expected draw commands or layout fields; regression tests for cursor position and item list. Run in CI or `make test`.
- **Reference:** `M_Drawer`, `V_DrawPatch`; `M_DrawMainMenu`-style layout in `m_menu.c`.
- **Deliverable:** Main menu (and optionally episode/skill) with recognizable Doom-like layout; no website, all local.
- **Status:** Not started.

---

## Phase 3 — Level data and first level load

### 3.0 — E1M1 data in JSON
- **Goal:** First level geometry and things available as JSON so jq doesn’t parse binary WAD.
- **Tasks:**
  - Tool (Python script or small program) that reads a WAD, finds E1M1 lumps, and outputs one JSON file: `vertexes`, `linedefs`, `sidedefs`, `sectors`, `nodes`, `ssectors`, `segs`, `things` (same names/semantics as `doomdata.h`).
  - Document the schema (types and field names matching the C structs where useful: e.g. `mapvertex_t`, `maplinedef_t`, `mapsector_t`, `mapthing_t`, etc.).
  - **Tests / regression:** List and add tests: WAD exporter on a known WAD (e.g. doom1.wad) produces JSON that validates against the schema; checksums or counts for vertexes/linedefs/sectors/things to detect accidental changes. Run in CI or `make test`.
- **Reference:** `w_wad.c` / `w_wad.h` (lump names, `W_ReadLump`); `doomdata.h` (map lump order, structs); `p_setup.c` (`P_SetupLevel`, level loading).
- **Deliverable:** `doom_jq/data/e1m1.json` (or similar) and a short schema doc.
- **Status:** Not started.

### 3.1 — Level state in jq (load E1M1)
- **Goal:** When starting a game from the menu, jq loads E1M1 into “level” state and sets player spawn.
- **Tasks:**
  - State shape: `{ "mode": "game", "level": { "vertexes", "linedefs", ... }, "player": { "x", "y", "angle", "health", ... }, "things": [...] }`.
  - Player spawn: from `things` with type “player 1” (Doom thing type 1); set `player.x`, `player.y`, `player.angle`.
  - jq reads level from a static JSON input (e.g. `--slurpfile level doom_jq/data/e1m1.json`) and merges into state when `mode` becomes `game` and `episode == 1`, `map == 1`. Python can pass level path or inject level JSON when starting game.
  - **Tests / regression:** List and add tests: jq with injected E1M1 JSON and “start game” state yields state with `level` populated and `player.x`/`player.y`/`player.angle` from thing type 1; no level when mode is menu. Snapshot or schema assertions. Run in CI or `make test`.
- **Reference:** `P_SetupLevel`, `playerstarts[]`, `mapthing_t`; `G_DoLoadLevel` / `G_InitNew`.
- **Deliverable:** After “Start” from menu, state contains full E1M1 and player at correct spawn; Python can pass level to jq each time or jq embeds it once.
- **Status:** Not started.

---

## Phase 4 — First level: rendering

### 4.0 — Top-down 2D “map” view
- **Goal:** Draw E1M1 in 2D (top-down) so we can verify geometry and player position.
- **Tasks:**
  - jq: from `level.linedefs` and `level.vertexes`, produce a list of line segments (or draw commands) in world coordinates; add player as a point or triangle.
  - Python: 2D projection (e.g. scale and center map in a window); draw lines and player.
  - **Tests / regression:** List and add tests: jq given level + player state outputs a list of line segments (or draw commands) with expected count/bounds; player marker present. Snapshot for fixed camera/position. Run in CI or `make test`.
- **Reference:** `am_map.c` (automap); we’re not doing BSP yet, just raw linedefs.
- **Deliverable:** See E1M1 outline and player position from above; player doesn’t move yet.
- **Status:** Not started.

### 4.1 — First-person “wireframe” or minimal 3D
- **Goal:** First-person view: only walls (no textures), e.g. wireframe or flat-shaded segments.
- **Tasks:**
  - Option A: jq uses BSP (or simple front-to-back order) to produce a list of wall segments in screen space (e.g. `{ "segments": [ {"x1","y1","x2","y2"}, ... ] }`). Python draws them.
  - Option B: jq outputs world-space wall segments + player view (x, y, angle); Python does projection and draw. (More work in Python, less in jq.)
  - Use fixed-point or float in jq for angles and coordinates; match Doom’s coordinate system (right-handed, angle 0 = east).
  - **Tests / regression:** List and add tests: jq for fixed player (x, y, angle) and level outputs segment list (non-empty, bounded by screen); changing angle changes segment order or set. Snapshot for one or two view angles. Run in CI or `make test`.
- **Reference:** `r_main.c` (viewx, viewy, viewangle, projection); `r_bsp.c` (BSP walk); `r_segs.c` (R_StoreWallRange); `r_draw.c` (column drawing). For MVP we can do a single-angle projection and no ceiling/floor.
- **Deliverable:** First-person view of E1M1 walls (wireframe or flat segments), no movement yet.
- **Status:** Not started.

### 4.2 — BSP-based visibility (optional but recommended)
- **Goal:** Correct back-to-front or BSP order so walls don’t overlap wrongly.
- **Tasks:**
  - In jq: implement BSP traversal from `nodes` and `ssectors`; output subsector segs in draw order (back-to-front relative to player).
  - Same output format as 4.1 (list of segments or column ranges); Python unchanged.
  - **Tests / regression:** List and add tests: BSP traversal order (e.g. subsector order) differs from non-BSP; known view position yields deterministic segment list; no duplicate or reversed segs. Snapshot for a few viewpoints. Run in CI or `make test`.
- **Reference:** `r_bsp.c` (`R_RenderBSPNode`), `r_segs.c`; `mapnode_t` (NF_SUBSECTOR), `mapsubsector_t`, `mapseg_t`.
- **Deliverable:** First-person view with correct occlusion for E1M1.
- **Status:** Not started.

### 4.3 — Floors and ceilings (flat shading)
- **Goal:** Draw sector floors and ceilings (single color per sector, no textures).
- **Tasks:**
  - jq: from visible subsectors/sectors, output horizontal spans or sector bounds per column (or per segment) with floor/ceiling heights and a “color” or “light” index.
  - Python: clip and fill floor/ceiling regions (e.g. with a single color per sector).
  - **Tests / regression:** List and add tests: jq output includes floor/ceiling spans or sector colors for visible subsectors; span bounds and light/color consistent with sector data. Snapshot for fixed view. Run in CI or `make test`.
- **Reference:** `r_plane.c` (floors/ceilings); `sector_t` (floorheight, ceilingheight, lightlevel).
- **Deliverable:** First-person view with solid floor and ceiling colors per sector.
- **Status:** Not started.

---

## Phase 5 — First level: gameplay

### 5.0 — Player movement (walk, turn)
- **Goal:** Arrow keys (or WASD) move and turn the player; collision with walls.
- **Tasks:**
  - Each tic: jq gets `input.keys`; update `player.angle` (left/right) and move `player.x`, `player.y` (forward/back); implement simple collision (e.g. test movement against linedefs with ML_BLOCKING or slide along wall).
  - Use fixed-point or scaled integers in jq if we want to match Doom’s movement feel; otherwise float is fine for MVP.
  - **Tests / regression:** List and add tests: jq movement (forward/back/strafe/turn) updates position and angle; collision prevents player from crossing blocking linedefs (unit test with minimal level); sequence of tics from fixed state yields reproducible final state. Run in CI or `make test`.
- **Reference:** `p_user.c` (`P_PlayerThink`), `G_BuildTiccmd`; `p_mobj.c` / `p_map.c` (movement, collision); `d_ticcmd.h` (ticcmd_t: forwardmove, sidemove, angle delta).
- **Deliverable:** Walk and turn in E1M1; no clipping through walls.
- **Status:** Not started.

### 5.1 — One weapon and firing (optional)
- **Goal:** Press fire (keyboard only, e.g. Ctrl or dedicated key); show a shot (hit-scan or simple projectile) and maybe a HUD change.
- **Tasks:**
  - jq: on fire key, compute hit (ray vs linedefs or first thing hit); update state (ammo, hit thing if any).
  - For MVP: no sprites; maybe a muzzle flash frame or HUD “firing” state for one tic.
  - **Tests / regression:** List and add tests: jq fire with clear line of sight hits expected target or wall distance; ammo decrements; hit state or damage applied. Snapshot or assertion for a few scenarios (no target, hit thing). Run in CI or `make test`.
- **Reference:** `p_pspr.c` (weapon sprites); `p_map.c` (P_AimLineAttack, P_LineAttack); `p_inter.c` (damage).
- **Deliverable:** Fire key causes a hit check; can damage/kill one enemy type if we add it next.
- **Status:** Not started.

### 5.2 — One enemy type and basic AI (optional)
- **Goal:** E1M1 things: spawn one enemy type (e.g. zombie); simple AI (face player, move toward, or one attack).
- **Tasks:**
  - Load `things` into state; filter by type (e.g. 3004 for sergeant). Each tic: jq updates enemy positions or state (e.g. “see player” → move closer); simple collision so monsters don’t overlap.
  - One attack (e.g. hitscan or one projectile) and reduce `player.health` when hit.
  - **Tests / regression:** List and add tests: jq enemy AI (e.g. move toward player) and attack logic; player health decreases when hit; enemy state (position, health) updates each tic. Snapshot for a short sequence. Run in CI or `make test`.
- **Reference:** `p_enemy.c`, `info.c` (mobjinfo); `p_mobj.c` (P_NightmareRespawn, movement); `p_tick.c` (thinkers).
- **Deliverable:** At least one enemy in E1M1 that can damage the player; optional: player can kill it (reuse 5.1).
- **Status:** Not started.

---

## Phase 6 — Polish (first level + menu)

### 6.0 — Status bar / HUD (minimal)
- **Goal:** Show health, ammo (if we added weapon), and maybe keys or face.
- **Tasks:**
  - jq output: add `hud: { "health", "ammo", ... }` to frame; Python draws a small status bar (text or simple patches).
  - **Tests / regression:** List and add tests: jq frame includes `hud` with correct health (and ammo when applicable) from state; after damage or ammo change, HUD values match. Assertion or snapshot. Run in CI or `make test`.
- **Reference:** `st_stuff.c` (ST_Drawer); `st_stuff.h`; status bar is 32px high in Doom.
- **Deliverable:** Minimal HUD so player can see health (and ammo if implemented).
- **Status:** Not started.

### 6.1 — Pause and menu return
- **Goal:** Escape pauses or opens menu; from menu, “Resume” or “New Game” / “Quit” work.
- **Tasks:**
  - State: `paused` or `menuactive`; when Escape in game, set `menuactive = true` and push “ingame” menu (Resume, New Game, Options, Quit). jq handles same menu navigation as 2.0/2.1.
  - **Tests / regression:** List and add tests: Escape in game sets `menuactive` and shows ingame menu; Resume clears it; New Game resets level state; Quit sets quit flag. Key sequences for each path. Run in CI or `make test`.
- **Reference:** `M_Responder` (Escape); `menuactive` in `doomstat.h`; ingame menu in `m_menu.c`.
- **Deliverable:** Pause and resume; from menu, New Game restarts E1M1, Quit exits.
- **Status:** Not started.

---

## Dependency summary

- **1.0** → **1.1** → **1.2** (runner and loop must exist before menu/game).
- **1.2** → **2.0** → **2.1** → **2.2** (input and mode before full menu).
- **2.1** → **3.0** → **3.1** (menu “Start” leads to level load).
- **3.1** → **4.0** → **4.1** → **4.2** → **4.3** (level data before any view).
- **4.1 or 4.2** → **5.0** (movement in 3D view).
- **5.0** → **5.1**, **5.2** (optional); **5.x** → **6.0** (HUD), **6.1** (pause/menu).

---

## Out of scope (for this plan)

- Any web or jq.bevel.work integration.
- Mouse input (keyboard only).
- Episodes 2–3 or other maps.
- Full weapon set, full monster set, or multiplayer.
- Sound (optional later).
- Textures and sprites (we can add “textured walls” as a later milestone if desired).
- Save/load game (optional later).

---

## File layout (suggested)

- `DOOM_IN_JQ_MILESTONES.md` — this plan (project root).
- `doom_jq/` — implementation directory.
  - `runner.py` — Python host: runs jq, handles display and input, drives the game loop.
  - `jq/` — jq scripts: e.g. `frame.jq`, `loop.jq`, `menu.jq`, `game.jq`, `level.jq`, `render.jq`.
  - `data/e1m1.json` — E1M1 level data (from WAD export).
  - `tools/` — WAD→JSON exporter (Python) and any small helpers.

Pipeline glue is Python throughout: `doom_jq/runner.py` invokes jq, feeds state/input, and renders frames.

You can implement in order 1.0 → 1.1 → 1.2 → 2.0 → 2.1 → 3.0 → 3.1 → 4.0 → 4.1 → 5.0, then add 2.2, 4.2, 4.3, 5.1, 5.2, 6.0, 6.1 as time allows.
