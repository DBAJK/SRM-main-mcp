# ① `slice-observe` — 계약

시뮬레이션 환경 그 자체. 에이전트가 관측하고 행동을 가하는 대상. 설계 근거는 `rationale/observe.md`.

## `get_observation()`

**입력: 없음** · **출력: `Observation`**

| 필드 | 타입 | 범위 | 의미 |
|---|---|---|---|
| `step` | int | 0 ~ `total_steps` | 현재 스텝 |
| `sim_time.hour_of_day` | int | 0~23 | **가상 시계.** 벽시계 아님 |
| `sim_time.day_of_week` | int | 0~6 | 0 = 월요일 |
| `sim_time.is_weekend` | bool | | `day_of_week >= 5` |
| `traffic` | `SliceTriple` | 0.1 ~ 2.0 | 수요. `np.clip`로 상하한 고정 |
| `allocation` | `SliceTriple` | 각 0.1~0.8, **합 1.0** | 현재 적용 중인 배분 |
| `utilization` | `SliceTriple` | 0 ~ 20 | `traffic / (allocation × capacity)` |
| `capacity` | `SliceTriple` | 1.6 ~ 2.6 | **슬라이스별 용량 배수.** 기본 `1.6`, 조달로 증가, 만료로 감소 |
| `thresholds` | `SliceTriple` | 고정 | `{0.9, 1.2, 0.8}`. 상수지만 매번 반환 |
| `violations` | `SliceFlags` | | `utilization > thresholds` |
| `client_count` | float | 0 ~ 1 | 정규화된 단말 수 |
| `bs_count` | float | 0 ~ 1 | 정규화된 기지국 수 |
| `demand_pressure` | float | 0 ~ 2 | `Σᵢ traffic / (θ × capacity)`. **1.0 초과면 재배분으로 해결 불가** |

```
demand_pressure < 1.0  →  재배분만으로 해결 가능
demand_pressure ≥ 1.0  →  용량을 늘리지 않으면 어딘가는 반드시 위반
```

서버는 **숫자만 주고 "조달하라"는 조언은 하지 않는다.**

실측(60스텝 × 시드 10): `normal` **5.6%** · `emergency` 27.7% · `special_event` 34.3% · `iot_surge` 28.5%.
평시는 94%가 재배분으로 해결되고, 이벤트에서만 조달이 정답이 된다. (`rationale/environment.md`)

**반환하지 않는 것** — `is_emergency` · `is_special_event` · `is_iot_surge`. 환경 내부의 정답이며 `runs/{run_id}/truth.jsonl`로만 나간다. 어떤 도구도 읽지 않는다. (`flow/forbidden.md`)

**예시** (비상 상황 전개 중, 에이전트는 그 사실을 모름)

```json
{
  "step": 12,
  "sim_time": {"hour_of_day": 3, "day_of_week": 0, "is_weekend": false},
  "traffic":     {"embb": 0.400, "urllc": 0.821, "mmtc": 0.325},
  "allocation":  {"embb": 0.400, "urllc": 0.400, "mmtc": 0.200},
  "utilization": {"embb": 0.624, "urllc": 1.283, "mmtc": 1.015},
  "capacity":    {"embb": 1.600, "urllc": 1.600, "mmtc": 1.600},
  "thresholds":  {"embb": 0.900, "urllc": 1.200, "mmtc": 0.800},
  "violations":  {"embb": false, "urllc": true,  "mmtc": true},
  "client_count": 0.631,
  "bs_count": 0.482,
  "demand_pressure": 0.959
}
```

`scenario="emergency", seed=0` 의 step 12 실측이다. 트래픽 **구성비**는 eMBB 26% · URLLC 53% · mMTC 21%로,
평시(44/33/22)와 비교하면 URLLC가 확연히 높다. `situation` 추론의 주된 근거는 절대량이 아니라 이 구성비다.
`demand_pressure 0.959 < 1.0` 이므로 이 스텝은 **재배분만으로 해결 가능하다.**

---

## `step(n)`

| 파라미터 | 타입 | 필수 | 기본 | 범위 | 설명 |
|---|---|---|---|---|---|
| `n` | int | 아니오 | `1` | 1 ~ 10 | 전진할 스텝 수 |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `steps_advanced` | int | 실제 전진한 수 (에피소드 끝에 걸리면 요청보다 적음) |
| `episode_done` | bool | `step >= total_steps` |
| `observation` | `Observation` | 전진 후 관측 |

