# Technique playbook

How to model, light and check assets in this pipeline. Written for whoever (person or Claude)
adds a new generator or builds from a new design. Code for every technique is in `forge/techniques.py`.

## 1. Pick the technique by what the object is

| object | technique | forge helpers |
|---|---|---|
| rock, cliff, rubble | planar-cut faceting (stylised) or noise sculpt + bake (realistic) | `Builder.rock`, `facet_cuts`, `sculpt_noise` |
| buildings, props, furniture | box modelling: primitive -> loop cuts -> inset/extrude -> bevel | `box`, `loop_cut`, `inset`, `extrude`, `bevel_edges` |
| timber, planks, railings, scaffolds | kitbash from beam/plank parts | `Builder.beam`, `Builder.plank` |
| holes, windows, notches, damage | boolean difference (or inset + extrude for clean recesses) | `boolean`, `inset`+`extrude` |
| smooth organic (characters, creatures) | SubD cage or skin-modifier body, voxel remesh, smooth | `subdivide_smooth`, `skin_body` |
| roofs, gables, tapered forms | extrude a face then scale it (ridge = scale to ~0 on one axis) | `extrude(scale=...)` |
| leaning / skewed stylisation | shear (keeps the floor flat) and taper, never rotate whole walls | `shear`, `taper` |
| adjusting proportions after the fact | edge slide a loop along its rails | `edge_slide` |
| ropes, cables, pipes, vines, curved rails | curve modelling: a 3D path with a profile swept along it | `curve_sweep`, `coil` |
| trees, creature/character base forms | Skin modifier (ZSpheres-like skeleton with radii) then SubD | `skin_body` |
| debris, pebbles, moss clumps, props dressing | Geometry Nodes scatter (instances on up-facing faces, random rot/scale) | `gn_scatter` |
| fine organic surface detail | procedural sculpt (noise displacement on a dense mesh), bake to low-poly | `sculpt_noise`, rock_hq bake |
| hero characters / high-detail organics | AI image-to-3D, then clean up + rig here | (external) |
| precise industrial curves | NURBS rarely worth it for games; use curves -> mesh or polygons | - |

Notes: interactive brush sculpting and Dyntopo need a person at the screen; scripts get the same
kind of result with displacement + remesh. Booleans need closed (manifold) meshes and leave messy
topology, so apply them before baking and keep them for carving, not for building whole shapes.
Geometry Nodes trees are built in Python, so every value in them can be a spec parameter.

## 2. Stylised (hand-painted) rules

- Big shapes first: silhouette must read at 64 px. Few large planes beat many small ones.
- Every hard edge gets a bevel so it catches light; bevel width ~1-3% of object size.
- Nothing perfectly straight: jitter 0.5-1% and shear 1-3% for a hand-made feel.
- Colour carries the lighting: warm lit faces, cool shadow faces, bright edges, dark crevices
  (the style's material library does this; don't hand-pick colours outside the palette).
- Detail by value, not geometry: cracks and grain in the material, not in the mesh.

## 3. Lighting recipes (per mood; set in the style JSON)

- Sunset (current relay style): warm low key sun from front-left, cool sky fill ~0.5, AgX Punchy.
- Overcast: no sun or weak sun, sky strength ~1.2, lower contrast look.
- Night: cool moon sun 0.5-1, dark blue sky, warm emissive props (lanterns) as accents.
- Interior: key area light at 45 degrees, fill at 1/3 power opposite, rim behind.
Always judge renders under the style's own rig, never under neutral grey studio light.

## 4. Budgets

rock 1.5k tris, crate 3k, lantern 1.5k, stairs 8k, pillar 12k, wall 15k, cabin 5k.
One baked albedo per asset (1024 px props, 2048 px hero pieces). Origin at bottom centre, metres.

## 5. UVs (after the Blender Studio UV guide; code in forge/uv.py)

- More seams rather than fewer. Boards/beams: seams on sharp edges + angle-based unwrap, so grain runs
  along each strip. Rocks/organic facets: Smart UV Project. Material borders are always seams.
- Even texel density: average island scale over the whole asset (one pixels-per-metre everywhere).
- Check stretch like the Area/Angle overlays: area stretch <= 0.2, angle distortion <= 8 degrees.
  Faces over the limit are re-projected automatically.
- Pack with a margin in pixels (6 px at 1024) so baked colours don't bleed across islands.
- Tiling textures may overlap islands and go outside 0-1; baked hand-painted maps never overlap.
- Texel density target: pick texture size so props land around 250-400 px/m and big set pieces
  60-120 px/m, then keep it the same across a set.

## 6. Critique checklist (after every render)

1. Does it look like the concept at thumbnail size? (silhouette, proportions)
2. Lit vs shadow sides clearly different in value?
3. Any floating, intersecting or missing parts? Anything cut off in frame?
4. Palette: QA style-match >= 0.55 for rock-family assets; no off-palette colours.
5. Scale sanity against a 1.8 m person; stairs rise 0.18-0.3 m.
6. Exported GLB has one texture and loads with the right size and origin.
Fix in the generator, re-run the seed, never hand-edit the output.
