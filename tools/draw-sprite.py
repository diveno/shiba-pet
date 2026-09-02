#!/usr/bin/env python3
"""
Disegna lo sprite originale dello shiba (30x44) e scrive la griglia.

Procedurale invece che a mano: le forme sono ellissi e triangoli con parametri
in testa, cosi' si itera sulle proporzioni senza ricontare 1320 celle.

Due tipi di contorno, e servono entrambi:
- la **sagoma esterna** e' derivata a fine disegno (ogni pixel pieno adiacente
  al vuoto diventa nero), cosi' resta chiusa qualunque forma si cambi;
- le **forme interne** (muso, zampe, coda) hanno contorno esplicito via blob(),
  perche' non toccano il vuoto e la derivazione non le vedrebbe.

L'ordine di disegno e' dal fondo al davanti: coda, corpo, pettorina, zampe,
orecchie, testa, muso, faccia.
"""

import json
import struct
import sys
import zlib

W, H = 30, 44
PAL = [(24, 20, 18), (120, 68, 46), (176, 98, 53), (190, 130, 74),
       (214, 154, 92), (239, 183, 116), (232, 220, 188), (250, 251, 248),
       (167, 130, 111), (150, 58, 45)]
OUT, DARK, RUST, MID, ORNG_D, ORNG, CREAM, WHITE, GREY, RED = range(10)

g = [[None] * W for _ in range(H)]


def ell(cx, cy, rx, ry, color):
    for y in range(H):
        for x in range(W):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                g[y][x] = color


def blob(cx, cy, rx, ry, fill):
    ell(cx, cy, rx, ry, OUT)
    ell(cx, cy, rx - 1.0, ry - 1.0, fill)


