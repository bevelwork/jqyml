# Doom-in-jq combined game (Phase 2): menu + game loop.
# Input: { "state": {...}, "input": {"keys": [...]} }
# Output: { "state": next_state, "frame": frame }
# If state.quit: pass through with frame null.
# If state.mode == "game": run game (bouncing box) tick.
# Else: run menu tick.

def screen_width: 320;
def screen_height: 200;

# ---------- Menu (Phase 2) ----------
def main_items: ["New Game", "Options", "Read This", "Quit DOOM"];
def episode_items: ["E1", "E2", "E3"];
def skill_items: ["Baby", "Easy", "Normal", "Hard", "Nightmare"];

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
        if $m.screen == "main" then
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
          { mode: "game",
            menu: null,
            episode: ($st.menu.episode // 1),
            map: 1,
            skill: $st.menu.selected,
            game: { x: 140, y: 90, vx: 4, vy: 3 }
          }
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

# ---------- Game (bouncing box from loop.jq) ----------
def box_w: 40;
def box_h: 20;

def game_state: .state.game // { x: 140, y: 90, vx: 4, vy: 3 };

def game_tick:
  state as $st
  | ($st.game // { x: 140, y: 90, vx: 4, vy: 3 }) as $g
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
  | $st | .game = $next_game;

def game_frame($st):
  $st.game as $g
  | {
      width: screen_width,
      height: screen_height,
      draw: [
        { rect: [0, 0, screen_width, screen_height], color: "#1a1a2e" },
        { rect: [($g.x | floor), ($g.y | floor), box_w, box_h], color: "#4a4a6a" }
      ]
    };

# ---------- Dispatch ----------
(if state.quit then
   { state: state, frame: null }
 elif state.mode == "game" then
   (game_tick) as $next
   | { state: $next, frame: game_frame($next) }
 else
   (menu_tick) as $next
   | { state: $next,
       frame: (if $next.mode == "game" then game_frame($next) else menu_frame($next) end) }
 end)
