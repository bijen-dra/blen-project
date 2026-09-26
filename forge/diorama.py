"""Assemble generated assets into one scene to check they read as a single set.

    python3 -m forge.diorama --style styles/relay.json --layout specs/relay_diorama.json -o out/diorama.png

Layout: {"items": [{"asset": "cliff_wall", "seed": 1, "params": {...}, "at": [x, y, z], "yaw": deg}, ...],
         "camera": {"azimuth": -35, "elevation": 12, "lens": 40}, "clouds": 30}
"""
import argparse
import json
import math
import os
import random

import bpy
from mathutils import Matrix, Vector

from . import assets, geo, materials, stage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--res", default="1280x800")
    ap.add_argument("--samples", type=int, default=64)
    a = ap.parse_args()
    style = json.load(open(a.style))
    layout = json.load(open(a.layout))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = []
    for i, it in enumerate(layout["items"]):
        p = it.get("params", {})
        mats = materials.library(style, height=it.get("gradient_height", p.get("height", 4.0)))
        b = geo.Builder(it.get("seed", i + 1), mats)
        assets.GENERATORS[it["asset"]](b, p)
        ob = geo.finalize(b.parts, f"{it['asset']}_{i}")
        ob.matrix_world = Matrix.Translation(it.get("at", (0, 0, 0))) @ Matrix.Rotation(
            math.radians(it.get("yaw", 0)), 4, "Z")
        if it.get("frame", True):
            objs.append(ob)
    # clouds
    rng = random.Random(7)
    cloud = bpy.data.materials.new("Cloud")
    cloud.use_nodes = True
    cb = cloud.node_tree.nodes["Principled BSDF"]
    col = materials.srgb_to_lin(style["palette_srgb"]["sky_horizon"])
    cb.inputs["Base Color"].default_value = (*col, 1)
    cb.inputs["Roughness"].default_value = 1.0
    cb.inputs["Emission Color"].default_value = (*col, 1)
    cb.inputs["Emission Strength"].default_value = 0.35
    lo, hi = stage.bounds(objs)
    c = (lo + hi) / 2
    span = (hi - lo) * 0.6
    for _ in range(layout.get("clouds", 30)):
        ang = rng.uniform(0, math.tau)
        rr = rng.uniform(0.7, 1.3)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=rng.uniform(1.0, 2.2),
                                              location=(c.x + math.cos(ang) * span.x * rr,
                                                        c.y + math.sin(ang) * span.y * rr,
                                                        rng.uniform(-1.4, 0.6)))
        cl = bpy.context.object
        cl.scale = (1.5, 1.2, 0.6)
        bpy.ops.object.shade_smooth()
        cl.data.materials.append(cloud)
    stage.setup_world(style)
    w, h = (int(v) for v in a.res.split("x"))
    cam = layout.get("camera", {})
    target = Vector(cam["target"]) if "target" in cam else None
    stage.render(objs, os.path.abspath(a.out), res=(w, h), samples=a.samples, transparent=False,
                 azimuth=cam.get("azimuth", -35), elevation=cam.get("elevation", 12), lens=cam.get("lens", 40),
                 margin=cam.get("margin", 0.95), target=target)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(os.path.abspath(a.out))[0] + ".blend")
    print("RESULT", a.out)


if __name__ == "__main__":
    main()
