"""UV unwrapping and UV quality metrics, following the Blender Studio UV guide:

- More seams rather than fewer: cut along sharp edges (facet/hard-surface borders) so islands flatten
  with little stretching.
- Even texel density: scale every island to the same pixels-per-metre (Average Island Scale).
- Check stretching the way the Area/Angle stretch overlays do, and keep angle distortion low.
- Pack with a margin measured in texture pixels, so bakes don't bleed between islands.
- Straighten/rotate islands for grain-aligned tiling (wood planks) where it matters.
"""
import math

import bpy  # must be imported before bmesh/mathutils
import bmesh


def unwrap(obj, tex_size=1024, seam_angle=50, margin_px=6):
    """Hybrid unwrap:
    - boards/beams (wood): seams on sharp edges + angle-based unwrap -> clean straight strips,
      so the grain runs along each board
    - rock and other organic facets: Smart UV Project (angle-limited cuts), which handles closed,
      irregular shapes without big distortion
    then even texel density across everything and a pack with a pixel-sized margin."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    me = obj.data
    wood = {i for i, m in enumerate(me.materials) if m and "Wood" in m.name}
    bm = bmesh.new()
    bm.from_mesh(me)
    lim = math.radians(seam_angle)
    for e in bm.edges:
        faces = e.link_faces
        if len(faces) != 2 or faces[0].material_index != faces[1].material_index:
            e.seam = True  # boundaries and material borders
        elif faces[0].material_index in wood and e.calc_face_angle(0) > lim:
            e.seam = True
    for f in bm.faces:
        f.select_set(False)
    for f in bm.faces:
        if f.material_index in wood:
            f.select_set(True)  # select_set also selects the face's verts/edges
    bm.select_mode = {"FACE"}
    bm.to_mesh(me)
    bm.free()
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    if wood:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.0)
    bpy.ops.mesh.select_all(action="INVERT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    # safety net: faces the seam unwrap distorted badly (like the Angle stretch overlay going red)
    # are re-projected on their own
    bad = distorted_faces(obj)
    if bad:
        for p in me.polygons:
            p.select = p.index in bad
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(55), island_margin=0.0)
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()            # even texel density
    bpy.ops.uv.pack_islands(rotate=True, margin=margin_px / tex_size, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


def distorted_faces(obj, max_angle_deg=12.0, max_area_ratio=3.0):
    """Faces whose UV angles or UV/3D area ratio deviate strongly (stretch hot spots)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.active
    ratios = {}
    bad = set()
    for f in bm.faces:
        a3 = f.calc_area()
        pts = [l[uv].uv for l in f.loops]
        a2 = 0.5 * abs(sum(pts[i].x * pts[i - 1].y - pts[i - 1].x * pts[i].y for i in range(len(pts))))
        if a3 > 1e-9:
            ratios[f.index] = a2 / a3
        n = len(f.loops)
        err = []
        for i, l in enumerate(f.loops):
            e1 = f.loops[i - 1].vert.co - l.vert.co
            e2 = f.loops[(i + 1) % n].vert.co - l.vert.co
            u1, u2 = pts[i - 1] - pts[i], pts[(i + 1) % n] - pts[i]
            if e1.length * e2.length * u1.length * u2.length == 0:
                continue
            err.append(abs(e1.angle(e2) - math.acos(max(-1, min(1, u1.normalized().dot(u2.normalized()))))))
        if err and math.degrees(sum(err) / len(err)) > max_angle_deg:
            bad.add(f.index)
    if ratios:
        med = sorted(ratios.values())[len(ratios) // 2]
        bad |= {i for i, r in ratios.items() if med and not (1 / max_area_ratio < r / med < max_area_ratio)}
    bm.free()
    return bad


def smart_unwrap(obj, tex_size=1024):
    """The quick default (Smart UV Project), kept for comparison."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")


def metrics(obj, tex_size=1024):
    """UV quality numbers:
    coverage      share of the texture used by islands (packing efficiency)
    area_stretch  spread of per-face texel density (0 = perfectly even; like the Area overlay)
    angle_stretch mean angle distortion per corner in degrees (like the Angle overlay)
    texel_density pixels per metre (median)
    islands       number of UV islands (seam count proxy)
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.active
    ratios, weights, angle_err, uv_total = [], [], [], 0.0
    for f in bm.faces:
        a3 = f.calc_area()
        if a3 < 1e-9:
            continue
        pts = [l[uv].uv for l in f.loops]
        a2 = 0.5 * abs(sum(pts[i].x * pts[i - 1].y - pts[i - 1].x * pts[i].y for i in range(len(pts))))
        uv_total += a2
        ratios.append(a2 / a3)
        weights.append(a3)
        n = len(f.loops)
        for i, l in enumerate(f.loops):
            v0, v1, v2 = f.loops[i - 1].vert.co, l.vert.co, f.loops[(i + 1) % n].vert.co
            p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
            e1, e2 = v0 - v1, v2 - v1
            u1, u2 = p0 - p1, p2 - p1
            if e1.length * e2.length * u1.length * u2.length == 0:
                continue
            a3d = e1.angle(e2)
            a2d = math.acos(max(-1, min(1, u1.normalized().dot(u2.normalized()))))
            angle_err.append(abs(a3d - a2d))
    # islands
    bm.faces.ensure_lookup_table()
    islands = 0
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        islands += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            for l in cur.loops:
                o = l.link_loop_radial_next
                if o == l:
                    continue
                # same island only if both edge ends share UVs across the edge
                same = ((l[uv].uv - o.link_loop_next[uv].uv).length < 1e-5 and
                        (l.link_loop_next[uv].uv - o[uv].uv).length < 1e-5)
                if same and o.face.index not in seen:
                    seen.add(o.face.index)
                    stack.append(o.face)
    bm.free()
    if not ratios:
        return {}
    wsum = sum(weights)
    mean = sum(r * w for r, w in zip(ratios, weights)) / wsum
    var = sum(w * (r / mean - 1) ** 2 for r, w in zip(ratios, weights)) / wsum
    density = sorted(math.sqrt(r) * tex_size for r in ratios)[len(ratios) // 2]
    return {"coverage": round(uv_total, 3), "area_stretch": round(math.sqrt(var), 3),
            "angle_stretch_deg": round(math.degrees(sum(angle_err) / max(1, len(angle_err))), 2),
            "texel_density_px_per_m": round(density), "islands": islands}
