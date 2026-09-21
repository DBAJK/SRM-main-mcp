# ③ `slice-market` — 계약

외부 벤더 슬라이스 마켓. 설계 근거는 `rationale/market.md`.

## `qos_requirements` 스펙 ⚠️

③의 도구 3개(`score_offerings` · `explain_score` · `procure`)가 공통으로 받는다. **코드가 실제로 읽는 키는 이것뿐이다** (`engine.py:339`, `:368`, `:398`):

| 키 | 타입 | 기본값 | 단위 | 의미 |
|---|---|---|---|---|
| `latency` | float | `50` | ms | 요구 지연 상한 |
| `bandwidth` | float | `100` | Mbps | 요구 대역 하한 |
| `reliability` | float | `99.0` | % | 요구 신뢰도 하한 |
| `advanced_params` | object | `{}` | | 선택. 1차 범위에서는 쓰지 않음 |

**키 이름에 단위를 붙이지 않는다.** `latency_ms`가 아니라 `latency`다. 혼동하면 전부 기본값으로 떨어져 모든 벤더가 같은 점수를 받는다.

`advanced_params` 허용 키: `price_sensitivity` (`high|medium|low` → price_weight 0.3/0.2/0.1) · `deterministic` · `missionCritical` · `maxPacketSize` · `groupCommunication` · `availability`

---

## `list_offerings(slice_type, region)`

| 파라미터 | 타입 | 필수 | 기본 | 설명 |
|---|---|---|---|---|
| `slice_type` | `SliceType` | 아니오 | `null` | 필터. `null`이면 전부 |
| `region` | string | 아니오 | `null` | 필터 |

**출력: `[Offering]`** — 벤더 5곳 × 슬라이스 3타입. 원본 `data/vendors.json`.

| 필드 | 타입 | 단위 |
|---|---|---|
| `vendor_id` · `name` | string | |
| `slice_type` | `SliceType` | |
| `latency` | float | ms |
| `bandwidth` | float | Mbps |
| `reliability` | float | % |
| `cost` | float | 시간당 |
| `regions` | `[string]` | |
| `rating` | float | 1.0 ~ 5.0 |

```json
// 요청
{"slice_type": "URLLC"}
// 응답 (실측값, 일부)
[
  {"vendor_id": "vendor-1", "name": "TelcoNet Solutions", "slice_type": "URLLC",
   "latency": 1.0, "bandwidth": 500.0, "reliability": 99.999, "cost": 250.0,
   "regions": ["us-east"], "rating": 4.8},
  {"vendor_id": "vendor-2", "name": "GlobalConnect 5G", "slice_type": "URLLC",
   "latency": 2.0, "bandwidth": 400.0, "reliability": 99.99, "cost": 220.0,
   "regions": ["eu-west"], "rating": 4.5},
  {"vendor_id": "vendor-3", "name": "NextGen Networks", "slice_type": "URLLC",
   "latency": 0.5, "bandwidth": 600.0, "reliability": 99.9995, "cost": 300.0,
   "regions": ["ap-northeast"], "rating": 4.9}
]
```

---

## `score_offerings(slice_type, qos_requirements)`

| 파라미터 | 타입 | 필수 |
|---|---|---|
| `slice_type` | `SliceType` | 예 |
| `qos_requirements` | object | 예 |

**출력: `[ScoredOffering]`** — 점수 내림차순

| 필드 | 타입 | 범위 |
|---|---|---|
| `rank` | int | 1부터 |
| `vendor_id` · `name` | string | |
| `score` | float | 0 ~ 100 |
| `rating` | float | 1.0 ~ 5.0 |
| `cost` | float | |

**점수 공식** (`engine.py:719~790`, `score_vendor_offering()`)

```
qos_score  = Σ(scoreᵢ × weightᵢ) / Σ(weightᵢ)      # 존재하는 기준만, 정규화
reputation = rating / 5.0                          # 가중치 0.2 (URLLC) / 0.1 (그 외)
price      = _calculate_price_score(cost, slice_type)   # 가중치 0.2 (기본)
qos_weight = 1.0 − (reputation_weight + price_weight)
total      = (qos_score × qos_weight + reputation × rep_w + price × price_w) × 100
```

`rating`이 총점의 10~20%를 차지한다. **⑤의 피드백이 `update_rating`으로 여기에 들어와 순위를 바꾼다.**

```json
// 요청
{"slice_type": "URLLC", "qos_requirements": {"latency": 1.0, "bandwidth": 400, "reliability": 99.99}}
// 응답 (engine.py 실행 실측값)
[
  {"rank": 1, "vendor_id": "vendor-1", "name": "TelcoNet Solutions",  "score": 99.20, "rating": 4.8, "cost": 250.0},
  {"rank": 2, "vendor_id": "vendor-5", "name": "AsiaPacific Telecom", "score": 98.00, "rating": 4.7, "cost": 260.0},
  {"rank": 3, "vendor_id": "vendor-3", "name": "NextGen Networks",    "score": 97.60, "rating": 4.9, "cost": 300.0},
  {"rank": 4, "vendor_id": "vendor-4", "name": "EuroSlice Providers", "score": 91.76, "rating": 4.6, "cost": 240.0},
  {"rank": 5, "vendor_id": "vendor-2", "name": "GlobalConnect 5G",    "score": 86.20, "rating": 4.5, "cost": 220.0}
]
```

---

## `explain_score(vendor_id, slice_type, qos_requirements)`

| 파라미터 | 타입 | 필수 |
|---|---|---|
| `vendor_id` | string | 예 |
| `slice_type` | `SliceType` | 예 |
| `qos_requirements` | object | 예 |

