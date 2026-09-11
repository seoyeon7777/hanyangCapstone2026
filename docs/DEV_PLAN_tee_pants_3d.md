# 개발 계획 — 이미지+치수 → 로고 보이는 3D (티/바지)

목표 시스템: **옷 이미지 + 치수 입력 → 자동으로 치수·로고/디테일이 반영된 3D(GLB)**  
품목: `tshirt` / `pants`  
고객 수동 메쉬 편집: 없음

기존 코드 전제: P0 캘리브·P1 텍스처·파이프라인 골격은 **이미 구현됨**.  
남은 개발은 “필드에서 bake를 켜고, 로고가 보이게 검증·고정·제품화”가 중심.

---

## 0. 현재 구현 상태 (개발 관점)

| 모듈 | 경로 | 상태 |
|------|------|------|
| API 진입 | `app.py` `POST /api/pipeline/run` | 동작, 기본 `bake_texture=True` |
| 세그멘테이션 | `pipeline/stages/understand.py` + rembg | 동작 (실패 시 passthrough) |
| 템플릿 | `cloth_top.blend` / `cloth_pants.blend` | 전용 메쉬 있음 |
| 치수 캘리브 | `models/calibrate_shape_keys.py` | 동작 |
| 텍스처 | `pipeline/stages/texture.py` → `blender/apply_texture.py` → `cloth_textured.glb` | **구현됨** |
| field 벤치 | `field_pipeline_tee_*` / `pants_*` | 케이스에 **`bake_texture: false`** ← 막힘 |
| 레거시 | `/api/fit/analyze` | 치수만, 텍스처 없음 |

→ 개발 병목은 “새 엔진 작성”이 아니라 **bake 경로를 주 경로로 고정 + 로고 품질 튜닝 + 데모/QA**.

---

## 1. 개발 에픽 & 작업 분해

### Epic 1 — Texture-on-by-default (필드/벤치)
**목적:** 티·바지 파이프가 GLB에 사진을 입힌 채로 끝나게 한다.

| ID | 작업 | 파일/위치 | 완료 조건 |
|----|------|-----------|-----------|
| D1.1 | field tee/pants 케이스 `bake_texture: true` | `benchmarks/cases/field_pipeline_tee_*.json`, `field_pipeline_pants_*.json` | 케이스 옵션 반영 |
| D1.2 | runner 기본값 `bake_texture` false 제거/오버라이드 | `pipeline/eval/runner.py` `run_field_pipeline_case` | field 실행 시 텍스처 스테이지 호출 |
| D1.3 | 결과 검증 키 추가 | runner metrics / QA | `cloth_textured.glb` 존재 assert (soft→hard 점진) |
| D1.4 | docs/API 예제를 bake true 기준으로 | `docs/API_EXAMPLES.md` | 예제가 본경로와 일치 |

### Epic 2 — 로고 품질 (텍스처 정렬)
**목적:** 가슴/프린트 로고가 앞판 UV에 식별 가능하게 붙는다.

| ID | 작업 | 파일/위치 | 완료 조건 |
|----|------|-----------|-----------|
| D2.1 | 로고 있는 실사 티 fixture + 치수 케이스 | `benchmarks/fixtures/`, `benchmarks/cases/` | 로고 티 field 케이스 1개 |
| D2.2 | rembg가 로고 영역을 날리지 않는지 확인 | `vision_adapter.segment_garment` | RGBA에 로고 잔존 스크린샷 |
| D2.3 | UV 투영 튜닝 (front island, pad/aspect) | `blender/apply_texture.py` `project_multiview_uv` | 로고가 가슴 중앙 근처 |
| D2.4 | atlas crop/edge blend 조정 | `pipeline/stages/texture.py` | 가장자리 깨짐·로고 절단 감소 |
| D2.5 | (권장) 후면 추가 시 1x2 atlas 검증 | 동일 | 앞·뒤 분리 유지 |

### Epic 3 — 치수 경로 회귀 (티/바지)
**목적:** 텍스처 켜도 캘리브 수치 깨지지 않는다.

