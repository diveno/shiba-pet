#!/usr/bin/env python3
"""
Generates assets/faces/<mood>.png: the muzzle in colour, one per expression.

Needed because ANSI colour reaches neither the `!` command panel nor the chat
markdown (both print the escapes literally), and a grey-block muzzle is ugly.
An image shows up everywhere: shiba.py prints the path of the right file and
whoever displays the output attaches it.

RGBA PNG written by hand (zlib + three chunks): transparent background, so it
sits well on both light and dark themes. No dependencies.
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shiba  # noqa: E402

OUT = os.path.join(shiba.ROOT, "assets", "faces")
SCALE = 14


def png_rgba(path, grid, pal, scale):
    h, w = len(grid), len(grid[0])
    raw = b""
    for row in grid:
        line = b""
        for c in row:
            line += (b"\x00\x00\x00\x00" if c == "."
                     else bytes(pal[int(c)]) + b"\xff") * scale
        raw += (b"\x00" + line) * scale

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    open(path, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w * scale, h * scale, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    os.makedirs(OUT, exist_ok=True)
    sp = shiba.sprite()
    r0, r1 = sp.get("head_rows", [0, 23])
    for emo in sp["moods"]:
        g = shiba.mood_grid(emo)
        cols = [i for i in range(len(g[0]))
                if any(g[j][i] != "." for j in range(r0, r1 + 1))]
        crop = [row[cols[0]:cols[-1] + 1] for row in g[r0:r1 + 1]]
        png_rgba(os.path.join(OUT, "%s.png" % emo), crop, sp["pal"], SCALE)
        print("%-12s %s.png" % (emo, emo))


if __name__ == "__main__":
    main()