**출력: `ScoreBreakdown`**

| 필드 | 타입 | 설명 |
|---|---|---|
| `total` | float | **`score_offerings`의 `score`와 반드시 일치** |
| `criteria_scores` | `{criterion: float}` | 기준별 원점수 0~1 |
| `weights` | `{criterion: float}` | 적용된 가중치 |
| `contributions` | `{criterion: float}` | 총점 100 기준 기여분 |
| `explanation` | string | 사람이 읽는 요약 |

**구현 규칙 ⚠️ (정정 J)**
- 기존 `get_score_breakdown()`(`engine.py:819`)을 **호출하지 않는다.** `rating` 대신 존재하지 않는 `reputation_score` 키를 읽어 총점이 어긋난다 (99.20 vs 92.00).
- `score_vendor_offering()`의 실제 계산을 분해해 새로 구현한다 (약 30줄).
- `neural_network` 키(601바이트, UI용 장식)는 **반환하지 않는다.**

```json
{
  "total": 99.20,
  "criteria_scores": {"latency": 1.00, "bandwidth": 1.00, "reliability": 1.00,
                      "reputation": 0.96, "price": 1.00},
  "weights": {"latency": 0.35, "bandwidth": 0.10, "reliability": 0.25,
              "reputation": 0.20, "price": 0.20},
  "contributions": {"latency": 30.00, "bandwidth": 8.57, "reliability": 21.43,
                    "reputation": 19.20, "price": 20.00},
  "explanation": "지연 1.0ms가 요구 1.0ms를 충족(1.00). 평판 4.8/5.0이 총점의 19.2점을 기여. 가격 250이 URLLC 기준가와 동일해 감점 없음."
}
```

---

## `procure(vendor_id, slice_type, qos_requirements, duration_steps, current_step)`

| 파라미터 | 타입 | 필수 | 범위 | 설명 |
|---|---|---|---|---|
| `vendor_id` | string | 예 | | |
| `slice_type` | `SliceType` | 예 | | |
| `qos_requirements` | object | 예 | | |
| `duration_steps` | int | 예 | 1 ~ 60 | **시간이 아니라 스텝** |
| `current_step` | int | **예** | ≥ 0 | `observation.step`. ③은 시뮬레이션 시각을 모른다 |

**비용 환산** — `vendors.json`의 `cost`는 시간당, `duration_steps`는 스텝. `MINUTES_PER_STEP = 15`.

```
cost_total = cost × duration_steps × (MINUTES_PER_STEP / 60)
           = 250 × 10 × 0.25 = 625.0
```

**용량 환산** — 상수는 `const.py`.

```
capacity_gain   = (offering.bandwidth / REFERENCE_BANDWIDTH[slice_type]) × GAIN_SCALE
expires_at_step = current_step + duration_steps
```

| 상수 | 값 |
|---|---|
| `REFERENCE_BANDWIDTH` | `{eMBB: 1100, URLLC: 500, mMTC: 120}` (벤더별 슬라이스 대역폭 중앙값) |
| `GAIN_SCALE` | `0.25` |
| `CAPACITY_MAX` | `2.0` (슬라이스당, ①이 강제) |

| 벤더 (URLLC) | 대역폭 | `capacity_gain` |
|---|---|---|
| GlobalConnect 5G | 400 | **0.20** |
| TelcoNet Solutions | 500 | **0.25** |
| NextGen Networks | 600 | **0.30** |

| 출력 필드 | 타입 | 설명 |
|---|---|---|
| `slice_id` | string | 조달된 슬라이스 식별자. **④ `record_decision.slice_id`에 기록** |
| `status` | string | `active` · `rejected` |
| `vendor_id` | string | |
| `cost_total` | float | 위 환산식 |
| **`capacity_gain`** | float | **①의 `add_capacity(amount=...)`에 그대로 넣는다** |
| `expires_at_step` | int | 만료 스텝 |
| `reason` | string \| null | 거부 사유 |

```json
// 요청
{"vendor_id": "vendor-1", "slice_type": "URLLC",
 "qos_requirements": {"latency": 1.0, "bandwidth": 400, "reliability": 99.99},
 "duration_steps": 10, "current_step": 12}
// 응답
{"slice_id": "slice-urllc-0012-v1", "status": "active", "vendor_id": "vendor-1",
 "cost_total": 625.0, "capacity_gain": 0.250, "expires_at_step": 22, "reason": null}
```

**비용은 제약이 아니다.** 예산 없음. ④가 `procurement_cost_total`을 집계해 논문 지표로 보고한다.

---

## `update_rating(vendor_id, outcome)`

⑤의 `report_outcome` 결과를 **에이전트가 중계**해 호출한다.

| 파라미터 | 타입 | 필수 | 출처 |
|---|---|---|---|
| `vendor_id` | string | 예 | ⑤ `report_outcome().vendor_id` |
| `outcome.sla_met` | bool | 예 | ⑤ `report_outcome().sla_met` |
| `outcome.decision_id` | string | 예 | 추적용 |

| 출력 필드 | 타입 |
|---|---|
| `vendor_id` | string |
| `rating_before` · `rating_after` | float |
| `delta` | float |

**갱신식**: `rating ← clip(rating + δ, 1.0, 5.0)`, `δ = +0.05` (충족) / `−0.20` (위반). `vendors.json`에 반영.

```json
// 요청
{"vendor_id": "vendor-1", "outcome": {"sla_met": false, "decision_id": "exp-proposed-emergency-s0-0012"}}
// 응답
{"vendor_id": "vendor-1", "rating_before": 4.80, "rating_after": 4.60, "delta": -0.20}
```
