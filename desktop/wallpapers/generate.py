#!/usr/bin/env python3
# =============================================================================
# DevForge OS — Wallpaper SVG Generator
# generate.py — Genera wallpaper generativi 1920×1080 per ogni profilo
#
# Uso:
#   python3 generate.py            -- genera tutti i wallpaper
#   python3 generate.py web        -- genera solo web.svg
#   python3 generate.py --list     -- elenca profili disponibili
#
# Output: web.svg  game.svg  ai.svg  security.svg  embedded.svg  devops.svg
# Nessuna dipendenza esterna — solo Python 3.10+
# =============================================================================

import math
import random
import sys
from pathlib import Path

WIDTH  = 1920
HEIGHT = 1080
OUT_DIR = Path(__file__).parent

PROFILES = {
    'web':      {'accent': '#0066FF', 'rgb': (0,   102, 255), 'bg0': '#060A12', 'bg1': '#0D1525'},
    'game':     {'accent': '#7B2FFF', 'rgb': (123,  47, 255), 'bg0': '#080612', 'bg1': '#100E22'},
    'ai':       {'accent': '#00CC66', 'rgb': (0,   204, 102), 'bg0': '#050E0A', 'bg1': '#0B1610'},
    'security': {'accent': '#FF3344', 'rgb': (255,  51,  68), 'bg0': '#060508', 'bg1': '#0C090D'},
    'embedded': {'accent': '#FF6600', 'rgb': (255, 102,   0), 'bg0': '#0A0804', 'bg1': '#120E08'},
    'devops':   {'accent': '#00AAFF', 'rgb': (0,   170, 255), 'bg0': '#040C12', 'bg1': '#081420'},
}


# =============================================================================
# SVG builder
# =============================================================================
def _rgba(r, g, b, a):
    return f'rgba({r},{g},{b},{a:.3f})'

def _hex_to_rgb(h: str):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class SVGBuilder:
    def __init__(self):
        self._defs: list[str] = []
        self._body: list[str] = []

    # ── Definizioni ──────────────────────────────────────────────────────────
    def linear_gradient(self, gid, x1, y1, x2, y2, stops):
        s = ' '.join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
            for o, c, a in stops
        )
        self._defs.append(
            f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'gradientUnits="objectBoundingBox">{s}</linearGradient>'
        )

    def radial_gradient(self, gid, cx, cy, r, stops):
        s = ' '.join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
            for o, c, a in stops
        )
        self._defs.append(
            f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}" '
            f'gradientUnits="objectBoundingBox">{s}</radialGradient>'
        )

    def glow_filter(self, fid, color, dev=4.0, alpha=0.8):
        r, g, b = _hex_to_rgb(color)
        self._defs.append(
            f'<filter id="{fid}" x="-60%" y="-60%" width="220%" height="220%">'
            f'<feGaussianBlur stdDeviation="{dev}" result="b"/>'
            f'<feColorMatrix type="matrix" in="b" result="c" '
            f'values="0 0 0 0 {r/255:.3f}  0 0 0 0 {g/255:.3f}  0 0 0 0 {b/255:.3f}  '
            f'0 0 0 {alpha:.2f} 0"/>'
            f'<feMerge><feMergeNode in="c"/><feMergeNode in="SourceGraphic"/></feMerge>'
            f'</filter>'
        )

    def blur_filter(self, fid, dev=4.0):
        self._defs.append(f'<filter id="{fid}"><feGaussianBlur stdDeviation="{dev}"/></filter>')

    # ── Elementi ─────────────────────────────────────────────────────────────
    def add(self, s: str):
        self._body.append(s)

    def rect(self, x, y, w, h, fill='none', stroke='none', sw=1, rx=0, op=1.0, extra=''):
        a = f'x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"'
        if stroke != 'none': a += f' stroke="{stroke}" stroke-width="{sw}"'
        if rx: a += f' rx="{rx}"'
        if op != 1.0: a += f' opacity="{op:.3f}"'
        if extra: a += f' {extra}'
        return f'<rect {a}/>'

    def circle(self, cx, cy, r, fill='none', stroke='none', sw=1, op=1.0, extra=''):
        a = f'cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}"'
        if stroke != 'none': a += f' stroke="{stroke}" stroke-width="{sw}"'
        if op != 1.0: a += f' opacity="{op:.3f}"'
        if extra: a += f' {extra}'
        return f'<circle {a}/>'

    def line(self, x1, y1, x2, y2, stroke='white', sw=1, op=1.0, extra=''):
        a = f'x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" stroke-width="{sw}"'
        if op != 1.0: a += f' opacity="{op:.3f}"'
        if extra: a += f' {extra}'
        return f'<line {a}/>'

    def polygon(self, pts, fill='none', stroke='none', sw=1, op=1.0, extra=''):
        ps = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        a = f'points="{ps}" fill="{fill}"'
        if stroke != 'none': a += f' stroke="{stroke}" stroke-width="{sw}"'
        if op != 1.0: a += f' opacity="{op:.3f}"'
        if extra: a += f' {extra}'
        return f'<polygon {a}/>'

    def text(self, x, y, content, fill='white', fs=12, ff='monospace', op=1.0, extra=''):
        a = f'x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{fs}" font-family="{ff}"'
        if op != 1.0: a += f' opacity="{op:.3f}"'
        if extra: a += f' {extra}'
        return f'<text {a}>{content}</text>'

    def group(self, items: list[str], extra='') -> str:
        inner = '\n'.join(f'  {e}' for e in items)
        return f'<g {extra}>\n{inner}\n</g>'

    def watermark(self, accent) -> str:
        x, y = WIDTH - 90, HEIGHT - 22
        return (
            self.text(x, y,   'DevForge OS', fill=accent, fs=12, op=0.22,
                      extra='text-anchor="middle" font-weight="bold"') + '\n' +
            self.text(x, y+14, 'v0.1.0-alpha', fill=accent, fs=9, op=0.16,
                      extra='text-anchor="middle"')
        )

    def build(self) -> str:
        defs = '\n'.join(self._defs)
        body = '\n'.join(self._body)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">\n'
            f'<defs>{defs}</defs>\n'
            f'{body}\n</svg>'
        )


