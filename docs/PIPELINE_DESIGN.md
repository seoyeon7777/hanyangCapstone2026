# 이미지 + 치수 → 3D 의류 자동화 파이프라인 설계

## 1. 목표

**입력:** 옷 사진(1~4장) + 치수 데이터(어깨/가슴/소매/총기장 등) + (선택) 원단·신축성  
**출력:** 치수가 반영된 3D 의류 메쉬(OBJ/GLB) + 아바타 피팅 시뮬레이션 + 실루엣 렌더

기존 레포의 **템플릿 Shape Key + Blender Cloth Sim** 경로를 유지하면서,  
앞에 **이미지 이해 / 치수 융합 / 텍스처 베이킹** 단계를 붙여 “최대한 자동화”한다.

---

## 2. 현실적인 전략 (Hybrid)

순수 “사진 한 장 → 완전한 신규 3D 옷”은 아직 연구/상용 모두 불안정하다.  
그래서 **자동화 가능 영역을 최대화**하는 3단계 로드맵을 쓴다.

| Phase | 이름 | 자동 범위 | 품질/리스크 |
|-------|------|-----------|-------------|
| **P0 (즉시)** | Template Morph + Texture | 치수→Shape Key, 이미지→텍스처/카테고리 | 높음 / 낮음 |
| **P1** | Silhouette-guided Deform | 실루엣으로 템플릿 외곽·디테일 보정 | 중~높 / 중 |
| **P2** | Neural Reconstruction | 신규 실루엣/패턴 생성 (선택적) | 가변 / 높음 |

**권장 운영:** P0을 기본 경로(production path)로 두고, P1/P2는 feature flag로 점진 도입.

현재 코드베이스(`export_cloth` → `simulate_cloth` → `script` 렌더)는 이미 P0의 **기하/피팅/렌더** 코어다.  
부족분은 **이미지 입력 파이프**와 **텍스처·카테고리 자동 추출**이다.

---

## 3. 전체 파이프라인 (End-to-End)

```text
┌─────────────┐   ┌──────────────┐   ┌─────────────────┐
│  Ingest     │──▶│  Understand  │──▶│  Measure Fusion │
│  images+JSON│   │  seg/class   │   │  OCR+user merge │
└─────────────┘   └──────────────┘   └────────┬────────┘
                                              │
                     ┌────────────────────────▼────────┐
                     │  Template Match + Shape Keys    │
                     │  (기존 fitting_model + blend)   │
                     └────────────────────────┬────────┘
                                              │
         ┌──────────────┬─────────────────────┼──────────────────┐
         ▼              ▼                     ▼                  ▼
   Texture Bake   Detail Deform(P1)    Cloth Sim(기존)     QA Gate
   (이미지→UV)    silhouette guide     avatar fit          measure check
         └──────────────┴─────────────────────┴──────────────────┘
                                              │
                                              ▼
                                    Export OBJ/GLB + Renders
```

### Stage 상세

#### S0. Ingest
- 업로드: `front` 필수, `side`/`back`/`detail` 선택
- 메타: `garment_type`(없으면 자동분류), `measurements{}`, `fabric{}`, `stretch`
- 산출: 정규화된 `JobManifest` (JSON schema)

#### S1. Image Understanding
- 배경 제거 / 옷 영역 세그멘테이션 (SAM / rembg / cloth-seg)
- 카테고리 분류: tshirt / hoodie / jacket / pants / skirt …
- 프론트 정규화(직립, 중심 정렬)
- (선택) 라벨/태그 OCR → 치수 후보

#### S2. Measurement Fusion
- 우선순위: **사용자 수동 입력 > OCR/표기 치수 > 이미지 추정**
- 필수 키(상의): `shoulder`, `chest`, `sleeve`, `length`
- 누락 시: 카테고리 기본값 + 신뢰도 플래그 `needs_review`
- 기존 `calc_export_shape_keys()`로 Blender Shape Key(-1~1) 변환

#### S3. Template Match
- `assets/clothing/cloth_*.blend` 카탈로그 매칭
- 미보유 카테고리 → nearest template + `partial_match` 경고
- 아바타: 기존 `match_avatar(height, weight)` → S/M/L

#### S4. Geometry Build (P0)
- `export_cloth.py`: Shape Key 적용 → `cloth_shaped.obj`
- (P1) 세그멘테이션 실루엣으로 외곽 버텍스 추가 변형
- (P2) neural mesh를 템플릿 토폴로지로 retarget

#### S5. Texture / Material
- 정면 이미지 → UV 프로젝션 또는 템플릿 UV에 albedo bake
- 원단 비율 → 기존 `FABRIC_ELASTICITY` / `FABRIC_BENDING` 매핑
- 패턴/로고는 front UV 패치로 합성 (실패 시 solid color fallback)

#### S6. Physics Fit (기존 유지)
- `simulate_cloth.py`: Collision + Cloth + ShoulderPin
- `calc_pressure_map`: too_tight ~ loose

