# Doom-in-jq game loop (Phase 1.1): input = { "state": {...}, "input": {"keys": [...]} }
# Output: { "state": next_state, "frame": frame }
# Bouncing box: state = { x, y, vx, vy }; frame = single rect.

def screen_width: 320;
def screen_height: 200;

def box_w: 40;
def box_h: 20;

# Initial state when .state is null or empty
def initial_state: { x: 140, y: 90, vx: 4, vy: 3 };

def state: .state // initial_state;
def keys: .input.keys // [];

# Clamp position and flip velocity on bounce
def tick:
  . as $s
  | ($s.x + $s.vx) as $nx
  | ($s.y + $s.vy) as $ny
  | (if $nx < 0 or $nx > (screen_width - box_w) then -$s.vx else $s.vx end) as $vx2
  | (if $ny < 0 or $ny > (screen_height - box_h) then -$s.vy else $s.vy end) as $vy2
  | {
      x: (if $nx < 0 then 0 elif $nx > (screen_width - box_w) then (screen_width - box_w) else $nx end),
      y: (if $ny < 0 then 0 elif $ny > (screen_height - box_h) then (screen_height - box_h) else $ny end),
      vx: $vx2,
      vy: $vy2
    };

def next_state: state | tick;

def frame:
  next_state as $s
  | {
      width: screen_width,
      height: screen_height,
      draw: [
        { rect: [0, 0, screen_width, screen_height], color: "#1a1a2e" },
        { rect: [($s.x | floor), ($s.y | floor), box_w, box_h], color: "#4a4a6a" }
      ]
    };

{
  state: next_state,
  frame: frame
}
