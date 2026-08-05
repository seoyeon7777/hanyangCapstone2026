"""
simulate_cloth.py — 블렌더 Cloth Modifier 기반 시뮬레이션

호출 방식:
    blender --background --python simulate_cloth.py -- <params_json_path>

params JSON 구조:
{
    "cloth_obj_path":    "outputs/<job_id>/cloth_shaped.obj",
    "avatar_blend_path": "assets/avatars/body_M.blend",
    "output_obj_path":   "outputs/<job_id>/simulated_cloth.obj",
    "avatar_verts_path": "outputs/<job_id>/avatar_verts.json",
    "fabric_elasticity": 0.15,
    "bending_stiffness": 25.0,
    "garment_type":      "top"
}
"""

import bpy
import sys
import json
import os
import mathutils


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


def import_avatar_from_blend(blend_path):
    """아바타 blend 파일에서 첫 번째 메쉬 오브젝트를 씬에 추가 후 반환"""
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


def align_cloth_to_avatar(cloth_obj, avatar_obj, garment_type="top", avatar_size="M"):
    """
    의류를 아바타에 맞게 배치.

    상의: 셔츠 상단(칼라)을 아바타 어깨 Z에 맞춤.
    하의: 허리밴드(의류 상단)을 허리 Z에 맞춤 + XY 스케일/센터.
    """
    UPPER_BODY = {"top", "shirt", "hoodie", "jacket", "coat", "tshirt", "sweatshirt"}
    gtype = (garment_type or "top").lower()
    is_upper = gtype in UPPER_BODY or gtype not in {"pants", "skirt", "shorts", "trousers"}

    if is_upper:
        COLLAR_RATIO = {"S": 0.85, "M": 0.84, "L": 0.83}
        ratio = COLLAR_RATIO.get(avatar_size.upper(), 0.84)
    else:
        WAIST_RATIO = {"S": 0.61, "M": 0.60, "L": 0.59}
        ratio = WAIST_RATIO.get(avatar_size.upper(), 0.60)

    av_verts = [avatar_obj.matrix_world @ v.co for v in avatar_obj.data.vertices]
    av_zs = [v.z for v in av_verts]
    av_xs = [v.x for v in av_verts]
    av_ys = [v.y for v in av_verts]
    av_zmin, av_zmax = min(av_zs), max(av_zs)
    av_target_z = av_zmin + ratio * (av_zmax - av_zmin)

    # 하의: 목표 Z 근처 아바타 폭에 맞춰 XY 스케일
    if not is_upper:
        band = [v for v in av_verts if abs(v.z - av_target_z) < 0.06]
        if len(band) >= 8:
            av_w = max(v.x for v in band) - min(v.x for v in band)
        else:
            av_w = max(av_xs) - min(av_xs)
        cl_xs = [(cloth_obj.matrix_world @ v.co).x for v in cloth_obj.data.vertices]
        cl_w = max(cl_xs) - min(cl_xs)
        if cl_w > 1e-6 and av_w > 1e-6:
            # 여유분 8%
            scale = (av_w * 1.08) / cl_w
            scale = max(0.55, min(1.8, scale))
            inv = cloth_obj.matrix_world.inverted_safe()
            cx = (min(cl_xs) + max(cl_xs)) * 0.5
            cy = sum((cloth_obj.matrix_world @ v.co).y for v in cloth_obj.data.vertices) / len(cloth_obj.data.vertices)
            for v in cloth_obj.data.vertices:
                w = cloth_obj.matrix_world @ v.co
                w.x = cx + (w.x - cx) * scale
                w.y = cy + (w.y - cy) * scale
                v.co = inv @ w
            cloth_obj.data.update()
            print(f"[Sim] 하의 XY 스케일={scale:.3f} (아바타폭={av_w:.3f}, 옷폭={cl_w:.3f})")

        # XY 센터를 아바타 중심에
        cl_world = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
        cl_cx = (min(c.x for c in cl_world) + max(c.x for c in cl_world)) * 0.5
        cl_cy = (min(c.y for c in cl_world) + max(c.y for c in cl_world)) * 0.5
        av_cx = (min(av_xs) + max(av_xs)) * 0.5
        av_cy = (min(av_ys) + max(av_ys)) * 0.5
        dx, dy = av_cx - cl_cx, av_cy - cl_cy
        offset_xy = cloth_obj.matrix_world.inverted_safe().to_3x3() @ mathutils.Vector((dx, dy, 0))
        for v in cloth_obj.data.vertices:
            v.co += offset_xy
        cloth_obj.data.update()
        print(f"[Sim] 하의 XY 센터 보정: dx={dx:+.3f}, dy={dy:+.3f}")

    cl_verts = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
    cl_zs = [v.z for v in cl_verts]
    cl_top_z = max(cl_zs)

    z_offset = av_target_z - cl_top_z
    offset_local = cloth_obj.matrix_world.inverted_safe().to_3x3() @ mathutils.Vector((0, 0, z_offset))

    for v in cloth_obj.data.vertices:
        v.co += offset_local
    cloth_obj.data.update()

    label = "어깨" if is_upper else "허리"
    print(f"[Sim] 의류 Z 보정: {z_offset:+.3f} (아바타 {label} Z={av_target_z:.3f}, 의류 상단 Z={cl_top_z:.3f})")


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


