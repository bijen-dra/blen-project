"""Batch driver: one spec in -> many assets out, each QA-checked, plus a contact sheet and report.

    python3 -m forge.build specs/relay_set.json -o out/relay_set

Spec format:
{
  "style": "styles/relay.json",
  "render": {"res": 640, "samples": 48, "tex": 1024},
  "assets": [
    {"asset": "pillar", "seeds": [1, 2, 3], "params": {"height": 7}},
    {"asset": "stairs", "seeds": [1], "params": {"steps": 12, "tread": "wood"}}
  ]
}
Each variant runs in its own Blender process, so one failure never takes down the batch.
"""
import argparse
import json
import os
import subprocess
import sys
import time

from PIL import Image, ImageDraw

from . import qa


def sky_background(size, style):
    top = tuple(int(c * 255) for c in style["palette_srgb"]["sky_top"])
    bot = tuple(int(c * 255) for c in style["palette_srgb"]["sky_horizon"])
    w, h = size
    bg = Image.new("RGB", size)
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = (y / h) ** 1.4
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    return bg


def present(hero, style):
    im = Image.open(hero).convert("RGBA")
    bg = sky_background(im.size, style).convert("RGBA")
    return Image.alpha_composite(bg, im).convert("RGB")


def contact_sheet(rows, style, path, tile=320):
    cols = 4
    n = len(rows)
    grid_rows = -(-n // cols)
    sheet = Image.new("RGB", (cols * tile, grid_rows * (tile + 44)), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        x, y = (i % cols) * tile, (i // cols) * (tile + 44)
        sheet.paste(present(r["hero_path"], style).resize((tile, tile)), (x, y))
        unlit = Image.open(r["unlit_path"]).convert("RGBA")
        unlit.thumbnail((tile // 3, tile // 3))
        sheet.paste(unlit, (x + tile - unlit.width - 4, y + 4), unlit)
        ok = r["qa"]["pass"]
        d.rectangle([x, y + tile, x + tile, y + tile + 44], fill=(28, 60, 36) if ok else (90, 30, 30))
        d.text((x + 6, y + tile + 4), f"{r['name']}  {'PASS' if ok else 'CHECK'}", fill=(240, 240, 240))
        img = r["qa"]["image"]
        d.text((x + 6, y + tile + 22),
               f"style {img['style_match']:.2f}  {r['stats']['triangles']} tris  {r['qa']['glb']['kb']} KB",
               fill=(200, 200, 200))
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    base = os.path.dirname(os.path.abspath(a.spec))
    style_path = os.path.normpath(os.path.join(base, spec["style"]))
    style = json.load(open(style_path))
    ref_paths = [os.path.normpath(os.path.join(os.path.dirname(style_path), p)) for p in style["references"]]
    ref_hist = qa.reference_histogram(style, ref_paths)
    r = {"res": 640, "samples": 48, "tex": 1024, **spec.get("render", {})}
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    rows, failures = [], []
    t0 = time.time()
    for item in spec["assets"]:
        for seed in item.get("seeds", [1]):
            name = f"{item['asset']}_{seed}"
            folder = os.path.join(out, name)
            cmd = [sys.executable, "-m", "forge.run_asset", "--style", style_path, "--asset", item["asset"],
                   "--seed", str(seed), "--params", json.dumps(item.get("params", {})), "--out", folder,
                   "--name", name, "--res", str(r["res"]), "--samples", str(r["samples"]), "--tex", str(r["tex"])]
            if "azimuth" in item:
                cmd += ["--azimuth", str(item["azimuth"])]
            print(f"[{time.time() - t0:6.0f}s] building {name}", flush=True)
            p = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            meta_path = os.path.join(folder, f"{name}.json")
            if p.returncode or not os.path.exists(meta_path):
                failures.append({"name": name, "error": (p.stderr or p.stdout)[-1500:]})
                print(f"   FAILED {name}", flush=True)
                continue
            meta = json.load(open(meta_path))
            meta["qa"] = qa.check(meta, folder, style, ref_hist, spec.get("thresholds"))
            meta["hero_path"] = os.path.join(folder, meta["hero"])
            meta["unlit_path"] = os.path.join(folder, meta["unlit"])
            present(meta["hero_path"], style).save(os.path.join(folder, f"{name}_preview.png"))
            rows.append(meta)
            status = "PASS" if meta["qa"]["pass"] else "CHECK: " + "; ".join(meta["qa"]["issues"])
            print(f"   {status}  style={meta['qa']['image']['style_match']}", flush=True)
    if rows:
        contact_sheet(rows, style, os.path.join(out, "contact_sheet.png"))
    report = {"spec": a.spec, "style": style["name"], "reference_roles": {k: round(v, 3) for k, v in ref_hist.items()},
              "assets": [{k: v for k, v in m.items() if not k.endswith("_path")} for m in rows],
              "failures": failures, "seconds": round(time.time() - t0)}
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=2)
    lines = [f"# Build report: {style['name']}", "",
             f"{len(rows)} built, {sum(m['qa']['pass'] for m in rows)} passed QA, {len(failures)} failed, "
             f"{report['seconds']} s", "", "| asset | QA | style match | tris | UV stretch / texture used | issues / warnings |",
             "|---|---|---|---|---|---|"]
    for m in rows:
        q = m["qa"]
        lines.append(f"| {m['name']} | {'pass' if q['pass'] else 'check'} | {q['image']['style_match']} | "
                     f"{m['stats']['triangles']} | {m['stats'].get('uv', {}).get('area_stretch', '-')} / "
                     f"{int(m['stats'].get('uv', {}).get('coverage', 0) * 100)}% | "
                     f"{'; '.join(q['issues'] + q['warnings']) or '-'} |")
    for f in failures:
        lines.append(f"| {f['name']} | FAILED | | | see report.json |")
    open(os.path.join(out, "report.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
