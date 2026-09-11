"""Blender 프로브: cloth_top.blend basis / shape-key extremum OBJ export.

호출:
  blender --background --python probe_cloth_shapekeys.py -- <blend_path> <out_dir>
"""

import bpy
import sys
import os
import json


def clear_shape_keys(mesh_obj):
    if not mesh_obj.data.shape_keys:
        return
    for kb in mesh_obj.data.shape_keys.key_blocks:
        if kb.name == "Basis":
            continue
        kb.value = 0.0


def export_obj(path):
    try:
        bpy.ops.wm.obj_export(
            filepath=path,
            export_selected_objects=False,
            apply_modifiers=True,
        )
    except AttributeError:
        bpy.ops.export_scene.obj(
            filepath=path,
            use_selection=False,
            use_mesh_modifiers=True,
        )


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:]
    blend_path = args[0]
    out_dir = args[1]
    os.makedirs(out_dir, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=blend_path)

    mesh_obj = None
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            mesh_obj = obj
            break
    if mesh_obj is None:
        raise RuntimeError("No mesh in blend")

    key_names = []
    if mesh_obj.data.shape_keys:
        key_names = [kb.name for kb in mesh_obj.data.shape_keys.key_blocks]

    meta = {
        "object": mesh_obj.name,
        "shape_keys": key_names,
        "exports": [],
    }
    print(f"[Probe] object={mesh_obj.name}")
    print(f"[Probe] shape_keys={key_names}")

    # Basis
    clear_shape_keys(mesh_obj)
    bpy.context.view_layer.update()
    basis_path = os.path.join(out_dir, "basis.obj")
    export_obj(basis_path)
    meta["exports"].append({"name": "basis", "path": basis_path, "keys": {}})
    print(f"[Probe] exported basis -> {basis_path}")

    # Each non-Basis key at value=1.0 alone
    key_map = {}
    if mesh_obj.data.shape_keys:
        key_map = {kb.name: kb for kb in mesh_obj.data.shape_keys.key_blocks}

    for name in key_names:
        if name == "Basis":
            continue
        clear_shape_keys(mesh_obj)
        key_map[name].value = 1.0
        bpy.context.view_layer.update()
        safe = name.replace("/", "_")
        path = os.path.join(out_dir, f"{safe}.obj")
        export_obj(path)
        meta["exports"].append({"name": name, "path": path, "keys": {name: 1.0}})
        print(f"[Probe] exported {name}=1.0 -> {path}")

    meta_path = os.path.join(out_dir, "probe_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[Probe] meta -> {meta_path}")


main()
