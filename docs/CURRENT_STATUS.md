# 현재 시스템 상태 (상세)

이 문서는 **이미지 + 치수 → 3D 의류** 자동화에서 지금 무엇이 돌아가는지,
왜 이렇게 만들었는지, 다음에 무엇을 하는지 정리한다.

---

## 1. 한 줄 요약

> 미리 만들어 둔 티셔츠 3D 템플릿(`cloth_top.blend`)을  
> **입력 치수(cm)에 맞게 Shape Key로 변형**하고,  
> **메쉬를 다시 재측정해 Shape Key를 보정(캘리브레이션)**한 뒤,  
> 아바타에 **옷감 물리 시뮬레이션**을 입혀 4면 렌더를 뽑는다.  
> 이미지는 (진행 중) 배경 제거 후 **정면 텍스처**로 옷에 붙인다.

“사진만으로 완전히 새로운 옷 메쉬를 생성”하는 방식이 **아니다**.  
정확도와 자동화 가능성을 위해 **템플릿 변형 + 치수 피드백**을 택했다.

---

## 2. 전체 파이프라인 (지금)

```text
[입력]
  - 정면 옷 사진 (선택)
  - 치수: shoulder / chest / sleeve / length (cm)
  - 키·몸무게, 원단 비율

        │
        ▼
┌───────────────────┐
│ 1. Ingest         │  업로드 정리, 필수 치수 체크
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 2. Understand     │  이미지 분류/배경제거(rembg, 실패시 bypass)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 3. Measure Fusion │  수동치수 > OCR > 템플릿 기본값
│                   │  → Shape Key 초깃값 (open-loop)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 4. Template Match │  cloth_top.blend + body_{S,M,L}.blend
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 5. Calibrate ★    │  export → 재측정 → Shape Key 보정 반복
│                   │  목표: 라벨 cm 오차 ≤ 1.5cm (보통 2 iter)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 6. Texture        │  세그 이미지 → albedo.png → (Blender 투영)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 7. Cloth Sim      │  기존 simulate_cloth (어깨핀 + 원단 물성)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ 8. Render + QA    │  4뷰 실루엣, 치수/클램프 QA
└───────────────────┘
```

API:
- 레거시(치수만): `POST /api/fit/analyze`
- 신규 파이프라인: `POST /api/pipeline/run`
- 진행률 SSE: `GET /api/fit/progress/<job_id>`

---

## 3. 왜 “템플릿 + 캘리브레이션”인가

| 방식 | 장점 | 단점 |
|------|------|------|
| 사진→Neural 3D 재구성 | 새 실루엣 가능 | 치수 cm 불안정, 상용 품질 들쭉날쭉 |
| **템플릿 Shape Key (채택)** | 치수 제어 가능, 기존 blend 재사용 | 템플릿에 없는 디자인은 한계 |
| + **재측정 피드백** | 실제 메쉬 cm로 오차 보정 | Blender export 반복 비용 |

핵심 버그였던 것: 예전 `EXPORT_SHAPE_KEY_RANGE`가 **과대**  
(예: sleeve 42cm, length 55cm).  
목표 치수에 비해 Shape Key가 너무 작게 움직였다.

`cloth_top.blend`를 Blender로 프로브한 뒤:

| 키 | 구 RANGE | 신 min/max (라벨 cm) |
|----|----------|----------------------|
| sleeve | 42 | 12.6 / 11.4 |
| length | 55 | 13.4 / 20.1 |
| chest | 25 | 16.1 / 7.9 |
| shoulder | 13 | 4.0 / 3.8 |

실측 스모크 (목표 46/105/24/70): **2번 만에 수렴**, 오차 < 1.5cm.

---

## 4. 치수가 메쉬가 되는 과정

