"""
drape_pattern.py — 패턴 베이스 메쉬를 아바타 월드 스케일에 맞춘 뒤 cloth sim.

기존 simulate_cloth.py 로직을 재사용하되, OBJ 임포트 후
아바타 키에 맞게 균등 스케일 + Z 정렬을 먼저 수행한다.
"""

import bpy
import sys
import json
import os
import mathutils


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)


def import_obj(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path)
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=path)
    added = [o for o in bpy.data.objects if o not in before]
    if not added:
        raise RuntimeError(f"OBJ 임포트 실패: {path}")
    # join if multiple
    if len(added) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in added:
            o.select_set(True)
        bpy.context.view_layer.objects.active = added[0]
        bpy.ops.object.join()
        return bpy.context.view_layer.objects.active
    return added[0]


def import_avatar_from_blend(blend_path):
    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    added = []
    for obj in data_to.objects:
        if obj is not None and obj.type == "MESH":
            bpy.context.collection.objects.link(obj)
            added.append(obj)
    if not added:
        raise RuntimeError(f"아바타 blend에서 메쉬를 찾을 수 없음: {blend_path}")
    return added[0]


def world_bbox(obj):
    corners = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    xs = [v.x for v in corners]
    ys = [v.y for v in corners]
    zs = [v.z for v in corners]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def scale_cloth_to_avatar(cloth_obj, avatar_obj, length_ratio=0.38):
    """
    패턴 메쉬는 실측 meter. 아바타 blend는 임의 스케일이므로
    아바타 키의 length_ratio(상의 총기장 비율)에 맞게 균등 스케일.
    """
    amin, amax = world_bbox(avatar_obj)
    cmin, cmax = world_bbox(cloth_obj)
    av_h = max(amax[2] - amin[2], 1e-6)
    cl_h = max(cmax[2] - cmin[2], 1e-6)
    target_h = av_h * length_ratio
    s = target_h / cl_h
    cloth_obj.scale = (s, s, s)
    bpy.context.view_layer.update()
    print(f"[Drape] scale={s:.4f} (avatar_h={av_h:.3f}, cloth_h={cl_h:.3f}, target_h={target_h:.3f})")


def align_collar_to_shoulder(cloth_obj, avatar_obj, avatar_size="M"):
    COLLAR_RATIO = {"S": 0.85, "M": 0.84, "L": 0.83}
    ratio = COLLAR_RATIO.get(avatar_size.upper(), 0.84)
    av_verts = [avatar_obj.matrix_world @ v.co for v in avatar_obj.data.vertices]
    av_zs = [v.z for v in av_verts]
    av_target_z = min(av_zs) + ratio * (max(av_zs) - min(av_zs))

    bpy.context.view_layer.update()
    cl_verts = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
    cl_top_z = max(v.z for v in cl_verts)
    z_offset = av_target_z - cl_top_z
    cloth_obj.location.z += z_offset
    bpy.context.view_layer.update()
    print(f"[Drape] Z align {z_offset:+.3f} → collar≈{av_target_z:.3f}")


def export_obj(obj, path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=True,
            apply_modifiers=True,
        )
    except AttributeError:
        bpy.ops.export_scene.obj(
            filepath=path,
            use_selection=True,
            use_mesh_modifiers=True,
        )


