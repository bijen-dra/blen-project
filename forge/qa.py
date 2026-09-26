"""Automatic quality checks for generated assets (no Blender needed).

Style match: the reference and each render are reduced to 'how much of the picture is each palette
role' (shadow, mid, lit, highlight, wood...). Similar distributions = the asset reads like the design.
Plus: how far render colours sit from the palette, framing, grounding, triangle budget, exports.
"""
import json
import os
import struct

import numpy as np
from PIL import Image

SKY_ROLES = {"sky_top", "sky_horizon"}
ROCK_FAMILY = {"rock", "pillar", "cliff_wall"}
BUDGET = {"rock": 1500, "crate": 3000, "lantern": 1500, "stairs": 8000, "pillar": 12000, "cliff_wall": 15000}


def _roles(style, include_sky):
    names = [k for k in style["palette_srgb"] if include_sky or k not in SKY_ROLES]
    return names, np.array([style["palette_srgb"][k] for k in names])


def role_histogram(pixels, style, include_sky=False):
    names, pal = _roles(style, include_sky)
    d = ((pixels[:, None, :] - pal[None]) ** 2).sum(-1)
    idx = d.argmin(1)
    nearest = np.sqrt(d.min(1))
    hist = {n: float((idx == i).mean()) for i, n in enumerate(names)}
    return hist, float(nearest.mean())


def reference_histogram(style, ref_paths):
    px = []
    for p in ref_paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((256, 256))
        px.append(np.asarray(im, dtype=float).reshape(-1, 3) / 255)
    hist, _ = role_histogram(np.concatenate(px), style, include_sky=True)
    body = {k: v for k, v in hist.items() if k not in SKY_ROLES}
    tot = sum(body.values()) or 1
    return {k: v / tot for k, v in body.items()}


def image_checks(hero_png, style, ref_hist):
    im = np.asarray(Image.open(hero_png).convert("RGBA"), dtype=float) / 255
    alpha = im[..., 3]
    mask = alpha > 0.5
    px = im[..., :3][mask]
    coverage = float(mask.mean())
    touches = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
    if len(px) == 0:
        return {"coverage": 0.0, "style_match": 0.0, "palette_distance": 1.0, "touches_edge": touches}
    hist, dist = role_histogram(px, style)
    keys = set(hist) | set(ref_hist)
    l1 = sum(abs(hist.get(k, 0) - ref_hist.get(k, 0)) for k in keys)
    return {"coverage": round(coverage, 3), "touches_edge": touches,
            "style_match": round(1 - l1 / 2, 3), "palette_distance": round(dist, 3),
            "roles": {k: round(v, 3) for k, v in sorted(hist.items(), key=lambda kv: -kv[1]) if v > 0.02}}


def glb_info(path):
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[12:16])[0]
    j = json.loads(d[20:20 + n])
    return {"meshes": len(j.get("meshes", [])), "materials": len(j.get("materials", [])),
            "textures": len(j.get("images", [])), "kb": len(d) // 1024}


def check(meta, folder, style, ref_hist, thresholds=None):
    t = {"style_match": 0.55, "palette_distance": 0.16, **(thresholds or {})}
    if meta["asset"] not in ROCK_FAMILY:  # small wood/metal props can't match a rock-dominated reference mix
        t["style_match"] = min(t["style_match"], 0.3)
        t["palette_distance"] = max(t["palette_distance"], 0.25)
    issues, warnings = [], []
    img = image_checks(os.path.join(folder, meta["hero"]), style, ref_hist)
    st = meta["stats"]
    glb = glb_info(os.path.join(folder, meta["files"]["glb"]))
    if img["style_match"] < t["style_match"]:
        issues.append(f"colours drift from the design (style match {img['style_match']})")
    if img["palette_distance"] > t["palette_distance"]:
        issues.append(f"off-palette colours (distance {img['palette_distance']})")
    if img["touches_edge"] or img["coverage"] < 0.05:
        warnings.append("framing: asset cut off or too small in preview")
    if abs(st["min_z"]) > 0.01:
        issues.append(f"not grounded (min z {st['min_z']})")
    budget = BUDGET.get(meta["asset"], 10000)
    if st["triangles"] > budget:
        issues.append(f"over triangle budget ({st['triangles']} > {budget})")
    if st["non_manifold_edges"]:
        warnings.append(f"{st['non_manifold_edges']} open edges (fine for props, check before 3D printing)")
    u = st.get("uv", {})
    if u.get("area_stretch", 0) > 0.2:
        warnings.append(f"uneven texel density (area stretch {u['area_stretch']})")
    if u.get("angle_stretch_deg", 0) > 8:
        warnings.append(f"UV angle distortion {u['angle_stretch_deg']} deg")
    if u and u.get("coverage", 1) < 0.35:
        warnings.append(f"texture space poorly used ({int(u['coverage'] * 100)}%)")
    if glb["textures"] < 1:
        issues.append("export has no baked texture")
    return {"pass": not issues, "issues": issues, "warnings": warnings, "image": img, "glb": glb}