# =============================================================================
# Wallpaper: Web — Grafo a nodi fluttuanti
# =============================================================================
def generate_web(seed=42) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['web']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.radial_gradient('bg', '50%', '40%', '70%', [
        ('0%', cfg['bg1'], 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('ng', accent, 6.0, 0.9)
    svg.glow_filter('hg', accent, 12.0, 1.0)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    # Griglia sottile
    grid = []
    for x in range(0, WIDTH + 1, 120):
        grid.append(svg.line(x, 0, x, HEIGHT, stroke=_rgba(ar, ag, ab, 0.04), sw=1))
    for y in range(0, HEIGHT + 1, 120):
        grid.append(svg.line(0, y, WIDTH, y, stroke=_rgba(ar, ag, ab, 0.04), sw=1))
    svg.add(svg.group(grid))

    # Nodi
    nodes = [(rng.uniform(80, WIDTH-80), rng.uniform(60, HEIGHT-60)) for _ in range(60)]

    # Archi
    edges = []
    MAX_DIST = 270
    for i, (x1, y1) in enumerate(nodes):
        for j, (x2, y2) in enumerate(nodes):
            if j <= i:
                continue
            d = math.hypot(x2-x1, y2-y1)
            if d < MAX_DIST:
                a = (1 - d / MAX_DIST) * 0.22
                edges.append(svg.line(x1, y1, x2, y2,
                                      stroke=_rgba(ar, ag, ab, a), sw=0.7))
    svg.add(svg.group(edges))

    # Cerchi nodo
    dots = []
    for i, (x, y) in enumerate(nodes):
        deg = sum(1 for j, (ox, oy) in enumerate(nodes)
                  if j != i and math.hypot(ox-x, oy-y) < MAX_DIST)
        if deg >= 5:
            dots.append(svg.circle(x, y, 5.5, fill=accent, op=0.95, extra='filter="url(#hg)"'))
            dots.append(svg.circle(x, y, 2.5, fill='white', op=0.8))
        elif deg >= 2:
            dots.append(svg.circle(x, y, 3.5, fill=accent, op=0.75, extra='filter="url(#ng)"'))
        else:
            dots.append(svg.circle(x, y, 2.0, fill=_rgba(ar, ag, ab, 0.55)))
    svg.add(svg.group(dots))

    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Wallpaper: Game — Maglia low-poly
# =============================================================================
def generate_game(seed=7) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['game']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.radial_gradient('bg', '50%', '45%', '65%', [
        ('0%', '#160E28', 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('eg', accent, 3.0, 0.65)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    COLS, ROWS = 23, 14
    cw = WIDTH  / (COLS - 1)
    ch = HEIGHT / (ROWS - 1)
    jitter = min(cw, ch) * 0.44

    pts = []
    for row in range(ROWS):
        for col in range(COLS):
            bx, by = col * cw, row * ch
            if col in (0, COLS-1) or row in (0, ROWS-1):
                pts.append((bx, by))
            else:
                pts.append((bx + rng.uniform(-jitter, jitter),
                             by + rng.uniform(-jitter, jitter)))

    def gp(r, c):
        return pts[r * COLS + c]

    fill_tris, glow_tris = [], []
    for row in range(ROWS - 1):
        for col in range(COLS - 1):
            p00, p01 = gp(row, col),   gp(row,   col+1)
            p10, p11 = gp(row+1, col), gp(row+1, col+1)
            for tri in ([p00, p01, p11], [p00, p11, p10]):
                lv = rng.uniform(-0.07, 0.10)
                r = max(0, min(255, ar + int(lv * 200)))
                g = max(0, min(255, ag + int(lv * 200)))
                b = max(0, min(255, ab + int(lv * 200)))
                fa = rng.uniform(0.04, 0.20)
                if rng.random() < 0.11:
                    ea = rng.uniform(0.20, 0.45)
                    glow_tris.append(svg.polygon(tri, fill='none',
                                                 stroke=_rgba(ar, ag, ab, ea), sw=0.8,
                                                 extra='filter="url(#eg)"'))
                else:
                    sa = rng.uniform(0.04, 0.12)
                    fill_tris.append(svg.polygon(tri,
                                                 fill=_rgba(r, g, b, fa),
                                                 stroke=_rgba(ar, ag, ab, sa), sw=0.4))

    svg.add(svg.group(fill_tris))
    svg.add(svg.group(glow_tris))
    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Wallpaper: AI — Rete neurale
# =============================================================================
def generate_ai(seed=13) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['ai']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.radial_gradient('bg', '50%', '50%', '60%', [
        ('0%', '#0D1E14', 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('ng', accent, 5.0, 0.9)
    svg.glow_filter('cg', accent, 3.0, 0.7)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    LAYERS = [
        {'n': 7,  'x': 250},
        {'n': 11, 'x': 570},
        {'n': 14, 'x': 960},
        {'n': 11, 'x': 1350},
        {'n': 7,  'x': 1670},
    ]
    SPY = HEIGHT / (max(l['n'] for l in LAYERS) + 1)

    for L in LAYERS:
        tot = (L['n'] - 1) * SPY
        sy  = (HEIGHT - tot) / 2
        L['pos'] = [(L['x'], sy + i * SPY) for i in range(L['n'])]

    conns, highlights = [], []
    for i in range(len(LAYERS) - 1):
        for x1, y1 in LAYERS[i]['pos']:
            for x2, y2 in LAYERS[i+1]['pos']:
                w = rng.random()
                a = w * 0.11 + 0.02
                if rng.random() < 0.07:
                    highlights.append(svg.line(x1, y1, x2, y2,
                                               stroke=_rgba(ar, ag, ab, 0.55),
                                               sw=0.9, extra='filter="url(#cg)"'))
                else:
                    conns.append(svg.line(x1, y1, x2, y2,
                                          stroke=_rgba(ar, ag, ab, a), sw=0.45))
    svg.add(svg.group(conns))
    svg.add(svg.group(highlights))

    neurons = []
    for L in LAYERS:
        for x, y in L['pos']:
            act = rng.uniform(0.3, 1.0)
            rc  = int(ar * act); gc = int(ag * act); bc = int(ab * act)
            neurons.append(svg.circle(x, y, 11, fill='none',
                                       stroke=_rgba(ar, ag, ab, 0.30), sw=1.0))
            ex = 'filter="url(#ng)"' if act > 0.72 else ''
            neurons.append(svg.circle(x, y, 7, fill=_rgba(rc, gc, bc, act * 0.85), extra=ex))
            if act > 0.85:
                neurons.append(svg.circle(x, y, 3, fill=_rgba(255, 255, 255, 0.7)))
    svg.add(svg.group(neurons))

    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Wallpaper: Security — Griglia esagonale con alert
# =============================================================================
def generate_security(seed=31) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['security']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.radial_gradient('bg', '50%', '50%', '55%', [
        ('0%', '#0E0810', 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('hg', accent, 4.0, 0.85)
    svg.blur_filter('sb', 0.8)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    HEX = 52
    HW  = HEX * math.sqrt(3)
    HH  = HEX * 2

    def hexpts(cx, cy, size):
        return [(cx + size * math.cos(math.radians(60*i - 30)),
                 cy + size * math.sin(math.radians(60*i - 30)))
                for i in range(6)]

    cols = int(WIDTH  / HW) + 3
    rows = int(HEIGHT / (HH * 0.75)) + 3
    normals, alerts = [], []

    for row in range(-1, rows):
        for col in range(-1, cols):
            cx = col * HW + (HW / 2 if row % 2 else 0)
            cy = row * HH * 0.75
            pts = hexpts(cx, cy, HEX - 3)
            roll = rng.random()
            if roll < 0.025:
                alerts.append(svg.polygon(pts,
                    fill=_rgba(ar, ag, ab, 0.38),
                    stroke=_rgba(ar, ag, ab, 0.90), sw=1.2,
                    extra='filter="url(#hg)"'))
            elif roll < 0.10:
                normals.append(svg.polygon(pts,
                    fill=_rgba(ar, ag, ab, 0.09),
                    stroke=_rgba(ar, ag, ab, 0.30), sw=0.8))
            else:
                normals.append(svg.polygon(pts,
                    fill='none',
                    stroke=_rgba(ar, ag, ab, 0.07), sw=0.5))

    svg.add(svg.group(normals))
    svg.add(svg.group(alerts))

    # Testo binario fluttuante
    bits = [svg.text(rng.uniform(20, WIDTH-20), rng.uniform(20, HEIGHT-20),
                     rng.choice('01'), fill=accent, fs=10, op=0.07,
                     extra='font-family="monospace"')
            for _ in range(90)]
    svg.add(svg.group(bits))

    # Scanline orizzontale
    sy = HEIGHT * 0.38
    svg.add(f'<rect x="0" y="{sy:.1f}" width="{WIDTH}" height="2" '
            f'fill="{_rgba(ar, ag, ab, 0.18)}" filter="url(#sb)"/>')
    svg.add(f'<rect x="0" y="{sy+4:.1f}" width="{WIDTH}" height="1" '
            f'fill="{_rgba(ar, ag, ab, 0.10)}"/>')

    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Wallpaper: Embedded — Tracce PCB
# =============================================================================
def generate_embedded(seed=19) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['embedded']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.linear_gradient('bg', '0', '0', '1', '1', [
        ('0%', '#0E0A04', 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('tg', accent, 2.5, 0.55)
    svg.glow_filter('pg', accent, 5.0, 0.85)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    GRID = 40
    # Griglia PCB
    grid = []
    for x in range(0, WIDTH, GRID):
        grid.append(svg.line(x, 0, x, HEIGHT, stroke=_rgba(ar, ag, ab, 0.03), sw=0.5))
    for y in range(0, HEIGHT, GRID):
        grid.append(svg.line(0, y, WIDTH, y, stroke=_rgba(ar, ag, ab, 0.03), sw=0.5))
    svg.add(svg.group(grid))

    traces, pads = [], []

    # Bus orizzontali principali
    bus_ys = [100, 200, 340, 480, 620, 760, 900, 1000]
    for by in bus_ys:
        x0 = rng.randint(2, 6)  * GRID
        x1 = rng.randint(43, 47) * GRID
        traces.append(svg.line(x0, by, x1, by, stroke=_rgba(ar, ag, ab, 0.30), sw=2.5,
                               extra='filter="url(#tg)"'))
        for px in (x0, x1):
            pads.append(svg.circle(px, by, 6, fill=_rgba(ar, ag, ab, 0.55), extra='filter="url(#pg)"'))

    # Connessioni verticali tra bus
    for _ in range(40):
        x  = rng.randint(4, 46) * GRID
        y1 = rng.choice(bus_ys)
        y2 = rng.choice(bus_ys)
        if y1 == y2:
            continue
        ya, yb = min(y1, y2), max(y1, y2)
        traces.append(svg.line(x, ya, x, yb, stroke=_rgba(ar, ag, ab, 0.22), sw=1.8))
        for yv in (ya, yb):
            pads.append(svg.circle(x, yv, 5, fill='none', stroke=_rgba(ar, ag, ab, 0.50), sw=1.5))
            pads.append(svg.circle(x, yv, 2, fill=_rgba(ar, ag, ab, 0.65)))

    # IC component outlines
    for _ in range(9):
        cx = rng.randint(4, 38) * GRID
        cy = rng.choice(bus_ys) + rng.choice([-3, -2, -1, 1, 2, 3]) * GRID
        w  = rng.randint(5, 9)  * GRID
        h  = rng.randint(3, 5)  * GRID
        traces.append(svg.rect(cx, cy, w, h,
                               fill=_rgba(ar, ag, ab, 0.04),
                               stroke=_rgba(ar, ag, ab, 0.22), sw=1.0, rx=4))
        pin_n = rng.randint(4, 8)
        ps    = w / (pin_n + 1)
        for p in range(pin_n):
            px = cx + (p + 1) * ps
            traces.append(svg.line(px, cy,   px, cy - 10,   stroke=_rgba(ar, ag, ab, 0.30), sw=1.5))
            traces.append(svg.line(px, cy+h, px, cy + h+10, stroke=_rgba(ar, ag, ab, 0.30), sw=1.5))
            pads.append(svg.circle(px, cy - 10,   3, fill=_rgba(ar, ag, ab, 0.45)))
            pads.append(svg.circle(px, cy + h+10, 3, fill=_rgba(ar, ag, ab, 0.45)))

    svg.add(svg.group(traces))
    svg.add(svg.group(pads))
    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Wallpaper: DevOps — Topologia container/cloud
# =============================================================================
def generate_devops(seed=23) -> str:
    rng = random.Random(seed)
    cfg = PROFILES['devops']
    accent = cfg['accent']
    ar, ag, ab = cfg['rgb']
    svg = SVGBuilder()

    svg.linear_gradient('bg', '0', '0', '0', '1', [
        ('0%', '#040E18', 1.0), ('100%', cfg['bg0'], 1.0)])
    svg.glow_filter('ag', accent, 4.0,  0.75)
    svg.glow_filter('hg', accent, 10.0, 1.0)
    svg.blur_filter('cb', 10.0)

    svg.add(svg.rect(0, 0, WIDTH, HEIGHT, fill='url(#bg)'))

    # Cloud shapes in alto
    cloud = (
        'M 60,220 Q 180,70 380,110 Q 440,10 640,80 Q 720,-10 920,65 '
        'Q 980,10 1160,70 Q 1240,15 1400,80 Q 1500,30 1640,105 '
        'Q 1750,50 1880,140 L 1920,200 L 1920,0 L 0,0 Z'
    )
    svg.add(f'<path d="{cloud}" fill="{_rgba(ar, ag, ab, 0.07)}" filter="url(#cb)"/>')

    # Namespace clusters
    NS = [
        (60,  170, 540, 350, 'frontend'),
        (660, 170, 540, 350, 'backend'),
        (1260,170, 600, 350, 'infra'),
        (60,  580, 540, 380, 'monitoring'),
        (660, 580, 540, 380, 'data'),
        (1260,580, 600, 380, 'security'),
    ]

    ns_centers = [(nx + nw/2, ny + nh/2) for nx, ny, nw, nh, _ in NS]

    # Connessioni tra namespace
    conns = [(0,1),(1,2),(0,3),(1,4),(2,5),(3,4),(4,5),(0,4),(1,5)]
    conn_els = []
    for i, j in conns:
        x1, y1 = ns_centers[i]
        x2, y2 = ns_centers[j]
        conn_els.append(svg.line(x1, y1, x2, y2,
                                  stroke=_rgba(ar, ag, ab, 0.20), sw=1.2,
                                  extra='stroke-dasharray="7 4"'))
    svg.add(svg.group(conn_els))

    # Container dentro ogni namespace
    ns_els = []
    CW, CH = 54, 28
    PAD = 22

    for nx, ny, nw, nh, name in NS:
        # Bordo namespace
        ns_els.append(svg.rect(nx, ny, nw, nh,
                               fill=_rgba(ar, ag, ab, 0.025),
                               stroke=_rgba(ar, ag, ab, 0.20),
                               sw=1.0, rx=10,
                               extra='stroke-dasharray="10 5"'))
        ns_els.append(svg.text(nx+14, ny+18, name, fill=accent, fs=10,
                               op=0.45, extra='font-weight="bold"'))

        cols_n = max(1, (nw - 2*PAD) // (CW + 14))
        rows_n = max(1, (nh - 38)    // (CH + 14))

        for row in range(rows_n):
            for col in range(cols_n):
                cx = nx + PAD + col * (CW + 14)
                cy = ny + 32  + row * (CH + 14)
                active  = rng.random() < 0.28
                warning = not active and rng.random() < 0.08

                if active:
                    fill   = _rgba(ar, ag, ab, 0.25)
                    stroke = _rgba(ar, ag, ab, 0.80)
                    ex     = 'filter="url(#ag)"'
                elif warning:
                    fill   = _rgba(255, 180, 0, 0.12)
                    stroke = _rgba(255, 180, 0, 0.50)
                    ex     = ''
                else:
                    fill   = _rgba(ar, ag, ab, 0.07)
                    stroke = _rgba(ar, ag, ab, 0.25)
                    ex     = ''

                ns_els.append(svg.rect(cx, cy, CW, CH,
                                       fill=fill, stroke=stroke, sw=0.8, rx=4, extra=ex))
                # LED status dot
                dot_c = _rgba(ar, ag, ab, 0.9) if active else _rgba(255, 180, 0, 0.7) if warning else _rgba(60, 80, 100, 0.6)
                ns_els.append(svg.circle(cx+CW-7, cy+7, 3, fill=dot_c))

    svg.add(svg.group(ns_els))
    svg.add(svg.watermark(accent))
    return svg.build()


# =============================================================================
# Entry point
# =============================================================================
GENERATORS = {
    'web':      generate_web,
    'game':     generate_game,
    'ai':       generate_ai,
    'security': generate_security,
    'embedded': generate_embedded,
    'devops':   generate_devops,
}

def main():
    args = sys.argv[1:]

    if '--list' in args:
        print('Profili disponibili:')
        for name in GENERATORS:
            print(f'  {name}')
        return

    targets = [a for a in args if not a.startswith('-')]
    if not targets:
        targets = list(GENERATORS)

    for name in targets:
        if name not in GENERATORS:
            print(f'[ERRORE] Profilo sconosciuto: {name}', file=sys.stderr)
            continue
        svg_text = GENERATORS[name]()
        out_path = OUT_DIR / f'{name}.svg'
        out_path.write_text(svg_text, encoding='utf-8')
        print(f'✓ Generato {out_path.name} ({len(svg_text)//1024} KB)')

    print(f'\n{len(targets)} wallpaper generati in {OUT_DIR}')


if __name__ == '__main__':
    main()
