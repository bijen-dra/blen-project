"""Modelling techniques as reusable, scriptable operations on a bmesh.

Each function is the script equivalent of an interactive Blender tool, so generators can
'box model' the way an artist would. Key in brackets = the Blender shortcut it mirrors.

    bm = box((2, 2, 3))                       # box modelling starting primitive  [Shift+A > Cube]
    loop_cut(bm, axis="z", at=[1.0, 2.2])     # add supporting loops              [Ctrl+R]
    top = faces_facing(bm, (0, 0, 1))
    inset(bm, top, 0.2)                       # inner face                       [I]
    extrude(bm, top, 0.8)                     # pull new geometry out            [E]
    edge_slide(bm, verts, 0.3, rail_dir)      # slide a loop along its rails     [G G]
    shear(bm, 0.15, along="x", by="z")        # skew without rotating            [Shift+Ctrl+Alt+S]
    bevel_edges(bm, sharp_edges(bm), 0.03)    # soften hard edges                [Ctrl+B]
    boolean(obj, cutter, "DIFFERENCE")        # carve / merge volumes            [Bool Tool]
    subdivide_smooth(obj, 2)                  # SubD cage -> smooth surface      [Ctrl+2]
"""
import bpy  # must be imported before bmesh/mathutils
import bmesh
from mathutils import Matrix, Vector

AXIS = {"x": 0, "y": 1, "z": 2}


# ---------------------------------------------------------------- primitives / selection
def box(size, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2])) + Vector(center)
    return bm


def cylinder(radius, depth, segments=8, center=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segments, radius1=radius, radius2=radius, depth=depth)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    return bm


def faces_facing(bm, direction, min_dot=0.7, where=None):
    """Select faces whose normal points along direction (optionally filtered by a predicate)."""
    d = Vector(direction).normalized()
    bm.normal_update()
    return [f for f in bm.faces if f.normal.dot(d) > min_dot and (where is None or where(f))]


def sharp_edges(bm, angle_deg=40):
    import math
    return [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(angle_deg)]


# ---------------------------------------------------------------- core edit operations
def loop_cut(bm, axis="z", at=(0.0,)):
    """Loop cut [Ctrl+R]: add edge loops around the mesh at given coordinates along an axis."""
    n = Vector((0, 0, 0))
    n[AXIS[axis]] = 1
    for c in at:
        co = Vector((0, 0, 0))
        co[AXIS[axis]] = c
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=n)


def inset(bm, faces, thickness, depth=0.0, individual=False):
    """Inset [I]: create an inner face (border of `thickness`), optionally pushed in/out by depth."""
    if individual:
        res = bmesh.ops.inset_individual(bm, faces=faces, thickness=thickness, depth=depth)
    else:
        res = bmesh.ops.inset_region(bm, faces=faces, thickness=thickness, depth=depth)
    return faces, res["faces"]  # (inner faces keep their identity, new rim faces)


def extrude(bm, faces, distance, direction=None, scale=1.0):
    """Extrude [E]: pull faces out along their average normal (or a direction), optional taper [S].
    Returns (cap_faces, moved_verts); the input faces no longer exist afterwards."""
    if direction is None:  # measure before extruding: the op flips the original faces' normals
        bm.normal_update()
        n = Vector()
        for f in faces:
            n += f.normal
        direction = n.normalized()
    res = bmesh.ops.extrude_face_region(bm, geom=faces)
    verts = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    new_faces = [e for e in res["geom"] if isinstance(e, bmesh.types.BMFace)]
    bmesh.ops.translate(bm, verts=verts, vec=Vector(direction) * distance)
    if scale != 1.0 and verts:
        c = sum((v.co for v in verts), Vector()) / len(verts)
        for v in verts:
            v.co = c + (v.co - c) * scale
    bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")
    vs = set(verts)
    cap = [f for f in new_faces if f.is_valid and all(v in vs for v in f.verts)]
    return cap, verts  # cap = the moved copy of the input faces (the originals are removed)


