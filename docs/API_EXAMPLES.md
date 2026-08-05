"""파이프라인 API 사용 예시 (참고용).

# JSON only (치수 중심, 캘리브레이션 ON)
curl -X POST http://localhost:5000/api/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{
    "body": {"height": 165, "weight": 55},
    "garment_type": "tshirt",
    "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
    "fabric": {"cotton": 0.9, "spandex": 0.1},
    "images": {"front": null},
    "options": {
      "phase": "P0",
      "bake_texture": false,
      "calibrate": true,
      "calibrate_tolerance_cm": 1.5,
      "calibrate_max_iters": 4
    }
  }'

# multipart (이미지 + payload JSON)
curl -X POST http://localhost:5000/api/pipeline/run \
  -F 'payload={"body":{"height":165,"weight":55},"garment_type":"tshirt","measurements":{"shoulder":44,"chest":100,"sleeve":20,"length":65},"fabric":{"cotton":1.0}};type=application/json' \
  -F 'front=@/path/to/shirt_front.jpg'

# 진행률: GET /api/fit/progress/<job_id>  (SSE)
# 결과:   GET /api/pipeline/result/<job_id>
"""
