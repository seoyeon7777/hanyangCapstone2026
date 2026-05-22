"""
script.py — 아바타 OBJ + 시뮬레이션된 의류 OBJ 렌더링

호출 방식:
    blender --background --python script.py -- <params_json_path>

params JSON 구조:
{
    "output_dir":   "...",
    "avatar_size":  "M",
    "garment_type": "top",
    "sim_obj_path": "outputs/<job_id>/simulated_cloth.obj",
    "base_dir":     "C:/hanyangCapstone2026"
}
"""

import bpy, sys, json, os, math
from mathutils import Vector


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]

    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    output_dir   = params["output_dir"]
    avatar_size  = params["avatar_size"]
    sim_obj_path = params["sim_obj_path"]
    base_dir     = params["base_dir"]

    # 씬 초기화
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    # 아바타 불러오기 (blend 파일)
    avatar_path = os.path.join(base_dir, "assets", "avatars", f"body_{avatar_size}.blend")
    avatar_objects = []
    with bpy.data.libraries.load(avatar_path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    for obj in data_to.objects:
        if obj is not None and obj.type == "MESH":
            bpy.context.collection.objects.link(obj)
            avatar_objects.append(obj)
    apply_material(avatar_objects, "Avatar_Mat", (0.6, 0.6, 0.6, 1.0))

    # 시뮬레이션된 의류 불러오기 — forward_axis='Y', up_axis='Z' : 축 변환 없음
    bpy.ops.wm.obj_import(filepath=sim_obj_path, forward_axis='Y', up_axis='Z')
    clothing_objects = list(bpy.context.selected_objects)
    apply_material(clothing_objects, "Clothing_Mat", (0.2, 0.4, 0.8, 1.0))

    # 렌더링
    render_silhouette(output_dir)
    print("완료")


def apply_material(objects, mat_name, rgba):
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
    mat.use_backface_culling = False  # 양면 렌더링 (메쉬 안쪽 면도 보이도록)

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
