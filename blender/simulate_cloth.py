"""
simulate_cloth.py — 블렌더 Cloth Modifier 기반 시뮬레이션

호출 방식:
    blender --background --python simulate_cloth.py -- <params_json_path>

params JSON 구조:
{
    "cloth_obj_path":   "...",   # export_cloth.py가 뽑아낸 OBJ 경로
    "avatar_obj_path":  "...",   # 아바타 OBJ 경로
    "output_obj_path":  "...",   # 시뮬 결과 저장 경로
    "fabric_elasticity": 0.15,  # 0~1
    "bending_stiffness": 25.0
}

※ 이 파일은 별도 의류 OBJ와 아바타 OBJ가 있을 때 사용.
   현재는 avatar_*.blend 방식을 사용 중 (script.py에서 처리).
"""

import bpy
import sys
import json
import os


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)


def import_obj(path):
    """OBJ 파일 임포트 후 오브젝트 반환 (블렌더 4.x / 3.x 호환)"""
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path)
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=path)
    added = [o for o in bpy.data.objects if o not in before]
    if not added:
        raise RuntimeError(f"OBJ 임포트 실패: {path}")
    return added[0]


def export_obj(obj, path):
    """선택된 오브젝트만 OBJ 저장 (블렌더 4.x / 3.x 호환)"""
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


def expand_cloth(cloth_obj, avatar_obj, amount=0.04):
    """
    옷을 아바타 중심에서 바깥쪽으로 팽창시켜 초기 관통 방지.
    """
    import mathutils

    avg = mathutils.Vector((0, 0, 0))
    for v in avatar_obj.data.vertices:
        avg += avatar_obj.matrix_world @ v.co
    avg /= len(avatar_obj.data.vertices)

    mesh = cloth_obj.data
    for v in mesh.vertices:
        world_co = cloth_obj.matrix_world @ v.co
        d = world_co - avg
        if d.length > 1e-6:
            v.co += cloth_obj.matrix_world.inverted() @ (d.normalized() * amount)

    mesh.update()
    print(f"[Sim] 옷 팽창 완료 (amount={amount})")


def map_fabric_to_cloth_settings(mod, fabric_elasticity, bending_stiffness):
    """
    원단 물성값을 블렌더 Cloth modifier 파라미터에 매핑.
    """
    s = mod.settings

    # elasticity 0.0 → tension 500 (딱딱), elasticity 1.0 → tension 5 (유연)
    tension = 500 - 495 * fabric_elasticity
    s.tension_stiffness     = tension
    s.compression_stiffness = tension * 0.8
    s.shear_stiffness       = tension * 0.5
    s.bending_stiffness     = bending_stiffness

    # 신축성 없을수록 무거운 원단 가정
    s.mass    = 0.1 + (1 - fabric_elasticity) * 0.4
    s.quality = 5

    print(f"[Sim] Cloth 설정: tension={tension:.1f}, bending={bending_stiffness:.1f}, mass={s.mass:.2f}")


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]

    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    cloth_obj_path    = params["cloth_obj_path"]
    avatar_obj_path   = params["avatar_obj_path"]
    output_obj_path   = params["output_obj_path"]
    fabric_elasticity = float(params.get("fabric_elasticity", 0.15))
    bending_stiffness = float(params.get("bending_stiffness", 25.0))

    print(f"[Sim] 옷: {cloth_obj_path}")
    print(f"[Sim] 아바타: {avatar_obj_path}")
    print(f"[Sim] 탄성: {fabric_elasticity}, 굽힘: {bending_stiffness}")

    clear_scene()

    avatar_obj = import_obj(avatar_obj_path)
    avatar_obj.name = "Avatar"
    cloth_obj  = import_obj(cloth_obj_path)
    cloth_obj.name  = "Cloth"

    # 초기 팽창 (관통 방지)
    expand_cloth(cloth_obj, avatar_obj, amount=0.04)

    # 아바타에 Collision modifier 적용
    bpy.ops.object.select_all(action="DESELECT")
    avatar_obj.select_set(True)
    bpy.context.view_layer.objects.active = avatar_obj
    bpy.ops.object.modifier_add(type="COLLISION")
    col_mod = next((m for m in avatar_obj.modifiers if m.type == "COLLISION"), None)
    if col_mod:
        col_mod.settings.thickness_outer = 0.002
        col_mod.settings.thickness_inner = 0.004
        col_mod.settings.cloth_friction  = 5.0
    print("[Sim] Avatar Collision modifier 적용 완료")

    # 옷에 Cloth modifier 적용
    bpy.ops.object.select_all(action="DESELECT")
    cloth_obj.select_set(True)
    bpy.context.view_layer.objects.active = cloth_obj
    bpy.ops.object.modifier_add(type="CLOTH")
    cloth_mod = next((m for m in cloth_obj.modifiers if m.type == "CLOTH"), None)
    if not cloth_mod:
        raise RuntimeError("Cloth modifier 추가 실패")
    map_fabric_to_cloth_settings(cloth_mod, fabric_elasticity, bending_stiffness)
    print("[Sim] Cloth modifier 적용 완료")

    # 시뮬레이션 실행
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = 25

    print("[Sim] 시뮬레이션 시작 (25프레임)...")
    scene.frame_set(1)
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        if frame % 10 == 0:
            print(f"[Sim] 프레임 {frame}/{scene.frame_end}")
    print("[Sim] 시뮬레이션 완료")

    # Cloth modifier 적용 (mesh로 굳히기)
    bpy.ops.object.select_all(action="DESELECT")
    cloth_obj.select_set(True)
    bpy.context.view_layer.objects.active = cloth_obj
    cloth_mod_name = next((m.name for m in cloth_obj.modifiers if m.type == "CLOTH"), None)
    if cloth_mod_name:
        bpy.ops.object.modifier_apply(modifier=cloth_mod_name)

    # Smooth 모디파이어로 미세 뾰족함 제거
    bpy.ops.object.modifier_add(type="SMOOTH")
    smooth_mod = next((m for m in cloth_obj.modifiers if m.type == "SMOOTH"), None)
    if smooth_mod:
        smooth_mod.iterations = 12
        smooth_mod.factor     = 0.8
        bpy.ops.object.modifier_apply(modifier=smooth_mod.name)
    print("[Sim] 스무딩 완료")

    # 결과 OBJ 저장
    export_obj(cloth_obj, output_obj_path)
    print(f"[Sim] 결과 저장: {output_obj_path}")


main()
