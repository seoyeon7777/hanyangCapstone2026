"""
apply_texture.py — 정면 albedo를 의류 메쉬에 투영·적용 후 GLB/텍스처 저장

호출:
  blender --background --python apply_texture.py -- <params.json>

params:
{
  "cloth_obj_path": "outputs/.../simulated_cloth.obj",  # 또는 shaped
  "albedo_path":    "outputs/.../albedo.png",
  "output_glb":     "outputs/.../cloth_textured.glb",
  "output_obj":     "outputs/.../cloth_textured.obj",   # optional
  "baked_albedo":   "outputs/.../albedo_uv.png"         # optional bake
}
"""

import bpy
import sys
import json
import os
import math
from mathutils import Vector, Euler


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)
    for block in list(bpy.data.images):
        bpy.data.images.remove(block)


def import_obj(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path)
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=path)
    added = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not added:
        raise RuntimeError(f"OBJ import failed: {path}")
    return added[0]


def project_front_uv(obj):
    """정면 직교 투영 UV. up 축은 mid-point 휴리스틱 (소매로 X가 길어도 Y/Z 유지)."""
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    uv_layer = mesh.uv_layers.active.data

    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    mins = {"x": min(xs), "y": min(ys), "z": min(zs)}
    maxs = {"x": max(xs), "y": max(ys), "z": max(zs)}
    size = {a: maxs[a] - mins[a] for a in ("x", "y", "z")}
    mid = {a: (mins[a] + maxs[a]) * 0.5 for a in ("x", "y", "z")}
    longest = max(size.values())
    scores = {}
    for a in ("x", "y", "z"):
        scores[a] = abs(mid[a]) if size[a] >= 0.35 * longest else abs(mid[a]) * 0.05
    # prefer Y then Z
    up_axis = "y" if scores["y"] >= max(scores.values()) * 0.98 else max(scores, key=scores.get)
    horiz = [a for a in ("x", "y", "z") if a != up_axis]
    u_axis = "x" if "x" in horiz else horiz[0]
    v_axis = up_axis

    u0, u1 = mins[u_axis], maxs[u_axis]
    v0, v1 = mins[v_axis], maxs[v_axis]
    du = max(u1 - u0, 1e-6)
    dv = max(v1 - v0, 1e-6)
    aspect = du / dv

    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            co = mesh.vertices[vi].co
            raw_u = (getattr(co, u_axis) - u0) / du
            raw_v = (getattr(co, v_axis) - v0) / dv
            if aspect >= 1.0:
                u, v = raw_u, 0.5 + (raw_v - 0.5) / aspect
            else:
                u, v = 0.5 + (raw_u - 0.5) * aspect, raw_v
            uv_layer[li].uv = (u, v)

    print(f"[Tex] UV projected u={u_axis} v={v_axis} aspect={aspect:.3f}")
    return u_axis, v_axis


def make_textured_material(albedo_path, name="GarmentTex"):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    img = bpy.data.images.load(albedo_path)
    tex.image = img
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    # alpha if present
    if "Alpha" in bsdf.inputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "HASHED"
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.7
    return mat


def export_glb(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )


def export_obj(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=True,
            export_materials=True,
            apply_modifiers=True,
        )
    except TypeError:
        bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True)
    except AttributeError:
        bpy.ops.export_scene.obj(filepath=path, use_selection=True, use_materials=True)


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]
    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    cloth_obj_path = params["cloth_obj_path"]
    albedo_path = params["albedo_path"]
    output_glb = params.get("output_glb")
    output_obj = params.get("output_obj")

    if not os.path.exists(albedo_path):
        raise FileNotFoundError(albedo_path)
    if not os.path.exists(cloth_obj_path):
        raise FileNotFoundError(cloth_obj_path)

    clear_scene()
    obj = import_obj(cloth_obj_path)
    obj.name = "ClothTextured"
    project_front_uv(obj)
    mat = make_textured_material(albedo_path)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    if output_glb:
        export_glb(obj, output_glb)
        print(f"[Tex] GLB: {output_glb}")
    if output_obj:
        export_obj(obj, output_obj)
        print(f"[Tex] OBJ: {output_obj}")

    print("[Tex] done")


main()
