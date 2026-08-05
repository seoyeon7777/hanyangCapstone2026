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
# 헬스:   GET /api/health
# 큐:     GET /api/pipeline/queue
# 복구:   POST /api/pipeline/reclaim   {"max_age_sec": 600}

# P1 실루엣 (강제 또는 자동)
# options.silhouette_deform=true | options.phase="P1"
# options.silhouette_auto=true  → 마스크 품질 충분 시 자동
# options.silhouette_edge_snap=0.35
# options.silhouette_depth_strength=0.35  (측면 → Z)
# options.silhouette_strength=0.45
# options.silhouette_length_fit=true
# options.phase="P2" | neural_enabled=true  (stub)

# 워커:
#   PIPELINE_QUEUE=disk|thread   (기본 disk)
#   PIPELINE_STALE_RUNNING_SEC=900
#   PIPELINE_ALERT_WEBHOOK=https://...
#   python -m services.worker
# 분류기 학습:
#   python scripts/train_garment_classifier.py --out assets/clothing/classifier_weights.json
#   CLASSIFIER_WEIGHTS=... python app.py

# 정확도 벤치마크:
#   python scripts/run_accuracy_benchmark.py --blender
#   → outputs/_accuracy/accuracy_report.md
#   문서: docs/ACCURACY.md
"""
