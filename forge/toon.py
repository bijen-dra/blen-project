"""Cel / toon shading presets (EEVEE), after the four classic Blender approaches:

  pgp  Pure Generative Process: light level -> hard bands coloured straight from the style palette
       (shadow / mid / lit / highlight). Locks everything to the palette; loses texture detail.
  esp  Emissive Strength Process: base colour emitted at a banded strength. Stark, desaturates shadows.
  dso  Direct Shadow Overlay: base colour multiplied by a shadow tint where the banded light is low.
       Keeps texture/painted detail and colour in the shadows. Best general default.
  cvo  Comparative Value Overlay: like dso, but bands come from comparing light against the base
       colour's own value, so dark and light materials band consistently. Most flexible, slowest.

Optional inverted-hull outline (works the same in game engines).
Shader-to-RGB only exists in EEVEE, so toon renders use EEVEE; on a machine without a GPU this needs
Mesa's software EGL (apt: libegl1 libegl-mesa0 libgl1-mesa-dri libgbm1).
"""
import bpy

from .materials import G, srgb_to_lin


def _light_value(g):
    diff = g.node("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2rgb = g.node("ShaderNodeShaderToRGB")
    g.link(diff.outputs["BSDF"], s2rgb.inputs["Shader"])
    bw = g.node("ShaderNodeRGBToBW")
    g.link(s2rgb.outputs["Color"], bw.inputs["Color"])
    return bw.outputs["Val"]


def _bands(g, value, stops):
    """Constant colour ramp: stops = [(position, rgb), ...] ascending."""
    ramp = g.node("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, rgb) in zip(cr.elements, stops):
        el.position = pos
        el.color = (*rgb, 1)
    g.link(value, ramp.inputs["Fac"])
    return ramp.outputs["Color"]


def toonify(mat, style, method="dso", thresholds=(0.12, 0.45, 0.85)):
    """Rewire an existing forge material to a toon output, reusing its painted base colour."""
    P = {k: srgb_to_lin(v) for k, v in style["palette_srgb"].items()}
    g = G.__new__(G)
    g.nt = mat.node_tree
    g.N, g.L = g.nt.nodes, g.nt.links
    g.bsdf = g.N["Principled BSDF"]
    out = g.N["Material Output"]
    link = next((l for l in g.nt.links if l.to_socket == g.bsdf.inputs["Base Color"]), None)
    base = link.from_socket if link else g.mix(0.0, tuple(g.bsdf.inputs["Base Color"].default_value[:3]), (0, 0, 0))
    light = g.math("DIVIDE", _light_value(g), style["light"]["sun_energy"])  # ~0 in shadow, ~1 fully lit
    t0, t1, t2 = thresholds
    if method == "pgp":
        col = _bands(g, light, [(0.0, P["crevice"]), (t0, P["shadow"]), (t1, P["mid"]), (t2, P["highlight"])])
    elif method == "esp":
        strength = _bands(g, light, [(0.0, (0.25,) * 3), (t1, (0.7,) * 3), (t2, (1.0,) * 3)])
        col = g.mix(1.0, base, strength, "MULTIPLY")
    elif method == "cvo":
        hsv = g.node("ShaderNodeSeparateColor", mode="HSV")
        g.link(base, hsv.inputs["Color"])
        rel = g.math("SUBTRACT", light, g.math("MULTIPLY", hsv.outputs["Blue"], 0.35))
        shade = _bands(g, rel, [(0.0, (0.0,) * 3), (t1 - 0.2, (0.55,) * 3), (t2 - 0.2, (1.0,) * 3)])
        tinted = g.mix(1.0, base, P["shadow"], "MULTIPLY")
        bw = g.node("ShaderNodeRGBToBW")
        g.link(shade, bw.inputs["Color"])
        col = g.mix(bw.outputs["Val"], tinted, base)
    else:  # dso
        shade = _bands(g, light, [(0.0, (0.0,) * 3), (t1, (0.6,) * 3), (t2, (1.0,) * 3)])
        tint = g.mix(0.35, P["shadow"], (1, 1, 1))  # shadows keep colour, shifted toward the style's shadow hue
        shadowed = g.mix(1.0, base, tint, "MULTIPLY")
        bw = g.node("ShaderNodeRGBToBW")
        g.link(shade, bw.inputs["Color"])
        col = g.mix(bw.outputs["Val"], shadowed, base)
    emit = g.node("ShaderNodeEmission")
    g.link(col, emit.inputs["Color"])
    g.link(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def outline(obj, thickness=0.02, color=(0.02, 0.02, 0.04)):
    """Inverted-hull outline: a slightly inflated, back-face-only copy drawn in a dark colour."""
    m = bpy.data.materials.new("Outline")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    m.use_backface_culling = True
    obj.data.materials.append(m)
    sol = obj.modifiers.new("Outline", "SOLIDIFY")
    sol.thickness = -thickness
    sol.use_flip_normals = True
    sol.material_offset = len(obj.data.materials) - 1
    return sol


def toon_render(objs, style, path, method="dso", outlines=True, **render_kw):
    """Render with EEVEE toon materials (copies materials, leaves the originals for baking/export)."""
    from . import stage
    for o in objs:
        for i, m in enumerate(o.data.materials):
            if m.name.startswith(("Glow", "Outline")):
                continue
            o.data.materials[i] = toonify(m.copy(), style, method)
        if outlines:
            outline(o)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 16
    view = scene.view_settings
    view.view_transform, view.look = "Standard", "None"
    return stage.render(objs, path, **render_kw)
