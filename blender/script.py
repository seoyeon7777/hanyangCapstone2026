import bpy
import sys
import os
import json
import math
import mathutils

# 커맨드라인 인자 파싱
argv = sys.argv
argv = argv[argv.index("--") + 1:]

avatar_size = argv[0]
shape_keys  = json.loads(argv[1])
output_dir  = argv[2]

os.makedirs(output_dir, exist_ok=True)

# 메시 오브젝트 가져오기
mesh_obj = None
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        mesh_obj = obj
        break

if mesh_obj is None:
    print("ERROR: 메시 오브젝트를 찾을 수 없습니다")
    sys.exit(1)

# Shape Key 적용
if mesh_obj.data.shape_keys:
    for key_name, value in shape_keys.items():
        if key_name in mesh_obj.data.shape_keys.key_blocks:
            mesh_obj.data.shape_keys.key_blocks[key_name].value = value
            print(f"Shape Key 적용: {key_name} = {value}")
else:
    print("Shape Key 없음 — 기본 메시로 렌더링합니다")

# 기존 카메라/조명 모두 삭제
for obj in bpy.data.objects:
    if obj.type in ['CAMERA', 'LIGHT']:
        bpy.data.objects.remove(obj, do_unlink=True)

# 아바타 바운딩박스로 중심/크기 계산
bbox = [mesh_obj.matrix_world @ mathutils.Vector(c) for c in mesh_obj.bound_box]
min_x = min(v.x for v in bbox)
max_x = max(v.x for v in bbox)
min_y = min(v.y for v in bbox)
max_y = max(v.y for v in bbox)
min_z = min(v.z for v in bbox)
max_z = max(v.z for v in bbox)

center_x = (min_x + max_x) / 2
center_y = (min_y + max_y) / 2
center_z = (min_z + max_z) / 2
height   = max_z - min_z

# 카메라 추가
cam_distance = height * 1.4
cam_z        = center_z + (height * 0.2)

bpy.ops.object.camera_add(location=(center_x, center_y - cam_distance, cam_z))
camera = bpy.context.active_object
camera.name = 'RenderCamera'

target    = mathutils.Vector((center_x, center_y, center_z))
direction = target - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
camera.data.lens = 35

bpy.context.scene.camera = camera

# 조명 추가
bpy.ops.object.light_add(type='AREA', location=(center_x + 2, center_y - 2, center_z + 2))
bpy.context.active_object.data.energy = 80
bpy.context.active_object.data.size = 3

bpy.ops.object.light_add(type='AREA', location=(center_x - 2, center_y - 2, center_z + 2))
bpy.context.active_object.data.energy = 60
bpy.context.active_object.data.size = 3

bpy.ops.object.light_add(type='AREA', location=(center_x, center_y - 3, center_z))
bpy.context.active_object.data.energy = 40
bpy.context.active_object.data.size = 5

# 모든 메시에 피부색 재질 적용
mat = bpy.data.materials.new(name="AvatarMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.4, 0.35, 0.30, 1)
bsdf.inputs["Roughness"].default_value = 0.5

for obj in bpy.data.objects:
    if obj.type == 'MESH':
        obj.data.materials.clear()
        obj.data.materials.append(mat)

# 렌더 설정 (회색 배경)
scene = bpy.context.scene
world = bpy.data.worlds.new("Gray")
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.96, 0.96, 0.95, 1)
bg.inputs[1].default_value = 1.0
scene.world = world

scene.render.engine = 'CYCLES'
scene.cycles.samples = 64
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 512
scene.render.resolution_y = 768

# 4방향 렌더링
views = {
    "front": 0,
    "left":  90,
    "back":  180,
    "right": 270,
}

for view_name, angle in views.items():
    rad   = math.radians(angle)
    cam_x = math.sin(rad) * cam_distance
    cam_y = -math.cos(rad) * cam_distance
    camera.location = (center_x + cam_x, center_y + cam_y, cam_z)

    target    = mathutils.Vector((center_x, center_y, center_z))
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    scene.render.filepath = os.path.join(output_dir, f"silhouette_{view_name}.png")
    bpy.ops.render.render(write_still=True)
    print(f"{view_name} 렌더링 완료!")

print("전체 렌더링 완료!")