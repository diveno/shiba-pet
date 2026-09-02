#!/usr/bin/env python3
"""
Status line with the dog's state: four rows of bars.

Read-only: applies the time decay so the numbers are right but does NOT save.
The status line is redrawn every turn and rewriting the JSON each time would
mean races between processes and a last_seen that is always fresh - a dog that
is never hungry nor sleepy.

For a few seconds after a `shiba` command it widens and shows the muzzle in
colour to the LEFT of the text. Not to the right: Claude Code's status line
trims the leading whitespace of every line, so the rows made of padding plus
drawing lose their indent and the muzzle breaks into two pieces.

The block is framed: without a border the rows float in the middle of the
terminal with nothing telling them apart from the rest of the output. The frame
also fixes the alignment - every row now starts with a bar instead of a space,
so there is no leading whitespace left for Claude Code to trim.

SHIBA_STATUSLINE=bars (default, 4 rows) | line (1 row).
SHIBA_BORDER=0 drops the frame, SHIBA_COLOR=0 turns colour off.
"""

import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shiba  # noqa: E402

COLOR = os.environ.get("SHIBA_COLOR", "1") != "0"
LAYOUT = os.environ.get("SHIBA_STATUSLINE", "bars")
BORDER = os.environ.get("SHIBA_BORDER", "1") != "0"

# One icon per stat. Two rules, or the two rows of pairs stop lining up.
# They must be real emoji: anything below U+1F300 is a dual-presentation
# character and the terminal is free to draw the thin monochrome glyph
# instead, so U+26A1 carries U+FE0F to pin it to the colour one. And they must
# all be the same width: U+2764 HEAVY BLACK HEART, say, measures one column
# and draws two, which is exactly how a grid goes crooked. What is here is all
# East Asian Wide; icon() pads anyway, so a narrower pick still fits.
ICONS = {"belly": "\U0001f356",          # meat on bone
         "energy": "\u26a1\ufe0f",       # high voltage, forced to emoji
         "mood": "\U0001f60a",           # smiling face with smiling eyes
         "bond": "\U0001f9e1"}           # orange heart, the shiba's own colour
BORDER_RGB = (124, 101, 88)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def paint(text, rgb):
    if not COLOR:
        return text
    return "\x1b[38;2;%d;%d;%dm%s\x1b[0m" % (rgb[0], rgb[1], rgb[2], text)


def bar(v, width=10):
    full = int(round(v / 100.0 * width))
    rgb = (120, 200, 120) if v >= 60 else (225, 190, 90) if v >= 30 else (220, 100, 90)
    return paint("█" * full + "░" * (width - full), rgb)


def icon(key):
    """The icon padded to two columns, so every cell starts at the same place."""
    g = ICONS[key]
    return g + " " * max(0, 2 - dwidth(g))


def stat(key, label, value):
    return "%s %-8s %s %3d" % (icon(key), label, bar(value), value)


def dwidth(s):
    """Columns the row really takes: escapes count zero, emoji count two."""
    w = 0
    for ch in ANSI.sub("", s):
        if unicodedata.combining(ch) or ch in "\ufe0e\ufe0f":
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def boxed(rows):
    """Frame the block on all four sides, padding every row to the widest."""
    if not BORDER:
        return rows
    inner = max(dwidth(r) for r in rows)
    rule = paint("\u2500" * (inner + 2), BORDER_RGB)
    side = paint("\u2502", BORDER_RGB)
    out = [paint("\u256d", BORDER_RGB) + rule + paint("\u256e", BORDER_RGB)]
    for r in rows:
        out.append("%s %s%s %s" % (side, r, " " * (inner - dwidth(r)), side))
    out.append(paint("\u2570", BORDER_RGB) + rule + paint("\u256f", BORDER_RGB))
    return out


