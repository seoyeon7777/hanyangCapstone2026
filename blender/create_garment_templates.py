"""
create_garment_templates.py — cloth_hoodie / cloth_pants blend 생성

hoodie: cloth_top.blend 복사
pants:  프로시저럴 바지 + waist/hip/inseam/length Shape Keys (Y-up 유지)

Usage:
  blender --background --python create_garment_templates.py -- <clothing_dir>
"""

import bpy
import sys
import os
import math


def clear_scene():
    try:
        bpy.ops.wm.read_homefile(use_empty=True)
    except Exception:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)


def copy_hoodie(clothing_dir: str):
    src = os.path.join(clothing_dir, "cloth_top.blend")
    dst = os.path.join(clothing_dir, "cloth_hoodie.blend")
    if not os.path.exists(src):
        print(f"[Hoodie] skip — missing {src}")
        return False
    bpy.ops.wm.open_mainfile(filepath=src)
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            obj.name = "ClothHoodie"
            break
    bpy.ops.wm.save_as_mainfile(filepath=dst)
    print(f"[Hoodie] saved {dst}")
    return True


def _add_shape_key(obj, name: str):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    return obj.shape_key_add(name=name, from_mix=False)


def create_pants(clothing_dir: str):
    """Blender Z-up 씬에 Y를 세로로 두지 않고, 아바타와 맞추기 쉽게 Z-up 바지 생성.

    측정 코드는 up축을 자동 감지한다.
    """
    clear_scene()

    # Z-up: 허리 위(+Z), 발목 아래(-Z). 단위 ≈ m
    waist_z = 1.00
    hip_z = 0.78
    crotch_z = 0.50
    mid_z = 0.05
    ankle_z = -0.55
    waist_rx, waist_rz = 0.16, 0.11
    hip_rx, hip_rz = 0.20, 0.13
    leg_r = 0.085
    leg_sep = 0.10
    n = 16

    verts = []
    faces = []

    def ring(z, rx, ry, n=16, x_off=0.0):
        idxs = []
        for i in range(n):
            a = 2 * math.pi * i / n
            # Blender: X,Y horizontal, Z up
            verts.append((x_off + rx * math.cos(a), ry * math.sin(a), z))
            idxs.append(len(verts) - 1)
        return idxs

    def bridge(a, b):
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], a[j], b[j], b[i]))

    r_waist = ring(waist_z, waist_rx, waist_rz, n)
    r_hip = ring(hip_z, hip_rx, hip_rz, n)
    r_crotch = ring(crotch_z, hip_rx * 0.92, hip_rz * 0.88, n)
    bridge(r_waist, r_hip)
    bridge(r_hip, r_crotch)

    for sign in (-1.0, 1.0):
        top = ring(crotch_z, leg_r, leg_r * 0.85, n, x_off=sign * leg_sep)
        mid = ring(mid_z, leg_r * 0.95, leg_r * 0.8, n, x_off=sign * leg_sep)
        bot = ring(ankle_z, leg_r * 0.82, leg_r * 0.72, n, x_off=sign * leg_sep)
        bridge(top, mid)
        bridge(mid, bot)

    mesh = bpy.data.meshes.new("PantsMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("ClothPants", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.mesh.normals_make_consistent(inside=False)
    except Exception:
        pass
    bpy.ops.object.mode_set(mode="OBJECT")

    _add_shape_key(obj, "Basis")

    def deform_band(key_name, z_center, z_half, scale_xy):
        kb = _add_shape_key(obj, key_name)
        for i, v in enumerate(obj.data.vertices):
            co = v.co.copy()
            w = 1.0 - min(1.0, abs(co.z - z_center) / max(z_half, 1e-6))
            w = max(0.0, w) ** 1.2
            kb.data[i].co.x = co.x * (1.0 + (scale_xy - 1.0) * w)
            kb.data[i].co.y = co.y * (1.0 + (scale_xy - 1.0) * w)
            kb.data[i].co.z = co.z

    deform_band("waist_max", waist_z, 0.12, 1.28)
    deform_band("waist_min", waist_z, 0.12, 0.78)
    deform_band("hip_max", hip_z, 0.14, 1.30)
    deform_band("hip_min", hip_z, 0.14, 0.78)

    for name, factor in (("inseam_max", 1.20), ("inseam_min", 0.82)):
        kb = _add_shape_key(obj, name)
        for i, v in enumerate(obj.data.vertices):
            co = v.co.copy()
            if co.z < crotch_z:
                t = (co.z - crotch_z) / (ankle_z - crotch_z)
                kb.data[i].co.z = crotch_z + (ankle_z - crotch_z) * t * factor
            else:
                kb.data[i].co = co

    for name, factor in (("length_max", 1.14), ("length_min", 0.88)):
        kb = _add_shape_key(obj, name)
        mid = hip_z
        for i, v in enumerate(obj.data.vertices):
            co = v.co.copy()
            kb.data[i].co.z = mid + (co.z - mid) * factor

    dst = os.path.join(clothing_dir, "cloth_pants.blend")
    bpy.ops.wm.save_as_mainfile(filepath=dst)
    print(f"[Pants] saved {dst} verts={len(verts)} faces={len(faces)}")
    return True


def main():
    argv = sys.argv
    clothing_dir = argv[argv.index("--") + 1] if "--" in argv else None
    if not clothing_dir:
        raise SystemExit("usage: blender --python create_garment_templates.py -- <clothing_dir>")
    os.makedirs(clothing_dir, exist_ok=True)
    create_pants(clothing_dir)
    copy_hoodie(clothing_dir)
    print("[Templates] done")


main()
