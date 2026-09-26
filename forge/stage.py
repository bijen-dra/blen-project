"""Lighting, rendering, texture baking and export, all driven by the style JSON."""
import math
import os

import bpy
from mathutils import Vector

from .materials import srgb_to_lin


def setup_world(style):
    P = style["palette_srgb"]
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    wn, wl = world.node_tree.nodes, world.node_tree.links
    view = wn.new("ShaderNodeNewGeometry")  # 'Incoming' = view direction in world space
    sep = wn.new("ShaderNodeSeparateXYZ")
    wl.new(view.outputs["Incoming"], sep.inputs["Vector"])
    ramp = wn.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*srgb_to_lin(P["sky_horizon"]), 1)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 0.35
    ramp.color_ramp.elements[1].color = (*srgb_to_lin(P["sky_top"]), 1)
    # a light in-between stop keeps the warm-to-blue blend from turning muddy brown
    mid = ramp.color_ramp.elements.new(0.07)
    mid.color = (*srgb_to_lin([0.5 * h + 0.5 * t for h, t in zip(P["sky_horizon"], P["sky_top"])]), 1)
    mid.color = tuple(min(1.0, c * 1.35) for c in mid.color[:3]) + (1,)
    up = wn.new("ShaderNodeMath")
    up.operation = "ABSOLUTE"  # mirror below the horizon so looking down still shows sky, not ground
    wl.new(sep.outputs["Z"], up.inputs[0])
    wl.new(up.outputs[0], ramp.inputs["Fac"])
    wl.new(ramp.outputs["Color"], wn["Background"].inputs["Color"])
    wn["Background"].inputs["Strength"].default_value = style["light"]["sky_strength"]
    scene.world = world
    bpy.ops.object.light_add(type="SUN")
    sun = bpy.context.object
    sun.name = "Sun"
    sun.rotation_euler = Vector(style["light"]["sun_dir"]).to_track_quat("-Z", "Y").to_euler()
    sun.data.energy = style["light"]["sun_energy"]
    sun.data.color = srgb_to_lin(P["warm_light"])
    sun.data.color = tuple(0.72 + 0.28 * c for c in sun.data.color)  # tint, don't saturate
    sun.data.angle = math.radians(4)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = style["light"].get("look", "AgX - Punchy")


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def render(objs, path, res=(640, 640), samples=48, azimuth=-30, elevation=12, lens=50, transparent=True,
           margin=1.12, target=None):
    """Hero render with an auto-framed camera (az/el in degrees; az 0 = looking from -Y)."""
    scene = bpy.context.scene
    lo, hi = bounds(objs)
    center = target or (lo + hi) / 2
    radius = (hi - lo).length / 2
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    fov = 2 * math.atan(18 / lens)  # sensor 36mm, fits the larger image side
    aspect = min(res) / max(res)
    dist = radius * margin / math.sin(fov / 2 * aspect ** 0.5)
    az, el = math.radians(azimuth), math.radians(elevation)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = center + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.film_transparent = transparent
    scene.cycles.samples = samples
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return path


def bake_albedo(obj, size=1024, out_dir=".", name="asset"):
    """Bake the painted colour of every material into one texture on a fresh UV layout,
    then swap to a single export material (emissive parts keep their own material)."""
    scene = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    from . import uv
    uv.unwrap(obj, size)  # seams + even texel density + pixel-margin packing (see forge/uv.py)
    img = bpy.data.images.new(f"{name}_albedo", size, size)
    restore = []
    for mat in obj.data.materials:
        nt = mat.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        out = nt.nodes["Material Output"]
        link = next((l for l in nt.links if l.to_socket == bsdf.inputs["Base Color"]), None)
        emit = nt.nodes.new("ShaderNodeEmission")
        if link:
            nt.links.new(link.from_socket, emit.inputs["Color"])
        else:
            emit.inputs["Color"].default_value = bsdf.inputs["Base Color"].default_value
        nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
        restore.append((mat, bsdf, out, emit, tex))
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.bake.margin = 6
    scene.render.bake.use_selected_to_active = False
    bpy.ops.object.bake(type="EMIT")
    img.filepath_raw = os.path.join(out_dir, f"{name}_albedo.png")
    img.file_format = "PNG"
    img.save()
    for mat, bsdf, out, emit, tex in restore:
        mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mat.node_tree.nodes.remove(emit)
        mat.node_tree.nodes.remove(tex)
    baked = bpy.data.materials.new(f"{name}_baked")
    baked.use_nodes = True
    bn = baked.node_tree.nodes
    t = bn.new("ShaderNodeTexImage")
    t.image = img
    b = bn["Principled BSDF"]
    baked.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Specular IOR Level"].default_value = 0.1
    for i, mat in enumerate(obj.data.materials):
        if not mat.name.startswith("Glow"):
            obj.data.materials[i] = baked
    return img.filepath_raw, baked


def unlit_preview(obj, baked_mat, path, res=(512, 512), azimuth=-30, elevation=12):
    """Render the baked texture with no lighting: exactly what an unlit/toon game shader shows."""
    nt = baked_mat.node_tree
    out = nt.nodes["Material Output"]
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
    nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    view = bpy.context.scene.view_settings
    old = view.view_transform, view.look
    view.view_transform, view.look = "Standard", "None"
    render([obj], path, res=res, samples=8, azimuth=azimuth, elevation=elevation)
    view.view_transform, view.look = old
    nt.links.new(nt.nodes["Principled BSDF"].outputs["BSDF"], out.inputs["Surface"])
    nt.nodes.remove(emit)


def export(obj, out_dir, name, formats=("glb", "fbx")):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    files = {}
    if "glb" in formats:
        p = os.path.join(out_dir, f"{name}.glb")
        bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=True)
        files["glb"] = p
    if "fbx" in formats:
        p = os.path.join(out_dir, f"{name}.fbx")
        bpy.ops.export_scene.fbx(filepath=p, use_selection=True, path_mode="COPY", embed_textures=True)
        files["fbx"] = p
    return files
