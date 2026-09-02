#!/usr/bin/env python3
"""
Status line with the dog's state: four rows of bars.

Read-only: applies the time decay so the numbers are right but does NOT save.
The status line is redrawn every turn and rewriting the JSON each time would
mean races between processes and a last_seen that is always fresh - a dog that
is never hungry nor sleepy.

For a few seconds after a `mochi` command it widens and shows the muzzle in
colour to the LEFT of the text. Not to the right: Claude Code's status line
trims the leading whitespace of every line, so the rows made of padding plus
drawing lose their indent and the muzzle breaks into two pieces.

SHIBA_STATUSLINE=bars (default, 4 rows) | line (1 row).
SHIBA_COLOR=0 turns colour off.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shiba  # noqa: E402

COLOR = os.environ.get("SHIBA_COLOR", "1") != "0"
LAYOUT = os.environ.get("SHIBA_STATUSLINE", "bars")


def paint(text, rgb):
    if not COLOR:
        return text
    return "\x1b[38;2;%d;%d;%dm%s\x1b[0m" % (rgb[0], rgb[1], rgb[2], text)


def bar(v, width=10):
    full = int(round(v / 100.0 * width))
    rgb = (120, 200, 120) if v >= 60 else (225, 190, 90) if v >= 30 else (220, 100, 90)
    return paint("█" * full + "░" * (width - full), rgb)


def stat(icon, label, value):
    return "%s %-8s %s %3d" % (icon, label, bar(value), value)


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
        sys.stdout.write(" ".join([
            paint("(%s%s%s)" % (el, mu, er), (239, 183, 116)),
            paint(st["name"], (250, 251, 248)),
            paint("%s%d" % (lab["level"], lvl), (167, 130, 111)),
            paint(t["moods"][emo], (214, 154, 92)),
            "\U0001f356" + bar(100 - st["hunger"], 5),
            "⚡" + bar(st["energy"], 5),
            "♥" + bar(st["mood"], 5),
        ]) + "\n")
        return

    info = [
        "%s  %s  %s" % (paint(st["name"], (250, 251, 248)),
                        paint("%s%d %s" % (lab["level"], lvl, t["levels"][lvl]),
                              (167, 130, 111)),
                        paint(t["moods"][emo], (214, 154, 92))),
        "%s    %s" % (stat("\U0001f356", lab["belly"], 100 - st["hunger"]),
                      stat("⚡", lab["energy"], st["energy"])),
        "%s    %s" % (stat("♥", lab["mood"], st["mood"]),
                      stat("♡", lab["bond"], st["bond"])),
        paint("%s %d%s   %s %dg   %d %s"
              % (lab["xp"], st["xp"], "/%d" % nxt if nxt else "",
                 lab["streak"], st.get("streak", 1), age, lab["together"]),
              (137, 110, 97)),
    ]

    if not showing_face(st):
        sys.stdout.write("\n".join(info) + "\n")
        return

    # A state written by an older version may carry a mood name this build
    # does not know: fall back instead of drawing nothing.
    saved = st.get("face_emo")
    if saved not in shiba.sprite()["moods"]:
        saved = emo
    for k, row in enumerate(face_lines(saved)):
        txt = info[k] if k < len(info) else ""
        sys.stdout.write(row + ("  " + txt if txt else "") + "\n")


if __name__ == "__main__":
    main()
