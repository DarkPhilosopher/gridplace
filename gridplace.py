#!/data/data/com.termux/files/usr/bin/python3
"""gridplace -- move an ASCII cursor around a grid, place a piece, color
it, and submit it. A piece flashes (blinks) the whole time it is still
being worked on -- placed but not yet submitted -- and submitting is
what makes it stop flashing for good. The bare cursor itself blinks
too, the ordinary way a text cursor does, whenever it's sitting over
empty ground with nothing pending.

Requested directly: "make a new program in my local files of this
device it will play from its folder in downloads folder it will allow
me ASCII to move a cursor and place a piece than color it and submit
it while its flashing so it doesnt flash anymore." Lives entirely
under this same folder (Downloads, not Termux's own private home the
way spark/spark2/termux-chat do) so it's reachable and editable through
an ordinary file manager or text editor app, not just Termux itself.

See README.md for the full variables-and-rules table (every piece of
state this program keeps, where it lives, and exactly which WHEN
something happens DOES what to which other variable).

No external libraries, no other files required to run it:

    python3 gridplace.py
"""

import json
import os
import shutil
import sys
import termios
import time
import tty

SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid.json")

COLORS = {
    "white": 37, "red": 31, "green": 32, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36,
}
COLOR_ORDER = ["white", "red", "green", "yellow", "blue", "magenta", "cyan"]

TICK_SECONDS = 0.1     # main loop pace -- 10/sec, same as spark2's own
BLINK_EVERY = 5         # toggle every 5 ticks -- about a 1x/second flash

GLYPH = "#"             # every piece looks the same; only its color varies


# ---------------------------------------------------------------------------
# state -- see README.md's table for what each of these means and the
# WHEN/DO rules connecting them
# ---------------------------------------------------------------------------

def new_state(width, height):
    return {
        "width": width, "height": height,
        "cursor_x": width // 2, "cursor_y": height // 2,
        "grid": {},        # "x,y" -> {"color": name, "committed": bool}
        "pending": None,   # "x,y" of the one piece still flashing, or None
        "tick": 0,
        "blink_on": True,
    }


def _key(state, x, y):
    return "%d,%d" % (x, y)


def load_grid(state):
    if not os.path.exists(SAVE_FILE):
        return
    try:
        with open(SAVE_FILE) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    for k, piece in saved.items():
        if piece.get("color") in COLORS:
            state["grid"][k] = {"color": piece["color"], "committed": True}


