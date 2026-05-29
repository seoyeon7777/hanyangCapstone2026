"""
export_cloth.py — 의류 blend 파일에 shape key 적용 후 OBJ export

호출 방식:
    blender --background --python export_cloth.py -- <params_json_path>

params JSON 구조:
{
    "blend_path": "assets/clothing/cloth_top.blend",
    "output_obj": "outputs/<job_id>/cloth_shaped.obj",
    "shape_keys": {"chest": 0.3, "shoulder": -0.1, ...}   # -1~1
}
"""

import bpy, sys, json, os


def main():
    argv = sys.argv
    params_path = argv[argv.index("--") + 1]

    with open(params_path, encoding="utf-8") as f:
        params = json.load(f)

    blend_path     = params["blend_path"]
    output_obj     = params["output_obj"]
    shape_keys_raw = params.get("shape_keys", {})  # -1~1 값

    # .blend 파일 열기
    bpy.ops.wm.open_mainfile(filepath=blend_path)

    # 메쉬 오브젝트 찾기
    mesh_obj = None
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            mesh_obj = obj
            break

    if not mesh_obj:
        raise RuntimeError("메쉬 오브젝트를 찾을 수 없습니다.")

    print(f"[Export] 오브젝트: {mesh_obj.name}")

    # Shape Key 적용
    # fitting_model shape_key 값(-1~1) → _min/_max 구조 매핑
    # 음수(타이트) → {부위}_min 에 절댓값 적용
    # 양수(여유)   → {부위}_max 에 값 그대로 적용
    if mesh_obj.data.shape_keys:
        key_names = [kb.name for kb in mesh_obj.data.shape_keys.key_blocks]
        print(f"[Export] 사용 가능한 Shape Key: {key_names}")

        key_map = {kb.name.lower(): kb for kb in mesh_obj.data.shape_keys.key_blocks}

        for region, raw_val in shape_keys_raw.items():
            if raw_val < 0:
                target      = f"{region}_min"
                blender_val = min(1.0, abs(raw_val))
            else:
                target      = f"{region}_max"
                blender_val = min(1.0, raw_val)

            if target in key_map:
                key_map[target].value = blender_val
                print(f"[Export] Shape Key '{target}' = {blender_val:.3f}")
            else:
                print(f"[Export] Shape Key '{target}' 없음 — 건너뜀")
    else:
        print("[Export] Shape Key 없음 — 기본 메쉬 그대로 export")

    # OBJ export
    try:
        bpy.ops.wm.obj_export(
            filepath=output_obj,
            export_selected_objects=False,
            apply_modifiers=True,
        )
    except AttributeError:
        bpy.ops.export_scene.obj(
            filepath=output_obj,
            use_selection=False,
            use_mesh_modifiers=True,
        )

    print(f"[Export] OBJ 저장: {output_obj}")


main()
