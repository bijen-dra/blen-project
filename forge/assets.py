"""Parametric asset generators. Each takes (builder, params) and adds parts; all share the style's
materials, so everything from one design looks like one set.

Add a new asset type by writing one function and registering it in GENERATORS.
Every param has a default; seeds give endless variations.
"""
import math

from mathutils import Matrix, Vector


def _p(params, key, default):
    return params.get(key, default)


# ---------------------------------------------------------------- rock family
def rock(b, params):
    """Boulder: 1-3 faceted chunks fused together."""
    s = _p(params, "size", 1.2)
    n = _p(params, "chunks", b.rng.randint(1, 3))
    for i in range(n):
        k = s * (1.0 if i == 0 else b.rng.uniform(0.45, 0.7))
        off = Vector((b.rng.uniform(-0.5, 0.5) * s, b.rng.uniform(-0.4, 0.4) * s, 0)) if i else Vector()
        size = (k * b.rng.uniform(1.0, 1.5), k * b.rng.uniform(0.8, 1.2), k * b.rng.uniform(0.6, 1.0))
        m = Matrix.Translation(off + Vector((0, 0, size[2] * 0.4))) @ Matrix.Rotation(b.rng.uniform(0, 6.3), 4, "Z")
        b.rock(size, m, cuts=b.rng.randint(12, 16), z_bias=1.0, lo=0.45, hi=0.8, keep_bottom=True)


def pillar(b, params):
    """Tall tapered rock column made of overlapping plates, optional timber frame on top."""
    H = _p(params, "height", 7.0)
    W = _p(params, "width", 3.2)
    top = _p(params, "top_scale", 0.45)
    rad = lambda z: W / 2 * (1 - (1 - top) * z / H)  # noqa: E731
    b.rock((W, W * 0.9, H), Matrix.Translation((0, 0, H / 2)), cuts=14, taper=top, z_bias=0.25)
    lean = math.atan((W / 2) * (1 - top) / H)
    tiers = _p(params, "tiers", 3)
    for t in range(tiers):
        z0 = H * t / tiers * 0.95
        hgt = H / tiers * 1.25
        count = max(3, 6 - t)
        start = b.rng.uniform(0, math.tau)
        for k in range(count):
            if b.rng.random() < 0.25:
                continue
            ang = start + k * math.tau / count + b.rng.uniform(-0.2, 0.2)
            zc = z0 + hgt / 2 + b.rng.uniform(-0.3, 0.3)
            thick = b.rng.uniform(0.5, 0.9) * W / 3.2
            r = rad(zc) - thick * 0.25
            rot = (Matrix.Rotation(ang, 4, "Z") @ Matrix.Rotation(-lean + b.rng.uniform(-0.06, 0.06), 4, "X"))
            loc = Vector((math.sin(ang) * r, -math.cos(ang) * r, zc))
            b.rock((rad(zc) * b.rng.uniform(1.1, 1.5), thick, hgt * b.rng.uniform(0.75, 1.0)),
                   Matrix.Translation(loc) @ rot, cuts=b.rng.randint(7, 10), taper=0.85, z_bias=0.8)
    tr = rad(H)
    b.rock((tr * 2.3, tr * 2.1, 0.45), Matrix.Translation((0, 0, H + 0.1)), cuts=8, z_bias=0.3)
    if _p(params, "frame", True):
        zt = H + 0.33
        for x in (-0.55, 0.55):
            for y in (-0.35, 0.35):
                b.beam((x, y, zt), (x, y, zt + 1.4))
            b.beam((x, -0.35, zt + 0.2), (x, 0.35, zt + 1.2), 0.1)
        for y in (-0.35, 0.35):
            b.beam((-0.75, y, zt + 1.35), (0.75, y, zt + 1.35), 0.16)
        b.beam((-0.55, -0.35, zt + 0.3), (0.55, -0.35, zt + 1.2), 0.1)


