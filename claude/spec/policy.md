# ② `slice-policy` — 계약

무상태. 배분 정책 여러 개를 나란히 노출한다. 설계 근거는 `rationale/policy.md`.

## `list_policies()`

**입력: 없음** · **출력: `[PolicyInfo]`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | `PolicyName` | |
| `description` | string | **`SLICE_DESC_MODE`에 따라 달라짐** (`minimal` / `advisory`) |
| `requires` | string \| null | 전제조건 |
| `available` | bool | 지금 호출 가능한가 |
| `unavailable_reason` | string \| null | 불가 사유 |

TensorFlow 적재에 실패하면 서버는 죽지 않고 해당 정책만 `available: false`로 내린다.

```json
[
  {"name": "rule_based", "description": "임계값 기반 배분. 상황 라벨을 입력으로 받는다.",
   "requires": null, "available": true, "unavailable_reason": null},
  {"name": "lstm_forecast", "description": "시계열 모델 기반 배분. 관측 이력 10스텝 필요.",
   "requires": "history >= 10", "available": true, "unavailable_reason": null},
  {"name": "dqn", "description": "강화학습 정책 기반 배분.",
   "requires": "trained weights", "available": false,
   "unavailable_reason": "no trained weights"}
]
```

---

## `propose_allocation(policy, observation, situation, history, recent_error)`

| 파라미터 | 타입 | 필수 | 기본 | 출처 |
|---|---|---|---|---|
| `policy` | `PolicyName` | **예** | — | |
| `observation` | `Observation` | **예** | — | ①.`get_observation()` 그대로 |
| `situation` | `Situation` | **예** | **없음** | **에이전트가 추론한 상황** |
| `history` | `HistoryBlock` | 아니오 | `null` | ①.`get_history()` 그대로 |
| `recent_error` | float | 아니오 | `null` | ⑤.`get_reliability_table()`의 `{policy}.recent_error` |

- **`situation`에 기본값을 두지 않는다.** 모든 정책이 필수로 받는다 (배분에 영향은 `rule_based`만).
- **`recent_error`는 에이전트가 ⑤에서 ②로 중계한다.** ②는 무상태라 ⑤를 조회할 수 없다. `null`이면 보수적 기본값 `0.5`를 쓰고 `rationale`에 그 사실을 적는다.

**출력: `PolicyProposal`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `policy` | `PolicyName` | 요청한 정책. **절대 다른 값으로 바꾸지 않는다** |
| `allocation` | `SliceTriple` \| **null** | 목표 배분. 실패 시 `null` |
| `confidence` | float | 0~1. **내재적 신뢰도** — 이번 입력에 대한 확신 |
| `in_distribution` | bool | 학습 분포 안인가 |
| `status` | `Status` | `ok` · `unavailable` · `error` |
| `reason` | string \| null | `status != ok`일 때의 사유 |
| `rationale` | string | 사람이 읽는 근거 |

**폴백 금지 ⚠️** — 실패 시 다른 정책을 조용히 호출하지 않는다. `allocation: null` + `status`로 반환한다. 원본 `update_allocation_ml()`(`:341`, `:414`, `:419`)의 폴백을 옮기지 말 것. 대체 정책 선택은 에이전트의 일이다.

**`confidence` 산출**

| 정책 | 식 |
|---|---|
| `rule_based` | `0.50 + 0.30 × min(1, minᵢ|uᵢ−θᵢ|/θᵢ)` |
| `lstm_forecast` | `exp(−3 · ē)`, `ē` = `recent_error` (최근 5회 예측 오차의 EMA, ⑤가 계산) |

**예시 1 — 성공**

```json
// 요청
{"policy": "rule_based",
 "observation": {"step": 12, "utilization": {"embb": 1.300, "urllc": 1.525, "mmtc": 0.950}, ...},
 "situation": "emergency"}
// 응답
{"policy": "rule_based",
 "allocation": {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
 "confidence": 0.556,
 "in_distribution": true,
 "status": "ok",
 "reason": null,
 "rationale": "situation=emergency → URLLC 우선 목표 [0.2, 0.7, 0.1]. URLLC 이용률 1.525가 임계 1.2를 27% 초과."}
```

**예시 2 — 이력 부족**

```json
{"policy": "lstm_forecast", "allocation": null, "confidence": 0.0,
 "in_distribution": false, "status": "unavailable",
 "reason": "history_insufficient: 4 < 10",
 "rationale": "시퀀스 길이 미달로 추론하지 않음."}
```

**예시 3 — 모델 적재 실패**

```json
{"policy": "lstm_forecast", "allocation": null, "confidence": 0.0,
 "in_distribution": false, "status": "error",
 "reason": "model_load_failed: SavedModel requires Keras 2 (tensorflow==2.15.1)",
 "rationale": "모델을 적재하지 못해 추론 불가."}
```

---

## `compare_policies(observation, situation, history, recent_errors)`

`propose_allocation`에서 `policy`를 빼고, `recent_error`를 **정책별 딕셔너리**로 바꾼 것.

| 파라미터 | 타입 | 필수 | 출처 |
|---|---|---|---|
| `observation` | `Observation` | 예 | |
| `situation` | `Situation` | 예 | |
| `history` | `HistoryBlock` | 아니오 | |
| `recent_errors` | `{PolicyName: float}` | 아니오 | ⑤.`get_reliability_table()`을 **그대로** 넘긴다 |

**출력**: `[PolicyProposal]` — 사용 가능 여부와 무관하게 **전 정책을 반환한다.**

```json
[
  {"policy": "rule_based", "allocation": {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10},
   "confidence": 0.556, "status": "ok", ...},
  {"policy": "lstm_forecast", "allocation": null,
   "confidence": 0.0, "status": "unavailable", "reason": "history_insufficient: 4 < 10", ...},
  {"policy": "dqn", "allocation": null,
   "confidence": 0.0, "status": "unavailable", "reason": "no trained weights", ...}
]
```

**호출 비용 주의** — 반환량이 `propose_allocation`의 3배. 정책 전환을 고민할 때만 쓰도록 프롬프트에서 유도한다.

---

## `classify_demand(observation)`

학습된 분류기(`TrafficClassifier`, 11 → 3 softmax)로 **어떤 수요가 지배적인지**만 알려준다.

| 파라미터 | 타입 | 필수 |
|---|---|---|
| `observation` | `Observation` | 예 |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `dominant` | `SliceType` | 최대 확률 클래스 |
| `probabilities` | `{eMBB, URLLC, mMTC: float}` | 합 1.0 |
| `margin` | float | 1등 − 2등 확률차 |
| `available` | bool | 모델 적재 여부 |

```json
{"dominant": "URLLC",
 "probabilities": {"eMBB": 0.281, "URLLC": 0.644, "mMTC": 0.075},
 "margin": 0.363,
 "available": true}
```

**이 도구는 "비상 상황인가"를 말하지 않는다.** 상황 판단은 에이전트의 몫이다.
