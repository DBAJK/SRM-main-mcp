# ④ `slice-audit` — 계약

판단 기록과 지표 집계. 설계 근거는 `rationale/audit.md`. 기록 파일: `runs/{run_id}/decisions.json`.

## `record_decision(...)`

**판단을 실행(`apply_allocation`)보다 먼저 기록한다.**

| 파라미터 | 타입 | 필수 | 출처 |
|---|---|---|---|
| `step` | int | 예 | `observation.step` |
| `observation` | `Observation` | 예 | 판단의 근거가 된 관측 (`obs_t`) |
| `situation` | `Situation` | **예** | **에이전트의 상황 판단.** `perception_accuracy`의 입력 |
| `chosen_policy` | `PolicyName` | 예 | |
| `allocation` | `SliceTriple` | 예 | ②가 제안한 값 (적용 전) |
| `confidence.situation` | float | **예** | **상황 판단에 대한 확신. 에이전트가 직접 낸다** |
| `confidence.intrinsic` | float | 예 | ②의 `confidence` (정책에 대한 확신) |
| `confidence.empirical` | float | 예 | ⑤의 `effective` |
| `confidence.combined` | float | 예 | `(situation × intrinsic × empirical)^(1/3)` |
| `rationale` | string | 예 | 판단 근거 |
| `slice_id` | string | 아니오 | 조달했다면 ③의 `slice_id` |
| `vendor_id` | string | 아니오 | 조달했다면 ③의 `vendor_id`. **⑤가 이걸 읽어 에이전트에 돌려준다** |
| `in_distribution` | bool | 아니오 | ②의 `PolicyProposal.in_distribution` |
| `demand_class` | object | 아니오 | ②의 `classify_demand()` 출력 |
| `considered` | `[{policy, confidence, status}]` | 아니오 | `compare_policies`를 썼다면 탈락한 후보들 |

**출력**

```json
{"decision_id": "exp-proposed-emergency-s0-0012", "recorded_at_step": 12}
```

**`decision_id` 형식**: `{run_id}-{step:04d}`. 정렬 가능하고 `truth.jsonl`과 `step`으로 조인된다.

```json
// 요청 예시
{
  "step": 12,
  "observation": {"step": 12, "utilization": {"embb": 0.624, "urllc": 1.283, "mmtc": 1.015}, ...},
  "situation": "emergency",
  "chosen_policy": "rule_based",
  "allocation": {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
  "confidence": {"situation": 0.70, "intrinsic": 0.521, "empirical": 0.880, "combined": 0.685},
  "rationale": "URLLC 구성비 53% (평시 33%), 새벽 3시인데 URLLC 지배적. 이용률 1.283 (임계의 107%). LSTM은 이력 부족으로 사용 불가."
}
```

`combined = (0.70 × 0.521 × 0.880)^(1/3) = 0.685`. **기하평균이라 셋 중 하나만 낮아도 전체가 낮아진다.**

`confidence.situation`이 따로 필요한 이유 — `intrinsic`·`empirical`은 둘 다 **정책**에 대한 확신이라
상황을 잘못 읽었을 가능성이 어디에도 반영되지 않는다. 오판 + 정책 자신감 = 높은 `combined` =
**에스컬레이션 안 됨.** `normal` 인지 정확도가 50.5%라 오탐이 구조적으로 많다 (`rationale/environment.md`).

---

## `record_escalation(...)`

**이 도구를 호출한 것 자체가 개입 1회다.** 사람의 응답을 기다리지 않는다. **한 호출이 `kind: "escalation"` 레코드와 `kind: "decision"` 레코드를 같은 `step`으로 둘 다 남긴다.**

| 파라미터 | 타입 | 필수 |
|---|---|---|
| `step` | int | 예 |
| `observation` | `Observation` | 예 |
| `situation` | `Situation` | 예 |
| `reason` | string | 예 |
| `confidence` | object | 예 (`situation` 포함) |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `escalation_id` | string | 개입 1건의 식별자 |
| **`decision_id`** | string | **폴백 결정의 ID. `report_outcome`에 쓴다** |
| `fallback_policy` | `PolicyName` | **항상 `"rule_based"`** |
| `fallback_situation` | `Situation` | **항상 `"normal"`** |
| `fallback_allocation` | `SliceTriple` | 폴백 정책이 낸 배분. **`apply_allocation`에 넣는다** |
| `instruction` | string | 에이전트에게 주는 다음 행동 지시 |