def save_grid(state):
    # Only ever-committed pieces are worth keeping -- a still-flashing
    # pending piece is, by definition, unfinished work.
    committed = {k: {"color": v["color"]} for k, v in state["grid"].items() if v["committed"]}
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(committed, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# the six things a keypress can do
# ---------------------------------------------------------------------------

def move(state, dx, dy):
    state["cursor_x"] = max(0, min(state["width"] - 1, state["cursor_x"] + dx))
    state["cursor_y"] = max(0, min(state["height"] - 1, state["cursor_y"] + dy))


def place_or_pick_up(state):
    """WHEN space is pressed: an empty cell gets a brand new flashing
    piece; a cell that already holds a submitted piece is picked back
    up -- unflashed again, editable -- instead of being replaced.
    Never touches a cell that's already the pending one."""
    k = _key(state, state["cursor_x"], state["cursor_y"])
    if state["pending"] == k:
        return
    existing = state["grid"].get(k)
    if existing is None:
        state["grid"][k] = {"color": COLOR_ORDER[0], "committed": False}
    else:
        existing["committed"] = False
    state["pending"] = k


def cycle_color(state):
    """WHEN c is pressed AND a piece is pending: its color steps to the
    next one in COLOR_ORDER, wrapping around. Does nothing with no
    pending piece -- there's nothing yet to color."""
    if state["pending"] is None:
        return
    piece = state["grid"][state["pending"]]
    i = (COLOR_ORDER.index(piece["color"]) + 1) % len(COLOR_ORDER)
    piece["color"] = COLOR_ORDER[i]


def submit(state):
    """WHEN enter is pressed AND a piece is pending: it's marked
    committed and cleared from "pending" -- the one and only thing in
    this whole program that ever stops a piece from flashing again."""
    if state["pending"] is None:
        return
    state["grid"][state["pending"]]["committed"] = True
    state["pending"] = None
    save_grid(state)


def tick(state):
    state["tick"] += 1
    if state["tick"] % BLINK_EVERY == 0:
        state["blink_on"] = not state["blink_on"]


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------

def render(state):
    grid = [[" "] * state["width"] for _ in range(state["height"])]
    for k, piece in state["grid"].items():
        x, y = (int(p) for p in k.split(","))
        if piece["committed"] or state["blink_on"]:
            code = COLORS[piece["color"]]
            grid[y][x] = "\033[%dm%s\033[0m" % (code, GLYPH)
    cx, cy = state["cursor_x"], state["cursor_y"]
    if _key(state, cx, cy) not in state["grid"] and state["blink_on"]:
        grid[cy][cx] = "_"
    lines = ["+" + "-" * state["width"] + "+"]
    lines += ["|" + "".join(row) + "|" for row in grid]
    lines.append("+" + "-" * state["width"] + "+")
    return lines


def draw(state):
    out = ["\033[H\033[2J"]
    out.extend(render(state))
    pending_note = "flashing -- not submitted yet" if state["pending"] else "nothing pending"
    out.append("pos %d,%d   %d piece%s placed   %s"
                % (state["cursor_x"], state["cursor_y"], len(state["grid"]),
                   "" if len(state["grid"]) == 1 else "s", pending_note))
    out.append("arrows/wasd move . space place/pick up . c color . enter submit . q quit")
    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# raw keyboard -- same shape as spark2.py's own Keyboard, deliberately:
# arrows decode to a short escape sequence that has to be read as a
# whole, and cbreak mode must never eat a keystroke sent before it's
# actually in effect (see spark2's own TCSAFLUSH note, if this program
# ever grows a pty test of its own)
# ---------------------------------------------------------------------------

class Keyboard:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old = None

    def __enter__(self):
        self.old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc):
        if self.old is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def pressed(self):
        import select
        if not select.select([self.fd], [], [], 0)[0]:
            return None
        ch = os.read(self.fd, 1)
        if ch == b"\x1b":
            if select.select([self.fd], [], [], 0.05)[0]:
                rest = os.read(self.fd, 2)
                return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left"}.get(rest)
            return "quit"
        if ch in (b"\x03", b"\x04"):
            return "quit"
        return {"w": "up", "s": "down", "a": "left", "d": "right",
                " ": "place", "c": "color", "\r": "submit", "\n": "submit",
                "q": "quit"}.get(ch.decode("utf-8", "ignore").lower())


def _grid_size():
    """Computed once at startup, not every redraw -- a resize mid-session
    isn't re-fit, the same tradeoff spark2.py's own _grid_side() made,
    for the same reason: the grid IS this size, not a viewport onto a
    bigger one."""
    cols, rows = shutil.get_terminal_size(fallback=(40, 20))
    # 3 rows for the border + 2 status lines below it
    return max(10, min(cols - 2, 60)), max(6, min(rows - 5, 20))


def run():
    width, height = _grid_size()
    state = new_state(width, height)
    load_grid(state)
    moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    with Keyboard() as kb:
        while True:
            draw(state)
            time.sleep(TICK_SECONDS)
            tick(state)
            key = kb.pressed()
            if key == "quit":
                break
            elif key in moves:
                move(state, *moves[key])
            elif key == "place":
                place_or_pick_up(state)
            elif key == "color":
                cycle_color(state)
            elif key == "submit":
                submit(state)
    save_grid(state)
    print("\nsaved to " + SAVE_FILE)


if __name__ == "__main__":
    run()
