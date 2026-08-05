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

# 한글 소재명도 가능: {"면": 70, "스판": 30}


# multipart (정면+후면 이미지 + payload JSON)
curl -X POST http://localhost:5000/api/pipeline/run \
  -F 'payload={"body":{"height":165,"weight":55},"garment_type":"tshirt","measurements":{"shoulder":44,"chest":100,"sleeve":20,"length":65},"fabric":{"cotton":80,"spandex":20},"stretch":"보통"};type=application/json' \
  -F 'front=@/path/to/shirt_front.jpg' \
  -F 'back=@/path/to/shirt_back.jpg'

# 진행률: GET /api/fit/progress/<job_id>  (SSE)
# 결과:   GET /api/pipeline/result/<job_id>
"""