1. 사용자 입력 (라벨 cm) 예: chest=105  
2. Basis 라벨 100 → 차이 +5  
3. `RANGE_MAX[chest]=7.85` → Shape Key `chest_max ≈ 0.64`  
4. Blender가 `chest_max` 키를 0.64로 적용 후 OBJ export  
5. 파이썬이 OBJ를 **같은 공식으로 재측정** (라벨 cm로 환산)  
6. 아직 오차 있으면 Shape Key를 더 보정 (`gain * err / RANGE`)  
7. 수렴 후 그 Shape Key로 시뮬/렌더

재측정 공식 (`models/garment_measure.py`):
- 축: Y-up (Blender OBJ)
- shoulder: 어깨 높이 full-width / 2
- chest: 몸통 단면 convex-hull 둘레 / 2
- sleeve: max\|x\| − 어깨 솔기 half
- length: Y AABB (라벨 65 ↔ mesh ~115, scale≈1.78로 환산)

---

## 5.5 원단/소재 입력 (이미 지원)

UI·API 모두 `fabric` + `stretch` 를 받을 수 있다.

```json
"fabric": { "cotton": 80, "spandex": 20 },
"stretch": "높음"
```

- `%`(합 100) 또는 비율(합 1) 모두 가능
- 한글 별칭 가능: `면`, `스판`, `폴리에스터`, `데님` …
- 파이프라인 `fabric` 스테이지에서 정규화 →  
  **elasticity / bending** 계산 → Cloth 시뮬 tension·굽힘·질량에 반영
- 결과 JSON `fabric.summary_ko`, `fabric.elasticity` 등으로 확인

지원 소재: cotton, polyester, linen, wool, denim, knit, silk, nylon, acrylic, rayon, spandex, cashmere, chiffon

| 단계 | 상태 |
|------|------|
| 카테고리 분류 | hint/파일명 휴리스틱 (ML 자리만 있음) |
| 배경 제거 | rembg — front/back/side 각각 |
| albedo 준비 | `albedo.png` + **`albedo_atlas.png`** |
| — side 없음 | 1×2 `[front\|back]` |
| — side 있음 | 2×2 `[front\|back / side\|sideF]` + 가장자리 보간 |
| **메쉬에 붙이기** | ✅ 법선 기준 front/back(/side) UV 분할 + atlas |
| 렌더 반영 | ✅ `script.py` atlas_layout 지원 |
| GLB export | ✅ `cloth_textured.glb` |
| UI 이미지 업로드 | ✅ 정면/후면/측면 → `/api/pipeline/run` |
| 실루엣으로 형상 변경 | 아직 없음 (P1) |

---

## 6. 코드 맵

| 경로 | 역할 |
|------|------|
| `docs/PIPELINE_DESIGN.md` | 설계/로드맵 |
| `pipeline/orchestrator.py` | 스테이지 실행 |
| `models/fitting_model.py` | Shape Key / 원단 / 압박도 |
| `models/fabric.py` | 소재 정규화·물성 |
| `models/garment_measure.py` | 메쉬→cm 재측정 |
| `models/calibrate_shape_keys.py` | 캘리브레이션 루프 |
| `assets/clothing/cloth_top_ground_truth.json` | 프로브 결과 |
| `services/blender_runner.py` | export→sim→texture→render |
| `blender/simulate_cloth.py` | 물리 시뮬 |
| `blender/apply_texture.py` | 멀티뷰 atlas GLB |
| `blender/script.py` | 4뷰 렌더 (+텍스처) |

---

## 7. 방금까지 한 작업

**멀티뷰 텍스처 (front/back) — 완료**
**Runner 단계 분리 + 템플릿 카탈로그 — 완료**
**측면 보간 + UI 이미지 업로드 — 완료**
**실행 진행률 % + P1 실루엣 디폼 초안 — 완료**
**hoodie/pants 템플릿 + OCR 텍스트 + QA UX — 완료**
**pants GT 프로브·tesseract·QA 재시도·실루엣 센터 시프트 — 완료**

### 다음 후보
- pants 아바타 정렬/핀 고도화
- 분류 ML
- Celery 잡 큐
