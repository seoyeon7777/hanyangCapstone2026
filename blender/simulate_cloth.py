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
    """OBJ 파일 임포트 후 오브젝트 반환 (블렌더 4.x / 3.x 호환)
    forward_axis='Y', up_axis='Z' → Blender 기본 축 그대로 (변환 없음)
    """
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.obj_import(filepath=path, forward_axis='Y', up_axis='Z')
    except AttributeError:
        bpy.ops.import_scene.obj(filepath=path)
    added = [o for o in bpy.data.objects if o not in before]
    if not added:
        raise RuntimeError(f"OBJ 임포트 실패: {path}")
    return added[0]


def import_blend(path):
    """blend 파일에서 메쉬 오브젝트 임포트 후 반환"""
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
    added = []
    for obj in data_to.objects:
        if obj is not None and obj.type == "MESH":
            bpy.context.collection.objects.link(obj)
            added.append(obj)
    if not added:
        raise RuntimeError(f"Blend 임포트 실패: {path}")
    return added[0]


def export_obj(obj, path):
    """선택된 오브젝트만 OBJ 저장 (블렌더 4.x / 3.x 호환)
    forward_axis='Y', up_axis='Z' → Blender 기본 축 그대로 (변환 없음)
    """
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=True,
            apply_modifiers=True,
            forward_axis='Y',
            up_axis='Z',
        )
    except AttributeError:
        bpy.ops.export_scene.obj(
            filepath=path,
            use_selection=True,
            use_mesh_modifiers=True,
        )


