"""Build ONE asset variant in a fresh Blender session (called by build.py; can be run by hand).

    python3 -m forge.run_asset --style styles/relay.json --asset pillar --seed 3 \
        --params '{"height": 7}' --out out/pillar_3
Writes: <name>_hero.png (lit, transparent bg), <name>_unlit.png (baked texture only),
<name>_albedo.png, <name>.glb, <name>.fbx, <name>.blend, <name>.json (stats for QA).
"""
import argparse
import json
import os
import time

import bpy  # must be imported before bmesh/mathutils
import bmesh

from . import assets, geo, materials, stage, uv


def mesh_stats(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    lo, hi = stage.bounds([obj])
    return {"triangles": tris, "non_manifold_edges": non_manifold,
            "size_m": [round(v, 3) for v in (hi - lo)], "min_z": round(lo.z, 4),
            "materials": [m.name for m in obj.data.materials]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True)
    ap.add_argument("--asset", required=True, choices=sorted(assets.GENERATORS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--params", default="{}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--tex", type=int, default=1024)
    ap.add_argument("--res", type=int, default=640)
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--azimuth", type=float, default=-30)
    a = ap.parse_args()
    t0 = time.time()
    style = json.load(open(a.style))
    params = json.loads(a.params)
    name = a.name or f"{a.asset}_{a.seed}"
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    height = params.get("height", {"pillar": 7.0, "cliff_wall": 4.0, "stairs": 3.0}.get(a.asset, 1.5))
    mats = materials.library(style, height=height)
    b = geo.Builder(a.seed, mats)
    assets.GENERATORS[a.asset](b, params)
    obj = geo.finalize(b.parts, name)
    stage.setup_world(style)

    stats = mesh_stats(obj)
    hero = stage.render([obj], os.path.join(out, f"{name}_hero.png"), res=(a.res, a.res),
                        samples=a.samples, azimuth=a.azimuth)
    tex, baked = stage.bake_albedo(obj, a.tex, out, name)
    stats["uv"] = uv.metrics(obj, a.tex)
    unlit = os.path.join(out, f"{name}_unlit.png")
    stage.unlit_preview(obj, baked, unlit, res=(a.res // 2, a.res // 2), azimuth=a.azimuth)
    files = stage.export(obj, out, name)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"{name}.blend"))
    meta = {"name": name, "asset": a.asset, "seed": a.seed, "params": params, "style": style["name"],
            "stats": stats, "files": {k: os.path.basename(v) for k, v in files.items()},
            "hero": os.path.basename(hero), "unlit": os.path.basename(unlit),
            "texture": os.path.basename(tex), "seconds": round(time.time() - t0, 1)}
    json.dump(meta, open(os.path.join(out, f"{name}.json"), "w"), indent=2)
    print("RESULT", json.dumps(meta))


if __name__ == "__main__":
    main()
