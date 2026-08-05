"""
apply_texture.py — 멀티뷰 albedo atlas를 의류 메쉬에 적용 후 GLB 저장

params:
{
  "cloth_obj_path": ".../simulated_cloth.obj",
  "albedo_path":    ".../albedo.png",          # front (fallback)
  "atlas_path":     ".../albedo_atlas.png",    # optional
  "atlas_layout":   "1x2" | "2x2",             # default 1x2
  "output_glb":     ".../cloth_textured.glb"
}

atlas 1x2: [front | back]
atlas 2x2:
  top:    [front | back ]
  bottom: [side  | sideF]
"""

import bpy
import sys
import json
import os


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


def _detect_axes(mesh):
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    mins = {"x": min(xs), "y": min(ys), "z": min(zs)}
    maxs = {"x": max(xs), "y": max(ys), "z": max(zs)}
    size = {a: maxs[a] - mins[a] for a in ("x", "y", "z")}
    mid = {a: (mins[a] + maxs[a]) * 0.5 for a in ("x", "y", "z")}
    longest = max(size.values())
    scores = {
        a: (abs(mid[a]) if size[a] >= 0.35 * longest else abs(mid[a]) * 0.05)
        for a in ("x", "y", "z")
    }
    up_axis = "y" if scores["y"] >= max(scores.values()) * 0.98 else max(scores, key=scores.get)
    if scores["z"] > scores["y"] and scores["z"] >= max(scores.values()) * 0.98:
        up_axis = "z"
    horiz = [a for a in ("x", "y", "z") if a != up_axis]
    u_axis = "x" if "x" in horiz else horiz[0]
    depth_axis = [a for a in horiz if a != u_axis][0]
    return up_axis, u_axis, depth_axis, mins, maxs


def _project_uv(pu, pv, aspect):
    if aspect >= 1.0:
        return pu, 0.5 + (pv - 0.5) / aspect
    return 0.5 + (pu - 0.5) * aspect, pv


def project_multiview_uv(obj, use_atlas: bool = True, atlas_layout: str = "1x2"):
    """정면/후면(/측면) atlas UV.

    1x2: u∈[0,0.5)=front, u∈[0.5,1]=back
    2x2: 상단 front/back, 하단 side/sideF — 법선이 좌우로 더 크면 측면 타일
    """
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    uv_layer = mesh.uv_layers.active.data

    up_axis, u_axis, depth_axis, mins, maxs = _detect_axes(mesh)
    u0, u1 = mins[u_axis], maxs[u_axis]
    v0, v1 = mins[up_axis], maxs[up_axis]
    d0, d1 = mins[depth_axis], maxs[depth_axis]
    du = max(u1 - u0, 1e-6)
    dv = max(v1 - v0, 1e-6)
    dd = max(d1 - d0, 1e-6)
    aspect = du / dv
    aspect_side = dd / dv

    try:
        mesh.calc_normals()
    except AttributeError:
        pass
    try:
        mesh.calc_normals_split()
    except Exception:
        pass

    use_side = use_atlas and atlas_layout == "2x2"
    front_count = back_count = side_count = 0
    face_kind = []  # "front" | "back" | "left" | "right"

    for poly in mesh.polygons:
        n = poly.normal
        depth_n = getattr(n, depth_axis)
        lat_n = getattr(n, u_axis)
        if use_side and abs(lat_n) > abs(depth_n) * 0.85:
            kind = "right" if lat_n > 0.0 else "left"
            side_count += 1
        elif depth_n <= 0.0:
            kind = "front"
            front_count += 1
        else:
            kind = "back"
            back_count += 1
        face_kind.append(kind)

    # If most faces classified as back, flip front/back convention
    flip_fb = back_count > front_count * 1.5
    if flip_fb:
        print("[Tex] front/back convention flipped (normals)")
        face_kind = [
            ("back" if k == "front" else "front" if k == "back" else k)
            for k in face_kind
        ]
        front_count, back_count = back_count, front_count

    for poly, kind in zip(mesh.polygons, face_kind):
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            co = mesh.vertices[vi].co
            raw_v = (getattr(co, up_axis) - v0) / dv

            if kind in ("left", "right"):
                raw_u = (getattr(co, depth_axis) - d0) / dd
                pu, pv = _project_uv(raw_u, raw_v, aspect_side)
                pu = max(0.0, min(1.0, pu))
                pv = max(0.0, min(1.0, pv))
                if not use_atlas:
                    uu, vv = pu, pv
                elif kind == "left":
                    uu, vv = pu * 0.5, pv * 0.5
                else:
                    uu, vv = 0.5 + (1.0 - pu) * 0.5, pv * 0.5
            else:
                raw_u = (getattr(co, u_axis) - u0) / du
                pu, pv = _project_uv(raw_u, raw_v, aspect)
                pu = max(0.0, min(1.0, pu))
                pv = max(0.0, min(1.0, pv))
                if not use_atlas:
                    uu, vv = pu, pv
                elif use_side:
                    # top row of 2x2 (front/back) — Blender v=1 is image top
                    if kind == "front":
                        uu, vv = pu * 0.5, 0.5 + pv * 0.5
                    else:
                        uu, vv = 0.5 + (1.0 - pu) * 0.5, 0.5 + pv * 0.5
                else:
                    # 1x2 strip
                    if kind == "front":
                        uu, vv = pu * 0.5, pv
                    else:
                        uu, vv = 0.5 + (1.0 - pu) * 0.5, pv

            uv_layer[li].uv = (uu, vv)

    print(
        f"[Tex] multiview UV up={up_axis} u={u_axis} depth={depth_axis} "
        f"front={front_count} back={back_count} side={side_count} "
        f"atlas={use_atlas} layout={atlas_layout}"
    )
    return up_axis, u_axis, depth_axis


def make_textured_material(image_path, name="GarmentTex"):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(image_path)
    tex.interpolation = "Linear"
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        try:
            mat.blend_method = "HASHED"
        except Exception:
            pass
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


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]
    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    cloth_obj_path = params["cloth_obj_path"]
    albedo_path = params.get("albedo_path")
    atlas_path = params.get("atlas_path")
    atlas_layout = params.get("atlas_layout") or "1x2"
    output_glb = params.get("output_glb")

    image_path = None
    use_atlas = False
    if atlas_path and os.path.exists(atlas_path):
        image_path = atlas_path
        use_atlas = True
    elif albedo_path and os.path.exists(albedo_path):
        image_path = albedo_path
    else:
        raise FileNotFoundError("albedo/atlas missing")

    if not os.path.exists(cloth_obj_path):
        raise FileNotFoundError(cloth_obj_path)

    clear_scene()
    obj = import_obj(cloth_obj_path)
    obj.name = "ClothTextured"
    project_multiview_uv(obj, use_atlas=use_atlas, atlas_layout=atlas_layout)
    mat = make_textured_material(image_path)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    if output_glb:
        export_glb(obj, output_glb)
        print(f"[Tex] GLB: {output_glb}")

    print("[Tex] done")


main()
