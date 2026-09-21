<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 0단계 — 모델 적재 검증

TF 2.15.1 고정 · 검증 6항목 · 실패 시 분기

# 7. 0단계 — 모델 적재 검증

**나머지 전부의 전제다** (분리 설계서 §7·§9 0번). 정정 I 때문에 단순 설치보다 손이 더 간다.

```bash
py -3.10 -m venv .venv310
.venv310/Scripts/python -m pip install "tensorflow==2.15.1" numpy pandas fastmcp pydantic
.venv310/Scripts/python tools/step0_verify_models.py
```

`tools/step0_verify_models.py`가 확인할 것 — **적재 성공만으로는 통과가 아니다.**

| # | 확인 | 실패 시 |
|---|---|---|
| 1 | `load_model("models/lstm_model_20250601_011235")` 성공 | TF 버전 재확인 → `TFSMLayer` → 재학습 |
| 2 | 입력 shape가 `(1, 10, 11)`을 받는가 | `create_feature_vector` 차원 재확인 |
| 3 | 출력이 3차원이고 **합 ≈ 1, 각 항 ∈ [0,1]** | **스케일러 필요** → 재학습 (정정 I) |
| 4 | 동일 입력 2회 → 동일 출력 | 비결정 레이어 존재 → 신뢰도 산출식 변경 |
| 5 | `load_model("models/dqn_model_20250601_012010")` + softmax 합 ≈ 1 | `classify_demand` 제외 |
| 6 | `dqn_training_data/*.csv` 컬럼별 min/max → `policy/ranges.json` | `in_distribution` 판정 불가 |

**3번이 진짜 관문이다.** `lstm_model_*/`에 스케일러 파일이 없다 (`models/lstm_single/`에만 `X_scaler.npy` 존재). 적재는 되는데 출력이 `[-3.2, 8.1, 0.4]` 같으면 정규화 전제가 다른 것이고, 복원할 스케일러가 없으므로 **재학습**이다. 이 경우 `lstm_forecast`의 작업량이 中~大로 되돌아간다.

**분기 계획**

| 3번 결과 | 1차 범위 |
|---|---|
| 통과 | `rule_based` + `lstm_forecast` (분리 설계서 §5 권고대로) |
| 실패 | **`rule_based` 단독으로 1차 진행** |

`rule_based` 단독이어도 논문은 성립한다. 정정 E 덕분에 *"동일한 규칙 엔진에 상황 라벨만 사람 → 에이전트로 교체"* 라는 가장 깨끗한 통제 실험이 되고, 에스컬레이션(신뢰도 기반 선택적 개입)은 정책 개수와 무관하게 돌아간다. 잃는 것은 "정책 선택" 축 하나뿐이다.

→ **§9 1번(DQN 1차 포함 여부)의 답: 포함하지 않는다.** 0단계 결과와 무관하게 결정 가능하다.

---
