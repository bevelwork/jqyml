# Doom-in-jq combined game (Phase 2): menu + game loop.
# Input: { "state": {...}, "input": {"keys": [...]} }
# Output: { "state": next_state, "frame": frame }
# If state.quit: pass through with frame null.
# If state.mode == "game": run game (bouncing box) tick.
# Else: run menu tick.

def screen_width: 320;
def screen_height: 200;

# Phase 5.0: movement (angle in degrees, 0 = east). Taylor in first quadrant, then symmetry for any angle.
def _pi: 3.141592653589793;
def _deg2rad: . * (_pi / 180);
def _norm_angle: if . >= 360 then . - 360 | _norm_angle elif . < 0 then . + 360 | _norm_angle else . end;
def _sin_first_quad($deg): ($deg | _deg2rad) as $r | $r - ($r * $r * $r / 6) + ($r * $r * $r * $r * $r / 120);
def _cos_first_quad($deg): ($deg | _deg2rad) as $r | 1 - ($r * $r / 2) + ($r * $r * $r * $r / 24);
def _sin: _norm_angle as $a | if $a <= 90 then _sin_first_quad($a) elif $a < 180 then _sin_first_quad(180 - $a) elif $a < 270 then -(_sin_first_quad($a - 180)) else -(_sin_first_quad(360 - $a)) end;
def _cos: _norm_angle as $a | if $a <= 90 then _cos_first_quad($a) elif $a < 180 then -(_cos_first_quad(180 - $a)) elif $a < 270 then -(_cos_first_quad($a - 180)) else _cos_first_quad(360 - $a) end;
def move_speed: 8;
def turn_speed: 6;

# ---------- Menu (Phase 2) ----------
def main_items: ["New Game", "Options", "Read This", "Quit DOOM"];
def episode_items: ["E1", "E2", "E3"];
def skill_items: ["Baby", "Easy", "Normal", "Hard", "Nightmare"];
def ingame_items: ["Resume", "New Game", "Options", "Quit DOOM"];

def initial_menu_state:
  { mode: "menu",
    menu: { screen: "main", items: main_items, selected: 0 }
  };

def keys: .input.keys // [];
def state: .state // initial_menu_state;

def wrap_selected($items):
  (if type == "object" then .selected else . end) as $s
  | ($items | length) as $n
  | (if $n == 0 then 0 else (($s % $n) + $n) % $n end);