**동작 순서 (고정)**: 만료된 조달 회수 → `capacity` 재계산 → `traffic_{t+1}` 생성 → `utilization_{t+1} = traffic_{t+1} / (allocation_t × capacity_{t+1})` → `truth.jsonl` append.

- **만료가 `traffic` 생성보다 먼저다.**
- 이용률은 **직전에 적용한 배분**으로 계산된다. `step()` 직후의 관측 = **직전 결정의 성적표**. `report_outcome`은 반드시 `step()` **이후**.

```json
{"steps_advanced": 1, "episode_done": false,
 "observation": {"step": 13, "traffic": {"embb": 0.571, "urllc": 0.595, "mmtc": 0.390}, ...}}
```

---

## `apply_allocation(embb, urllc, mmtc)`

배분을 실제로 적용하는 **액추에이터**. 평활·클립·정규화가 전부 여기서 일어난다.

| 파라미터 | 타입 | 필수 | 범위 |
|---|---|---|---|
| `embb` · `urllc` · `mmtc` | float | 예 | > 0 |

**합이 1일 필요 없다.** 서버가 정규화한다.

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `accepted` | bool | 입력이 유효했는가 |
| `requested` | `SliceTriple` | 정규화만 한 요청값 |
| `normalized` | `SliceTriple` | **실제 적용된 값** (평활 후) |
| `delta` | float | `L1(requested, normalized) / 2`. 얼마나 깎였나 |
| `reason` | string | 어떤 변형이 가해졌는지 |

**변형 파이프라인** (`ml_orchestrator_demo.py:458~462`)

```
1. 정규화      a / Σa
2. 평활        0.7 × 현재배분 + 0.3 × a        ← STABILITY_FACTOR
3. 클립        clip(·, 0.1, 0.8)
4. 재정규화    a / Σa
```

```json
// 요청
{"embb": 0.20, "urllc": 0.70, "mmtc": 0.10}
// 응답 — 평활 때문에 절반밖에 안 움직임
{"accepted": true,
 "requested":  {"embb": 0.200, "urllc": 0.700, "mmtc": 0.100},
 "normalized": {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
 "delta": 0.210,
 "reason": "smoothed(0.7); within clip [0.1, 0.8]"}
```

**`accepted: false`는 입력이 비정상일 때만** — 음수, 전부 0, NaN. 거부되어도 **기존 배분은 유지된다.**

```json
{"accepted": false, "requested": null, "normalized": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
 "delta": 0.0, "reason": "rejected: negative value in urllc(-0.1); allocation unchanged"}
```

---

## `get_history(n)`

LSTM 정책의 입력 시퀀스를 만든다.

| 파라미터 | 타입 | 필수 | 기본 | 범위 |
|---|---|---|---|---|
| `n` | int | 아니오 | `10` | 1 ~ 100 |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `n_requested` | int | 요청한 수 |
| `n_available` | int | **실제 반환한 수.** 초반에는 요청보다 적다 |
| `columns` | `[string × 11]` | 컬럼 이름. 순서 고정 |
| `features` | `[[float × 11] × n_available]` | 오래된 것 → 최신 순 |

**`columns` 순서** — `create_feature_vector()`(`:513~526`)와 **정확히 일치해야 한다.** 매 호출 반환한다.

```json
["traffic_load", "hour_of_day", "day_of_week",
 "embb_allocation", "urllc_allocation", "mmtc_allocation",
 "embb_utilization", "urllc_utilization", "mmtc_utilization",
 "client_count", "bs_count"]
```

- 피처는 **11차원 고정.** `capacity`는 포함되지 않는다 (재학습 없이는 추가 불가). 조달 직후 `in_distribution: false`가 뜰 수 있다 — 버그가 아니다. (`rationale/observe.md`)
- **`n_available < 10`이면 `lstm_forecast`를 쓸 수 없다.** ②가 `status: "unavailable"`을 반환한다.

```json
{"n_requested": 10, "n_available": 4,
 "columns": ["traffic_load", "hour_of_day", ...],
 "features": [
   [0.4893, 0.0417, 0.0, 0.400, 0.400, 0.200, 0.605, 1.196, 0.948, 0.610, 0.470],
   [0.5020, 0.0833, 0.0, 0.400, 0.400, 0.200, 0.613, 1.231, 0.971, 0.618, 0.475],
   [0.5157, 0.0833, 0.0, 0.400, 0.400, 0.200, 0.619, 1.258, 0.994, 0.625, 0.479],
   [0.5153, 0.1250, 0.0, 0.400, 0.400, 0.200, 0.624, 1.283, 1.015, 0.631, 0.482]]}
```