def create_shoulder_pin(cloth_obj, avatar_obj, avatar_size="M"):
    SHOULDER_RATIO = {"S": 0.83, "M": 0.84, "L": 0.83}
    ratio = SHOULDER_RATIO.get(avatar_size.upper(), 0.84)
    tolerance = 0.03
    av_zs = [(avatar_obj.matrix_world @ v.co).z for v in avatar_obj.data.vertices]
    av_shoulder_z = min(av_zs) + ratio * (max(av_zs) - min(av_zs))
    cl_world = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
    cl_zs = [co.z for co in cl_world]
    cl_xs = [co.x for co in cl_world]
    cl_x_center = 0.5 * (min(cl_xs) + max(cl_xs))
    x_limit = min((max(cl_xs) - min(cl_xs)) * 0.15, 0.08)
    pin_idx = [
        i for i, (z, x) in enumerate(zip(cl_zs, cl_xs))
        if abs(z - av_shoulder_z) <= tolerance and abs(x - cl_x_center) < x_limit
    ]
    if len(pin_idx) < 6:
        z_max = max(cl_zs)
        pin_idx = [i for i, z in enumerate(cl_zs) if z >= z_max - 0.03 * (z_max - min(cl_zs))]
    if "ShoulderPin" in cloth_obj.vertex_groups:
        cloth_obj.vertex_groups.remove(cloth_obj.vertex_groups["ShoulderPin"])
    vg = cloth_obj.vertex_groups.new(name="ShoulderPin")
    vg.add(pin_idx, 1.0, "REPLACE")
    print(f"[Drape] pin verts={len(pin_idx)}")
    return vg.name


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]
    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    clear_scene()
    avatar = import_avatar_from_blend(params["avatar_blend_path"])
    avatar.name = "Avatar"
    cloth = import_obj(params["cloth_obj_path"])
    cloth.name = "Cloth"

    # apply import transforms
    bpy.ops.object.select_all(action="DESELECT")
    cloth.select_set(True)
    bpy.context.view_layer.objects.active = cloth
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    scale_cloth_to_avatar(cloth, avatar, length_ratio=float(params.get("length_ratio", 0.38)))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    align_collar_to_shoulder(cloth, avatar, params.get("avatar_size", "M"))

    # slight inflate
    avg = mathutils.Vector((0, 0, 0))
    for v in avatar.data.vertices:
        avg += avatar.matrix_world @ v.co
    avg /= max(len(avatar.data.vertices), 1)
    for v in cloth.data.vertices:
        w = cloth.matrix_world @ v.co
        d = w - avg
        if d.length > 1e-6:
            v.co += cloth.matrix_world.inverted() @ (d.normalized() * 0.02)
    cloth.data.update()

    # collision
    bpy.ops.object.select_all(action="DESELECT")
    avatar.select_set(True)
    bpy.context.view_layer.objects.active = avatar
    bpy.ops.object.modifier_add(type="COLLISION")

    # cloth
    bpy.ops.object.select_all(action="DESELECT")
    cloth.select_set(True)
    bpy.context.view_layer.objects.active = cloth
    bpy.ops.object.modifier_add(type="CLOTH")
    mod = next(m for m in cloth.modifiers if m.type == "CLOTH")
    elasticity = float(params.get("fabric_elasticity", 0.15))
    bending = float(params.get("bending_stiffness", 25.0))
    tension = 1.0 + 24.0 * (1.0 - elasticity)
    mod.settings.tension_stiffness = tension
    mod.settings.compression_stiffness = tension * 0.8
    mod.settings.shear_stiffness = tension * 0.5
    mod.settings.bending_stiffness = max(0.1, bending / 20.0)
    mod.settings.mass = 0.3 + (1.0 - elasticity) * 0.2
    mod.settings.quality = 6
    mod.settings.pin_stiffness = 1.0

    pin = create_shoulder_pin(cloth, avatar, params.get("avatar_size", "M"))
    mod.settings.vertex_group_mass = pin

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 30
    bpy.context.view_layer.update()
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)

    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.modifier_add(type="SMOOTH")
    sm = next(m for m in cloth.modifiers if m.type == "SMOOTH")
    sm.iterations = 8
    sm.factor = 0.6
    bpy.ops.object.modifier_apply(modifier=sm.name)

    export_obj(cloth, params["output_obj_path"])
    avatar_verts = [[v.co.x, v.co.y, v.co.z] for v in avatar.data.vertices]
    with open(params["avatar_verts_path"], "w", encoding="utf-8") as f:
        json.dump(avatar_verts, f)
    print(f"[Drape] saved {params['output_obj_path']}")


main()
