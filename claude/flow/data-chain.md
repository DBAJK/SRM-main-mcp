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
    [에이전트: combined = √(intrinsic × effective)]
            │
            ├── combined < 0.45 ──→ ④.record_escalation(...) ──→ decision_id + fallback 지시
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
  slice_id · vendor_id → ④.record_decision에 함께 기록
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
| ③.`procure` | `slice_id` | ④.`record_decision` · ①.`add_capacity` | `slice_id` |
| | `vendor_id` | ④.`record_decision` | `vendor_id` |
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

어느 도구에서도 오지 않는다. **이 네 가지가 연구의 기여 지점 전체다.** 어느 서버에도 이 코드가 없다.

| 값 | 쓰이는 곳 | 근거 |
|---|---|---|
| `situation` | ②.`propose_allocation`, ④.`record_decision` | 관측으로부터 **추론** |
| `confidence.combined` | ④.`record_decision` | `√(intrinsic × effective)` |
| 에스컬레이션 판단 | ④.`record_escalation` | `combined < 0.45` |
| 정책 선택 | ②.`propose_allocation`의 `policy` | 신뢰도 비교 |