def edge_slide(bm, verts, factor, rail_hint=None):
    """Edge slide [G G]: move each vertex of a loop along its connecting 'rail' edge.
    factor in -1..1 is the fraction of the rail length. rail_hint picks which rail when there are
    two (the one best aligned with the hint direction)."""
    loop = set(verts)
    moves = []
    for v in verts:
        rails = [e.other_vert(v) for e in v.link_edges if e.other_vert(v) not in loop]
        if not rails:
            continue
        if rail_hint is not None:
            h = Vector(rail_hint)
            target = max(rails, key=lambda o: (o.co - v.co).normalized().dot(h))
        else:
            target = rails[0]
        moves.append((v, (target.co - v.co) * factor))
    for v, d in moves:
        v.co += d


def shear(bm, amount, along="x", by="z", verts=None, origin=0.0):
    """Shear: offset `along` in proportion to `by` (skews without rotating, keeps floor flat)."""
    a, b = AXIS[along], AXIS[by]
    for v in (verts or bm.verts):
        v.co[a] += amount * (v.co[b] - origin)


def taper(bm, factor, axis="z", verts=None):
    """Scale cross-section linearly along an axis (e.g. narrower toward the top)."""
    vs = verts or bm.verts
    k = AXIS[axis]
    lo = min(v.co[k] for v in vs)
    hi = max(v.co[k] for v in vs)
    for v in vs:
        t = (v.co[k] - lo) / ((hi - lo) or 1)
        s = 1 + (factor - 1) * t
        for i in range(3):
            if i != k:
                v.co[i] *= s


def bevel_edges(bm, edges, offset, segments=1):
    """Bevel [Ctrl+B]: chamfer edges so they catch light (key for stylised readability)."""
    bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=segments, affect="EDGES", profile=0.5)


def jitter(bm, amount, rng, verts=None):
    """Hand-made wobble: nudge verts a little so shapes aren't CAD-perfect."""
    for v in (verts or bm.verts):
        v.co += Vector((rng.uniform(-amount, amount), rng.uniform(-amount, amount), rng.uniform(-amount, amount)))


# ---------------------------------------------------------------- object-level techniques
def boolean(obj, cutter, op="DIFFERENCE", keep_cutter=False):
    """Boolean: carve (DIFFERENCE), merge (UNION) or intersect two volumes."""
    m = obj.modifiers.new("Bool", "BOOLEAN")
    m.object = cutter
    m.operation = op
    m.solver = "EXACT"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=m.name)
    if not keep_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)


def subdivide_smooth(obj, levels=2, crease_edges=None):
    """SubD: treat the mesh as a cage and smooth it; creased edges stay sharp."""
    m = obj.modifiers.new("SubD", "SUBSURF")
    m.levels = m.render_levels = levels
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=m.name)


def sculpt_noise(obj, strength=0.05, scale=1.5, detail=4, seed=0):
    """Procedural 'sculpting': displace a dense mesh along normals with fractal noise."""
    from mathutils import noise
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    me = obj.data
    me.calc_normals_split() if hasattr(me, "calc_normals_split") else None
    for v in me.vertices:
        v.co += v.normal * strength * noise.fractal(v.co * scale + off, 0.5, 2.0, detail)