def menu_tick:
  state as $st
  | ($st.menu // initial_menu_state.menu) as $m
  | keys as $k
  | ($st.menu.selected // 0) as $sel
  | (if ($k | index("Up")) then ($sel - 1) elif ($k | index("Down")) then ($sel + 1) else $sel end) as $new_sel
  | ($new_sel | wrap_selected($m.items)) as $wrapped
  | (if ($k | index("Enter")) then
        if $m.screen == "ingame" then
          if ($m.items[$wrapped] == "Resume") then $st | .menuactive = false | .menu = null
          elif ($m.items[$wrapped] == "New Game") then $st | .menuactive = false | .mode = "menu" | .menu = { screen: "episode", items: episode_items, selected: 0 }
          elif ($m.items[$wrapped] == "Quit DOOM") then $st | .quit = true
          else $st | .menu.selected = $wrapped end
        elif $m.screen == "main" then
          if ($m.items[$wrapped] == "New Game") then
            $st | .menu = { screen: "episode", items: episode_items, selected: 0 }
          elif ($m.items[$wrapped] == "Quit DOOM") then
            $st | .quit = true
          else
            $st | .menu.selected = $wrapped
          end
        elif $m.screen == "episode" then
          (($m.items[$wrapped] | capture("E(?<e>[0-9]+)") | .e | tonumber) // 1) as $ep
          | $st | .menu = { screen: "skill", items: skill_items, selected: 2, episode: $ep }
        elif $m.screen == "skill" then
          ($st.menu.episode // 1) as $ep
          | (if ($ep == 1) and (.input.level != null) then .input.level else null end) as $level_data
          | (if $level_data != null then ($level_data.things // [] | map(select(.type == 1)) | .[0]) else null end) as $p1
          | { mode: "game",
              menu: null,
              episode: $ep,
              map: 1,
              skill: $st.menu.selected,
              game: { x: 140, y: 90, vx: 4, vy: 3 }
            }
          | (if $level_data != null then .level = $level_data else . end)
          | (if $p1 != null then .player = { x: $p1.x, y: $p1.y, angle: $p1.angle, health: 100 } else . end)
          | (if $level_data != null then .things = ($level_data.things // []) else . end)
        else
          $st | .menu.selected = $wrapped
        end
    else
      $st | .menu.selected = $wrapped
    end);

def menu_frame($next):
  if $next.menu then
    { width: screen_width,
      height: screen_height,
      menu: { lines: $next.menu.items, selected: ($next.menu.selected // 0) }
    }
  else
    null
  end;

# ---------- Game: level map (Phase 4.0) or bouncing box ----------
def box_w: 40;
def box_h: 20;

def game_state: .state.game // { x: 140, y: 90, vx: 4, vy: 3 };

# Level lines for top-down map: from linedefs + vertexes -> [{x1,y1,x2,y2}]
def level_lines($level):
  ($level.vertexes // []) as $v
  | ($level.linedefs // [])
  | map(
      { x1: $v[.v1].x, y1: $v[.v1].y, x2: $v[.v2].x, y2: $v[.v2].y }
    );

# Walls for first-person (Phase 4.1): each wall has world segment + floor/ceiling heights from front sector
def level_walls_3d($level):
  ($level.vertexes // []) as $v
  | ($level.linedefs // []) as $ld
  | ($level.sidedefs // []) as $sd
  | ($level.sectors // []) as $sec
  | [ range(0; $ld | length) as $i
      | $ld[$i] as $l
      | ($l.sidenum[0] // -1) as $si
      | if $si >= 0 and ($si < ($sd | length)) and ($sd[$si] != null) then
          (($sd[$si].sector // -1) | if . >= 0 and . < ($sec | length) then $sec[.] else null end) as $s
          | if $s != null then
              { x1: $v[$l.v1].x, y1: $v[$l.v1].y, x2: $v[$l.v2].x, y2: $v[$l.v2].y,
                  floorheight: ($s.floorheight // 0), ceilingheight: ($s.ceilingheight // 128) }
            else empty end
        else
          empty
        end
    ];

# BSP (Phase 4.2): one wall from a seg (vertexes + linedef front sector)
def _seg_wall($level; $seg):
  ($level.vertexes // []) as $v
  | ($level.linedefs // []) as $ld
  | ($level.sidedefs // []) as $sd
  | ($level.sectors // []) as $sec
  | $ld[$seg.linedef] as $l
  | ($l.sidenum[0] // -1) as $si
  | (if $si >= 0 then $sec[$sd[$si].sector] else null end) as $s
  | (if $s != null then { x1: $v[$seg.v1].x, y1: $v[$seg.v1].y, x2: $v[$seg.v2].x, y2: $v[$seg.v2].y, floorheight: ($s.floorheight // 0), ceilingheight: ($s.ceilingheight // 128) } else empty end);

# NF_SUBSECTOR = 0x8000 (32768)
def _bsp_walls($level; $px; $py; $child):
  if $child >= 32768 then
    ($child - 32768) as $ssi
    | ($level.ssectors[$ssi] // { firstseg: 0, numsegs: 0 })
    | range(0; .numsegs) as $j
    | $level.segs[.firstseg + $j] as $seg
    | _seg_wall($level; $seg)
  else
    ($level.nodes[$child] // null) as $n
    | if $n == null then empty
      else (($px - $n.x) * $n.dy - ($py - $n.y) * $n.dx) as $side
      | (if $side > 0 then [$n.children[1], $n.children[0]] else [$n.children[0], $n.children[1]] end) as $order
      | $order[0] as $c0 | $order[1] as $c1
      | _bsp_walls($level; $px; $py; $c0), _bsp_walls($level; $px; $py; $c1)
      end
  end;

def level_walls_3d_bsp($level; $px; $py):
  if ($level.nodes | length) > 0 then
    [ _bsp_walls($level; $px; $py; ($level.nodes | length - 1)) ]
  else
    level_walls_3d($level)
  end;

# Phase 5.0: is (px, py) inside the map? (on correct side of all blocking linedefs)
def _level_bbox_center($level):
  ($level.vertexes // [] | map(.x) | (min + max) / 2) as $cx
  | ($level.vertexes // [] | map(.y) | (min + max) / 2) as $cy
  | [$cx, $cy];

# Phase 5.0: point inside map (on correct side of all blocking linedefs). Linedef-based: point must
# be on the same side as level center for every linedef (cross-product test).
def _point_inside_level($level; $px; $py):
  ($level.vertexes // []) as $v
  | ($level.linedefs // []) as $ld
  | _level_bbox_center($level) as [$cx, $cy]
  | if ($ld | length) == 0 then
      (($v | map(.x) | min)) as $minx
      | (($v | map(.x) | max)) as $maxx
      | (($v | map(.y) | min)) as $miny
      | (($v | map(.y) | max)) as $maxy
      | ($px >= $minx and $px <= $maxx and $py >= $miny and $py <= $maxy)
    else
      reduce range(0; $ld | length) as $i (true;
        (($v[$ld[$i].v1]) as $v1
        | ($v[$ld[$i].v2]) as $v2
        | (($v2.x - $v1.x) * ($py - $v1.y) - ($v2.y - $v1.y) * ($px - $v1.x)) as $cross_p
        | (($v2.x - $v1.x) * ($cy - $v1.y) - ($v2.y - $v1.y) * ($cx - $v1.x)) as $cross_c
        | ($cross_c >= 0 and $cross_p >= 0) or ($cross_c <= 0 and $cross_p <= 0)
        ) as $ok
        | . and $ok
      )
    end;

# Reference cube at level center for distance perception (same wall format as level walls)
def _refcube_walls($level):
  _level_bbox_center($level) as [$cx, $cy]
  | (24 | floor) as $half
  | 64 as $ceiling
  | [
      { x1: ($cx - $half), y1: ($cy - $half), x2: ($cx + $half), y2: ($cy - $half), floorheight: 0, ceilingheight: $ceiling },
      { x1: ($cx + $half), y1: ($cy - $half), x2: ($cx + $half), y2: ($cy + $half), floorheight: 0, ceilingheight: $ceiling },
      { x1: ($cx + $half), y1: ($cy + $half), x2: ($cx - $half), y2: ($cy + $half), floorheight: 0, ceilingheight: $ceiling },
      { x1: ($cx - $half), y1: ($cy + $half), x2: ($cx - $half), y2: ($cy - $half), floorheight: 0, ceilingheight: $ceiling }
    ];

def game_tick:
  state as $st
  | if $st.level != null and $st.player != null then
      keys as $k
      | (if ($k | index("Escape")) then
            $st | .menuactive = true | .menu = { screen: "ingame", items: ingame_items, selected: 0 }
          else
            ($st.player.angle // 0) as $a
            | ($st.player.x // 0) as $px
            | ($st.player.y // 0) as $py
            | (if (($k | index("Left")) != null and ($k | index("Right")) != null) then $a
               elif ($k | index("Left")) != null then $a - turn_speed
               elif ($k | index("Right")) != null then $a + turn_speed
               else $a end) as $new_a
            | ($new_a | _norm_angle) as $angle
            | ($angle | _cos) as $ca
            | ($angle | _sin) as $sa
            | (if (($k | index("Up")) != null and ($k | index("Down")) != null) then 0
               elif ($k | index("Up")) != null then move_speed
               elif ($k | index("Down")) != null then -move_speed
               else 0 end) as $fwd
            | ($px + ($fwd * $ca)) as $nx
            | ($py + ($fwd * $sa)) as $ny
            | ( (($nx - $px) | . * .) as $dx2
              | (($ny - $py) | . * .) as $dy2
              | if _point_inside_level($st.level; $nx; $ny) then [$nx, $ny]
                elif ($dx2 < 0.0001 or $dy2 < 0.0001) then [$px, $py]
                elif _point_inside_level($st.level; $nx; $py) then [$nx, $py]
                elif _point_inside_level($st.level; $px; $ny) then [$px, $ny]
                else [$px, $py]
                end
              ) as $candidate
            | ( (($candidate[0] - $px) | . * .) + (($candidate[1] - $py) | . * .) ) as $dist_sq
            | ( (move_speed * move_speed * 2) | floor ) as $max_dist_sq
            | (if $dist_sq <= $max_dist_sq then $candidate else [$px, $py] end) as $pos
            | $st
            | .player.x = $pos[0]
            | .player.y = $pos[1]
            | .player.angle = $angle
          end)
    else
      ($st.game // { x: 140, y: 90, vx: 4, vy: 3 }) as $g
      | ($g.x + $g.vx) as $nx
      | ($g.y + $g.vy) as $ny
      | (if $nx < 0 or $nx > (screen_width - box_w) then -$g.vx else $g.vx end) as $vx2
      | (if $ny < 0 or $ny > (screen_height - box_h) then -$g.vy else $g.vy end) as $vy2
      | {
          x: (if $nx < 0 then 0 elif $nx > (screen_width - box_w) then (screen_width - box_w) else $nx end),
          y: (if $ny < 0 then 0 elif $ny > (screen_height - box_h) then (screen_height - box_h) else $ny end),
          vx: $vx2,
          vy: $vy2
        } as $next_game
      | $st | .game = $next_game
    end;

def game_frame($st):
  if ($st.level != null) and ($st.player != null) then
    # Phase 4.0 map + 4.1 first-person + 6.0 HUD
    {
      width: screen_width,
      height: screen_height,
      map: {
        lines: level_lines($st.level),
        player: { x: $st.player.x, y: $st.player.y, angle: $st.player.angle }
      },
      view3d: {
        walls: level_walls_3d_bsp($st.level; $st.player.x; $st.player.y),
        refcube: _refcube_walls($st.level),
        player: { x: $st.player.x, y: $st.player.y, angle: $st.player.angle },
        floorlight: ($st.level.sectors[0].lightlevel // 160),
        ceilinglight: ($st.level.sectors[0].lightlevel // 160)
      },
      hud: { health: ($st.player.health // 100) }
    }
  else
    ($st.game // { x: 140, y: 90, vx: 4, vy: 3 }) as $g
    | {
        width: screen_width,
        height: screen_height,
        draw: [
          { rect: [0, 0, screen_width, screen_height], color: "#1a1a2e" },
          { rect: [($g.x | floor), ($g.y | floor), box_w, box_h], color: "#4a4a6a" }
        ]
      }
  end;

# ---------- Dispatch ----------
(if state.quit then
   { state: state, frame: null }
 elif (state.menuactive == true) and (state.menu != null) then
   (menu_tick) as $next
   | { state: $next, frame: menu_frame($next) }
 elif state.mode == "game" then
   (game_tick) as $next
   | { state: $next, frame: (if $next.menuactive == true and $next.menu != null then menu_frame($next) else game_frame($next) end) }
 else
   (menu_tick) as $next
   | { state: $next,
       frame: (if $next.mode == "game" then game_frame($next) else menu_frame($next) end) }
 end)