---

## `reset(run_id, scenario, seed)`

| 파라미터 | 타입 | 필수 | 기본 | 허용값 |
|---|---|---|---|---|
| `run_id` | string | **예** | — | 이 실행의 식별자. `truth.jsonl`의 모든 줄에 박힌다. ④에도 **같은 값**을 넘긴다 |
| `scenario` | string | 아니오 | `"normal"` | `normal` · `emergency` · `special_event` · `iot_surge` · `mixed` |
| `seed` | int | 아니오 | `0` | 임의 정수 |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `run_id` | string | 적용된 실행 식별자 |
| `scenario` | string | 적용된 시나리오 |
| `capacity` | `SliceTriple` | 항상 `{1.6, 1.6, 1.6}` (`CAPACITY_BASE`). 활성 조달 전부 회수 |
| `seed` | int | 적용된 시드 |
| `total_steps` | int | 이 에피소드의 길이 |
| `observation` | `Observation` | `step: 0` |

**시나리오별 길이** (`test_scenarios.py:54-102`)

| 시나리오 | `total_steps` | 전개 |
|---|---|---|
| `normal` | 60 | 평시 유지 |
| `emergency` | 60 | URLLC ×2.0 유지 |
| `special_event` | 60 | eMBB ×1.5 유지 |
| `iot_surge` | 60 | mMTC ×1.8 유지 |
| `mixed` | **120** | 20: 이벤트 on / 50: off / 60: 비상 on / 90: off / 100: IoT on |

- **동일 `seed` → 동일 전개.** 전용 RNG(`np.random.default_rng(seed)`)와 가상 시계.
- **`reset()`은 ①만 초기화한다.** ②③④⑤의 상태는 남는다.
- `truth.jsonl` 각 줄: `{"run_id": "...", "step": 12, "is_emergency": true, "is_special_event": false, "is_iot_surge": false}`

```json
{"run_id": "exp-proposed-emergency-s0", "scenario": "emergency", "seed": 0, "total_steps": 60,
 "observation": {"step": 0, "allocation": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}, ...}}
```

---

## `add_capacity(slice_type, amount, expires_at_step, slice_id)`

조달한 슬라이스를 **환경에 실제로 반영**한다. ③의 `procure()` 출력을 에이전트가 중계한다.

| 파라미터 | 타입 | 필수 | 범위 | 출처 |
|---|---|---|---|---|
| `slice_type` | `SliceType` | 예 | | |
| `amount` | float | 예 | 0 < x ≤ 0.5 | ③ `procure().capacity_gain` |
| `expires_at_step` | int | 예 | > 현재 step | ③ `procure().expires_at_step` |
| `slice_id` | string | 예 | | ③ `procure().slice_id` |

**출력: `CapacityState`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `accepted` | bool | 상한 초과 시 `false` |
| `capacity` | `SliceTriple` | 반영 후 용량 |
| `demand_pressure` | float | 반영 후 압력. **즉시 효과 확인용** |
| `active_leases` | `[{slice_id, slice_type, amount, expires_at_step}]` | 활성 조달 목록 |
| `reason` | string \| null | 거부 사유 |

- **용량 상한**: 슬라이스당 `2.6` (기본 `1.6` + 조달 4회분). 초과 요청은 거부.
- 상한을 `3.6`으로 올리면 모든 스텝이 조달로 해소되어 에스컬레이션이 무의미해진다. `2.6`에서 막는다.
- **거부되어도 ③의 `procure()`는 이미 일어났다.** 비용은 청구되고 용량은 안 늘어난다. 호출 전에 `Observation.capacity`로 상한을 확인할 것.

```json
// 요청
{"slice_type": "URLLC", "amount": 0.25, "expires_at_step": 22, "slice_id": "slice-urllc-0012-v1"}
// 응답 — 압력 0.959 → 0.901. 조달 1회가 약 6%를 덜어낸다
{"accepted": true,
 "capacity": {"embb": 1.600, "urllc": 1.850, "mmtc": 1.600},
 "demand_pressure": 0.901,
 "active_leases": [{"slice_id": "slice-urllc-0012-v1", "slice_type": "URLLC",
                    "amount": 0.25, "expires_at_step": 22}],
 "reason": null}
// 거부
{"accepted": false, "capacity": {"embb": 1.6, "urllc": 2.6, "mmtc": 1.6},
 "demand_pressure": 0.842, "active_leases": [...],
 "reason": "capacity_cap_exceeded: urllc 2.60 + 0.25 > 2.6"}
```