| ID | 작업 | 파일/위치 | 완료 조건 |
|----|------|-----------|-----------|
| D3.1 | `top_calib_*` / `pants_calib_*` 로컬 Blender 회귀 | `scripts/run_accuracy_benchmark.py` | release 케이스 통과율 유지 |
| D3.2 | field_tee_tape / field_pants_tape + 실데이터 | `benchmarks/cases/` | soft/hard 기준 문서화 |
| D3.3 | sim 끈 상태 데모 고정 | options `run_simulation=false` | 로고 왜곡 없이 GLB |

### Epic 4 — API·데모 제품화
**목적:** “이미지+치수 업로드 → GLB 확인” 한 흐름.

| ID | 작업 | 파일/위치 | 완료 조건 |
|----|------|-----------|-----------|
| D4.1 | `/api/pipeline/run` 멀티파트 데모 스크립트 | `docs/` 또는 `scripts/` | 한 명령으로 잡 생성 |
| D4.2 | 결과 페이지에서 **GLB** 우선 표시 | `templates/result.html` 등 | OBJ만 보여주지 않음 |
| D4.3 | 레거시 `/api/fit/analyze`에 “텍스처 없음” 안내 또는 pipeline으로 유도 | `app.py` | 혼선 방지 |
| D4.4 | 품목 잘못된 매핑 방지 (jacket nearest 데모 제외) | UI/docs | 데모는 tshirt/pants만 |

### Epic 5 — 확장 슬롯 (필수 아님)
| ID | 작업 | 완료 조건 |
|----|------|-----------|
| D5.1 | silhouette_deform 옵션 튜닝 (티/바지) | soft 개선 리포트 |
| D5.2 | neural soft 유지 + bake 이후 GLB | 폴백 문서 1페이지 |
| D5.3 | 자켓 전용 blend | 후속 이슈로만 |

---

## 2. 구현 순서 (의존성)

```text
D1 (bake on) ──► D2 (로고 품질) ──► D3 (치수 회귀)
                      │
                      └──► D4 (API/데모 UI)
                             │
                             └──► D5 (여유 시)
```

1. **D1부터**: 코드는 있는데 필드가 꺼져 있음 → 켜야 나머지가 의미 있음  
2. **D2**: 실사 로고로 품질 맞춤 (여기가 “디테일” 핵심 개발)  
3. **D3**: 회귀로 치수 가드  
4. **D4**: 발표·서비스 진입점  
5. **D5**: 여유 분만

---

## 3. 개발 환경 / 검증 명령

```powershell
cd C:\Users\bang4\hanyangCapstone2026
git checkout cursor/jacket-measure-yup-fix-4ea6   # 또는 통합 브랜치
$env:BLENDER_PATH="C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
$env:PIPELINE_DISABLE_WORKER="1"

# 치수 회귀
python scripts/run_accuracy_benchmark.py --blender --suite calibration --case top_calib_base --case pants_calib_base

# 텍스처 켠 field (D1 반영 후)
python scripts/run_accuracy_benchmark.py --blender --case field_pipeline_tee_synthetic
# 산출물: outputs/_accuracy/<case>/.../cloth_textured.glb
```

단위 테스트:
- `tests/test_texture.py`
- `tests/test_multiview_texture.py`
- `tests/test_calibration.py`

---

## 4. Definition of Done (시스템)

다음이 모두 참이면 본 개발 범위 완료:

1. `tshirt` + 로고 사진 + 치수 → 자동 파이프 → **`cloth_textured.glb`에서 로고 육안 확인**
2. `pants` + 사진 + 치수 → 동일하게 GLB 생성
3. 캘리브 오차 목표(대략 ≤2cm) 유지 또는 soft로 문서화
4. API/UI에서 동일 흐름 재현 (수동 Blender 편집 0)
5. 자켓 Exact / 뉴럴 완전체는 **미완으로 명시**해도 DoD에 포함하지 않음

---

## 5. 즉시 착수 티켓 (이번 스프린트)

1. ~~**D1.1–D1.2** field bake_texture true + runner 기본값 수정~~ ✅
2. ~~**D2.1** 로고 티 fixture + `field_pipeline_tee_texture`~~ ✅ (합성; 실사는 추후 교체)
3. ~~**D2.3** UV front/back 분리 + U 미러 보정~~ ✅ (`blender/apply_texture.py`)
4. ~~렌더 증거~~ ✅ `tee_texture_logo_final.png` — 가슴에 LOGO/HYU 육안 확인

다음: 실사 로고 티 데이터 교체, 바지 texture 케이스, D4 데모 UI

