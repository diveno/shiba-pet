#!/usr/bin/env python3
"""
shiba.py - state machine and renderer for the CLI shiba inu.

State lives in ~/.claude/shiba/state.json (override with $SHIBA_STATE).
User-facing strings live in ../i18n/<lang>.json, picked by the `lang` field in
the state or by $SHIBA_LANG (default: en). Mood keys and event names stay in
English inside the code: they address sprite patches and asset files, they are
not text to translate.

Never prints ANSI colour when stdout is not a terminal: the output is meant to
be pasted into a code block, where escapes would be noise.

Usage:
  shiba.py [status] | feed [snack] | pet | play | walk | nap [minutes] | wake
           trick [name] | react <event> | tip | name <n> | style <s> | help
  flags: --oneline --plain --art --full --png --open --color --no-color --force
"""

import json
import os
import random
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
STATE = os.environ.get("SHIBA_STATE",
                       os.path.expanduser("~/.claude/shiba/state.json"))
SPRITE_PATH = os.path.join(ROOT, "assets", "sprite.json")
FACES_DIR = os.path.join(ROOT, "assets", "faces")

# Cumulative XP thresholds; the index is the level.
LEVELS = [0, 25, 70, 140, 250, 420, 650, 1000]

# Palette index -> block character, for the colourless fallback. Three greys
# plus black: the minimum that keeps muzzle, eyes and bib readable.
BLOCKS = {"0": "█", "1": "▓", "2": "▓", "3": "▓",
          "4": "▒", "5": "▒", "6": "░", "7": "░",
          "8": "▒", "9": "▓"}

# Speech-bubble text set beside the sprite, per mood.
SIDE = {
    "happy": ["", "~", "", ""],
    "calm": ["", "", "", ""],
    "excited": ["!!", "", "<3", ""],
    "hungry": ["", "", "...?", ""],
    "sleepy": ["~z", "", "", ""],
    "asleep": ["z", "Z", "z", ""],
    "sad": ["", "...", "", ""],
    "suspicious": ["?", "", "", ""],
}

# Text faces for the one-line form: eyes, muzzle, eyes.
FACES = {
    "happy": ("^", "w", "^"), "calm": ("o", "Y", "o"),
    "excited": ("*", "D", "*"), "hungry": ("o", "u", "o"),
    "sleepy": ("-", "u", "-"), "asleep": ("=", "u", "="),
    "sad": (";", "n", ";"), "suspicious": ("o", "Y", "-"),
}

# event -> (mood, xp). The phrases come from the locale.
REACTIONS = {
    "commit": ("happy", 2), "deploy": ("excited", 4),
    "tests-pass": ("happy", 3), "tests-fail": ("suspicious", 1),
    "error": ("suspicious", 1), "fixed": ("excited", 3),
    "apply": ("suspicious", 2), "long-task": ("sleepy", 1),
    "greet": (None, 1), "bye": (None, 0),
}

ALIASES = {
    "treat": ["feed", "snack"], "snack": ["feed", "snack"],
    "tricks": ["trick"], "photo": ["status", "--png"], "png": ["status", "--png"],
    "sleep": ["nap"], "rename": ["name"], "-h": ["help"], "--help": ["help"],
}

_sprite = None
_t = None


def sprite():
    global _sprite
    if _sprite is None:
        with open(SPRITE_PATH) as f:
            _sprite = json.load(f)
    return _sprite


def T():
    """Locale, loaded once. Falls back to English if the language is unknown."""
    global _t
    if _t is None:
        lang = os.environ.get("SHIBA_LANG")
        if not lang and os.path.exists(STATE):
            try:
                with open(STATE) as f:
                    lang = json.load(f).get("lang")
            except Exception:
                lang = None
        path = os.path.join(ROOT, "i18n", "%s.json" % (lang or "en"))
        if not os.path.exists(path):
            path = os.path.join(ROOT, "i18n", "en.json")
        with open(path) as f:
            _t = json.load(f)
    return _t


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def parse(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return now()


def session_id():
    """The Claude Code session asking, empty in a plain terminal.

    The muzzle is lit for whoever ran the command: with four sessions open,
    the other three have no reason to interrupt themselves with a dog.
    """
    return os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(round(v))))


def one(value):
    """Locale entries may be a single string or a pool to pick from."""
    return random.choice(value) if isinstance(value, list) else value