def create_shoulder_pin_group(cloth_obj, avatar_obj, avatar_size="M"):
    """
    아바타 실제 어깨 높이(world Z) 기준으로 셔츠 버텍스를 핀 그룹 지정.
    top_pct 방식(셔츠 꼭대기 고정)과 달리 아바타 체형에 정확히 맞는
    어깨 위치에서 옷이 걸리도록 함 → 칼라가 어깨 위로 뜨는 문제 해결.

    어깨 비율 산출 근거 (아바타 전체 높이 Z 범위 대비):
      인체 비율상 어깨는 전신의 약 83~86% 높이.
      S/M/L 모두 독립 모델링이므로 크기별로 소폭 조정.
      chest 배치 비율(S:0.72, M:0.71, L:0.68)과 함께 보정.
    """
    SHOULDER_RATIO = {"S": 0.83, "M": 0.84, "L": 0.83}
    ratio     = SHOULDER_RATIO.get(avatar_size.upper(), 0.84)
    tolerance = 0.025  # ±2.5cm — 어깨 솔기 라인만 핀 (너무 넓으면 셔츠가 굳어버림)

    # 아바타 어깨 Z 계산
    av_zs = [(avatar_obj.matrix_world @ v.co).z for v in avatar_obj.data.vertices]
    av_shoulder_z = min(av_zs) + ratio * (max(av_zs) - min(av_zs))

    # 셔츠 버텍스 world 좌표
    cl_world = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
    cl_zs    = [co.z for co in cl_world]
    cl_xs    = [co.x for co in cl_world]

    # X 중심과 절반 너비 계산
    cl_x_center    = (min(cl_xs) + max(cl_xs)) / 2.0
    cl_x_halfwidth = (max(cl_xs) - min(cl_xs)) / 2.0

    # 칼라 링만 핀: Z 범위 + X 중심 이내
    #
    # [수정] 비율(35%) → 절대 상한(5.5cm) + 낮은 비율(22%) 중 작은 값 사용.
    # 이유: L 셔츠처럼 어깨 너비가 넓으면 35%가 8.7cm까지 늘어나
    #       칼라 링 측면 버텍스까지 핀에 걸려 칼라 전체가 T-포즈로 굳음.
    #       → 앞쪽이 내려가지 못해 스퀘어넥처럼 보이는 원인.
    # 22%·5.5cm 상한: S/M/L 모두 칼라 전후(목 앞·뒤) 부분만 핀,
    #               측면은 자유롭게 처져 라운드넥 형태 유지.
    x_limit = min(cl_x_halfwidth * 0.22, 0.055)

    pin_idx = [
        i for i, (z, x) in enumerate(zip(cl_zs, cl_xs))
        if av_shoulder_z - tolerance <= z <= av_shoulder_z + tolerance
        and abs(x - cl_x_center) < x_limit
    ]

    # 폴백: 어깨 높이 근처 버텍스가 너무 적으면 셔츠 상위 2% + X 중심 이내
    if len(pin_idx) < 6:
        z_min, z_max = min(cl_zs), max(cl_zs)
        threshold = z_max - 0.02 * (z_max - z_min)
        pin_idx   = [
            i for i, (z, x) in enumerate(zip(cl_zs, cl_xs))
            if z >= threshold and abs(x - cl_x_center) < x_limit
        ]
        print(f"[Sim] 어깨 핀 폴백: 어깨 Z 근처 버텍스 부족 → 상위 2%+X필터 ({len(pin_idx)}개)")

    # 기존 그룹 정리 후 생성
    for gname in ("CollarPin", "ShoulderPin"):
        if gname in cloth_obj.vertex_groups:
            cloth_obj.vertex_groups.remove(cloth_obj.vertex_groups[gname])

    vg = cloth_obj.vertex_groups.new(name="ShoulderPin")
    vg.add(pin_idx, 1.0, 'REPLACE')
    print(f"[Sim] 어깨 핀: {len(pin_idx)}개 버텍스 (아바타 어깨 Z={av_shoulder_z:.3f} ±{tolerance}, size={avatar_size})")
    return vg.name


