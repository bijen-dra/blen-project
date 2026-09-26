"""Material library generated from a style JSON (see extract_style.py).

Hand-painted game look: colour depends on face direction (lit tops, sun-facing warm, shadow cool),
per-part tone variation, highlighted edges, dark crevices and painted cracks. Because the 'lighting'
is painted into the colour, it bakes into a single albedo texture for export (the way hand-painted
game assets are made).
"""
import bpy
from mathutils import Vector


def srgb_to_lin(c):
    return tuple((v / 12.92) if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


class G:
    """Tiny node-graph helper."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.N, self.L = self.nt.nodes, self.nt.links
        self.bsdf = self.N["Principled BSDF"]

    def node(self, t, **kw):
        n = self.N.new(t)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.L.new(a, b)

    def val(self, x):
        if isinstance(x, (int, float)):
            n = self.node("ShaderNodeValue")
            n.outputs[0].default_value = x
            return n.outputs[0]
        return x

    def mix(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        if isinstance(fac, (int, float)):
            n.inputs["Factor"].default_value = fac
        else:
            self.link(fac, n.inputs["Factor"])
        for sock, v in (("A", a), ("B", b)):
            if isinstance(v, tuple):
                n.inputs[sock].default_value = (*v, 1)
            else:
                self.link(v, n.inputs[sock])
        return n.outputs["Result"]

    def remap(self, v, a, b):
        n = self.node("ShaderNodeMapRange")
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        self.link(v, n.inputs["Value"])
        return n.outputs["Result"]

    def math(self, op, a, b):
        n = self.node("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def scale(self, col, k):
        return self.mix(1.0, col, (k, k, k), "MULTIPLY")

    def common(self, sun_dir):
        geo = self.node("ShaderNodeNewGeometry")
        self.geo = geo
        sep = self.node("ShaderNodeSeparateXYZ")
        self.link(geo.outputs["Normal"], sep.inputs["Vector"])
        self.nz = sep.outputs["Z"]
        dot = self.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        self.link(geo.outputs["Normal"], dot.inputs[0])
        dot.inputs[1].default_value = tuple(-Vector(sun_dir).normalized())
        self.sun = self.remap(dot.outputs["Value"], -0.1, 0.8)
        part = self.node("ShaderNodeAttribute", attribute_name="part")
        self.part = part.outputs["Fac"]
        sepp = self.node("ShaderNodeSeparateXYZ")
        self.link(geo.outputs["Position"], sepp.inputs["Vector"])
        self.pz = sepp.outputs["Z"]

    def edge_mask(self, radius=0.04):
        bev = self.node("ShaderNodeBevel", samples=8)
        bev.inputs["Radius"].default_value = radius
        dot = self.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        self.link(bev.outputs["Normal"], dot.inputs[0])
        self.link(self.geo.outputs["Normal"], dot.inputs[1])
        return self.remap(dot.outputs["Value"], 0.985, 0.9)

    def crevice(self, dist=0.3):
        ao = self.node("ShaderNodeAmbientOcclusion", samples=8)
        ao.inputs["Distance"].default_value = dist
        return self.remap(ao.outputs["AO"], 0.15, 0.85)

    def finish(self, col, rough=0.95):
        self.link(col, self.bsdf.inputs["Base Color"])
        self.bsdf.inputs["Roughness"].default_value = rough
        self.bsdf.inputs["Specular IOR Level"].default_value = 0.15


def painted_rock(style, height=6.0):
    P = {k: srgb_to_lin(v) for k, v in style["palette_srgb"].items()}
    m = bpy.data.materials.new("PaintedRock")
    g = G(m)
    g.common(style["light"]["sun_dir"])
    # per-plate tone, cool base
    col = g.mix(g.part, g.scale(g.mix(0.5, P["shadow"], P["mid"]), 0.95), P["mid"])
    # sun-facing planes pick up the warm lit colour; up-facing planes go toward highlight
    col = g.mix(g.math("MULTIPLY", g.sun, 0.4), col, g.mix(0.55, P["mid"], P["lit"]))
    col = g.mix(g.math("MULTIPLY", g.remap(g.nz, 0.45, 0.85), 0.7), col, g.mix(0.3, P["lit"], P["highlight"]))
    # darker and cooler toward the base
    col = g.mix(g.math("MULTIPLY", g.remap(g.pz, height * 0.6, 0.0), 0.55), col, P["shadow"])
    # painterly blotches + vertical brush streaks
    nz = g.node("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.9
    nz.inputs["Detail"].default_value = 1.5
    col = g.mix(g.remap(nz.outputs["Fac"], 0.35, 0.65), g.scale(col, 0.88), g.scale(col, 1.1))
    tc = g.node("ShaderNodeTexCoord")
    mp = g.node("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (6, 6, 0.6)
    g.link(tc.outputs["Object"], mp.inputs["Vector"])
    st = g.node("ShaderNodeTexNoise")
    st.inputs["Scale"].default_value = 1.2
    st.inputs["Detail"].default_value = 2
    g.link(mp.outputs["Vector"], st.inputs["Vector"])
    col = g.mix(g.remap(st.outputs["Fac"], 0.45, 0.7), col, g.scale(col, 0.82))
    # painted cracks with a light lip
    cm = g.node("ShaderNodeMapping")
    cm.inputs["Scale"].default_value = (1.0, 1.0, 0.45)
    g.link(tc.outputs["Object"], cm.inputs["Vector"])
    vor = g.node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    vor.inputs["Scale"].default_value = 1.6
    g.link(cm.outputs["Vector"], vor.inputs["Vector"])
    keepn = g.node("ShaderNodeTexNoise")
    keepn.inputs["Scale"].default_value = 0.7
    dens = style["shape"].get("crack_density", 0.5)
    keep = g.remap(keepn.outputs["Fac"], 1.0 - dens, 1.06 - dens)
    line = g.math("MULTIPLY", g.remap(vor.outputs["Distance"], 0.012, 0.0), keep)
    lip = g.math("MULTIPLY", g.remap(vor.outputs["Distance"], 0.03, 0.014), keep)
    col = g.mix(lip, col, g.scale(col, 1.3))
    col = g.mix(line, col, P["crevice"])
    # edges catch the light, crevices go dark
    col = g.mix(g.math("MULTIPLY", g.edge_mask(), style["shape"].get("edge_highlight", 0.6)), col,
                g.mix(0.5, P["lit"], P["highlight"]))
    col = g.mix(g.crevice(0.35), P["crevice"], col)
    g.finish(col)
    return m


def painted_wood(style):
    P = {k: srgb_to_lin(v) for k, v in style["palette_srgb"].items()}
    m = bpy.data.materials.new("PaintedWood")
    g = G(m)
    g.common(style["light"]["sun_dir"])
    # grain: compress position along the part's grain axis -> long streaks for any board orientation
    gr = g.node("ShaderNodeAttribute", attribute_name="grain")
    along = g.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    g.link(g.geo.outputs["Position"], along.inputs[0])
    g.link(gr.outputs["Vector"], along.inputs[1])
    proj = g.node("ShaderNodeVectorMath", operation="SCALE")
    g.link(gr.outputs["Vector"], proj.inputs[0])
    g.link(g.math("MULTIPLY", along.outputs["Value"], 0.93), proj.inputs["Scale"])
    squashed = g.node("ShaderNodeVectorMath", operation="SUBTRACT")
    g.link(g.geo.outputs["Position"], squashed.inputs[0])
    g.link(proj.outputs["Vector"], squashed.inputs[1])
    grain = g.node("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 9.0
    grain.inputs["Detail"].default_value = 3
    g.link(squashed.outputs["Vector"], grain.inputs["Vector"])
    base = g.mix(g.part, g.scale(P["wood_dark"], 0.8), g.mix(0.35, P["wood_dark"], P["wood_lit"]))
    col = g.mix(g.remap(grain.outputs["Fac"], 0.4, 0.65), g.scale(base, 0.75), base)
    col = g.mix(g.math("MULTIPLY", g.sun, 0.55), col, P["wood_lit"])
    col = g.mix(g.math("MULTIPLY", g.remap(g.nz, 0.5, 0.9), 0.6), col, g.mix(0.5, P["wood_lit"], P["highlight"]))
    col = g.mix(g.math("MULTIPLY", g.edge_mask(0.02), 0.7), col, g.mix(0.6, P["wood_lit"], P["highlight"]))
    col = g.mix(g.crevice(0.15), g.scale(P["crevice"], 0.8), col)
    g.finish(col, 0.85)
    return m


def painted_metal(style):
    P = {k: srgb_to_lin(v) for k, v in style["palette_srgb"].items()}
    m = bpy.data.materials.new("PaintedMetal")
    g = G(m)
    g.common(style["light"]["sun_dir"])
    col = g.mix(g.math("MULTIPLY", g.sun, 0.5), g.scale(P["crevice"], 0.9), g.scale(P["shadow"], 0.9))
    col = g.mix(g.edge_mask(0.015), col, P["highlight"])
    g.finish(col, 0.5)
    return m


def glow(style):
    P = {k: srgb_to_lin(v) for k, v in style["palette_srgb"].items()}
    m = bpy.data.materials.new("Glow")
    g = G(m)
    c = g.mix(0.4, P["warm_light"], (1.0, 0.95, 0.7))
    g.finish(c, 0.3)
    g.link(c, g.bsdf.inputs["Emission Color"])
    g.bsdf.inputs["Emission Strength"].default_value = 6.0
    return m


def library(style, height=6.0):
    return {"rock": painted_rock(style, height), "wood": painted_wood(style),
            "metal": painted_metal(style), "glow": glow(style)}