def expand_cloth(cloth_obj, avatar_obj, amount=0.04):
    """
    옷을 아바타 무게중심에서 바깥쪽으로 팽창시켜 초기 관통 방지.
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


def fix_waistband_penetration(cloth_obj, avatar_obj, top_ratio=0.15, offset=0.006):
    """
    핀으로 고정될 허리 버텍스 중 아바타 안에 있는 것만 골라 바깥으로 꺼냄.
    centroid 팽창 후에도 등쪽·옆구리 허리 버텍스가 아바타 안에 남을 수 있음.
    핀 고정 전에 실행해야 함 — 핀이 걸리면 시뮬로 절대 수정 불가.
    전체 메쉬 대신 허리 영역만 BVH로 처리하므로 사타구니 등 복잡한 부위는 건드리지 않음.
    """
    from mathutils.bvhtree import BVHTree

    avatar_matrix = avatar_obj.matrix_world
    verts_world   = [avatar_matrix @ v.co for v in avatar_obj.data.vertices]
    polys         = [list(p.vertices) for p in avatar_obj.data.polygons]
    bvh           = BVHTree.FromPolygons(verts_world, polys)

    cloth_mesh       = cloth_obj.data
    cloth_matrix     = cloth_obj.matrix_world
    cloth_matrix_inv = cloth_matrix.inverted()

    zvals     = [v.co.z for v in cloth_mesh.vertices]
    z_max     = max(zvals)
    z_min     = min(zvals)
    threshold = z_max - (z_max - z_min) * top_ratio

    fixed = 0
    for v in cloth_mesh.vertices:
        if v.co.z < threshold:
            continue  # 허리 영역 버텍스만 처리

        world_co = cloth_matrix @ v.co
        location, normal, index, distance = bvh.find_nearest(world_co)

        if location is None or normal is None:
            continue

        direction = world_co - location
        is_inside = (direction.length < 1e-6) or (direction.dot(normal) < 0)

        if is_inside or distance < offset:
            v.co = cloth_matrix_inv @ (location + normal * offset)
            fixed += 1

    cloth_mesh.update()
    print(f"[Sim] 허리 버텍스 관통 보정 완료: {fixed}개 이동")


def pin_waistband(cloth_obj, cloth_mod, top_ratio=0.15):
    """
    바지 허리 부분 버텍스를 핀 그룹으로 고정.
    상위 top_ratio(기본 15%) Z값 버텍스를 허리띠로 간주하여 고정.
    중력으로 인해 바지가 아래로 처지는 현상 방지.
    """
    mesh  = cloth_obj.data
    verts = mesh.vertices

    if not verts:
        return

    zvals     = [v.co.z for v in verts]
    z_max     = max(zvals)
    z_min     = min(zvals)
    threshold = z_max - (z_max - z_min) * top_ratio

    vg          = cloth_obj.vertex_groups.new(name="Waistband_Pin")
    pin_indices = [v.index for v in verts if v.co.z >= threshold]
    vg.add(pin_indices, 1.0, "REPLACE")

    # Blender 버전별 핀 그룹 속성 이름 차이 처리
    for attr in ("vertex_group_mass", "vertex_group_pin"):
        if hasattr(cloth_mod.settings, attr):
            setattr(cloth_mod.settings, attr, "Waistband_Pin")
            print(f"[Sim] 허리 핀 그룹 설정: {attr} = Waistband_Pin ({len(pin_indices)}개 버텍스)")
            break


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

    cloth_obj_path      = params["cloth_obj_path"]
    avatar_blend_path   = params["avatar_blend_path"]
    avatar_obj_export   = params["avatar_obj_export"]   # 압박도 계산용 OBJ 저장 경로
    output_obj_path     = params["output_obj_path"]
    fabric_elasticity   = float(params.get("fabric_elasticity", 0.15))
    bending_stiffness   = float(params.get("bending_stiffness", 25.0))
    garment_type        = params.get("garment_type", "tshirt")
    no_sim              = bool(params.get("no_sim", False))
    z_offset            = float(params.get("z_offset", 0.0))
    expand_normals      = float(params.get("expand_normals", 0.0))

    print(f"[Sim] 옷: {cloth_obj_path}")
    print(f"[Sim] 아바타: {avatar_blend_path}")
    print(f"[Sim] no_sim={no_sim}")

    clear_scene()

    avatar_obj = import_blend(avatar_blend_path)
    avatar_obj.name = "Avatar"
    export_obj(avatar_obj, avatar_obj_export)
    print(f"[Sim] 아바타 OBJ 저장: {avatar_obj_export}")

    cloth_obj = import_obj(cloth_obj_path)
    cloth_obj.name = "Cloth"

    if no_sim:
        mesh = cloth_obj.data

        # Z 오프셋 적용 (허리 높이 보정)
        if z_offset != 0.0:
            for v in mesh.vertices:
                v.co.z += z_offset
            mesh.update()
            print(f"[Sim] Z 오프셋 적용: {z_offset:+.3f}m")

        # Subdivision Surface — OBJ는 shape key가 이미 구워진 상태라 안전하게 적용 가능
        bpy.ops.object.select_all(action="DESELECT")
        cloth_obj.select_set(True)
        bpy.context.view_layer.objects.active = cloth_obj
        bpy.ops.object.modifier_add(type="SUBSURF")
        subsurf_mod = next((m for m in cloth_obj.modifiers if m.type == "SUBSURF"), None)
        if subsurf_mod:
            subsurf_mod.levels           = 1
            subsurf_mod.render_levels    = 1
            subsurf_mod.subdivision_type = "CATMULL_CLARK"
            bpy.ops.object.modifier_apply(modifier=subsurf_mod.name)
            mesh = cloth_obj.data
            print(f"[Sim] Subdivision 적용: {len(mesh.polygons)}개 페이스")

        # 법선 방향 팽창 (뚫림 완화 — Blender 4.x: v.normal 자동 계산)
        if expand_normals > 0.0:
            for v in mesh.vertices:
                v.co += v.normal * expand_normals
            mesh.update()
            print(f"[Sim] 법선 팽창 적용: {expand_normals:.4f}m")

        # Smooth modifier로 팽창 후 울퉁불퉁한 부분 완화
        bpy.ops.object.select_all(action="DESELECT")
        cloth_obj.select_set(True)
        bpy.context.view_layer.objects.active = cloth_obj
        bpy.ops.object.modifier_add(type="SMOOTH")
        smooth_mod = next((m for m in cloth_obj.modifiers if m.type == "SMOOTH"), None)
        if smooth_mod:
            smooth_mod.iterations = 3
            smooth_mod.factor     = 0.5
            bpy.ops.object.modifier_apply(modifier=smooth_mod.name)
            print("[Sim] 스무딩 적용 완료")

        export_obj(cloth_obj, output_obj_path)
        print(f"[Sim] 시뮬레이션 건너뜀 — 보정 메쉬 저장: {output_obj_path}")
        return

    print(f"[Sim] 탄성: {fabric_elasticity}, 굽힘: {bending_stiffness}")

    # 초기 팽창 — 핀 고정 전 허리띠가 아바타에서 너무 멀면 핀이 잘못된 위치에 고정됨
    # pants: 4cm (기존 8cm → 핀이 13cm 바깥에 걸리던 문제 해결)
    expand_amount = 0.04 if garment_type == "pants" else 0.04
    expand_cloth(cloth_obj, avatar_obj, amount=expand_amount)

    # ── 바지 추가 전처리 (시뮬 전 정확한 위치 확보) ──────────────────────
    # no_sim 모드에서 시각적으로 잘 나오던 것과 동일한 순서로 전처리 적용
    if garment_type == "pants":
        mesh = cloth_obj.data

        # 1) Z 오프셋 (허리 높이 맞춤)
        if z_offset != 0.0:
            for v in mesh.vertices:
                v.co.z += z_offset
            mesh.update()
            print(f"[Sim] 바지 Z 오프셋 적용: {z_offset:+.3f}m")

        # 2) Subdivision — 관통 감지 정밀도 향상 (페이스 수 ↑)
        bpy.ops.object.select_all(action="DESELECT")
        cloth_obj.select_set(True)
        bpy.context.view_layer.objects.active = cloth_obj
        bpy.ops.object.modifier_add(type="SUBSURF")
        subsurf_mod = next((m for m in cloth_obj.modifiers if m.type == "SUBSURF"), None)
        if subsurf_mod:
            subsurf_mod.levels           = 1
            subsurf_mod.render_levels    = 1
            subsurf_mod.subdivision_type = "CATMULL_CLARK"
            bpy.ops.object.modifier_apply(modifier=subsurf_mod.name)
            mesh = cloth_obj.data
            print(f"[Sim] Subdivision 적용: {len(mesh.polygons)}개 페이스")

        # 3) 법선 방향 팽창 — 아바타 표면 바깥으로 메쉬를 밀어냄
        if expand_normals > 0.0:
            bpy.ops.object.select_all(action="DESELECT")
            cloth_obj.select_set(True)
            bpy.context.view_layer.objects.active = cloth_obj
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')
            mesh = cloth_obj.data
            for v in mesh.vertices:
                v.co += v.normal * expand_normals
            mesh.update()
            print(f"[Sim] 시뮬 전 법선 팽창 적용: {expand_normals:.4f}m")
    # ─────────────────────────────────────────────────────────────────────

    # 아바타에 Collision modifier 적용
    bpy.ops.object.select_all(action="DESELECT")
    avatar_obj.select_set(True)
    bpy.context.view_layer.objects.active = avatar_obj
    bpy.ops.object.modifier_add(type="COLLISION")
    col_mod = next((m for m in avatar_obj.modifiers if m.type == "COLLISION"), None)
    if col_mod:
        thickness = 0.008 if garment_type == "pants" else 0.002
        col_mod.settings.thickness_outer = thickness
        col_mod.settings.thickness_inner = thickness * 2
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

    if garment_type == "pants":
        pin_waistband(cloth_obj, cloth_mod)   # 허리 고정 (중력 있어도 아래로 안 떨어짐)
        bpy.context.scene.use_gravity = False
        print("[Sim] 바지: 씬 중력 비활성화")

        # 골반·허벅지 곡면에서 관통 방지
        cloth_mod.settings.quality = 8
        col_mod.settings.thickness_outer = 0.010
        col_mod.settings.thickness_inner = 0.018

        coll_settings = cloth_mod.collision_settings
        coll_settings.use_self_collision = False   # 자기충돌 OFF (불필요 + 성능 저하)
        coll_settings.collision_quality  = 8

    print("[Sim] Cloth modifier 적용 완료")

    # 바지: 20프레임 (quality 8 기준 300초 이내)
    # 티셔츠: 25프레임 (중력 드레이프 포함)
    sim_frames = 20 if garment_type == "pants" else 25
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = sim_frames

    print(f"[Sim] 시뮬레이션 시작 ({sim_frames}프레임)...")
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

    export_obj(cloth_obj, output_obj_path)
    print(f"[Sim] 결과 저장: {output_obj_path}")


main()
