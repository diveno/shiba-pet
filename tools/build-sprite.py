#!/usr/bin/env python3
"""
Rebuilds assets/sprite-full.json from assets/source.png - the whole dog,
30x44, which assets/sprite.json then crops down to the muzzle.

Only needed when the source image or the expressions change: at runtime
shiba.py reads the JSON and never touches the PNG. No dependencies, the PNG
decoder is in png.py.

The original pixel art is a blurry upscale, so the logical grid (30x44, cell
7.03 px) was found by minimising the intra-cell variance; each cell is then
the median of 9 samples mapped onto the fixed palette below. The transparent
background comes from a flood fill starting at the edges, so the white of the
chest is not mistaken for the white outside the outline.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from png import load  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "skills", "shiba", "assets")
SRC = os.path.join(ASSETS, "source.png")
DST = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ASSETS, "sprite-full.json")

# Bounding box of the outline in the source PNG, and the logical grid.
BBOX = (140, 350, 17, 325)
N, M = 30, 44
HEAD_ROWS = [0, 23]

PAL = [(24, 20, 18), (120, 68, 46), (176, 98, 53), (190, 130, 74),
       (214, 154, 92), (239, 183, 116), (232, 220, 188), (250, 251, 248),
       (167, 130, 111), (150, 58, 45)]
WHITEISH = {6, 7}  # indices the background flood fill treats as white

# Expression patches: (row, column, palette index).
# Left eye rows 12-14 columns 7-9, right eye rows 12-14 columns 17-19.
CLOSED = [(12, 8, '4'), (12, 9, '4'), (13, 7, '0'), (13, 8, '0'), (13, 9, '0'),
          (14, 8, '4'), (14, 9, '4'), (12, 17, '5'), (12, 18, '5'),
          (13, 17, '0'), (13, 18, '0'), (13, 19, '0'), (14, 17, '5'), (14, 18, '5')]
SQUINT = [(12, 8, '0'), (12, 9, '4'), (13, 7, '0'), (13, 8, '4'), (13, 9, '0'),
          (14, 8, '4'), (14, 9, '4'), (12, 17, '4'), (12, 18, '0'),
          (13, 17, '0'), (13, 18, '4'), (13, 19, '0'), (14, 17, '5'), (14, 18, '5')]
SLEEPY = [(12, 8, '4'), (12, 9, '4'), (13, 7, '0'), (13, 8, '0'), (13, 9, '0'),
          (12, 17, '5'), (12, 18, '5'), (13, 17, '0'), (13, 18, '0'), (13, 19, '0')]
BROWS = [(11, 7, '1'), (11, 8, '1'), (11, 18, '1'), (11, 19, '1')]
WINK = [(12, 17, '5'), (12, 18, '5'), (13, 17, '0'), (13, 18, '0'),
        (13, 19, '0'), (14, 17, '5'), (14, 18, '5')]
TONGUE = [(22, 12, '9'), (22, 13, '9'), (22, 14, '9'), (23, 13, '9')]
NOTONGUE = [(21, 12, '0'), (21, 13, '0'), (21, 14, '0')]

MOODS = {
    "calm": [],
    "happy": SQUINT + TONGUE,
    "excited": TONGUE + [(22, 11, '9'), (23, 12, '9'), (23, 14, '9')],
    "hungry": TONGUE,
    "sleepy": SLEEPY,
    "asleep": CLOSED + NOTONGUE,
    "sad": CLOSED + BROWS + NOTONGUE,
    "suspicious": WINK + BROWS,
}


def main():
    w, h, ct, px = load(SRC)
    x0, x1, y0, y1 = BBOX
    s = (x1 - x0 + 1) / float(N)

    def cell(i, j):
        samp = []
        for dy in (0.3, 0.5, 0.7):
            for dx in (0.3, 0.5, 0.7):
                samp.append(px[int(y0 + j * s + s * dy)][int(x0 + i * s + s * dx)][:3])
        return tuple(sorted(c[k] for c in samp)[len(samp) // 2] for k in range(3))

    def near(c):
        return min(range(len(PAL)),
                   key=lambda i: sum((c[k] - PAL[i][k]) ** 2 for k in range(3)))

    idx = [[near(cell(i, j)) for i in range(N)] for j in range(M)]

    bg = [[False] * N for _ in range(M)]
    stack = [(j, i) for j in range(M) for i in range(N)
             if (j in (0, M - 1) or i in (0, N - 1)) and idx[j][i] in WHITEISH]
    while stack:
        j, i = stack.pop()
        if bg[j][i]:
            continue
        bg[j][i] = True
        for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = j + dj, i + di
            if 0 <= a < M and 0 <= b < N and not bg[a][b] and idx[a][b] in WHITEISH:
                stack.append((a, b))

    rows = ["".join("." if bg[j][i] else str(idx[j][i]) for i in range(N))
            for j in range(M)]
    out = {
        "_source": "pixel art provided by the user, sampled on a 30x44 logical grid",
        "w": N, "h": M, "pal": PAL, "rows": rows,
        # Which rows are the muzzle. Everything that renders - the status
        # line, the portraits - crops to these, so a rebuild has to carry it
        # or the dog comes back as a full body nothing knows how to draw.
        "head_rows": HEAD_ROWS,
        "moods": {k: [[j, i, c] for (j, i, c) in v] for k, v in MOODS.items()},
    }
    with open(DST, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", DST)


if __name__ == "__main__":
    main()