def fresh(name="Mochi", lang=None):
    t = iso(now())
    return {
        "name": name,
        "lang": lang or os.environ.get("SHIBA_LANG", "en"),
        "born": t,
        "last_seen": t,
        "last_day": now().date().isoformat(),
        "hunger": 25,      # 0 = full, 100 = starving
        "energy": 80,
        "mood": 75,
        "bond": 10,
        "xp": 0,
        "tricks": ["sit"],
        "streak": 1,
        "asleep_until": None,
        "face_until": None,
        "face_emo": None,
        "face_session": None,
        "last_tip": None,
        "style": "pixel",
        "companion": True,
        "log": [],
    }


def load():
    if not os.path.exists(STATE):
        st = fresh()
        save(st)
        st["_new"] = True
        return st
    with open(STATE) as f:
        st = json.load(f)
    base = fresh(st.get("name", "Mochi"), st.get("lang"))
    base.update(st)
    return base


def save(st):
    d = os.path.dirname(STATE)
    if d:
        os.makedirs(d, exist_ok=True)
    st.pop("_new", None)
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)


def level_of(xp):
    lvl = 0
    for i, need in enumerate(LEVELS):
        if xp >= need:
            lvl = i
    return lvl


def asleep(st):
    u = st.get("asleep_until")
    return bool(u) and parse(u) > now()


def decay(st):
    """Apply elapsed time. Read-only callers rely on this not saving."""
    elapsed = (now() - parse(st["last_seen"])).total_seconds() / 3600.0
    if elapsed <= 0:
        return st, []
    h = min(elapsed, 72)  # past three days there is nothing left to accumulate
    st["hunger"] = clamp(st["hunger"] + 4.0 * h)

    # Share of the elapsed hours spent asleep: a nap has to rest more than
    # being awake, otherwise `nap` is only a change of face. Computed as the
    # overlap between [last_seen, now] and the sleep window, so it also works
    # when the nap expired in the meantime or the command lands mid-sleep.
    slept = 0.0
    until = st.get("asleep_until")
    if until:
        end = min(now(), parse(until))
        if end > parse(st["last_seen"]):
            slept = min((end - parse(st["last_seen"])).total_seconds() / 3600.0, h)
    st["energy"] = clamp(st["energy"] + 7.0 * (h - slept) + 21.0 * slept)

    malus = 1.2
    if st["hunger"] > 70:
        malus += 1.8
    if elapsed > 24:
        malus += 1.0  # loneliness: past a day the mood drops faster
    st["mood"] = clamp(st["mood"] - malus * h)

    notes = []
    today = now().date()
    last = st.get("last_day")
    if last != today.isoformat():
        try:
            prev = datetime.fromisoformat(last).date()
        except (TypeError, ValueError):
            prev = None
        if prev == today - timedelta(days=1):
            st["streak"] = st.get("streak", 0) + 1
            notes.append(T()["notes"]["streak"] % st["streak"])
        else:
            if st.get("streak", 0) > 1:
                notes.append(T()["notes"]["streak_lost"] % st["streak"])
            st["streak"] = 1
        st["last_day"] = today.isoformat()
    st["last_seen"] = iso(now())
    return st, notes


def emotion(st):
    if asleep(st):
        return "asleep"
    if st["hunger"] >= 78:
        return "hungry"
    if st["energy"] <= 18:
        return "sleepy"
    if st["mood"] <= 28:
        return "sad"
    if st["mood"] >= 85 and st["energy"] >= 55:
        return "excited"
    if st["mood"] >= 60:
        return "happy"
    return "calm"


def log(st, what):
    st.setdefault("log", []).append({"t": iso(now()), "what": what})
    st["log"] = st["log"][-12:]


def award(st, xp):
    before = level_of(st["xp"])
    st["xp"] += xp
    after = level_of(st["xp"])
    if after <= before:
        return None
    unlocked = T()["tricks"].get(str(after), [])
    for tr in unlocked:
        if tr not in st["tricks"]:
            st["tricks"].append(tr)
    msg = T()["notes"]["levelup"] % (after, T()["levels"][after])
    if unlocked:
        msg += " " + T()["notes"]["trick_new"] % ", ".join(unlocked)
    return msg


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def mood_grid(emo):
    """The sprite grid with the expression patch for this mood applied."""
    sp = sprite()
    g = [list(r) for r in sp["rows"]]
    for j, i, c in sp["moods"].get(emo, []):
        g[j][i] = c
    return g


