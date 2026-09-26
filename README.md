# blender-forge: design in, asset set out

A headless Blender pipeline that turns one piece of concept art into a whole set of matching,
game-ready assets. It is built to run unattended: one spec file in, many assets out, each one
QA-checked.

```
concept art ──► style.json ──► generators × seeds ──► render + bake + export ──► QA ──► report + contact sheet
  (refs/)       (palette,       (pillar, wall,        (hero PNG, unlit PNG,     (style match,    (report.md,
                 light, shape)   stairs, rock...)       albedo, GLB, FBX)        budget, ground)  contact_sheet.png)
```

## Setup

```
scripts/setup.sh                     # pip install bpy (Blender 5.0 as a Python module), pillow, numpy
WITH_EEVEE=1 scripts/setup.sh        # also installs software EGL for EEVEE toon previews (apt)
```

## Use

1. **Extract a style from the design** (once per art direction):
   `python3 -m forge.extract_style refs/a.png refs/b.png -o styles/mystyle.json`
   Look at `styles/mystyle_swatch.png`; hand-edit any colour or the light/shape knobs in the JSON.
2. **Write a spec** listing what to make (see `specs/relay_set.json`): asset type, seeds, params.
3. **Build**: `python3 -m forge.build specs/relay_set.json -o out/relay_set`
   Each variant runs in its own Blender process. Output per asset: `<name>_preview.png`,
   `<name>_unlit.png` (what an unlit/toon game shader shows), `<name>_albedo.png`, `.glb`, `.fbx`, `.blend`.
   Batch output: `report.md`, `report.json`, `contact_sheet.png`.
4. **Check the set together**: `python3 -m forge.diorama --style styles/relay.json --layout specs/relay_diorama.json -o out/diorama.png`

## Pieces

| file | role |
|---|---|
| `forge/extract_style.py` | k-means palette from the concept, mapped to roles (shadow, mid, lit, highlight, crevice, wood, sky) |
| `forge/materials.py` | style-driven painted materials: rock, wood, metal, glow. Face-direction colour, per-part tone, edge highlights, cracks, crevice darkening |
| `forge/geo.py` | building blocks: faceted rock chunk (random planar cuts), beam, plank, box; joins parts into one mesh, origin at ground |
| `forge/assets.py` | parametric generators: `pillar`, `cliff_wall`, `stairs`, `rock`, `crate`, `lantern`, `cabin` |
| `forge/techniques.py` | modelling techniques as code: box/loop cut/inset/extrude/edge slide/shear/taper/bevel, boolean, SubD, curve sweep, Skin modifier, Geometry Nodes scatter |
| `forge/assets_cabin.py` | worked example of box modelling with `techniques.py` |
| `forge/uv.py` | UV unwrap (seams for boards, Smart UV for rock, even texel density, pixel-margin packing, stretch fix-up) + UV metrics |
| `forge/toon.py` | cel-shading presets (pgp/esp/dso/cvo) + inverted-hull outlines for EEVEE. Experimental: bands not tuned yet |
| `forge/stage.py` | style lighting + sky, auto-framed renders, albedo baking to one texture, GLB/FBX export |
| `forge/qa.py` | automatic checks: colour-role distribution vs the reference, palette distance, framing, grounded, triangle budget, texture present |
| `forge/build.py` | batch driver, report and contact sheet |
| `forge/diorama.py` | assembles assets into one scene |

## Adding a new asset type

Write one function `def my_asset(b, params)` in `forge/assets.py` using `b.rock(...)`, `b.beam(...)`,
`b.plank(...)`, `b.box(...)`, and register it in `GENERATORS`. It automatically gets the style's
materials, rendering, baking, export and QA.

## New art style

Run `extract_style` on the new concept, tune the JSON, and rebuild the same specs: the geometry
generators are shared, only colours/light/shape knobs change.

## What QA can and can't judge

The style-match score compares how much of the image falls on each palette role against the concept.
It reliably catches colour drift (e.g. rock rendering warm brown instead of blue-slate) and broken
exports. It can't judge painterly finesse or silhouette appeal: a person still signs off the style
once and picks favourites from the contact sheet.

## Example output

First batch from `specs/relay_set.json` (14 assets, 9 passed QA): `docs/contact_sheet.png`,
assembled scene: `docs/diorama.png`, cabin with its baked texture atlas: `docs/cabin_uv.png`.

## Status and limits

Scripted generation gives consistent, game-ready props and set pieces in a style, but it does not
reach hand-made or AI-generated quality for hero characters or detailed buildings. The intended next
step is: AI image-to-3D for hero shapes, then this pipeline for cleanup, UVs, baking, toon shading,
rigging, QA and export; and a surfacing + lighting pass for existing blockouts.