def tri(pts, color):
    (x0, y0), (x1, y1), (x2, y2) = pts

    def side(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    for y in range(H):
        for x in range(W):
            d = (side(x0, y0, x1, y1, x, y), side(x1, y1, x2, y2, x, y),
                 side(x2, y2, x0, y0, x, y))
            if all(v >= 0 for v in d) or all(v <= 0 for v in d):
                g[y][x] = color


def rect(x0, y0, x1, y1, color):
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            g[y][x] = color


def px(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        g[y][x] = c


# ---- coda arrotolata, dietro a tutto -----------------------------------
blob(25.0, 27.0, 4.6, 5.2, ORNG)
ell(25.0, 27.0, 1.7, 2.0, MID)

# ---- collo: senza questo testa e corpo restano due sagome staccate -----
rect(9, 17, 20, 26, ORNG)

# ---- corpo seduto ------------------------------------------------------
ell(14.5, 34.0, 10.5, 10.0, ORNG)
rect(5, 40, 24, 43, ORNG)

# ---- pettorina a V -----------------------------------------------------
tri([(9, 25), (20, 25), (14.5, 38)], WHITE)

# ---- zampe anteriori ---------------------------------------------------
for cx in (9.5, 19.5):
    blob(cx, 38.5, 3.6, 5.5, WHITE)
    blob(cx, 42.0, 4.0, 2.6, WHITE)

# ---- orecchie ----------------------------------------------------------
tri([(3, 14), (7, 1), (13, 10)], ORNG)
tri([(26, 14), (22, 1), (16, 10)], ORNG)
tri([(6, 11), (7.5, 5), (11, 10)], RUST)
tri([(23, 11), (21.5, 5), (18, 10)], RUST)

# ---- testa -------------------------------------------------------------
ell(14.5, 12.0, 9.5, 8.0, ORNG)
ell(14.5, 8.0, 7.5, 3.5, ORNG_D)
ell(14.5, 17.0, 7.6, 4.4, WHITE)              # maschera: muso e guance insieme
ell(14.5, 15.0, 3.0, 1.6, CREAM)              # ombra sotto il tartufo

# ---- sagoma esterna ----------------------------------------------------
filled = [[g[y][x] is not None for x in range(W)] for y in range(H)]
for y in range(H):
    for x in range(W):
        if not filled[y][x]:
            continue
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = y + dy, x + dx
            if not (0 <= a < H and 0 <= b < W) or not filled[a][b]:
                g[y][x] = OUT
                break

# ---- faccia ------------------------------------------------------------
for ex in (9, 18):                             # occhi 3x2 con riflesso
    for dx in range(3):
        px(ex + dx, 11, OUT)
        px(ex + dx, 12, OUT)
    px(ex + 2, 11, WHITE)

for dx in range(-2, 3):                        # tartufo
    px(14 + dx, 15, OUT)
for dx in range(-1, 2):
    px(14 + dx, 16, OUT)
px(11, 17, OUT); px(12, 17, OUT); px(13, 17, OUT)      # bocca
px(15, 17, OUT); px(16, 17, OUT); px(17, 17, OUT)
px(13, 18, OUT); px(14, 18, RED); px(15, 18, OUT)
px(14, 19, RED)

# ---- pixel isolati: le punte delle orecchie lasciavano puntini staccati
for y in range(H):
    for x in range(W):
        if g[y][x] is None:
            continue
        if not any(0 <= y + dy < H and 0 <= x + dx < W and g[y + dy][x + dx] is not None
                   for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            g[y][x] = None

# ---- collare: separa la testa dal corpo, non e' solo decorazione -------
for x in range(4, 26):
    for y, c in ((21, DARK), (22, GREY)):
        if g[y][x] is not None and g[y][x] != OUT:
            g[y][x] = c

rows = ["".join("." if c is None else str(c) for c in r) for r in g]
json.dump(rows, open("/tmp/shiba-draft.json", "w"))


def png(path, rows, scale=10):
    raw = b""
    for r in rows:
        line = b""
        for c in r:
            line += (b"\xff\xff\xff" if c == "." else bytes(PAL[int(c)])) * scale
        raw += (b"\x00" + line) * scale

    def ch(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + ch(b"IHDR", struct.pack(">IIBBBBB", W * scale, H * scale, 8, 2, 0, 0, 0))
        + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))


png(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shiba-draft.png", rows)

# ---------------------------------------------------------------------------
# Espressioni: patch (riga, colonna, indice palette) applicate sulla griglia.
# Occhi 3x2 a righe 11-12, colonne 9-11 e 18-20. Bocca a riga 17, lingua 18-19.
# ---------------------------------------------------------------------------
EYE_L, EYE_R = 9, 18
FUR = str(ORNG)


def shut(ex):
    """Occhio chiuso: pelo dove c'era il nero, una riga scura come palpebra."""
    return ([(11, ex + d, FUR) for d in range(3)]
            + [(12, ex + d, str(OUT)) for d in range(3)])


def squint(ex):
    """Occhio a fessura: il nero sale al centro, gli angoli restano in basso."""
    return [(11, ex, FUR), (11, ex + 1, str(OUT)), (11, ex + 2, FUR),
            (12, ex, str(OUT)), (12, ex + 1, FUR), (12, ex + 2, str(OUT))]


BROWS = [(10, EYE_L + d, str(DARK)) for d in range(3)] + \
        [(10, EYE_R + d, str(DARK)) for d in range(3)]
TONGUE = [(19, 13, str(RED)), (19, 14, str(RED)), (19, 15, str(RED)),
          (20, 14, str(RED))]
MOUTH_SHUT = [(18, 14, str(OUT)), (19, 14, str(WHITE))]

MOODS = {
    "calm": [],
    "happy": squint(EYE_L) + squint(EYE_R) + TONGUE,
    "excited": TONGUE + [(20, 13, str(RED)), (20, 15, str(RED)),
                         (21, 14, str(RED))],
    "hungry": TONGUE,
    "sleepy": shut(EYE_L) + shut(EYE_R),
    "asleep": shut(EYE_L) + shut(EYE_R) + MOUTH_SHUT,
    "sad": shut(EYE_L) + shut(EYE_R) + BROWS + MOUTH_SHUT,
    "suspicious": shut(EYE_R) + BROWS,
}

if len(sys.argv) > 2 and sys.argv[2] == "--emit":
    out = {
        "_source": "sprite originale, generato da tools/draw-sprite.py",
        "w": W, "h": H, "pal": PAL, "rows": rows,
        "head_rows": [0, 21],   # sotto la 21 comincia la coda: entrerebbe nel ritratto
        "moods": {k: [[j, i, c] for (j, i, c) in v] for k, v in MOODS.items()},
    }
    json.dump(out, open("skills/shiba/assets/sprite.json", "w"), indent=1)
    print("scritto skills/shiba/assets/sprite.json")

    # foglio di contatto per controllare le espressioni a occhio
    sheet = []
    for name in MOODS:
        gg = [list(r) for r in rows]
        for j, i, c in MOODS[name]:
            gg[j][i] = c
        sheet.append(["".join(r) for r in gg])
    N = W + 2
    buf = [[(255, 255, 255)] * (N * len(sheet)) for _ in range(H)]
    for k, gg in enumerate(sheet):
        for y in range(H):
            for x in range(W):
                if gg[y][x] != ".":
                    buf[y][k * N + x] = PAL[int(gg[y][x])]
    sc = 6
    raw = b""
    for row in buf:
        raw += (b"\x00" + b"".join(bytes(c) * sc for c in row)) * sc

    def ch(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    open("/tmp/moods.png", "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + ch(b"IHDR", struct.pack(">IIBBBBB", len(buf[0]) * sc, H * sc, 8, 2, 0, 0, 0))
        + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))
    print("espressioni:", " ".join(MOODS))