def art_pixel(emo, color, head_only=False):
    """Pixel art: coloured half blocks on a terminal, grey blocks otherwise.

    The grey version needs one character per pixel: half blocks in black and
    white lose the tone and the muzzle turns into mush.
    """
    g = mood_grid(emo)
    pal = sprite()["pal"]
    if head_only:
        r0, r1 = sprite().get("head_rows", [0, 23])
        cols = [i for i in range(len(g[0]))
                if any(g[j][i] != "." for j in range(r0, r1 + 1))]
        g = [row[cols[0]:cols[-1] + 1] for row in g[r0:r1 + 1]]

    lines = []
    if color:
        for j in range(0, len(g), 2):
            top = g[j]
            bot = g[j + 1] if j + 1 < len(g) else ["."] * len(top)
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
            lines.append("".join(buf) + "\x1b[0m")
        slots = [1, 3, 5, 7]
    else:
        for row in g:
            lines.append("".join(" " if c == "." else BLOCKS[c] for c in row).rstrip())
        slots = [2, 6, 10, 14]

    width = len(g[0]) + 2
    for k, text in enumerate(SIDE.get(emo, [])):
        if text and k < len(slots) and slots[k] < len(lines):
            n = slots[k]
            pad = "" if color else " " * max(1, width - len(lines[n]))
            lines[n] = lines[n] + (pad or "  ") + text
    return lines


def art_ascii(emo):
    el, mu, er = FACES[emo]
    tail = {"happy": "||~", "excited": "||~~", "sad": "|"}.get(emo, "||")
    lines = ["      /^ ^\\", "     / %s %s \\" % (el, er),
             "     V\\ %s /V" % mu, "      / - \\", "     /    |",
             "    V__) " + tail]
    for k, text in enumerate(SIDE.get(emo, [])):
        if text and k < len(lines):
            lines[k] += "   " + text
    return lines


def art_doge(emo):
    el, mu, er = FACES[emo]
    eye = {"^": "^^^", "o": "###", "*": "***", "-": "---", "=": "===", ";": ";;;"}
    mouth = {"w": "\\___/", "Y": " \\_/ ", "D": "\\ o /", "u": " ___ ", "n": " /-\\ "}
    lines = [
        "    .-~~~~~~~~~~~-.",
        "   /  ..       ..  \\",
        "  |   %s     %s   |" % (eye.get(el, "###"), eye.get(er, "###")),
        "  |       ___       |",
        "   \\     %s     /" % mouth.get(mu, " \\_/ "),
        "    '-._________.-'",
        "      /         \\",
        "     (__)     (__)",
    ]
    for k, text in enumerate(SIDE.get(emo, [])):
        if text and k < len(lines):
            lines[k] += "   " + text
    return lines


def art(st, emo, color=False, head_only=False):
    style = st.get("style", "pixel")
    if style == "doge":
        return art_doge(emo)
    if style == "ascii":
        return art_ascii(emo)
    return art_pixel(emo, color, head_only)


def bar(v, width=10):
    full = int(round(v / 100.0 * width))
    return "#" * full + "." * (width - full)


def face_png(emo):
    p = os.path.normpath(os.path.join(FACES_DIR, "%s.png" % emo))
    return p if os.path.exists(p) else None


def oneline(st, emo=None, text=None):
    emo = emo or emotion(st)
    el, mu, er = FACES[emo]
    return "(%s %s %s) %s: %s" % (el, mu, er, st["name"],
                                  text or one(T()["lines"][emo]))


