# AI-Hub jacket → field_tape 변환 결과

케이스 7개 생성 (라벨만, 사진 미업로드)

| case_id | shoulder | chest | sleeve | length | height | weight | view/color |
|---------|----------|-------|--------|--------|--------|--------|------------|
| `field_jacket_aihub_316767_tape` | 43.0 | 90.0 | 55.0 | 56.0 | 158.0 | 55.0 | back/converted from 01_sou_063354_316767_back |
| `field_jacket_aihub_316807_tape` | 42.0 | 88.0 | 53.0 | 50.0 | 166.0 | 68.0 | back/converted from 01_sou_063362_316807_back |
| `field_jacket_aihub_316874_tape` | 45.0 | 92.0 | 57.0 | 63.0 | 157.0 | 50.0 | wear/converted from 01_sou_063375_316874_wear |
| `field_jacket_aihub_316881_tape` | 45.0 | 102.0 | 52.0 | 71.0 | 157.0 | 50.0 | front/converted from 01_sou_063377_316881_fron |
| `field_jacket_aihub_316909_tape` | 45.0 | 98.0 | 54.0 | 68.0 | 157.0 | 50.0 | wear/converted from 01_sou_063382_316909_wear |
| `field_jacket_aihub_316964_tape` | 36.0 | 72.0 | 52.0 | 76.0 | 153.0 | 47.0 | wear/converted from 01_sou_063393_316964_wear |
| `field_jacket_aihub_316969_tape` | 38.0 | 84.0 | 57.0 | 72.0 | 153.0 | 47.0 | wear/converted from 01_sou_063394_316969_wear |

## 주의
- 업로드는 **라벨 JSON만**. 원천 jpg 없음 → 분류/실루엣/텍스처 불가
- 가능 결과: **P0 치수 캘리브레이션 MAE**
- 사진 추가 시 `images.front` 넣으면 됨
