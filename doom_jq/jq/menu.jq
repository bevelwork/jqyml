# Doom-in-jq menu (Phase 2): input = { "state": {...}, "input": {"keys": [...]} }
# Output: { "state": next_state, "frame": frame }
# State when in menu: { mode: "menu", menu: { screen, items, selected, episode?, skill? } }
# Frame when in menu: { width, height, menu: { lines, selected } }

def screen_width: 320;
def screen_height: 200;

# Main menu items (Doom-style)
def main_items: ["New Game", "Options", "Read This", "Quit DOOM"];
def episode_items: ["E1", "E2", "E3"];
def skill_items: ["Baby", "Easy", "Normal", "Hard", "Nightmare"];

# Initial menu state (null or missing state)
def initial_menu_state:
  { mode: "menu",
    menu: { screen: "main", items: main_items, selected: 0 }
  };

def keys: .input.keys // [];
def state: .state // initial_menu_state;
def menu: .state.menu // initial_menu_state.menu;

# Wrap selected index in items array (input: number or { selected: n })
def wrap_selected($items):
  (if type == "object" then .selected else . end) as $s
  | ($items | length) as $n
  | (if $n == 0 then 0 else (($s % $n) + $n) % $n end);

# Next menu state from key input
def menu_tick:
  state as $st
  | menu as $m
  | ($m.items | length) as $n
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
          # Start game: switch to game mode
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
    end) as $next
  | $next;

# Single tick: compute next state once, then frame from it
(menu_tick) as $next
| {
    state: $next,
    frame: (if $next.menu then
      { width: screen_width,
        height: screen_height,
        menu: { lines: $next.menu.items, selected: ($next.menu.selected // 0) }
      }
    else
      null
    end)
  }
