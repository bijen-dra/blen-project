"""Cabin: a worked example of box modelling with forge.techniques.

Cube -> loop cuts -> inset + extrude (window/door recesses) -> edge slide (arched-up lintel)
-> taper + shear (hand-made lean) -> gable roof by extrude + scale -> chimney by extrude.
"""
import math

from mathutils import Matrix, Vector

from . import techniques as T


def cabin(b, params):
    W = params.get("width", 3.0)
    D = params.get("depth", 2.4)
    H = params.get("height", 2.2)
    base = 0.4  # stone foundation height

    # ---- stone foundation: a row of faceted chunks
    n = 4
    for i in range(n):
        x = -W / 2 + W * (i + 0.5) / n
        b.rock((W / n * 1.15, D * 1.08, base * 1.2), Matrix.Translation((x, 0, base / 2)), cuts=7, z_bias=0.3,
               lo=0.75, hi=0.95, keep_bottom=True)

    # ---- body: box modelling
    bm = T.box((W, D, H), center=(0, 0, base + H / 2))
    win_x = (-W * 0.33, -W * 0.08)
    door_x = (W * 0.1, W * 0.34)
    T.loop_cut(bm, "x", at=[*win_x, *door_x])
    T.loop_cut(bm, "z", at=[base + 0.15, base + H * 0.45, base + H * 0.8])
    front = lambda f, x0, x1, z0, z1: (x0 < f.calc_center_median().x < x1 and  # noqa: E731
                                        z0 < f.calc_center_median().z < z1)
    window = T.faces_facing(bm, (0, -1, 0), where=lambda f: front(f, *win_x, base + H * 0.45, base + H * 0.8))
    door = T.faces_facing(bm, (0, -1, 0), where=lambda f: front(f, *door_x, base + 0.15, base + H * 0.8))
    T.inset(bm, window, 0.07)
    window, _ = T.extrude(bm, window, -0.12)          # recess the window
    for f in window:
        f.material_index = 1                          # warm glowing glass
    T.inset(bm, door, 0.06)
    door, _ = T.extrude(bm, door, -0.08)              # recess the door
    # edge slide: lift the door's top edge a little so the door is taller than the window band
    top_z = max(v.co.z for f in door for v in f.verts)
    top_verts = list({v for f in door for v in f.verts if abs(v.co.z - top_z) < 1e-4})
    T.edge_slide(bm, top_verts, 0.35, rail_hint=(0, 0, 1))
    # side windows on the gable ends
    side = T.faces_facing(bm, (1, 0, 0), where=lambda f: base + H * 0.45 < f.calc_center_median().z < base + H * 0.8)
    if side:
        T.inset(bm, side, 0.12)
        side, _ = T.extrude(bm, side, -0.1)
        for f in side:
            f.material_index = 1
    body_verts = [v for v in bm.verts if v.co.z > base + 0.01]
    T.taper(bm, 0.94, "z", verts=body_verts)          # slightly narrower at the eaves
    T.shear(bm, 0.05, along="x", by="z", verts=body_verts, origin=base)  # hand-made lean
    T.jitter(bm, 0.012, b.rng)
    body = b._object("CabinBody", bm, Matrix(), "wood", grain_axis=(1, 0, 0), bevel=0.02)
    body.data.materials.append(b.mats["glow"])

    # ---- corner posts
    eave = base + H
    for x in (-W / 2, W / 2):
        for y in (-D / 2, D / 2):
            b.beam((x * 0.97 + 0.05 * (eave - base) * 0.5, y, base), (x * 0.94 + 0.05 * H, y * 0.94, eave), 0.16)

    # ---- gable roof: extrude a slab's top face up and squash it to a ridge
    ov = 0.35
    rb = T.box((W + ov * 2, D + ov * 2, 0.16), center=(0.05 * H, 0, eave + 0.08))
    top = T.faces_facing(rb, (0, 0, 1))
    _, ridge = T.extrude(rb, top, H * 0.55)
    for v in ridge:
        v.co.y *= 0.04                                 # scale to a ridge line [S Y 0]
    T.shear(rb, 0.06, along="x", by="z", origin=eave)
    T.jitter(rb, 0.02, b.rng)
    b._object("Roof", rb, Matrix(), "wood", grain_axis=(0, 1, 0), bevel=0.02)

    # ---- chimney: box, then extrude its top with a slight taper
    cx = -W * 0.25
    cb = T.box((0.45, 0.45, 1.2), center=(cx + 0.05 * H, D * 0.2, eave + H * 0.62))
    ctop = T.faces_facing(cb, (0, 0, 1))
    T.extrude(cb, ctop, 0.25, scale=1.15)
    T.jitter(cb, 0.015, b.rng)
    b._object("Chimney", cb, Matrix(), "rock", bevel=0.02)
