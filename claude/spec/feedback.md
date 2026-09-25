# ⑤ `slice-feedback` — 계약

결정을 채점하고 정책별 경험적 신뢰도를 유지한다. 설계 근거는 `rationale/feedback.md`.

## `report_outcome(decision_id, observed)`

| 파라미터 | 타입 | 필수 | 출처 |
|---|---|---|---|
| `decision_id` | string | 예 | ④가 발급한 것 |
| `observed` | `Observation` | 예 | **`step()` 이후의 관측** (= `obs_{t+1}`) |

**반드시 `step()` 이후에 호출한다.** `obs_{t+1}.allocation`이 t에 적용된 배분, `obs_{t+1}.traffic`이 그 배분이 감당해야 했던 수요다. `step()` 전 호출은 `premature_scoring` 오류 (`flow/errors.md`).

**출력: `Outcome`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `sla_met` | bool | `violations`가 전부 `false` |
| `policy` | `PolicyName` | 채점 대상 정책 |
| `error` | float | 0~1. 이상 배분과의 거리 |
| `ideal_allocation` | `SliceTriple` | 위반이 딱 없어지는 배분 |
| `applied_allocation` | `SliceTriple` | **실제 적용된 배분** (= `observed.allocation`) |
| `requested_allocation` | `SliceTriple` | 에이전트가 요청했던 배분 (`decisions.json`에서 조회) |
| `actuator_delta` | float | 둘 사이의 거리. 액추에이터가 얼마나 깎았나 |
| `observed_violations` | `SliceFlags` | 채점 시점의 위반. MTTR 재구성용 |
| `vendor_id` | string \| null | **있으면 에이전트가 ③ `update_rating`에 중계** |
| `reliability_before` · `reliability_after` | float | |

**`error` 계산** — 정답을 쓰지 않고 관측만으로 나온다. **`capacity`를 빼면 안 된다.**

```
a*    = normalize(traffic / (thresholds × capacity))   # 이상 배분
error = L1(applied_allocation, a*) / 2                 # [0, 1]
```

**신뢰도 갱신**: `r ← (1−0.2)·r + 0.2·(sla_met ? 1 : 0)`

- **개입(`escalated`) 레코드는 정책의 `r`·`n`·`errors` 를 갱신하지 않는다** (B-2). 적용된 배분이 정책의 제안이 아니라 ④의 폴백 상수이기 때문이다. 채점은 그대로 하고, 그 성적은 `reliability.json` 의 `fallback` 항목에 쌓인다 — `get_reliability_table()` 출력에는 넣지 않는다(정책이 아니다). 반환값의 `counted_in_reliability` 가 반영 여부를 알린다.

**부작용**: ④의 해당 레코드에 `outcome`을 덧붙인다 (`sla_met`, `error`, `scored_at_step`, `applied_allocation`, `requested_allocation`, `actuator_delta`, `observed_violations`).

```json
// 요청 — step() 후의 관측
{"decision_id": "exp-proposed-emergency-s0-0012",
 "observed": {"step": 13,
   "traffic":     {"embb": 0.571, "urllc": 0.595, "mmtc": 0.390},
   "allocation":  {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
   "capacity":    {"embb": 1.600, "urllc": 1.600, "mmtc": 1.600},
   "utilization": {"embb": 1.050, "urllc": 0.760, "mmtc": 1.435},
   "violations":  {"embb": true,  "urllc": false, "mmtc": true}, ...}}
// 응답
{"sla_met": false,
 "policy": "rule_based",
 "error": 0.184,
 "ideal_allocation":     {"embb": 0.392, "urllc": 0.306, "mmtc": 0.301},
 "applied_allocation":   {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
 "requested_allocation": {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
 "actuator_delta": 0.210,
 "observed_violations": {"embb": true, "urllc": false, "mmtc": true},
 "vendor_id": null,
 "reliability_before": 0.880,
 "reliability_after": 0.704}
```

계산 확인: `a* = normalize([0.571/(0.9×1.6), 0.595/(1.2×1.6), 0.390/(0.8×1.6)]) = [0.392, 0.306, 0.301]`,
`error = (|0.340−0.392| + |0.490−0.306| + |0.170−0.301|) / 2 = 0.184`, `r = 0.8 × 0.880 = 0.704`.

> **이 예시가 `rule_based`의 한계를 보여준다.** `situation="emergency"`의 고정 목표 `[0.2, 0.7, 0.1]`은
> 과잉 반응이었다 — URLLC에 0.49를 줬는데 이용률 0.76으로 여유가 남았고, 굶긴 mMTC가 1.435로 터졌다.
> **상황 판단은 맞았는데 정책이 틀렸다.** ⑤가 `rule_based`의 신뢰도를 낮춘다.

---

## `get_reliability_table()`

**입력: 없음** · **출력: `ReliabilityTable`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `{policy}.reliability` | float | EMA 원값 |
| `{policy}.n` | int | 누적 표본 수 |
| `{policy}.effective` | float | **축소 보정값. 에이전트는 이걸 쓴다** → ④ `confidence.empirical` |
| `{policy}.recent_error` | float | 최근 5회 `error`의 EMA. **② `propose_allocation.recent_error`에 중계**. 표본이 없으면(n=0) `1 − POLICY_PRIOR[policy]`로 유도한 **사전값**을 낸다 (B-3) |

**축소 보정**: `effective = (r·n + 0.5·5) / (n + 5)`

```json
{"rule_based":    {"reliability": 0.910, "n": 120, "effective": 0.894, "recent_error": 0.094},
 "lstm_forecast": {"reliability": 0.840, "n": 95,  "effective": 0.823, "recent_error": 0.112},
 "dqn":           {"reliability": 0.420, "n": 6,   "effective": 0.456, "recent_error": 0.380}}
```

**두 종류의 신뢰도** — 종합은 에이전트만 한다.

| | 제공 | 의미 |
|---|---|---|
| 내재적 (`confidence`) | ② | **이번 입력**에 대한 확신 |
| 경험적 (`effective`) | ⑤ | 이 정책이 **평소** 얼마나 맞았나 |

```
combined = (situation × intrinsic × effective)^(1/3)
escalate if combined < 0.45
```

**셋의 기하평균이다.** `situation`은 에이전트가 내는 **상황 판단 자체에 대한 확신**이며
②·⑤ 어느 쪽도 주지 않는다. 이게 없으면 상황을 잘못 읽고도 정책에 자신 있을 때
`combined`가 높게 나와 **에스컬레이션이 일어나지 않는다.** `normal` 인지 정확도가
50.5%라 오탐이 구조적으로 많다 (`rationale/environment.md`).
