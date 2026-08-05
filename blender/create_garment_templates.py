"""
create_garment_templates.py — cloth_hoodie / cloth_pants blend 생성

hoodie: cloth_top.blend 복사 (동일 Shape Key, 별도 파일로 카탈로그 등록)
pants:  단순 프로시저럴 바지 메쉬 + waist/hip/inseam/length Shape Keys

Usage:
  blender --background --python create_garment_templates.py -- \
    /path/to/assets/clothing
"""

import bpy
import sys
import os
import math
from mathutils import Vector


def clear_scene():
    # open_mainfile 이후에도 동작하도록 빈 파일로 리셋
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
    kb = obj.shape_key_add(name=name, from_mix=False)
    return kb


def create_pants(clothing_dir: str):
    """Y-up에 가깝게: 허리 위, 발목 아래. 단위 ≈ Blender 미터 스케일(아바타와 맞춤)."""
    clear_scene()

    # 바지 대략 치수 (Blender unit, cloth_top과 비슷한 스케일 ~1.0 height)
    # cloth_top length mesh ~1.15 → pants longer ~1.6
    waist_y = 1.05
    hip_y = 0.85
    crotch_y = 0.55
    ankle_y = -0.55
    waist_rx, waist_rz = 0.18, 0.12
    hip_rx, hip_rz = 0.22, 0.14
    leg_r = 0.09

    verts = []
    faces = []

    def ring(y, rx, rz, n=16, x_off=0.0):
        idxs = []
        for i in range(n):
            a = 2 * math.pi * i / n
            verts.append((x_off + rx * math.cos(a), y, rz * math.sin(a)))
            idxs.append(len(verts) - 1)
        return idxs

    n = 16
    # torso: waist -> hip -> crotch (single tube)
    r_waist = ring(waist_y, waist_rx, waist_rz, n)
    r_hip = ring(hip_y, hip_rx, hip_rz, n)
    r_crotch = ring(crotch_y, hip_rx * 0.95, hip_rz * 0.9, n)

    def bridge(a, b):
        for i in range(n):
            j = (i + 1) % n
            faces.append((a[i], a[j], b[j], b[i]))

    bridge(r_waist, r_hip)
    bridge(r_hip, r_crotch)

    # legs
    leg_sep = 0.11
    for side, sign in (("L", -1.0), ("R", 1.0)):
        top = ring(crotch_y, leg_r, leg_r * 0.85, n, x_off=sign * leg_sep)
        mid = ring((crotch_y + ankle_y) * 0.5, leg_r * 0.95, leg_r * 0.8, n, x_off=sign * leg_sep)
        bot = ring(ankle_y, leg_r * 0.85, leg_r * 0.75, n, x_off=sign * leg_sep)
        bridge(top, mid)
        bridge(mid, bot)
        # stitch crotch side approx to leg top — skip full boolean for simplicity

    mesh = bpy.data.meshes.new("PantsMesh")
    mesh.from_pydata(verts, [], [f if len(f) == 4 else f for f in faces])
    mesh.update()
    obj = bpy.data.objects.new("ClothPants", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Smooth / normals
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.mesh.normals_make_consistent(inside=False)
    except Exception:
        pass
    bpy.ops.object.mode_set(mode="OBJECT")

    # Shape keys
    basis = _add_shape_key(obj, "Basis")

    def deform_scale_band(key_name, y_center, y_half, scale_xz, scale_y=1.0):
        kb = _add_shape_key(obj, key_name)
        for i, v in enumerate(obj.data.vertices):
            co = v.co
            w = 1.0 - min(1.0, abs(co.y - y_center) / max(y_half, 1e-6))
            w = max(0.0, w)
            kb.data[i].co.x = co.x * (1.0 + (scale_xz - 1.0) * w)
            kb.data[i].co.z = co.z * (1.0 + (scale_xz - 1.0) * w)
            kb.data[i].co.y = co.y + (co.y - y_center) * (scale_y - 1.0) * w * 0.5

    # waist max/min — scale near waist
    deform_scale_band("waist_max", waist_y, 0.15, 1.22)
    deform_scale_band("waist_min", waist_y, 0.15, 0.82)
    deform_scale_band("hip_max", hip_y, 0.18, 1.25)
    deform_scale_band("hip_min", hip_y, 0.18, 0.80)

    # inseam: stretch/compress legs in Y below crotch
    for name, factor in (("inseam_max", 1.18), ("inseam_min", 0.85)):
        kb = _add_shape_key(obj, name)
        for i, v in enumerate(obj.data.vertices):
            co = v.co
            if co.y < crotch_y:
                t = (co.y - crotch_y) / (ankle_y - crotch_y + 1e-6)  # 0 at crotch → 1 at ankle
                kb.data[i].co.y = crotch_y + (ankle_y - crotch_y) * t * factor
            else:
                kb.data[i].co = co

    # length: overall Y scale around hip
    for name, factor in (("length_max", 1.12), ("length_min", 0.90)):
        kb = _add_shape_key(obj, name)
        mid = hip_y
        for i, v in enumerate(obj.data.vertices):
            co = v.co
            kb.data[i].co.y = mid + (co.y - mid) * factor

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
    # pants 먼저 (빈 씬), hoodie는 top 파일 열어서 저장
    create_pants(clothing_dir)
    copy_hoodie(clothing_dir)
    print("[Templates] done")


main()
