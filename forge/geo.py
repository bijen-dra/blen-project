"""Geometry building blocks shared by every generator.

Everything is built as separate part objects that carry two attributes the material library reads:
  part  (float)  random value per part -> tone variation between plates/planks
  grain (vector) the part's long axis in world space -> wood grain direction
Assets are then merged into one mesh (see finalize), so these survive the join.
"""
import math
import random

import bpy  # must be imported before bmesh/mathutils
import bmesh
from mathutils import Matrix, Vector

scene = lambda: bpy.context.scene  # noqa: E731


class Builder:
    """Collects parts for one asset. rng is seeded so every variant is reproducible."""

    def __init__(self, seed, materials):
        self.rng = random.Random(seed)
        self.mats = materials
        self.parts = []

    # ---------- low-level ----------
    def _object(self, name, bm, matrix, mat, grain_axis=(0, 0, 1), bevel=0.0):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        scene().collection.objects.link(ob)
        ob.matrix_world = matrix
        ob.data.materials.append(self.mats[mat])
        if bevel:
            b = ob.modifiers.new("Bevel", "BEVEL")
            b.width = bevel
            b.segments = 1
            b.limit_method = "ANGLE"
            b.harden_normals = False
        g = (matrix.to_3x3() @ Vector(grain_axis)).normalized()
        ob["part_rand"] = self.rng.random()
        ob["grain_axis"] = tuple(g)
        self.parts.append(ob)
        return ob

    @staticmethod
    def facet_cuts(bm, n, rng, lo=0.6, hi=0.9, z_bias=1.0, keep_bottom=False):
        """Chop n random planes off a convex bmesh -> big flat facets (stylised rock)."""
        for _ in range(n):
            nrm = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1) * z_bias))
            if keep_bottom and nrm.z < 0:
                nrm.z = abs(nrm.z) * 0.3
            nrm.normalize()
            support = max(v.co.dot(nrm) for v in bm.verts)
            d = support * rng.uniform(lo, hi)
            res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                         plane_co=nrm * d, plane_no=nrm, clear_outer=True)
            cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
            if cut:
                bmesh.ops.edgeloop_fill(bm, edges=cut)

    # ---------- parts ----------
    def rock(self, size, matrix, cuts=8, taper=1.0, z_bias=1.0, lo=0.6, hi=0.9, bevel=0.035,
             keep_bottom=False, mat="rock", name="Rock"):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
            if v.co.z > 0:
                v.co.x *= taper
                v.co.y *= taper
        self.facet_cuts(bm, cuts, self.rng, lo, hi, z_bias, keep_bottom)
        return self._object(name, bm, matrix, mat, bevel=bevel)

    def beam(self, p0, p1, w=0.14, h=None, mat="wood", wobble=0.015, name="Beam", roll=0.0):
        """Square-ish timber between two points, slightly irregular so it reads hand-made."""
        h = h or w
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * w, v.co.y * h, v.co.z * d.length))
            v.co.x += self.rng.uniform(-wobble, wobble)
            v.co.y += self.rng.uniform(-wobble, wobble)
        rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, "Z")
        return self._object(name, bm, Matrix.Translation((p0 + p1) / 2) @ rot, mat,
                            grain_axis=(0, 0, 1), bevel=min(w, h) * 0.12)

    def plank(self, center, length, width, thick, yaw=0.0, mat="wood", name="Plank", tilt=0.0):
        """Flat board lying in XY, long axis along local X."""
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        chip = self.rng.uniform(0, 0.04)
        for v in bm.verts:
            v.co = Vector((v.co.x * length, v.co.y * width, v.co.z * thick))
            if v.co.x > 0 and v.co.y > 0:
                v.co.x -= chip  # uneven board ends
        m = (Matrix.Translation(center) @ Matrix.Rotation(yaw, 4, "Z")
             @ Matrix.Rotation(tilt + self.rng.uniform(-0.015, 0.015), 4, "X"))
        return self._object(name, bm, m, mat, grain_axis=(1, 0, 0), bevel=thick * 0.25)

    def box(self, center, size, matrix=None, mat="metal", bevel=0.01, name="Box"):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
        m = Matrix.Translation(center) @ (matrix or Matrix())
        return self._object(name, bm, m, mat, bevel=bevel)


def finalize(parts, name):
    """Apply modifiers, write part attributes, join into one mesh with origin at ground centre."""
    for ob in parts:
        bpy.context.view_layer.objects.active = ob
        for m in list(ob.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
        me = ob.data
        pr = me.attributes.new("part", "FLOAT", "POINT")
        pr.data.foreach_set("value", [ob["part_rand"]] * len(me.vertices))
        gr = me.attributes.new("grain", "FLOAT_VECTOR", "POINT")
        gr.data.foreach_set("vector", list(ob["grain_axis"]) * len(me.vertices))
    bpy.ops.object.select_all(action="DESELECT")
    for ob in parts:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    asset = bpy.context.object
    asset.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # origin at bottom centre so assets drop straight onto the ground in an engine
    vs = [asset.matrix_world @ v.co for v in asset.data.vertices]
    minz = min(v.z for v in vs)
    cx = (min(v.x for v in vs) + max(v.x for v in vs)) / 2
    cy = (min(v.y for v in vs) + max(v.y for v in vs)) / 2
    asset.data.transform(Matrix.Translation((-cx, -cy, -minz)))
    for p in asset.data.polygons:
        p.use_smooth = False
    return asset