def face_lines(emo):
    """The muzzle in half blocks: two pixel rows per text row."""
    g = shiba.mood_grid(emo)
    pal = shiba.sprite()["pal"]
    r0, r1 = shiba.sprite().get("head_rows", [0, 23])
    cols = [i for i in range(len(g[0]))
            if any(g[j][i] != "." for j in range(r0, r1 + 1))]
    crop = [row[cols[0]:cols[-1] + 1] for row in g[r0:r1 + 1]]
    out = []
    for j in range(0, len(crop), 2):
        top = crop[j]
        bot = crop[j + 1] if j + 1 < len(crop) else ["."] * len(top)
        buf = []
        for i in range(len(top)):
            a, b = top[i], bot[i]
            if a == "." and b == ".":
                buf.append("\x1b[0m ")
            elif b == ".":
                buf.append("\x1b[0m\x1b[38;2;%d;%d;%dm▀" % tuple(pal[int(a)]))
            elif a == ".":
                buf.append("\x1b[0m\x1b[38;2;%d;%d;%dm▄" % tuple(pal[int(b)]))
            else:
                buf.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀"
                           % (tuple(pal[int(a)]) + tuple(pal[int(b)])))
        out.append("".join(buf) + "\x1b[0m")
    return out


def showing_face(st):
    if not COLOR or LAYOUT == "line":
        return False
    u = st.get("face_until")
    return bool(u) and shiba.parse(u) > shiba.now()


def main():
    # stdin carries Claude Code's session JSON: it has to be consumed anyway,
    # or whoever writes into it gets a broken pipe.
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except Exception:
            pass

    try:
        st = shiba.load()
        st, _ = shiba.decay(st)
        t = shiba.T()
    except Exception:
        return  # better a status line without the dog than a broken one

    emo = shiba.emotion(st)
    lvl = shiba.level_of(st["xp"])
    nxt = shiba.LEVELS[lvl + 1] if lvl + 1 < len(shiba.LEVELS) else None
    age = (shiba.now() - shiba.parse(st["born"])).days
    lab = t["labels"]

    if LAYOUT == "line":
        el, mu, er = shiba.FACES[emo]
        parts = [
            paint("(%s%s%s)" % (el, mu, er), (239, 183, 116)),
            paint(st["name"], (250, 251, 248)),
            paint("%s%d" % (lab["level"], lvl), (167, 130, 111)),
            paint(t["moods"][emo], (214, 154, 92)),
            icon("belly") + bar(100 - st["hunger"], 5),
            icon("energy") + bar(st["energy"], 5),
            icon("mood") + bar(st["mood"], 5),
        ]
        if BORDER:  # sides only: a full frame would triple a one-row layout
            edge = paint("\u2502", BORDER_RGB)
            parts = [edge] + parts + [edge]
        sys.stdout.write(" ".join(parts) + "\n")
        return

    info = [
        "%s  %s  %s" % (paint(st["name"], (250, 251, 248)),
                        paint("%s%d %s" % (lab["level"], lvl, t["levels"][lvl]),
                              (167, 130, 111)),
                        paint(t["moods"][emo], (214, 154, 92))),
        "%s    %s" % (stat("belly", lab["belly"], 100 - st["hunger"]),
                      stat("energy", lab["energy"], st["energy"])),
        "%s    %s" % (stat("mood", lab["mood"], st["mood"]),
                      stat("bond", lab["bond"], st["bond"])),
        paint("%s %d%s   %s %dg   %d %s"
              % (lab["xp"], st["xp"], "/%d" % nxt if nxt else "",
                 lab["streak"], st.get("streak", 1), age, lab["together"]),
              (137, 110, 97)),
    ]

    if not showing_face(st):
        sys.stdout.write("\n".join(boxed(info)) + "\n")
        return

    # A state written by an older version may carry a mood name this build
    # does not know: fall back instead of drawing nothing.
    saved = st.get("face_emo")
    if saved not in shiba.sprite()["moods"]:
        saved = emo
    rows = []
    for k, row in enumerate(face_lines(saved)):
        txt = info[k] if k < len(info) else ""
        rows.append(row + ("  " + txt if txt else ""))
    sys.stdout.write("\n".join(boxed(rows)) + "\n")


if __name__ == "__main__":
    main()
