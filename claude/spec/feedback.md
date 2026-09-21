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

**부작용**: ④의 해당 레코드에 `outcome`을 덧붙인다 (`sla_met`, `error`, `scored_at_step`, `applied_allocation`, `requested_allocation`, `actuator_delta`, `observed_violations`).

```json
// 요청 — step() 후의 관측
{"decision_id": "exp-proposed-emergency-s0-0012",
 "observed": {"step": 13,
   "traffic":     {"embb": 0.550, "urllc": 0.720, "mmtc": 0.180},
   "allocation":  {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
   "utilization": {"embb": 1.618, "urllc": 1.469, "mmtc": 1.059},
   "violations":  {"embb": true,  "urllc": true,  "mmtc": true}, ...}}
// 응답
{"sla_met": false,
 "policy": "rule_based",
 "error": 0.086,
 "ideal_allocation":     {"embb": 0.426, "urllc": 0.418, "mmtc": 0.157},
 "applied_allocation":   {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
 "requested_allocation": {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
 "actuator_delta": 0.210,
 "observed_violations": {"embb": true, "urllc": true, "mmtc": true},
 "vendor_id": null,
 "reliability_before": 0.880,
 "reliability_after": 0.704}
```

계산 확인: `a* = normalize([0.550/0.9, 0.720/1.2, 0.180/0.8]) = [0.426, 0.418, 0.157]`, `error = (|0.340−0.426| + |0.490−0.418| + |0.170−0.157|) / 2 = 0.086`, `r = 0.8 × 0.880 = 0.704`.

---

## `get_reliability_table()`

**입력: 없음** · **출력: `ReliabilityTable`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `{policy}.reliability` | float | EMA 원값 |
| `{policy}.n` | int | 누적 표본 수 |
| `{policy}.effective` | float | **축소 보정값. 에이전트는 이걸 쓴다** → ④ `confidence.empirical` |
| `{policy}.recent_error` | float | 최근 5회 `error`의 EMA. **② `propose_allocation.recent_error`에 중계** |

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
combined = sqrt(intrinsic × effective)
escalate if combined < 0.45
```
