import struct, zlib, sys

def load(path):
    d = open(path,'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n'
    pos = 8; idat = b''; pal = None; trns = None
    while pos < len(d):
        ln, typ = struct.unpack('>I4s', d[pos:pos+8]); pos += 8
        data = d[pos:pos+ln]; pos += ln + 4
        if typ == b'IHDR':
            w,h,bd,ct,comp,filt,inter = struct.unpack('>IIBBBBB', data)
        elif typ == b'PLTE': pal = data
        elif typ == b'tRNS': trns = data
        elif typ == b'IDAT': idat += data
        elif typ == b'IEND': break
    assert inter == 0, 'interlaced'
    raw = zlib.decompress(idat)
    ch = {0:1,2:3,3:1,4:2,6:4}[ct]
    assert bd == 8, ('bitdepth', bd)
    bpp = ch
    stride = w*bpp
    out = bytearray(); prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(bpp, stride): line[i] = (line[i] + line[i-bpp]) & 255
        elif f == 2:
            for i in range(stride): line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i-bpp] if i >= bpp else 0
                b = prev[i]; c = prev[i-bpp] if i >= bpp else 0
                pp = a + b - c
                pa, pb, pc = abs(pp-a), abs(pp-b), abs(pp-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out += line; prev = line
    # normalizza a RGBA
    px = []
    for y in range(h):
        row = []
        for x in range(w):
            o = (y*w+x)*bpp
            v = out[o:o+bpp]
            if ct == 6: r,g,b,a = v
            elif ct == 2: r,g,b = v; a = 255
            elif ct == 0: r=g=b=v[0]; a=255
            elif ct == 4: r=g=b=v[0]; a=v[1]
            elif ct == 3:
                i = v[0]; r,g,b = pal[i*3:i*3+3]
                a = trns[i] if trns and i < len(trns) else 255
            row.append((r,g,b,a))
        px.append(row)
    return w,h,ct,px

if __name__ == '__main__':
    w,h,ct,px = load(sys.argv[1])
    print('size', w, h, 'colortype', ct)