# ---------------------------------------------------------------- curves, skin, geometry nodes
def curve_sweep(points, radius=0.03, profile_res=6, name="Sweep", closed=False, twist_noise=0.0):
    """Curve modelling: a 3D path with a round profile swept along it (ropes, cables, pipes, vines,
    handrails). Returns a mesh object (converted, so it bakes/exports like everything else)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_mode = "ROUND"
    cu.bevel_depth = radius
    cu.bevel_resolution = max(0, profile_res // 2 - 1)
    cu.resolution_u = 8
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    sp.use_cyclic_u = closed
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    return bpy.context.object


def coil(radius=0.25, turns=4, pitch=0.035, wire=0.03, center=(0, 0, 0), name="Rope"):
    """Coiled rope from a helix curve sweep."""
    import math
    pts = []
    for i in range(turns * 12 + 1):
        a = i / 12 * math.tau
        r = radius * (1 - 0.15 * (i % 24 < 12))  # slightly uneven loops
        pts.append((center[0] + math.cos(a) * r, center[1] + math.sin(a) * r * 0.3, center[2] - i / 12 * pitch))
    return curve_sweep(pts, wire, name=name)


def skin_body(joints, edges, name="SkinBody", subdiv=2):
    """Skin modifier (ZSpheres-like): a vertex/edge skeleton with a radius per vertex grows a
    connected tube mesh. joints = {name: ((x,y,z), rx, ry)}; edges = [(a, b), ...]. First joint = root."""
    names = list(joints)
    me = bpy.data.meshes.new(name)
    me.from_pydata([joints[n][0] for n in names], [(names.index(a), names.index(b)) for a, b in edges], [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    sk = ob.modifiers.new("Skin", "SKIN")
    for i, n in enumerate(names):
        sv = me.skin_vertices[0].data[i]
        sv.radius = (joints[n][1], joints[n][2])
        sv.use_root = i == 0
    bpy.ops.object.modifier_apply(modifier=sk.name)
    if subdiv:
        subdivide_smooth(ob, subdiv)
    return ob


def gn_scatter(target, instance, density=2.0, seed=0, scale=(0.6, 1.4), up_only=0.6, realize=True):
    """Geometry Nodes: scatter copies of `instance` over `target`'s surface (debris, pebbles, moss
    clumps, props), random rotation/scale, only on faces pointing up. Built as a node tree in code,
    so it's fully parametric; realize=True bakes it into real geometry for export."""
    import math
    tree = bpy.data.node_groups.new("Scatter", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = tree.nodes, tree.links
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    # keep only up-facing faces as scatter area
    normal = N.new("GeometryNodeInputNormal")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(normal.outputs[0], sep.inputs[0])
    cmp = N.new("FunctionNodeCompare")
    cmp.data_type = "FLOAT"
    cmp.operation = "GREATER_THAN"
    cmp.inputs[1].default_value = up_only
    L.new(sep.outputs["Z"], cmp.inputs[0])
    dist = N.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed
    L.new(gin.outputs[0], dist.inputs["Mesh"])
    L.new(cmp.outputs[0], dist.inputs["Selection"])
    info = N.new("GeometryNodeObjectInfo")
    info.inputs["Object"].default_value = instance
    info.transform_space = "ORIGINAL"  # use the instance mesh as-is, ignore where it sits
    inst = N.new("GeometryNodeInstanceOnPoints")
    L.new(dist.outputs["Points"], inst.inputs["Points"])
    L.new(info.outputs["Geometry"], inst.inputs["Instance"])
    rot = N.new("FunctionNodeRandomValue")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Max"].default_value = (0.3, 0.3, math.tau)
    rot.inputs["Seed"].default_value = seed + 1
    L.new(rot.outputs[0], inst.inputs["Rotation"])
    scl = N.new("FunctionNodeRandomValue")
    scl.data_type = "FLOAT"
    scl.inputs[2].default_value = scale[0]
    scl.inputs[3].default_value = scale[1]
    scl.inputs["Seed"].default_value = seed + 2
    L.new(scl.outputs[1], inst.inputs["Scale"])
    join = N.new("GeometryNodeJoinGeometry")
    last = inst.outputs[0]
    if realize:
        rz = N.new("GeometryNodeRealizeInstances")
        L.new(inst.outputs[0], rz.inputs[0])
        last = rz.outputs[0]
    L.new(last, join.inputs[0])
    L.new(gin.outputs[0], join.inputs[0])
    L.new(join.outputs[0], gout.inputs[0])
    mod = target.modifiers.new("Scatter", "NODES")
    mod.node_group = tree
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return target
