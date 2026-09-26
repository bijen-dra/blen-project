"""Extract a style guide (palette roles + light mood) from concept art.

    python3 -m forge.extract_style refs/ref_pillar.png refs/ref_plinth.png -o styles/relay.json

Clusters the reference pixels (k-means), then assigns clusters to roles the material library
uses: crevice, shadow, mid, lit, highlight, wood_dark, wood_lit, warm_light, sky_top, sky_horizon.
Writes a JSON style file plus a swatch PNG for a quick human check. Every value can be hand-edited
afterwards; the generators only ever read the JSON.
"""
import argparse
import colorsys
import json
import os

import numpy as np
from PIL import Image, ImageDraw


def kmeans(x, k, iters=25, seed=0):
    rng = np.random.default_rng(seed)
    c = x[rng.choice(len(x), k, replace=False)]
    for _ in range(iters):
        d = ((x[:, None, :] - c[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(k):
            pts = x[lab == j]
            if len(pts):
                c[j] = pts.mean(0)
    counts = np.bincount(lab, minlength=k)
    return c, counts


def srgb_to_linear(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def describe(rgb):
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    warm = rgb[0] - rgb[2]  # >0 warm, <0 cool
    return {"h": h, "s": s, "v": v, "warm": warm}


def extract(paths, k=14):
    px = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        im.thumbnail((256, 256))
        px.append(np.asarray(im, dtype=float).reshape(-1, 3) / 255)
    x = np.concatenate(px)
    cents, counts = kmeans(x, k)
    cl = [dict(rgb=c.tolist(), n=int(n), **describe(c)) for c, n in zip(cents, counts) if n > 0]
    total = sum(c["n"] for c in cl)

    def pick(cands, key, default):
        cands = [c for c in cands if c["n"] > total * 0.004]
        return max(cands, key=key)["rgb"] if cands else default

    # Sky: bright-ish, saturated blue in the upper part of frames is common in concept art
    sky = [c for c in cl if 0.55 < c["h"] < 0.7 and c["s"] > 0.35 and c["v"] > 0.45]
    sky_ids = {id(c) for c in sky}
    body = [c for c in cl if id(c) not in sky_ids]
    cool = [c for c in body if c["warm"] < 0.0]
    warm = [c for c in body if c["warm"] >= 0.0]
    style = {
        "crevice": pick(body, lambda c: -c["v"], [0.08, 0.08, 0.12]),
        "shadow": pick([c for c in cool if 0.2 < c["v"] < 0.52], lambda c: c["n"], [0.3, 0.33, 0.45]),
        "mid": pick([c for c in cool if 0.52 <= c["v"] < 0.85], lambda c: c["n"], [0.5, 0.52, 0.6]),
        "lit": pick([c for c in warm if 0.5 < c["v"] < 0.9 and c["s"] < 0.45], lambda c: c["n"], [0.7, 0.65, 0.58]),
        "highlight": pick([c for c in warm if c["v"] > 0.7], lambda c: c["v"] - c["s"] * 0.3, [0.95, 0.85, 0.65]),
        "wood_dark": pick([c for c in warm if c["s"] > 0.35 and c["v"] < 0.45], lambda c: c["n"], [0.25, 0.14, 0.07]),
        "wood_lit": pick([c for c in warm if c["s"] > 0.4 and 0.4 < c["v"] < 0.85], lambda c: c["n"], [0.6, 0.38, 0.18]),
        "warm_light": pick([c for c in warm if c["s"] > 0.3], lambda c: c["v"] * c["s"], [1.0, 0.75, 0.45]),
        "sky_top": pick(sky, lambda c: c["s"], [0.3, 0.45, 0.75]),
        "sky_horizon": pick([c for c in warm if c["v"] > 0.75 and c["s"] < 0.35], lambda c: c["n"], [0.95, 0.8, 0.7]),
    }
    return style, cl


def swatch(style, path):
    names = list(style["palette_srgb"])
    w = 120
    im = Image.new("RGB", (w * len(names), 150), "white")
    d = ImageDraw.Draw(im)
    for i, n in enumerate(names):
        c = tuple(int(v * 255) for v in style["palette_srgb"][n])
        d.rectangle([i * w, 0, (i + 1) * w - 4, 120], fill=c)
        d.text((i * w + 4, 128), n, fill=(0, 0, 0))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refs", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    pal, clusters = extract(a.refs)
    style = {
        "name": a.name or os.path.splitext(os.path.basename(a.out))[0],
        "references": [os.path.relpath(p, os.path.dirname(os.path.abspath(a.out))) for p in a.refs],
        "palette_srgb": {k: [round(v, 3) for v in c] for k, c in pal.items()},
        # Mood / rendering knobs (hand-tune once per art direction)
        "light": {"sun_dir": [0.75, 0.45, -0.55], "sun_energy": 5.5, "sky_strength": 0.55,
                  "look": "AgX - Punchy"},
        "shape": {"facet_cuts": [6, 10], "bevel": 0.035, "edge_highlight": 0.6, "crack_density": 0.5},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(style, f, indent=2)
    swatch(style, os.path.splitext(a.out)[0] + "_swatch.png")
    print(json.dumps(style["palette_srgb"], indent=1))


if __name__ == "__main__":
    main()
