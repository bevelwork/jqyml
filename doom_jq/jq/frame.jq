# Doom-in-jq frame output (Phase 1.0).
# Frame schema: { "width": 320, "height": 200, "draw": [ {"rect": [x,y,w,h], "color": "#rrggbb"}, ... ] }
# Doom base resolution: SCREENWIDTH 320, SCREENHEIGHT 200 (doomdef.h).

def screen_width: 320;
def screen_height: 200;

# Emit a single static frame: full-screen dark background + one centered "pattern" rectangle.
{
  width: screen_width,
  height: screen_height,
  draw: [
    { rect: [0, 0, screen_width, screen_height], color: "#1a1a2e" },
    { rect: [120, 80, 80, 40], color: "#4a4a6a" }
  ]
}