def compact(st, emo=None, text=None, deltas=None, notes=None):
    """Two lines: the phrase and a strip of stats.

    This is the default after an action. The whole sprite is 44 terminal rows
    and the dog is visible in the status line anyway: reprinting it on every
    command is just lost scroll.
    """
    deltas = deltas or {}
    emo = emo or emotion(st)
    lvl = level_of(st["xp"])
    nxt = LEVELS[lvl + 1] if lvl + 1 < len(LEVELS) else None
    lab = T()["labels"]

    def field(label, value, delta):
        out = "%s %d" % (label, value)
        if delta:
            out += " (%+d)" % delta
        return out

    bits = [
        "%s%d %s" % (lab["level"], lvl, T()["levels"][lvl]),
        field(lab["belly"], 100 - st["hunger"], -deltas.get("hunger", 0)),
        field(lab["energy"], st["energy"], deltas.get("energy", 0)),
        field(lab["mood"], st["mood"], deltas.get("mood", 0)),
        field(lab["bond"], st["bond"], deltas.get("bond", 0)),
    ]
    xp = "%s %d%s" % (lab["xp"], st["xp"], "/%d" % nxt if nxt else "")
    if deltas.get("xp"):
        xp += " (%+d)" % deltas["xp"]
    bits.append(xp)

    lines = [oneline(st, emo, text), "  ".join(bits)]
    lines += ["* " + n for n in (notes or [])]
    return "\n".join(lines)


def render(st, emo=None, notes=None, extra_line=None, color=False):
    """Full card: sprite, bars, level, phrase. Only on --art."""
    emo = emo or emotion(st)
    lvl = level_of(st["xp"])
    lab = T()["labels"]
    age = (now() - parse(st["born"])).days
    out = list(art(st, emo, color))
    out.append("")
    out.append("%s  -  %s (%s%d)  -  %s"
               % (st["name"], T()["levels"][lvl], lab["level"], lvl,
                  T()["moods"][emo]))
    out.append("  %-8s [%s] %3d" % (lab["belly"], bar(100 - st["hunger"]),
                                    100 - st["hunger"]))
    out.append("  %-8s [%s] %3d" % (lab["energy"], bar(st["energy"]), st["energy"]))
    out.append("  %-8s [%s] %3d" % (lab["mood"], bar(st["mood"]), st["mood"]))
    out.append("  %-8s [%s] %3d" % (lab["bond"], bar(st["bond"]), st["bond"]))
    nxt = LEVELS[lvl + 1] if lvl + 1 < len(LEVELS) else None
    out.append("  %s %d%s  -  %d %s  -  %s %d"
               % (lab["xp"], st["xp"], "/%d" % nxt if nxt else "", age,
                  lab["together"], lab["streak"], st.get("streak", 1)))
    out.append("")
    out.append('"%s"' % (extra_line or one(T()["lines"][emo])))
    for n in notes or []:
        out.append("* " + n)
    return "\n".join(out)


def write_png(path, emo, scale=12, bg=(255, 255, 255)):
    """The sprite in true colour as a PNG.

    Needed because neither the `!` command panel nor the chat markdown
    interpret ANSI escapes - they print them literally. An image is visible
    everywhere. Written by hand (zlib + three chunks) to avoid Pillow.
    """
    g = mood_grid(emo)
    pal = sprite()["pal"]
    h, w = len(g), len(g[0])
    raw = b""
    for row in g:
        line = b""
        for c in row:
            line += bytes(bg if c == "." else tuple(pal[int(c)])) * scale
        raw += (b"\x00" + line) * scale

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    blob = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale,
                                         8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)
    return path


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def pick_tip():
    """A reminder, with a few rules that look at the real state of the repo.

    The contextual rules come before the generic pool: a reminder about what
    you actually have in your hands gets read, a generic one gets skipped.
    """
    ctx = T()["tips_ctx"]
    try:
        import subprocess

        def git(*args):
            r = subprocess.run(("git",) + args, capture_output=True,
                               text=True, timeout=3)
            return r.stdout.strip() if r.returncode == 0 else None

        dirty = git("status", "--porcelain")
        if dirty is not None:
            files = [l for l in dirty.splitlines() if l.strip()]
            branch = git("rev-parse", "--abbrev-ref", "HEAD")
            if files and branch in ("main", "master"):
                return ctx["on_main"] % (branch, len(files))
            if len(files) >= 12:
                return ctx["many_files"] % len(files)
            if files and random.random() < 0.4:
                return ctx["pending"] % len(files)
    except Exception:
        pass
    return random.choice(T()["tips"])


