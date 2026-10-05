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

**정책 집합 (`SLICE_POLICIES` · 2026-10-05 결정)** — LSTM 을 쓰지 않고 `rule_based`(`theta_z`) 고정으로 진행한다.
기본값 `rule_based` 에서 `lstm_forecast` 는 목록에 남되 `available: false` ·
`unavailable_reason: "disabled_by_config: SLICE_POLICIES=rule_based"` 이고, `propose_allocation` ·
`compare_policies` 도 그 정책에 `status: "unavailable"` · `allocation: null` 을 같은 사유로 돌려준다(폴백 금지 그대로).
`SLICE_POLICIES=all` 이 예전 동작이다. 집합은 `srm_mcp/policy/enabled.py` 한 곳에 있고 규칙 판단자의 `pick_policy` 도
같은 집합을 쓴다. **아래 예시는 `all` 기준이다.**

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
  - **B-3 이후 ⑤가 `null`을 내지 않는다.** 표본이 없으면 ⑤가 `1 − POLICY_PRIOR[policy]`를 유도해 채운다(`const.py`). ②의 `0.5` 기본값은 값이 아예 오지 않은 경우의 방어선으로만 남는다. n=0인 행의 `recent_error`는 **사전값이지 실측이 아니다** — 같은 행의 `n`으로 구분한다.

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

`recent_error`가 `null`이면 `0.5`를 쓴다.

**위반 보정 (B-1 · D1)** — `rule_based` 는 목표표를 낸 뒤, 임계를 넘은 슬라이스에 `min(0.1, (uᵢ−θᵢ)×0.2)` 를 더하고 이용률이 가장 낮은 슬라이스에서 같은 양을 뺀다 (원본 `ml_orchestrator_demo.py:446~457`). 환경변수 `SLICE_RULE_CORRECTION` 으로 켜고 끈다. 기본은 **`off`**(2026-10-03 반복 1 — 보정은 이번 스텝의 위반에 반응하는데 그 위반은 대부분 다음 스텝과 독립인 잡음이라 다음 스텝을 못 돕고 가장 한가한 슬라이스만 깎는다. after-F 장부 재생: theta 표 보정 on 0.498 → off 0.516). 원본 동작은 `on`. **아래 예시는 `off` 기준이다** — `on` 이면 같은 입력에 보정 직후 `{0.250, 0.765, −0.015}` 가 되고, **②가 음수를 0 으로 잘라 다시 나눠** `{0.2463, 0.7537, 0.0}` 을 낸다. ①의 `apply_allocation()` 은 음수 요청을 클립하지 않고 거부하기 때문이다(`env.py _reject_reason`, 2026-09-28 수정 전 실측 4412회 중 4회 거부). [0.1, 0.8] 클립은 평활 뒤라야 뜻이 있어 여전히 ①의 몫이다. 적용 설정은 `rationale` 끝의 `(보정 on · 평활 뒤|보정 on · 목표표|보정 off)` 로 남는다.

**보정 위치 (D1-b · 2026-09-28 결정 (iii))** — 기본 `SLICE_CORRECTION_STAGE=post`: `rule_based` 의 `allocation` 은 **목표표 그대로**이고, 보정량은 `correction`(합 0, 자르지 않음)으로 따로 나간다. 에이전트가 이를 ① `apply_allocation(…, correction)` 에 넘기면 ①이 **평활 뒤 · 클립 앞**에 더한다 — 원본 `update_allocation_rule_based`(:429~462)와 같은 식이다(`check_observe` 가 200개 입력으로 대조, 최대 오차 1e-6). 위 예시 입력이면 `correction = {+0.050, +0.065, −0.115}`. `target` 은 위에 적은 예전 방식(목표표에 섞기 · 적용값엔 30%만)이며 이때 `correction` 은 null. 오케스트레이터는 LLM 이 보정량을 빠뜨려도 게이트웨이가 같은 배분의 보정량을 붙인다.

**목표표 (D7 · 2026-09-29 결정 → 2026-10-03 반복 1·2)** — `rule_based` 의 목표표는 환경변수 `SLICE_TARGET_TABLE` 이 고른다. 기본 **`theta_z`** = 잡음 여유 · 용량 반영 배분 `a_k = (μ_k + z·σ_k)/(θ_k·cap_k)`, `Σa = 1` 이 되는 공통 z (모든 슬라이스의 여유가 잡음 σ 단위로 같다). `μ = 1.2·BASE_TRAFFIC·배율`, `σ = 0.1·배율`, `cap` = 관측의 `capacity` — 전부 ①의 생성 상수에서 유도한 값이고(`rule.py DEMAND_*`, `target_audit` · `check_policy` 가 ①과 같은지 검사) 관측(capacity)을 쓰는 유일한 표다. emergency 에서는 URLLC 가 공통 여유에 `0.25σ` 를 더 받는다(`CRITICAL_MARGIN` — emergency URLLC 위반이 이전보다 나빠지지 않는 가장 작은 값). `theta` = `BASE_TRAFFIC × 배율 / θ` 를 합 1 로 정규화한 표(`rule.py TARGET_BY_SITUATION_THETA`, emergency `{0.329, 0.463, 0.208}`, D7 의 본 조건 · 지금은 재현용). `original` 은 원본 `ml_orchestrator_demo.py:429~438` 그대로(emergency `{0.2, 0.7, 0.1}`)이며 민감도 분석에만 쓴다. `theta_only` 는 원본 표를 θ 로만 나눈 것. 모르는 값은 `theta_z` 로 떨어진다. 어느 표로 돌았는지는 `rationale` 끝의 `목표표 <이름>` 으로 장부에 남는다. 근거는 `workplan-2` §1.6 · D7 · §1.7. **아래 예시는 `original` 기준이다.**

**수요 모형 오차 (강건성 실험 · 2026-10-05)** — 위 `DEMAND_*` 는 ①의 생성 상수라 "정답 상수를 알고 푼다"는 비판을 받는다. `SLICE_MODEL_EVENT`(상황 효과 크기 `M' = 1 + s·(M−1)`) · `SLICE_MODEL_LEVEL`(평균 수준 배율, theta_z 만) · `SLICE_MODEL_NOISE`(σ 배율, theta_z 와 HMM) 로 **에이전트 쪽 지식만** 틀리게 한다. 기본 1.0(오차 없음). 프로세스가 `rule.py` 를 처음 import 할 때 한 번 읽고, 규칙 판단자의 HMM 도 같은 값을 쓴다. `check_policy` 의 ①과 같은지 검사는 오차가 없을 때만 통과한다. `original` 비교군은 이 상수를 쓰지 않는다.

**예시 1 — 성공**

```json
// 요청
{"policy": "rule_based",
 "observation": {"step": 12, "utilization": {"embb": 0.624, "urllc": 1.283, "mmtc": 1.015}, ...},
 "situation": "emergency"}
// 응답
{"policy": "rule_based",
 "allocation": {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
 "confidence": 0.521,
 "in_distribution": true,
 "status": "ok",
 "reason": null,
 "rationale": "situation=emergency → URLLC 우선 목표 [0.2, 0.7, 0.1]. 여유가 가장 작은 것은 URLLC(1.283/1.2, 7% 초과)라 분기가 자의적 → confidence 0.521."}
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
   "confidence": 0.521, "status": "ok", ...},
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
