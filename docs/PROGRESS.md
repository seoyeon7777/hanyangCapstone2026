# 프로젝트 진행도 (큰 분류)

기준일: 2026-08-06

---

## 한눈에 — 큰 분류

| 대분류 | 진행률 | 한 줄 |
|--------|--------|------|
| **A. P0 제품 경로** | **≈ 99%** | field_pipeline 4종 + ops alerts |
| **B. P1 실루엣 형상** | **≈ 95%** | photo-like RMSE·depth·waist 게이트 |
| **C. P2 Neural 재구성** | **≈ 28%** | XZ morph + ONNX 골격 |
| **전체 비전 (A+B+C 가중)** | **≈ 85%** | 0.55·A + 0.30·B + 0.15·C |

---

## A. P0 (~99%)

| 중분류 | 상태 |
|--------|------|
| field_pipeline | tee / skirt / **pants** / **hoodie** |
| ops dashboard | A/B/C % · **active alerts** · suite 요약 |
| QA retry 정책 | 순수 함수 + 로그 아티팩트 |
| **남김** | 실제 줄자·실사진 (`field_tape`) |

## B. P1 (~95%)

| 중분류 | 상태 |
|--------|------|
| 프로필 RMSE / **depth RMSE** / **waist drift** | 완료 |
| photo-like 합성 픽스처 | 완료 (`scripts/generate_photo_like_fixtures.py`) |
| RGB 테두리 전경 추출 | 완료 |
| **남김** | 실사진 마스크 |

## C. P2 (~28%)

| 중분류 | 상태 |
|--------|------|
| stub / synthetic / **onnx** 백엔드 | onnx=계약만 (모델 없으면 skip) |
| **독립 X/Z vertex_morph** | 완료 |
| neural_contract 벤치 | 완료 |
| 학습 가중치 | **미착수** |

---

## 정확도

```bash
python scripts/run_accuracy_benchmark.py --blender
```

최근: **41/41**, release **36/36**, field_pipeline **4/4**, neural_contract **1/1**

## 다음 큰 분류

1. **A** — 실사진+테이프
2. **B** — 실사진 실루엣
3. **C** — ONNX/토치 실모델 연결
