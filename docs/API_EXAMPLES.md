"""파이프라인 API 사용 예시 (참고용).

# JSON only — 원단/신축성 포함
curl -X POST http://localhost:5000/api/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{
    "body": {"height": 165, "weight": 55},
    "garment_type": "tshirt",
    "measurements": {"shoulder": 44, "chest": 100, "sleeve": 20, "length": 65},
    "fabric": {"cotton": 80, "spandex": 20},
    "stretch": "높음",
    "images": {"front": null},
    "options": {
      "phase": "P0",
      "bake_texture": false,
      "calibrate": true,
      "calibrate_tolerance_cm": 1.5,
      "calibrate_max_iters": 4
    }
  }'

# JSON — 사이즈표 텍스트로 치수 보조 추출
curl -X POST http://localhost:5000/api/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{
    "body": {"height": 165, "weight": 55},
    "garment_type": "hoodie",
    "measurement_text": "어깨 46 가슴 110 소매 58 총기장 70",
    "fabric": {"cotton": 80, "spandex": 20},
    "options": {"bake_texture": false, "calibrate": true}
  }'


# multipart (정면+후면+측면 이미지 + payload JSON)
curl -X POST http://localhost:5000/api/pipeline/run \
  -F 'payload={"body":{"height":165,"weight":55},"garment_type":"tshirt","measurements":{"shoulder":44,"chest":100,"sleeve":20,"length":65},"fabric":{"cotton":80,"spandex":20},"stretch":"보통"};type=application/json' \
  -F 'front=@/path/to/shirt_front.jpg' \
  -F 'back=@/path/to/shirt_back.jpg' \
  -F 'side=@/path/to/shirt_side.jpg'

# 진행률: GET /api/pipeline/progress/<job_id>
# 상태:   GET /api/pipeline/status/<job_id>
# 목록:   GET /api/pipeline/jobs
# 재시도: POST /api/pipeline/retry/<job_id>
"""
