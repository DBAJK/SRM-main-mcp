# 도구 일람

5개 서버 · 도구 21개. 상세 계약은 `spec/<server>.md`.

| 서버 | 도구 | 입력 | 출력 | 부작용 |
|---|---|---|---|---|
| ① observe | `get_observation` | — | `Observation` | 없음 |
| | `step` | `n` | `Observation` | **상태 전진** |
| | `apply_allocation` | `SliceTriple` | `ApplyResult` | **배분 변경** |
| | `get_history` | `n` | `HistoryBlock` | 없음 |
| | `add_capacity` | `slice_type`, `amount`, `expires_at_step` | `CapacityState` | **용량 증설** |
| | `reset` | `run_id`, `scenario`, `seed` | `Observation` | **에피소드 초기화** |
| ② policy | `list_policies` | — | `[PolicyInfo]` | 없음 |
| | `propose_allocation` | `policy`, `Observation`, `situation`, `history`, `recent_error` | `PolicyProposal` | 없음 |
| | `compare_policies` | `Observation`, `situation`, `history` | `[PolicyProposal]` | 없음 |
| | `classify_demand` | `Observation` | `DemandClass` | 없음 |
| ③ market | `list_offerings` | `slice_type`, `region` | `[Offering]` | 없음 |
| | `score_offerings` | `slice_type`, `qos` | `[ScoredOffering]` | 없음 |
| | `explain_score` | `vendor_id`, `slice_type`, `qos` | `ScoreBreakdown` | 없음 |
| | `procure` | `vendor_id`, `slice_type`, `qos`, `duration_steps` | `Procurement` | **조달 기록** |
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
1. ①.get_observation()                          → obs
2. ②.classify_demand(obs)                       → dominant        (선택)
   ⑤.get_reliability_table()                    → effective, recent_error
   [에이전트] situation 추론
3. ②.propose_allocation(policy, obs, situation, history, recent_error)
   [에이전트] combined = √(intrinsic × effective);  < 0.45 → ④.record_escalation
4. ④.record_decision(...)                       → decision_id     (apply 전에!)
5. [demand_pressure ≥ 1.0] ③.score_offerings → ③.procure → ①.add_capacity
6. ①.apply_allocation(**allocation)             → normalized, delta
7. ①.step()                                     → obs₊₁
8. ⑤.report_outcome(decision_id, obs₊₁)         → sla_met, vendor_id
9. [vendor_id 있으면] ③.update_rating(vendor_id, {sla_met, decision_id})
```

**서버끼리 직접 대화하지 않는다.** 모든 값은 에이전트를 통과한다. 전체 도식과 출력→입력 대응표는 `flow/data-chain.md`.