def create_waist_pin_group(cloth_obj, avatar_obj, avatar_size="M"):
    """하의 허리밴드 핀 — 아바타 허리 Z 근처 + 바지 상단 링."""
    WAIST_RATIO = {"S": 0.61, "M": 0.60, "L": 0.59}
    ratio = WAIST_RATIO.get(avatar_size.upper(), 0.60)
    tolerance = 0.035

    av_zs = [(avatar_obj.matrix_world @ v.co).z for v in avatar_obj.data.vertices]
    av_waist_z = min(av_zs) + ratio * (max(av_zs) - min(av_zs))

    cl_world = [cloth_obj.matrix_world @ v.co for v in cloth_obj.data.vertices]
    cl_zs = [co.z for co in cl_world]
    z_max = max(cl_zs)
    z_min = min(cl_zs)
    # 상단 12% 또는 허리 Z 밴드
    top_thresh = z_max - 0.12 * (z_max - z_min)

    pin_idx = [
        i for i, z in enumerate(cl_zs)
        if (av_waist_z - tolerance <= z <= av_waist_z + tolerance) or z >= top_thresh
    ]
    # 너무 많으면 상단만
    if len(pin_idx) > max(24, len(cl_zs) // 4):
        pin_idx = [i for i, z in enumerate(cl_zs) if z >= top_thresh]

    if "WaistPin" in cloth_obj.vertex_groups:
        cloth_obj.vertex_groups.remove(cloth_obj.vertex_groups["WaistPin"])
    vg = cloth_obj.vertex_groups.new(name="WaistPin")
    if pin_idx:
        vg.add(pin_idx, 1.0, "REPLACE")
    print(f"[Sim] 허리 핀: {len(pin_idx)}개 버텍스 (아바타 허리 Z={av_waist_z:.3f})")
    return vg.name


def clip_pin_to_avatar_profile(cloth_obj, avatar_obj, pin_indices, offset=0.015):
    """
    핀 버텍스를 아바타 단면(Z-슬라이스) Y 프로파일로 클리핑.

    그룹 이동 스냅의 문제:
      find_nearest 법선이 앞면을 가리키면 앞 칼라가 더 앞으로 밀림.
      → 이동 방향이 문제의 원인이 됨.

    이 함수의 접근:
      1. 핀 버텍스들의 평균 Z에서 아바타 단면 버텍스 추출
      2. 단면의 Y max/min(앞면·뒷면 한계) 계산
      3. 한계를 초과하는 핀 버텍스의 Y 좌표만 클립
      → 앞 돌출(+Y)·뒷 돌출(-Y) 모두 해소, 칼라 링 형태 유지

    offset: 아바타 표면에서 추가로 띄울 간격 (기본 15mm)
    """
    mat     = cloth_obj.matrix_world
    mat_inv = mat.inverted_safe()
    mesh    = cloth_obj.data

    # 핀 버텍스 Z 평균
    z_level = sum(
        (mat @ mesh.vertices[i].co).z for i in pin_indices
    ) / max(len(pin_indices), 1)

    # 아바타 단면: Z ±8cm 범위
    av_at_z = [
        (avatar_obj.matrix_world @ v.co)
        for v in avatar_obj.data.vertices
        if abs((avatar_obj.matrix_world @ v.co).z - z_level) < 0.08
    ]
    if len(av_at_z) < 5:
        print("[Sim] 칼라 클립: 아바타 단면 버텍스 부족, 스킵")
        return

    # 전체 단면 Y 범위 (폴백용)
    global_max_y = max(co.y for co in av_at_z) + offset
    global_min_y = min(co.y for co in av_at_z) - offset

    # X-컬럼별 Y 클리핑:
    # 각 버텍스의 X 위치에서 아바타 단면의 Y 범위를 계산.
    # 전체 단면 Y 범위로 클립하면 어깨 단면의 사각형 윤곽을 따라가
    # 칼라가 스퀘어넥처럼 보이는 문제를 해소함.
    moved = 0
    for idx in pin_indices:
        v   = mesh.vertices[idx]
        wco = mat @ v.co

        # 해당 X 위치 ±3cm 컬럼에서 아바타 Y 범위 계산
        x_col = 0.03
        av_col = [co for co in av_at_z if abs(co.x - wco.x) < x_col]
        if len(av_col) >= 3:
            max_y = max(co.y for co in av_col) + offset
            min_y = min(co.y for co in av_col) - offset
        else:
            max_y = global_max_y
            min_y = global_min_y

        ny = max(min_y, min(max_y, wco.y))
        if abs(ny - wco.y) > 5e-4:
            wco.y = ny
            v.co  = mat_inv @ wco
            moved += 1

    mesh.update()
    print(f"[Sim] 칼라 클립: {moved}/{len(pin_indices)}개 클리핑 "
          f"(아바타 단면 Y=[{global_min_y:.3f}, {global_max_y:.3f}], Z≈{z_level:.3f})")


def map_fabric_to_cloth_settings(mod, fabric_elasticity, bending_stiffness):
    """
    원단 물성값을 블렌더 Cloth modifier 파라미터에 매핑.
    중력은 항상 ON — 상의는 ShoulderPin 그룹으로 어깨 고정.

    Blender cloth 단위 기준 (N/m):
      - 면(cotton) 기본값: tension≈15, bending≈0.5
      - 데님: tension≈40, bending≈4.0
      - 니트/스판: tension≈5, bending≈0.1
    → tension 범위 1~25, bending은 fitting_model 값(/20) 변환
    """
    s = mod.settings

    # elasticity 0.0 → tension 25 (딱딱), elasticity 1.0 → tension 1 (유연)
    tension = 1.0 + 24.0 * (1.0 - fabric_elasticity)
    s.tension_stiffness     = tension
    s.compression_stiffness = tension * 0.8
    s.shear_stiffness       = tension * 0.5

    # fitting_model.py의 bending 값(4~80 범위)을 Blender 단위(0.2~4)로 변환
    bending_blender = max(0.1, bending_stiffness / 20.0)
    s.bending_stiffness = bending_blender

    # 신축성 없을수록 무거운 원단 가정
    s.mass    = 0.3 + (1.0 - fabric_elasticity) * 0.2   # 0.3~0.5 kg/m²
    s.quality = 6    # 8→6 (stiffness 낮으면 수렴 빠름, 타임아웃 방지)

    # 핀 고정 강성 — Blender 4.x에서 기본값이 0일 수 있어 명시 설정
    s.pin_stiffness = 1.0

    print(f"[Sim] Cloth 설정: tension={tension:.2f}, bending={bending_blender:.3f}, mass={s.mass:.2f}")


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]

    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    cloth_obj_path    = params["cloth_obj_path"]
    avatar_blend_path = params["avatar_blend_path"]
    output_obj_path   = params["output_obj_path"]
    avatar_verts_path = params["avatar_verts_path"]
    fabric_elasticity = float(params.get("fabric_elasticity", 0.15))
    bending_stiffness = float(params.get("bending_stiffness", 25.0))
    garment_type      = params.get("garment_type", "top")
    avatar_size       = params.get("avatar_size", "M")

    LOWER_BODY = {"pants", "skirt", "shorts", "trousers"}
    is_upper = garment_type.lower() not in LOWER_BODY

    print(f"[Sim] 옷(OBJ): {cloth_obj_path}")
    print(f"[Sim] 아바타(blend): {avatar_blend_path} (size={avatar_size})")
    print(f"[Sim] 의류 타입: {garment_type}, 핀={'어깨' if is_upper else '허리'}")
    print(f"[Sim] 탄성: {fabric_elasticity}, 굽힘: {bending_stiffness}")

    clear_scene()

    avatar_obj = import_avatar_from_blend(avatar_blend_path)
    avatar_obj.name = "Avatar"
    print(f"[Sim] 아바타 오브젝트: {avatar_obj.name}")

    cloth_obj = import_obj(cloth_obj_path)
    cloth_obj.name = "Cloth"

    align_cloth_to_avatar(cloth_obj, avatar_obj, garment_type=garment_type, avatar_size=avatar_size)

    expand_amt = 0.035 if is_upper else 0.025
    expand_cloth(cloth_obj, avatar_obj, amount=expand_amt)

    bpy.ops.object.select_all(action="DESELECT")
    avatar_obj.select_set(True)
    bpy.context.view_layer.objects.active = avatar_obj
    bpy.ops.object.modifier_add(type="COLLISION")
    col_mod = next((m for m in avatar_obj.modifiers if m.type == "COLLISION"), None)
    if col_mod:
        col_mod.settings.thickness_outer = 0.002
        col_mod.settings.thickness_inner = 0.004
        col_mod.settings.cloth_friction = 5.0
    print("[Sim] Avatar Collision modifier 적용 완료")

    bpy.ops.object.select_all(action="DESELECT")
    cloth_obj.select_set(True)
    bpy.context.view_layer.objects.active = cloth_obj
    bpy.ops.object.modifier_add(type="CLOTH")
    cloth_mod = next((m for m in cloth_obj.modifiers if m.type == "CLOTH"), None)
    if not cloth_mod:
        raise RuntimeError("Cloth modifier 추가 실패")
    map_fabric_to_cloth_settings(cloth_mod, fabric_elasticity, bending_stiffness)

    if is_upper:
        pin_name = create_shoulder_pin_group(cloth_obj, avatar_obj, avatar_size=avatar_size)
        pin_vg = cloth_obj.vertex_groups.get(pin_name)
        if pin_vg:
            pin_vg_idx = pin_vg.index
            pin_id_list = [v.index for v in cloth_obj.data.vertices
                           if any(g.group == pin_vg_idx for g in v.groups)]
            clip_pin_to_avatar_profile(cloth_obj, avatar_obj, pin_id_list, offset=0.015)
        cloth_mod.settings.vertex_group_mass = pin_name
        print("[Sim] 어깨 핀 그룹 Cloth modifier에 연결 완료")
    else:
        pin_name = create_waist_pin_group(cloth_obj, avatar_obj, avatar_size=avatar_size)
        pin_vg = cloth_obj.vertex_groups.get(pin_name)
        if pin_vg:
            pin_vg_idx = pin_vg.index
            pin_id_list = [v.index for v in cloth_obj.data.vertices
                           if any(g.group == pin_vg_idx for g in v.groups)]
            if pin_id_list:
                clip_pin_to_avatar_profile(cloth_obj, avatar_obj, pin_id_list, offset=0.012)
        cloth_mod.settings.vertex_group_mass = pin_name
        print("[Sim] 허리 핀 그룹 Cloth modifier에 연결 완료")

    print("[Sim] Cloth modifier 적용 완료")

    # 시뮬레이션 실행
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = 35   # 60→35프레임 (stiffness 낮으면 빨리 안정됨, 타임아웃 방지)

    # depsgraph 갱신 — 핀 그룹·버텍스 이동 후 modifier가 최신 상태를 인식하도록
    bpy.context.view_layer.update()

    print("[Sim] 시뮬레이션 시작 (35프레임)...")
    scene.frame_set(1)
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        if frame % 5 == 0:
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

    # 아바타 버텍스 JSON 저장 (압박도 계산용 — body_*.obj 대체)
    avatar_verts = [[v.co.x, v.co.y, v.co.z] for v in avatar_obj.data.vertices]
    with open(avatar_verts_path, "w", encoding="utf-8") as f:
        json.dump(avatar_verts, f)
    print(f"[Sim] 아바타 버텍스 저장: {avatar_verts_path}")


main()