def act(st, argv):
    cmd = argv[0] if argv else "status"
    args = argv[1:]
    A = T()["acts"]
    notes, line, emo = [], None, None

    if cmd == "status":
        pass

    elif cmd == "feed":
        kind = (args[0] if args else "meal").lower()
        if asleep(st):
            line = A["feed.asleep"]
        elif kind == "snack":
            if st["hunger"] < 8:
                st["mood"] = clamp(st["mood"] - 3)
                line = A["feed.full"]
            else:
                st["hunger"] = clamp(st["hunger"] - 12)
                st["mood"] = clamp(st["mood"] + 6)
                st["bond"] = clamp(st["bond"] + 2)
                emo, line = "happy", A["feed.treat"]
                notes.append(award(st, 1))
        else:
            if st["hunger"] < 15:
                st["mood"] = clamp(st["mood"] - 2)
                line = A["feed.sniff"]
            else:
                st["hunger"] = clamp(st["hunger"] - 45)
                st["mood"] = clamp(st["mood"] + 12)
                st["energy"] = clamp(st["energy"] + 8)
                st["bond"] = clamp(st["bond"] + 3)
                emo, line = "happy", A["feed.meal"]
                notes.append(award(st, 3))
        log(st, "feed:%s" % kind)

    elif cmd == "pet":
        if asleep(st):
            st["mood"] = clamp(st["mood"] + 3)
            line = A["pet.asleep"]
        else:
            st["mood"] = clamp(st["mood"] + 9)
            st["bond"] = clamp(st["bond"] + 5)
            emo, line = "happy", one(A["pet"])
            notes.append(award(st, 2))
        log(st, "pet")

    elif cmd == "play":
        if asleep(st):
            line = A["play.asleep"]
        elif st["energy"] < 20:
            st["mood"] = clamp(st["mood"] - 2)
            emo, line = "sleepy", A["play.tired"]
        else:
            st["energy"] = clamp(st["energy"] - 18)
            st["hunger"] = clamp(st["hunger"] + 10)
            st["mood"] = clamp(st["mood"] + 15)
            st["bond"] = clamp(st["bond"] + 4)
            emo, line = "excited", one(A["play"])
            notes.append(award(st, 5))
        log(st, "play")

    elif cmd == "walk":
        if st["energy"] < 30:
            emo, line = "sleepy", A["walk.tired"]
        else:
            st["energy"] = clamp(st["energy"] - 30)
            st["hunger"] = clamp(st["hunger"] + 18)
            st["mood"] = clamp(st["mood"] + 22)
            st["bond"] = clamp(st["bond"] + 7)
            emo, line = "excited", A["walk"]
            notes.append(award(st, 8))
        log(st, "walk")

    elif cmd == "nap":
        mins = 20
        if args:
            try:
                mins = max(5, min(240, int(args[0])))
            except ValueError:
                pass
        st["asleep_until"] = iso(now() + timedelta(minutes=mins))
        emo, line = "asleep", A["nap"] % mins
        log(st, "nap:%dm" % mins)

    elif cmd == "wake":
        if asleep(st):
            st["asleep_until"] = None
            st["mood"] = clamp(st["mood"] - 4)
            emo, line = "sleepy", A["wake"]
        else:
            line = A["wake.awake"]
        log(st, "wake")

    elif cmd == "trick":
        want = " ".join(args).lower().strip()
        known = st["tricks"]
        if not want:
            line = A["trick.list"] % (", ".join(known) or "-")
        elif want in known:
            if st["bond"] >= 25 or random.random() < 0.6:
                st["mood"] = clamp(st["mood"] + 7)
                st["bond"] = clamp(st["bond"] + 3)
                emo, line = "happy", A["trick.done"] % want
                notes.append(award(st, 4))
            else:
                emo, line = "suspicious", A["trick.refused"] % want
        else:
            line = A["trick.unknown"] % (want, ", ".join(known))
        log(st, "trick:%s" % want)

    elif cmd == "react":
        ev = (args[0] if args else "greet").lower()
        emo, xp = REACTIONS.get(ev, REACTIONS["greet"])
        line = one(T()["reactions"].get(ev, T()["reactions"]["greet"]))
        if xp:
            notes.append(award(st, xp))
            st["mood"] = clamp(st["mood"] + 2)
        log(st, "react:%s" % ev)

    elif cmd == "tip":
        # Cadence: one reminder every TIP_COOLDOWN at most, otherwise it turns
        # into noise and stops being read.
        secs = int(os.environ.get("SHIBA_TIP_COOLDOWN", "1800"))
        last = st.get("last_tip")
        forced = "--force" in sys.argv or not last
        if not forced and (now() - parse(last)).total_seconds() < secs:
            return None
        st["last_tip"] = iso(now())
        emo = "suspicious" if random.random() < 0.3 else "calm"
        line = pick_tip()
        log(st, "tip")

    elif cmd == "name":
        if args:
            st["name"] = " ".join(args)[:24]
            st["bond"] = clamp(st["bond"] + 2)
            line = A["name.set"] % st["name"]
        else:
            line = A["name.get"] % st["name"]

    elif cmd == "style":
        if args and args[0] in ("pixel", "ascii", "doge"):
            st["style"] = args[0]
            line = A["style.set"] % args[0]
        else:
            line = A["style.get"] % st.get("style")

    elif cmd == "companion":
        if args and args[0] in ("on", "off"):
            st["companion"] = args[0] == "on"
        line = A["companion"] % ("on" if st["companion"] else "off")

    elif cmd == "lang":
        if args and os.path.exists(os.path.join(ROOT, "i18n", "%s.json" % args[0])):
            st["lang"] = args[0]
        line = "lang: %s" % st.get("lang", "en")

    elif cmd == "stats":
        save(st)
        print(json.dumps({k: v for k, v in st.items() if k != "log"},
                         indent=2, ensure_ascii=False))
        return None

    elif cmd == "reset":
        name = " ".join(args) or "Mochi"
        st = fresh(name, st.get("lang"))
        save(st)
        print(compact(st, emo="excited", text=A["reset"] % name))
        return None

    elif cmd == "help":
        print(T()["help"])
        return None

    else:
        print(A["unknown"] % cmd + "\n")
        print(T()["help"])
        return None

    return st, emo, [n for n in notes if n], line


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if argv and argv[0] in ALIASES:
        expanded = ALIASES[argv[0]] + argv[1:]
        flags |= {a for a in expanded if a.startswith("--")}
        argv = [a for a in expanded if not a.startswith("--")]

    st = load()
    was_new = st.pop("_new", False)
    st, dnotes = decay(st)
    tracked = ("hunger", "energy", "mood", "bond", "xp")
    before = {k: st[k] for k in tracked}

    res = act(st, argv)
    if res is None:
        return
    st, emo, notes, line = res
    notes = dnotes + notes
    deltas = {k: st[k] - before[k] for k in tracked}

    if was_new:
        emo = emo or "excited"
        line = line or T()["acts"]["new"] % st["name"]

    # A command lights the muzzle up in the status line for a few seconds: that
    # is the only surface of Claude Code that renders colour (in the message
    # flow ANSI escapes come out literal and images stay clickable links).
    secs = int(os.environ.get("SHIBA_FACE_SECONDS", "10"))
    if secs > 0:
        st["face_until"] = iso(now() + timedelta(seconds=secs))
        st["face_emo"] = emo or emotion(st)
        st["face_session"] = session_id()

    save(st)

    # Colour only when writing to a real terminal: down a pipe (or inside a
    # code block) the ANSI escapes would be unreadable noise.
    color = sys.stdout.isatty() or os.environ.get("SHIBA_COLOR") == "1"
    if "--color" in flags:
        color = True
    if "--no-color" in flags:
        color = False

    if "--png" in flags or "--open" in flags:
        emo = emo or emotion(st)
        out = os.path.expanduser("~/.claude/shiba/%s.png" % st["name"].lower())
        write_png(out, emo)
        print(oneline(st, emo, line))
        print(out)
        if "--open" in flags and sys.platform == "darwin":
            os.system("open %s" % out.replace(" ", "\\ "))
        return

    if "--oneline" in flags:
        print(oneline(st, emo, line))
        return

    if "--art" in flags or "--full" in flags:
        print(render(st, emo=emo, notes=notes, extra_line=line, color=color))
        if "--full" in flags and st.get("log"):
            print("\n" + T()["labels"]["activity"])
            for e in reversed(st["log"][-6:]):
                print("  %s  %s" % (e["t"][:16].replace("T", " "), e["what"]))
        return

    print(compact(st, emo, line, deltas, notes))
    if "--plain" not in flags:
        face = face_png(emo or emotion(st))
        if face:
            print("FACE=%s" % face)


if __name__ == "__main__":
    main()