```json
{"escalation_id": "exp-proposed-mixed-s0-esc-0031",
 "decision_id": "exp-proposed-mixed-s0-0031",
 "fallback_policy": "rule_based",
 "fallback_situation": "normal",
 "fallback_allocation": {"embb": 0.40, "urllc": 0.40, "mmtc": 0.20},
 "instruction": "사람 호출을 기록했다. 대기하지 말고 fallback_allocation을 apply_allocation에 넣어 이번 스텝을 진행한 뒤, step() 후 decision_id로 report_outcome을 호출하라."}
```

---

## `get_decisions(n, kind)`

| 파라미터 | 타입 | 필수 | 기본 | 설명 |
|---|---|---|---|---|
| `n` | int | 아니오 | `50` | 최근 n건 |
| `kind` | string | 아니오 | `null` | `decision` · `escalation` 필터 |

**출력: `[Decision]`** — `decisions.json`의 레코드 그대로. ⑤가 채점했으면 `outcome`이 붙어 있다.

```json
[{"decision_id": "...-0012", "step": 12, "kind": "decision",
  "situation": "emergency", "chosen_policy": "rule_based",
  "allocation": {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10},
  "confidence": {"situation": 0.70, "intrinsic": 0.521, "empirical": 0.880, "combined": 0.685},
  "outcome": {"sla_met": false, "error": 0.184, "scored_at_step": 13}}]
```

**컨텍스트 주의** — 각 레코드에 `observation`이 통째로 들어 있다. 에이전트용 호출은 **`n ≤ 10`**. 전량 분석은 `eval/score.py`가 파일을 직접 읽는다.

---

## `get_metrics(window)`

| 파라미터 | 타입 | 필수 | 기본 | 설명 |
|---|---|---|---|---|
| `window` | int | 아니오 | `null` | 최근 n스텝만. `null`이면 전체 |

**출력: `Metrics`** — **관측만으로 계산되는 지표뿐이다.**

| 필드 | 타입 | 정의 |
|---|---|---|
| `steps` | int | **채점 완료된** 결정 수 (= 기록 수 − 1) |
| `interventions` | int | `record_escalation` 호출 횟수 |
| `autonomous_rate` | float | `1 − interventions / steps` |
| `sla_violations` | int | **`outcome.sla_met == false`인 결정 수.** `observation.violations`로 세지 않는다 |
| `mean_utilization` | `SliceTriple` | 평균 이용률 |
| `policy_usage` | `{PolicyName: int}` | 정책별 채택 횟수 |
| `mttr` | float | 위반 시작 스텝부터 전부 해소된 스텝까지의 평균 길이 |
| `unresolved` | int | **복구되지 않은 채 끝난 구간 수** |
| `procurements` | int | `procure()` 호출 횟수 |
| `procurement_cost_total` | float | 조달 비용 합계 |
| `mean_capacity` | `SliceTriple` | 평균 용량 배수 |
| `pressure_exceeded` | int | `demand_pressure ≥ 1.0`이던 스텝 수 |

**반환 금지 ⚠️**: `perception_accuracy` · `escalation_precision`. 정답이 필요한 지표는 `eval/score.py`가 오프라인으로 계산한다. (`flow/forbidden.md`)

**집계 불변식**

```
steps              = 채점된 결정 수           (60스텝 에피소드 → 59)
sum(policy_usage)  = 기록된 결정 수           (60)
Σ ⑤의 n           = 채점된 결정 수           (59)
```

`sum(policy_usage)`와 `Σn`이 **1 차이나는 것은 정상**이다. 2 이상 벌어지면 ②의 조용한 폴백이나 `report_outcome` 누락을 의심한다.

```json
{"steps": 59, "interventions": 4, "autonomous_rate": 0.932,
 "sla_violations": 17,
 "mean_utilization": {"embb": 1.021, "urllc": 1.183, "mmtc": 0.742},
 "policy_usage": {"rule_based": 42, "lstm_forecast": 18, "dqn": 0},
 "mttr": 3.4, "unresolved": 1,
 "procurements": 3, "procurement_cost_total": 1875.0,
 "mean_capacity": {"embb": 1.600, "urllc": 1.783, "mmtc": 1.600},
 "pressure_exceeded": 21}
```