def cliff_wall(b, params):
    """Plinth / cliff wall: a row of big faceted blocks under a flat top, optional timber deck."""
    L = _p(params, "length", 7.0)
    H = _p(params, "height", 4.0)
    D = _p(params, "depth", 3.0)
    n = max(2, int(L / b.rng.uniform(1.4, 2.0)))
    xs = [-L / 2 + L * (i + 0.5) / n for i in range(n)]
    for x in xs:
        w = L / n * b.rng.uniform(1.05, 1.3)
        h = H * b.rng.uniform(0.85, 1.0)
        b.rock((w, D, h), Matrix.Translation((x, 0, h / 2)) @ Matrix.Rotation(b.rng.uniform(-0.03, 0.03), 4, "Y"),
               cuts=b.rng.randint(8, 11), taper=0.93, z_bias=0.35, lo=0.7, hi=0.93)
        # front plates break up the face
        if b.rng.random() < 0.8:
            ph = h * b.rng.uniform(0.5, 0.9)
            b.rock((w * b.rng.uniform(0.5, 0.8), 0.45, ph),
                   Matrix.Translation((x + b.rng.uniform(-0.3, 0.3), -D / 2 - 0.05, ph / 2)),
                   cuts=b.rng.randint(6, 9), z_bias=0.6)
    # top slab row keeps a walkable, level top
    for x in xs:
        b.rock((L / n * 1.1, D * 1.02, 0.35), Matrix.Translation((x, 0, H + 0.02)),
               cuts=6, z_bias=0.15, lo=0.8, hi=0.95)
    if _p(params, "deck", True):
        zt = H + 0.22
        pw = 0.32
        for i in range(int(D / pw)):
            y = -D / 2 + pw * (i + 0.5)
            b.plank((0, y - 0.35, zt), L * 0.96, pw * 0.92, 0.08)
        # overhanging deck edge with diagonal brackets
        for x in xs[::1]:
            b.beam((x, -D / 2 - 0.05, H - 1.3), (x, -D / 2 - 0.75, zt - 0.08), 0.13)
        b.beam((-L / 2, -D / 2 - 0.75, zt - 0.08), (L / 2, -D / 2 - 0.75, zt - 0.08), 0.16)
        if _p(params, "railing", True):
            for x in [-L / 2 + 0.1 + i * (L - 0.2) / 4 for i in range(5)]:
                b.beam((x, -D / 2 - 0.7, zt), (x, -D / 2 - 0.7, zt + 1.0), 0.11)
            b.beam((-L / 2, -D / 2 - 0.7, zt + 0.95), (L / 2, -D / 2 - 0.7, zt + 0.95), 0.1)


def stairs(b, params):
    """Staircase: stone or wood treads on timber stringers, optional railing. Climbs along +X."""
    n = _p(params, "steps", 10)
    rise = _p(params, "rise", 0.3)
    run = _p(params, "run", 0.42)
    W = _p(params, "width", 1.4)
    tread = _p(params, "tread", "stone")
    for i in range(n):
        x = i * run + run / 2
        z = i * rise + rise / 2
        if tread == "stone":
            b.rock((run * 1.12, W, rise * 1.05), Matrix.Translation((x, 0, z)), cuts=5, z_bias=0.15, lo=0.8, hi=0.96,
                   bevel=0.025)
        else:
            b.plank((x, 0, (i + 1) * rise - 0.04), W, run * 0.95, 0.07, yaw=math.pi / 2)
    top = Vector((n * run, 0, n * rise))
    for y in (-W / 2 - 0.08, W / 2 + 0.08):
        b.beam((0, y, 0.05), (top.x, y, top.z - 0.05), 0.12, 0.28)
    if _p(params, "railing", True):
        y = -W / 2 - 0.12
        posts = list(range(0, n, 3)) + [n - 1]
        for i in posts:
            x = i * run + run / 2
            z = (i + 1) * rise
            b.beam((x, y, z - rise), (x, y, z + 0.95), 0.1)
        x0, x1 = posts[0] * run + run / 2, posts[-1] * run + run / 2
        b.beam((x0, y, (posts[0] + 1) * rise + 0.9), (x1, y, (posts[-1] + 1) * rise + 0.9), 0.09)


def crate(b, params):
    """Wooden crate: planked sides inside a frame."""
    s = _p(params, "size", 0.8)
    h = s * _p(params, "height_ratio", b.rng.uniform(0.8, 1.1))
    t = 0.07
    rows = 3
    for side in range(4):
        yaw = side * math.pi / 2
        n = Vector((math.sin(yaw), -math.cos(yaw), 0))
        for r in range(rows):
            z = h * (r + 0.5) / rows
            c = n * (s / 2 - t / 2)
            c.z = z
            b.plank(c, s * 0.98, h / rows * 0.9, t, yaw=yaw, tilt=math.pi / 2)
    for x in (-1, 1):
        for y in (-1, 1):
            b.beam((x * s / 2, y * s / 2, 0), (x * s / 2, y * s / 2, h), t * 1.4)
    for i in range(4):
        b.plank((0, -s / 2 + s * (i + 0.5) / 4, h + t / 2), s * 1.02, s / 4 * 0.94, t)


def lantern(b, params):
    """Hanging-style lantern with a warm emissive core."""
    s = _p(params, "size", 0.35)
    h = s * 1.6
    b.box((0, 0, h / 2), (s * 0.7, s * 0.7, h * 0.8), mat="glow", bevel=0.0)
    for x in (-1, 1):
        for y in (-1, 1):
            b.beam((x * s / 2, y * s / 2, 0), (x * s / 2, y * s / 2, h), 0.04, mat="metal")
    b.box((0, 0, 0.02), (s * 1.1, s * 1.1, 0.05), mat="metal")
    b.box((0, 0, h), (s * 1.15, s * 1.15, 0.06), mat="metal")
    b.box((0, 0, h + 0.1), (s * 0.5, s * 0.5, 0.15), mat="metal")


GENERATORS = {"rock": rock, "pillar": pillar, "cliff_wall": cliff_wall, "stairs": stairs,
              "crate": crate, "lantern": lantern}

from .assets_cabin import cabin  # noqa: E402  (box-modelling example built with forge.techniques)

GENERATORS["cabin"] = cabin
