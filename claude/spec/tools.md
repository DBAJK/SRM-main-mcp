# 도구 일람

5개 서버 · 도구 21개. 상세 계약은 `spec/<server>.md`.

| 서버 | 도구 | 입력 | 출력 | 부작용 |
|---|---|---|---|---|
| ① observe | `get_observation` | — | `Observation` | 없음 |
| | `step` | `n` | `Observation` | **상태 전진** |
| | `apply_allocation` | `SliceTriple` | `ApplyResult` | **배분 변경** |
| | `get_history` | `n` | `HistoryBlock` | 없음 |
| | `add_capacity` | `slice_type`, `amount`, `expires_at_step`, `slice_id` | `CapacityState` | **용량 증설** |
| | `reset` | `run_id`, `scenario`, `seed` | `Observation` | **에피소드 초기화** |
| ② policy | `list_policies` | — | `[PolicyInfo]` | 없음 |
| | `propose_allocation` | `policy`, `Observation`, `situation`, `history`, `recent_error` | `PolicyProposal` | 없음 |
| | `compare_policies` | `Observation`, `situation`, `history`, `recent_errors` | `[PolicyProposal]` | 없음 |
| | `classify_demand` | `Observation` | `DemandClass` | 없음 |
| ③ market | `list_offerings` | `slice_type`, `region` | `[Offering]` | 없음 |
| | `score_offerings` | `slice_type`, `qos` | `[ScoredOffering]` | 없음 |
| | `explain_score` | `vendor_id`, `slice_type`, `qos` | `ScoreBreakdown` | 없음 |
| | `procure` | `vendor_id`, `slice_type`, `qos`, `duration_steps`, `current_step` | `Procurement` | **조달 기록** |
| | `update_rating` | `vendor_id`, `outcome` | `RatingUpdate` | **vendors.json 갱신** |
| ④ audit | `record_decision` | 판단 일체 | `{decision_id}` | **기록** |
| | `record_escalation` | 판단 + 사유 | `{escalation_id, decision_id, fallback}` | **기록 = 개입 1회 + 폴백 결정** |
| | `get_decisions` | `n`, `kind` | `[Decision]` | 없음 |
| | `get_metrics` | `window` | `Metrics` | 없음 |
| ⑤ feedback | `report_outcome` | `decision_id`, `Observation` | `Outcome` | **신뢰도 갱신** |
| | `get_reliability_table` | — | `ReliabilityTable` | 없음 |

**부작용 있는 도구 8개는 한 스텝에 정해진 횟수만 호출된다.** `step`·`apply_allocation`·`record_decision`·`report_outcome`은 각 1회, `record_escalation`·`procure`·`add_capacity`는 0 또는 1회.

## 1스텝 표준 호출 순서

```
1.  ①.get_observation()                         → obs
1b. ①.get_history(10)                           → history          ← 빠뜨리면 LSTM이 영영 unavailable
2.  ②.classify_demand(obs)                      → dominant         (선택)
    ⑤.get_reliability_table()                   → effective, recent_error
    [LLM] situation · confidence.situation 추론
3.  ②.propose_allocation(policy, obs, situation, history, recent_error)
    [파이썬] combined = (situation × intrinsic × effective)^(1/3)

    ├─ combined < 0.45  →  4는 그대로 하고, 5 대신
    │                      ④.record_escalation(..., slice_id, vendor_id, cost_total)
    │                      → escalation_id, decision_id, fallback_allocation
    │                      **5를 건너뛰고 6으로.** allocation ← fallback_allocation
    │                      (record_decision을 또 부르면 같은 스텝에 decision 레코드가 둘)
    │
    └─ 계속 ↓

4.  [LLM 조달 판단 · demand_pressure ≥ 1.0일 때만]
    ③.score_offerings → ③.procure(current_step=obs.step) → ①.add_capacity
5.  ④.record_decision(..., slice_id, vendor_id)  → decision_id     (apply 전에!)

6.  ①.apply_allocation(**allocation)             → normalized, delta
7.  ①.step()                                     → obs₊₁
8.  ⑤.report_outcome(decision_id, obs₊₁)         → sla_met, vendor_id
9.  [vendor_id 있으면] ③.update_rating(vendor_id, {sla_met, decision_id})
```

**조달이 기록보다 앞서는 이유** — `record_decision` 이 `slice_id` · `vendor_id` 를 인자로 받기
때문이다 (설계서 §3.1 규칙 4). 뒤집으면 결정 레코드에 `vendor_id` 가 없고, ⑤ `report_outcome` 이
그 레코드에서 `vendor_id` 를 찾으므로 **항상 `null` 이 되어 ⑤→③ 레이팅 되먹임이 통째로 죽는다.**
"판단했으나 실행하지 못한 경우를 남긴다"는 규칙 3의 목적은 훼손되지 않는다 — 조달 실패도
`slice_id: null` + `rationale` 로 기록되기 때문이다.

`add_capacity` 는 반드시 `step()`(7) **전**에 부른다. 뒤로 가면 용량이 다음 스텝부터 반영되어
조달한 바로 그 스텝은 효과를 못 본다 (W1).

**1b를 빠뜨리면 `lstm_forecast`가 영영 `status: "unavailable"`(`history_insufficient`)이 되어
정책 선택 축이 죽는다.** `history`는 3단계의 인자인데 얻는 호출이 순서에 없으면 `null`로 넘어간다.

**에스컬레이션 분기는 5만 건너뛴다.** `record_escalation`이 이미 `decision_id`와 `fallback_allocation`을
내므로 `record_decision`을 또 부르면 같은 스텝에 `kind: "decision"` 레코드가 둘 생기고
`sum(policy_usage)` 불변식이 깨진다 (`spec/audit.md`).

**4(조달)는 건너뛰지 않는다.** 에스컬레이션은 "사람을 불렀다"는 기록이지 "아무것도 하지 말라"가
아니고, `demand_pressure ≥ 1.0`이면 폴백 배분 `[0.4, 0.4, 0.2]`으로는 어떤 배분으로도 SLA를
지킬 수 없어 **용량이 유일한 지렛대다.** 조달했다면 `slice_id` · `vendor_id` · `cost_total`을
`record_escalation`에 그대로 넘긴다 — `record_decision`과 같은 자리이며, 넘기지 않으면 그 조달이
아무 레코드에도 안 남고 ⑤→③ 레이팅 되먹임이 끊긴다.

**루프는 파이썬이 돌린다.** LLM은 2·4단계에서만 호출하며 답하는 값은 넷뿐이다 —
`situation` · `confidence.situation` · 정책 선택 · 조달 여부. `combined`와 에스컬레이션 여부는
파이썬이 계산한다. 근거는 `flow/loop.md`.

**서버끼리 직접 대화하지 않는다.** 모든 값은 에이전트를 통과한다. 전체 도식과 출력→입력 대응표는 `flow/data-chain.md`.
