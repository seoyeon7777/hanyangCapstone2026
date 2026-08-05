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

    if texture_path and os.path.exists(texture_path):
        for obj in clothing_objects:
            project_front_uv(obj)
        apply_textured_material(clothing_objects, texture_path)
        print(f"[Script] 텍스처 적용: {texture_path}")
    else:
        apply_solid_material(clothing_objects, "Clothing_Mat", (0.2, 0.4, 0.8, 1.0))
        if texture_path:
            print(f"[Script] 텍스처 없음 → solid fallback ({texture_path})")

    render_silhouette(output_dir)
    print("완료")


def project_front_uv(obj):
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
    up_axis = "y" if scores["y"] >= max(scores.values()) * 0.98 else max(scores, key=scores.get)
    # Blender 네이티브 Z-up 씬에서는 Z가 up
    if scores["z"] > scores["y"] and scores["z"] >= max(scores.values()) * 0.98:
        up_axis = "z"
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
    print(f"[Script] UV projected u={u_axis} v={v_axis}")


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
