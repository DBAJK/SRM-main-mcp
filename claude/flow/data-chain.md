# 데이터 연쇄 — 어떤 출력이 어떤 입력이 되는가

**서버끼리 직접 대화하지 않는다.** 모든 값은 에이전트를 통과한다.

## 1스텝 흐름

```
①.get_observation()  ──→  obs
                            │
    ┌───────────────────────┼────────────────────────┐
    │                       │                        │
    ▼                       ▼                        ▼
②.classify_demand      ⑤.get_reliability_table    [에이전트 추론]
  (observation=obs)       ( — )                     situation
    │                       │                        │
    │ dominant              │ effective, recent_error│
    └───────┬───────────────┴────────────────────────┘
            ▼
    ②.propose_allocation(policy, observation=obs, situation, history, recent_error)
            │
            │ allocation, confidence(내재적)
            ▼
    [에이전트: combined = (situation × intrinsic × effective)^(1/3)]
            │
            ├── combined < 0.45 ──→ ④.record_escalation(..., slice_id, vendor_id, cost_total)
            │                       ──→ decision_id + fallback 지시 (조달 3필드는 아래와 같은 중계선)
            │
            ▼
    ④.record_decision(step, obs, situation, policy, allocation, confidence, rationale, ...)
            │
            │ decision_id
            ▼
    ①.apply_allocation(**allocation)  ──→  normalized, delta
            │
            ▼
    ①.step()  ──→  obs₊₁
            │
            ▼
    ⑤.report_outcome(decision_id, observed=obs₊₁)
            │
            │ vendor_id (조달했다면)
            ▼
    ③.update_rating(vendor_id, outcome={sla_met, decision_id})
```

## 조달 분기

`demand_pressure ≥ 1.0`일 때만 의미가 있다. 배분 결정과 같은 스텝, `step()` 전에 일어난다.

```
obs.demand_pressure ≥ 1.0
        │
        ▼
③.score_offerings(slice_type, qos)  ──→ vendor_id (1위)
        │
        ▼
③.procure(vendor_id, slice_type, qos, duration_steps, current_step=obs.step)
        │
        │ capacity_gain, expires_at_step, slice_id
        ▼
①.add_capacity(slice_type, amount=capacity_gain, expires_at_step, slice_id)
        │
        │ demand_pressure (반영 후)
        ▼
  [에이전트: 여전히 ≥ 1.0이면 추가 조달 또는 위반 감수]
  slice_id · vendor_id · cost_total → ④.record_decision 에 함께 기록
                                      (에스컬레이션한 스텝이면 ④.record_escalation 에)
```

**③과 ①은 직접 대화하지 않는다.** `capacity_gain`을 에이전트가 옮겨 심는다. ⑤ → ③의 `update_rating` 중계, ⑤ → ②의 `recent_error` 중계와 같은 패턴이다.

## 출력 → 입력 대응표

| 생산 | 필드 | 소비 | 파라미터 |
|---|---|---|---|
| ①.`get_observation` | `Observation` 전체 | ②.`propose_allocation` | `observation` |
| | | ②.`classify_demand` | `observation` |
| | | ④.`record_decision` | `observation` |
| | `demand_pressure` | — | **에이전트의 조달 판단 근거** |
| ①.`get_history` | `HistoryBlock` 전체 | ②.`propose_allocation` | `history` |
| ①.`step` | `observation` | ⑤.`report_outcome` | `observed` |
| ②.`propose_allocation` | `allocation` | ①.`apply_allocation` | `embb`/`urllc`/`mmtc` |
| | `confidence` | ④.`record_decision` | `confidence.intrinsic` |
| | `in_distribution` | ④.`record_decision` | `in_distribution` |
| ②.`classify_demand` | 출력 전체 | ④.`record_decision` | `demand_class` |
| ②.`compare_policies` | 탈락 후보 목록 | ④.`record_decision` | `considered` |
| ③.`score_offerings` | `vendor_id` | ③.`explain_score` · ③.`procure` | `vendor_id` |
| ③.`procure` | `slice_id` | ④.`record_decision` \| `record_escalation` · ①.`add_capacity` | `slice_id` |
| | `vendor_id` | ④.`record_decision` \| `record_escalation` | `vendor_id` |
| | `cost_total` | ④.`record_decision` \| `record_escalation` | `cost_total` |
| | `capacity_gain` | ①.`add_capacity` | `amount` |
| | `expires_at_step` | ①.`add_capacity` | `expires_at_step` |
| ④.`record_decision` | `decision_id` | ⑤.`report_outcome` | `decision_id` |
| ④.`record_escalation` | `decision_id` | ⑤.`report_outcome` | `decision_id` |
| | `fallback_allocation` | ①.`apply_allocation` | `embb`/`urllc`/`mmtc` |
| ⑤.`report_outcome` | `vendor_id`, `sla_met` | ③.`update_rating` | `vendor_id`, `outcome` |
| ⑤.`get_reliability_table` | `{policy}.effective` | ④.`record_decision` | `confidence.empirical` |
| | `{policy}.recent_error` | ②.`propose_allocation` | `recent_error` |
| | 테이블 전체 | ②.`compare_policies` | `recent_errors` |
| 에이전트 | `run_id` | ①.`reset` · ④ 전체 | `run_id` |

## 에이전트가 만들어내는 값

어느 도구에서도 오지 않는다. **LLM이 답하는 값은 정확히 넷이다.** 어느 서버에도 이 코드가 없다.

| 값 | 쓰이는 곳 | 근거 |
|---|---|---|
| `situation` | ②.`propose_allocation`, ④.`record_decision` | 관측(특히 트래픽 **구성비**)으로부터 추론 |
| `confidence.situation` | ④.`record_decision` | **상황 판단 자체에 대한 확신.** 어느 도구도 주지 않는다 |
| 정책 선택 | ②.`propose_allocation`의 `policy` | 신뢰도 비교 |
| 조달 여부 | ③.`procure` 호출 여부 | `demand_pressure` + 비용 판단 |

**나머지 둘은 파이썬이 기계적으로 계산한다.** LLM에게 묻지 않는다.

| 값 | 계산 |
|---|---|
| `confidence.combined` | `(situation × intrinsic × empirical)^(1/3)` |
| 에스컬레이션 여부 | `combined < 0.45` |

`check_contract.py`는 `AGENT` 생산 값이 **정확히 이 넷**인지 검사한다 — 늘면 판단이 서버로 샌 것이고,
줄면 기여가 사라진 것이다. (`flow/loop.md` — 루프는 파이썬이 돌리고 LLM은 판단 지점에서만 호출한다)
