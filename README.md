# gridplace

Move an ASCII cursor around a grid, place a piece, color it, and
submit it. A piece flashes the whole time it's still being worked on
-- placed but not yet submitted -- and submitting is the one thing
that makes it stop flashing, for good.

Lives here in Downloads on purpose, not in Termux's own private home
folder the way spark/spark2/termux-chat do, so it's reachable and
editable through an ordinary file manager or text editor app too.

## Running it

```
python3 gridplace.py
```

Needs nothing else -- one file, Python's own standard library only.
Your board is saved to `grid.json`, right next to `gridplace.py`, every
time you submit a piece, and loaded back automatically next time you
run it.

## Controls

| Key | Does |
|---|---|
| arrows / wasd | move the cursor |
| space | place a new piece here, or pick an already-submitted one back up to edit it |
| c | cycle the color of whichever piece is currently pending |
| enter | submit the pending piece -- locks it in, stops it flashing |
| q | quit (autosaves first) |

## Every variable, where it lives, and what makes it change

The whole program is six pieces of state (in the dict `run()` builds
via `new_state()`) and six small rules connecting them -- the same
WHEN-something-happens/DO-something-about-it shape spark2's own
engine uses, just fixed in place here rather than user-editable.

| Variable | Lives in | What it is |
|---|---|---|
| `cursor_x`, `cursor_y` | `state` | where the cursor currently sits on the grid |
| `grid` | `state` | every piece ever placed: `"x,y"` -> `{color, committed}` |
| `pending` | `state` | the `"x,y"` of the one piece still flashing, or `None` if nothing is |
| `tick` | `state` | counts main-loop passes, purely to time the blink |
| `blink_on` | `state` | whether *this* frame shows flashing things or hides them |
| `piece["color"]` | inside each entry of `grid` | that one piece's color, one of `COLOR_ORDER` |
| `piece["committed"]` | inside each entry of `grid` | `True` once submitted -- never flashes again after that |

And the rules -- every one of them is its own small function, named
for what it does:

- **WHEN** an arrow/wasd key is pressed **DO** move `cursor_x`/`cursor_y`
  by one, clamped to the grid's edges. (`move`)
- **WHEN** space is pressed and the cursor's cell is empty **DO**
  create a new piece there (`committed: False`) and make it `pending`.
  (`place_or_pick_up`)
- **WHEN** space is pressed and the cursor's cell already holds a
  *submitted* piece **DO** set that piece's `committed` back to
  `False` and make it `pending` again, instead of replacing it -- this
  is how you go back and re-edit one later. (`place_or_pick_up`)
- **WHEN** c is pressed and `pending` is not `None` **DO** step that
  piece's `color` to the next one in `COLOR_ORDER`, wrapping around.
  Does nothing if nothing is pending. (`cycle_color`)
- **WHEN** enter is pressed and `pending` is not `None` **DO** set
  that piece's `committed` to `True`, set `pending` back to `None`,
  and save `grid` to `grid.json`. This is the only place anything
  stops flashing. (`submit`)
- **WHEN** the main loop ticks **DO** flip `blink_on` every 5 ticks
  (about once a second) -- this one variable is what both the bare
  cursor's blink and every pending piece's flash are driven by.
  (`tick`)

Drawing itself (`render`) just reads all of the above: a committed
piece always shows; a pending piece shows only when `blink_on` is
true; the cursor itself only shows (as `_`) when it's sitting on an
empty, non-pending cell and `blink_on` is true.

## Notes

- The grid's own size is fixed to the terminal's size *at startup*
  (same tradeoff spark2's own engine makes, for the same reason) --
  resizing mid-session won't re-fit it.
- No git repository here on purpose -- this folder is meant to be
  plain, ordinary files a phone's file manager can open directly.
- Not yet confirmed running on the actual device screen -- verified
  here only through a real pty session driving actual keystrokes
  (move, place, color, submit, quit, and a restart that reloaded the
  saved piece back in, steady and not flashing).
