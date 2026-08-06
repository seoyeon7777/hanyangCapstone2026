"""
script.py — 아바타 blend + 시뮬레이션된 의류 OBJ 렌더링

params JSON:
{
    "output_dir":        "outputs/<job_id>/",
    "avatar_blend_path": "assets/avatars/body_M.blend",
    "sim_obj_path":      "outputs/<job_id>/simulated_cloth.obj",
    "texture_path":      "outputs/<job_id>/albedo.png"   # optional
}
"""

import bpy, sys, json, os
from mathutils import Vector


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]

    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    output_dir        = params["output_dir"]
    avatar_blend_path = params["avatar_blend_path"]
    sim_obj_path      = params["sim_obj_path"]
    texture_path      = params.get("texture_path")
    atlas_path        = params.get("atlas_path")
    atlas_layout      = params.get("atlas_layout") or "1x2"

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    with bpy.data.libraries.load(avatar_blend_path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    avatar_objects = []
    for obj in data_to.objects:
        if obj is not None and obj.type == "MESH":
            bpy.context.collection.objects.link(obj)
            avatar_objects.append(obj)
    if not avatar_objects:
        raise RuntimeError(f"아바타 blend에서 메쉬를 찾을 수 없음: {avatar_blend_path}")
    apply_solid_material(avatar_objects, "Avatar_Mat", (0.6, 0.6, 0.6, 1.0))

    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=sim_obj_path)
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=sim_obj_path)
    clothing_objects = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]

    image_path = None
    use_atlas = False
    if atlas_path and os.path.exists(atlas_path):
        image_path = atlas_path
        use_atlas = True
    elif texture_path and os.path.exists(texture_path):
        image_path = texture_path

    if image_path:
        for obj in clothing_objects:
            project_multiview_uv(obj, use_atlas=use_atlas, atlas_layout=atlas_layout)
        apply_textured_material(clothing_objects, image_path)
        print(f"[Script] 텍스처 적용: {image_path} atlas={use_atlas} layout={atlas_layout}")
    else:
        apply_solid_material(clothing_objects, "Clothing_Mat", (0.2, 0.4, 0.8, 1.0))
        if texture_path or atlas_path:
            print(f"[Script] 텍스처 없음 → solid fallback")

    render_silhouette(output_dir)
    print("완료")


def _project_uv(pu, pv, aspect):
    if aspect >= 1.0:
        return pu, 0.5 + (pv - 0.5) / aspect
    return 0.5 + (pu - 0.5) * aspect, pv


def project_multiview_uv(obj, use_atlas: bool = False, atlas_layout: str = "1x2"):
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

    use_side = use_atlas and atlas_layout == "2x2"
    front_count = back_count = side_count = 0
    face_kind = []
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

    flip = back_count > front_count * 1.5
    if flip:
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
                if kind == "left":
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
                    if kind == "front":
                        uu, vv = pu * 0.5, 0.5 + pv * 0.5
                    else:
                        uu, vv = 0.5 + (1.0 - pu) * 0.5, 0.5 + pv * 0.5
                else:
                    uu = pu * 0.5 if kind == "front" else 0.5 + (1.0 - pu) * 0.5
                    vv = pv
            uv_layer[li].uv = (uu, vv)
    print(
        f"[Script] UV multiview atlas={use_atlas} layout={atlas_layout} "
        f"up={up_axis} depth={depth_axis} side={side_count}"
    )


def project_front_uv(obj):
    project_multiview_uv(obj, use_atlas=False)


def apply_solid_material(objects, mat_name, rgba):
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf   = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value  = 0.8
    for key in ("Specular IOR Level", "Specular"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 0.2
            break
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    for obj in objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(mat)


def apply_textured_material(objects, texture_path):
    mat = bpy.data.materials.new(name="Clothing_Tex")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(texture_path)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if "Alpha" in bsdf.inputs:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        try:
            mat.blend_method = "HASHED"
        except Exception:
            pass
    bsdf.inputs["Roughness"].default_value = 0.75
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    for obj in objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(mat)


def setup_lighting():
    lights = [
        ("Key",  (-2, -4, 6), 400),
        ("Fill", ( 4, -2, 4), 150),
        ("Back", ( 0,  4, 5), 200),
    ]
    for name, loc, energy in lights:
        light_data = bpy.data.lights.new(name=f"Light_{name}", type="POINT")
        light_data.energy = energy
        light_obj  = bpy.data.objects.new(f"Light_{name}", light_data)
        bpy.context.collection.objects.link(light_obj)
        light_obj.location = loc


def render_silhouette(output_dir):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        _ = scene.eevee
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"

    scene.render.film_transparent = True
    setup_lighting()
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode  = "RGBA"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 1024

    cam_data = bpy.data.cameras.new("RenderCam")
    cam_data.type        = "ORTHO"
    cam_data.ortho_scale = 6.5
    cam_obj = bpy.data.objects.new("RenderCam", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    target = Vector((0, 0, 2.295))
    views  = {
        "front": ( 0, -3, 2.295),
        "right": (-3,  0, 2.295),
        "back":  ( 0,  3, 2.295),
        "left":  ( 3,  0, 2.295),
    }

    for view_name, pos in views.items():
        cam_obj.location = Vector(pos)
        direction = target - Vector(pos)
        cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()

        scene.render.filepath = os.path.join(output_dir, f"silhouette_{view_name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[Script] {view_name} 렌더링 완료")

    bpy.data.objects.remove(cam_obj, do_unlink=True)


main()