#### S7. Render & Export
- 4-view silhouette (기존 `script.py`)
- 추가: `cloth.glb` (텍스처 포함), `job_report.json`

#### S8. QA Gate
- Shape Key clamp 여부, 측정값 vs 결과 AABB 오차
- 시뮬레이션 발산/관통 휴리스틱
- 실패 시 자동 재시도(팽창량↑, 프레임↑) 또는 `needs_human_review`

---

## 4. 데이터 계약

### JobManifest (입력 정규화)

```json
{
  "job_id": "uuid",
  "images": {
    "front": "uploads/.../front.jpg",
    "side": null,
    "back": null
  },
  "garment_type": "tshirt",
  "measurements": {
    "shoulder": 44,
    "chest": 100,
    "sleeve": 20,
    "length": 65
  },
  "body": { "height": 165, "weight": 55 },
  "fabric": { "cotton": 0.8, "spandex": 0.2 },
  "stretch": "보통",
  "options": {
    "phase": "P0",
    "bake_texture": true,
    "run_simulation": true
  }
}
```

### JobResult (출력)

```json
{
  "job_id": "uuid",
  "status": "done",
  "avatar_size": "M",
  "shape_keys": { "chest": 0.0, "shoulder": 0.0 },
  "fit": { "fit_result": "good", "avg_pressure": 0.31 },
  "artifacts": {
    "cloth_shaped_obj": "...",
    "simulated_obj": "...",
    "glb": "...",
    "texture": "...",
    "silhouettes": ["front", "right", "back", "left"]
  },
  "warnings": [],
  "qa": { "passed": true, "checks": [] }
}
```

---

## 5. 모듈 맵 (코드 구조)

```text
pipeline/
  orchestrator.py          # 스테이지 순서 실행, 재시도, 진행 SSE
  schemas/manifest.py      # JobManifest / JobResult
  stages/
    ingest.py
    understand.py          # 세그/분류 (P0 stub → rembg/classifier)
    measure_fusion.py
    template_match.py
    geometry.py            # → services.blender_runner export 단계
    texture.py             # albedo bake (P0: simple projection)
    simulate.py            # → 기존 blender_runner sim/render
    qa.py
  adapters/
    blender_adapter.py     # 기존 blender_runner 래핑
    vision_adapter.py      # 외부 vision API/로컬 모델
```

Flask `app.py`는 기존 `/api/fit/analyze`를 유지하고,  
신규 `/api/pipeline/run`이 이미지 업로드 + JobManifest 경로를 추가한다.

---

## 6. 자동화 vs 사람 개입

| 작업 | 자동 | 사람 검수 트리거 |
|------|------|------------------|
| 카테고리 분류 | ✅ | confidence < 0.7 |
| 치수 입력 | 반자동 | 필수 키 누락 |
| Shape Key 변형 | ✅ | clamp hit (±1) |
| 텍스처 | ✅ (품질 가변) | 패턴 왜곡/누락 |
| Cloth sim | ✅ | fit too_tight/loose 극단 |
| 신규 실루엣(P2) | 부분 | 항상 샘플 검수 |

---

## 7. 기존 시스템과의 연결

| 기존 | 파이프라인에서의 역할 |
|------|----------------------|
| `models/fitting_model.py` | Shape Key 계산, 원단 물성, 압박도 |
| `services/blender_runner.py` | S4~S7 실행 엔진 |
| `assets/clothing/cloth_top.blend` | P0 템플릿 |
| `assets/avatars/body_{S,M,L}.blend` | 피팅 아바타 |
| `/api/fit/analyze` | 치수만 있는 레거시 경로 (유지) |

---

## 8. 구현 우선순위

1. **스키마 + Orchestrator + 기존 Blender 연결** (이번 PR 골격)
2. **이미지 업로드 API + rembg 세그 + 텍스처 단순 프로젝션**
3. **카테고리 분류기 + 템플릿 카탈로그 확장** (hoodie/pants …)
4. **QA 리포트 + 재시도 정책**
5. **P1 실루엣 가이드 디폼**
6. **P2 neural (선택, 별도 실험 트랙)**

---

## 9. 비기능 요구

- Job 단위 격리 `outputs/<job_id>/`
- Blender subprocess 타임아웃 (export 60s / sim 300s / render 120s) 유지
- 진행 상태 SSE (`progress_queues`) 재사용
- GPU: vision 단계는 선택적 GPU, Blender는 CPU/GPU 모두 가능
- 실패 시 부분 artifact 보존 + `status=error` + traceback 로그

---

## 10. 성공 기준 (P0)

1. 정면 이미지 + 4개 치수 입력 시, 수동 개입 없이 GLB/OBJ + 4뷰 렌더 생성
2. 치수 반영 Shape Key가 기존 `/api/fit/analyze`와 동일 공식
3. 이미지 없이도 기존 API가 그대로 동작 (회귀 없음)
4. 세그/텍스처 실패 시 solid-color fallback으로 파이프라인 완주
