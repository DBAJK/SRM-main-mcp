<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 제어 루프 계약

1스텝의 시간 규약 · 액추에이터 · 고정 루프 · 컨텍스트 · 에스컬레이션 정의

# 3. 제어 루프 계약

**분리 설계서에 없던 부분이고, 측정 지표의 정의가 전부 여기에 달려 있다.**

# 3.1 시간 규약

원 코드의 `run_step()`(`:535`)은 한 스텝 안에서 트래픽 생성 → 이용률 계산 → 배분 갱신을 모두 한다. MCP에서는 배분 갱신이 에이전트 쪽으로 나가므로 **이 순서를 쪼개야 하고, 쪼개는 지점이 곧 지표의 정의가 된다.**

```python
# ml_orchestrator_demo.py:545
utilization = self.update_utilization(traffic)    # ← 이 시점의 allocation은 직전 스텝의 것
...
allocation = self.update_allocation_*(...)        # ← 그 다음에 갱신
```

즉 **이용률은 언제나 "직전 결정의 결과"** 다. 이 성질을 그대로 살린다.

```
reset(run_id, scenario, seed)
  └─ alloc ← [0.4, 0.4, 0.2],  cap ← [1, 1, 1],  traffic₀ 생성
     util₀ = traffic₀ / (alloc × cap)

── 스텝 t ──────────────────────────────────────────────────
  1.  obs_t = ①.get_observation()             # util_t 는 a_{t-1}의 성적표
  2.  [에이전트 판단]  ②.classify_demand / propose_allocation
                      ⑤.get_reliability_table
  2b. [조달 분기]  obs_t.demand_pressure ≥ 1.0 일 때만
        ③.score_offerings → ③.procure(..., current_step=t)
        ①.add_capacity(amount=capacity_gain, expires_at_step)
  3.  ④.record_decision(..., slice_id, vendor_id) → decision_id
  4.  ①.apply_allocation(a_t)                 # 액추에이터. 평활·클립·정규화
  5.  ①.step()                                # 만료 회수 → traffic_{t+1}
                                              # util_{t+1} = traffic_{t+1} / (a_t × cap_{t+1})
  6.  ⑤.report_outcome(decision_id, obs_{t+1})
──────────────────────────────────────────────────────────
```

**따르는 규칙 네 가지**

1. **결정의 채점은 1스텝 지연된다.** t의 결정은 t+1의 관측으로 평가된다. `report_outcome`은 반드시 `step()` 이후에 호출한다.
2. **에피소드 마지막 결정은 채점되지 않는다.** 지표 집계에서 제외한다. 60스텝이면 유효 표본 59.
3. **기록은 배분 실행(4)보다 먼저다.** 에이전트가 판단만 하고 실행에 실패한 경우도 ④에 남는다. 실행 후 기록이면 실패 사례가 사라져 자율 처리율이 과대평가된다.
4. **조달(2b)만 기록보다 앞선다.** 규칙 3의 예외이며, `record_decision`이 `slice_id`·`vendor_id`를 인자로 받기 때문이다. **에스컬레이션한 스텝도 똑같다** — 2b는 건너뛰지 않고, 조달 3필드를 `record_escalation`에 넘긴다 (`record_escalation`도 같은 인자를 받는다). 건너뛰면 `demand_pressure ≥ 1.0`에서 유일한 지렛대인 용량을 포기하는 것이고, 넘기지 않으면 그 조달이 아무 레코드에도 안 남아 ⑤→③ 레이팅 되먹임이 끊긴다.

# 조달이 기록보다 앞서는 것이 규칙 3과 충돌하지 않는 이유

규칙 3의 목적은 *"판단했으나 실행하지 못한 경우를 남기는 것"* 이다. 조달은 **판단의 일부로서 기록에 포함**되므로 목적이 훼손되지 않는다.

```
조달 성공 → record_decision(slice_id="slice-...", vendor_id="vendor-1", cost_total=625.0)
조달 실패 → record_decision(slice_id=null, rationale="procure rejected: capacity cap exceeded")
에스컬레이션 → record_escalation(..., slice_id="slice-...", vendor_id="vendor-1", cost_total=625.0)
```

실패해도 `rationale`에 남는다. **조달을 시도했다는 사실 자체가 판단의 증거**이므로 기록되어야 한다.

**`add_capacity`는 반드시 `step()`(5) 전에** 호출한다. 뒤로 가면 용량이 다음 스텝부터 반영되어 조달한 바로 그 스텝은 효과를 보지 못한다. 에이전트 입장에서 "샀는데 아무 일도 안 일어났다"가 되어 조달 학습이 왜곡된다.

# 3.2 `apply_allocation`은 액추에이터다

현재 평활·클립·정규화가 `update_allocation_ml`(`:401~407`)과 `update_allocation_rule_based`(`:459~462`)에 **중복**되어 있다.

```python
stability_factor = 0.7
new_allocation = 0.7 * self.allocation + 0.3 * target
new_allocation = np.clip(new_allocation, 0.1, 0.8)
new_allocation = new_allocation / np.sum(new_allocation)
```

**이걸 정책에서 떼어 ①의 `apply_allocation()` 한 곳에 둔다.** 세 가지 이득이 있다.

- **정책 비교가 공정해진다** — 모든 정책이 동일한 액추에이터를 통과한다. 정책은 "목표 배분"만 내고, 물리적 제약(급변 금지, 슬라이스당 10~80%)은 환경이 강제한다. 현실의 RAN 제약에 대응하므로 모델링으로도 타당하다.
- **에이전트가 제약을 학습할 수 있다** — 요청이 얼마나 깎였는지 `accepted`/`normalized`/`reason`으로 돌려준다.
- **DQN 추가 시 재작성이 없다** — DQN은 이산 액션 27개를 배분 벡터로 바꾸기만 하면 된다.

```python
apply_allocation(embb, urllc, mmtc) -> {
    "accepted": bool,
    "requested":  {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10},
    "normalized": {"embb": 0.34, "urllc": 0.49, "mmtc": 0.17},   # 평활 후
    "reason": "smoothed(0.7) + clipped to [0.1,0.8]"
}
```

`accepted=False`는 입력이 비정상일 때만(음수, 합이 0, NaN). 정상 입력은 항상 수용하되 변형해서 알린다.

# 3.3 오케스트레이터는 고정 루프다 — LLM이 순서를 정하지 않는다

**MCP는 도구를 줄 뿐 호출 순서를 강제하지 않는다.** §3.1의 6단계를 LLM에게 맡기면 스텝당 6~10회 호출 × 120스텝 × 60회 실행 동안 반드시 다음이 일어난다.

- `report_outcome`을 빠뜨린다 → 그 스텝이 채점되지 않는다 (§1.5 V2와 같은 증상)
- 순서가 뒤집힌다 → `add_capacity`가 `step()` 뒤로 가면 조달이 무효가 된다 (§1.6 W1)
- 20~30스텝 뒤 드리프트한다 → 후반부 데이터가 전반부와 다른 절차로 생산된다

§8의 오류 규약이 잡는 것은 일부뿐이다. **대부분의 위반은 조용하다** — 호출하지 않은 것은 오류를 내지 않는다.

**따라서 루프는 파이썬이 돌리고, LLM은 판단 지점에서만 호출한다.**

```python
for t in range(total_steps):
    obs = observe.get_observation()
    rel = feedback.get_reliability_table()

    j = ask_llm(obs, rel, recent)          # ← LLM은 여기서만
    #   j.situation, j.confidence_situation
    #   j.policy, j.procure_or_not, j.escalate_or_not

    if j.procure: ...                       # 2b
    audit.record_decision(...)              # 3   ← 파이썬이 보장
    observe.apply_allocation(...)           # 4
    observe.step()                          # 5
    feedback.report_outcome(...)            # 6
```

LLM이 답할 것은 **네 가지뿐**이다 — `situation` / 어느 정책 / 조달할까 / 사람을 부를까. §1.5에서 *"`AGENT`가 생산자인 값은 네 개뿐이어야 한다"* 고 한 그 넷과 정확히 일치한다.

**이것이 논문에도 유리하다.** 자율성 주장은 **판단**에 관한 것이지 도구 호출 순서에 관한 것이 아니다. 루프를 고정하면

- 변수가 격리되어 비교군 간 차이가 전부 판단에서 나온다
- *"에이전트가 루프를 잘못 돌아서 SLA가 나빴다"* 는 반론이 원천 차단된다
- 60회 실행이 **동일한 절차**로 생산된다

> 이 구조에서도 에이전트는 여전히 자율적이다. 무엇을 할지는 LLM이 정하고, 정한 것을 빠짐없이 실행하는 것만 파이썬이 보장한다. 사람으로 치면 **절차서를 지키는 것과 판단하는 것의 분리**다.

## 3.3b 두 번째 드라이버 — LLM 오케스트레이터 (2026-09-23 추가)

위 고정 루프는 `--driver fixed` 로 남고, **`--driver orchestrator`** 가 그 대조군으로 추가됐다.
LLM 이 게이트웨이(`agent/orchestrator/gateway.py`) 하나에 MCP 로 붙어 21개 도구를 직접 들고
한 스텝의 흐름을 스스로 잡는다. 파이썬이 하는 것은 셋뿐이다.

| 파이썬 | LLM |
|---|---|
| 스텝 경계 — `claude -p` 를 스텝마다 새로 띄우고 직전 5스텝 요약만 넣는다 (§3.4 그대로) | 어느 도구를 언제 몇 번 부를지 |
| Guard — 반환값마다 금지 문자열 검사 (게이트웨이 미들웨어) | 상황 · 정책 · 조달 · 벤더 선택 |
| 심판(`referee.py`) — 스텝이 끝난 뒤 위 §3.1 규약 위반을 **기록만** 한다 | `compute_confidence` 결과를 보고 `record_escalation` 을 스스로 부른다 |

위에서 든 우려(누락 · 역전 · 드리프트)는 막지 않고 **측정한다.** 심판이 내는 `procedure_adherence`
와 위반 코드 분포가 "LLM 이 절차를 얼마나 스스로 지키는가"의 지표이고, 고정 루프에서는 정의상 0이다.
`combined` 공식은 여기서도 코드다 — 게이트웨이의 `compute_confidence` 도구가 `schema.py` 와 같은
식을 계산하므로, 개입률 비교의 공정성은 두 드라이버에서 같다. `reset` 은 LLM 에 노출하지 않는다.

# 3.4 컨텍스트는 스텝마다 재구성한다

120스텝 대화를 누적하면 후반에 **100k 토큰**을 넘는다. 비용·지연이 폭증하고, 모델이 20스텝 전의 낡은 관측에 주의를 뺏긴다.

**매 스텝 프롬프트를 새로 만든다.** 대화 이력을 이어붙이지 않는다.

```
시스템 프롬프트 (고정, minimal/advisory 2벌)
+ 현재 관측 1건
+ ⑤의 신뢰도 표
+ 최근 N스텝 요약 (N = 5, 한 줄씩: step/situation/policy/sla_met)
```

최근 이력을 **원본이 아니라 요약**으로 넣는 것이 핵심이다. `get_decisions(n=5)`를 그대로 넣으면 관측이 통째로 딸려와 5배가 된다 (`TOOLS.md` §9).

> 부수 효과로 **프롬프트가 재현 가능해진다.** 같은 스텝에서 같은 입력이면 같은 프롬프트가 만들어지므로, 프롬프트 해시를 `decisions.json`에 기록해 사후 추적할 수 있다 (§9-9).

# 3.5 에스컬레이션의 조작적 정의

분리 설계서 §6의 "개입 1회"를 도구 수준으로 확정한다.

```python
④.record_escalation(observation, reason, confidence) -> {"escalation_id": str}
```

- 이 도구를 **호출한 것 자체가 개입 1회**다. 별도의 사람 응답 대기는 없다.
- 호출 후 에이전트는 **`rule_based` + `situation="normal"`로 진행한다.** 이것이 "사람이 올 때까지의 안전 기본 동작"이며, 사람의 개입 없이도 에피소드가 끝까지 돌아간다.
- 따라서 **모든 비교군이 동일한 스텝 수를 소화한다.** SLA 위반 비교가 공정해진다.

이 정의 덕분에 실험에 사람이 실제로 필요 없다. *"개입 횟수"는 사람을 부른 횟수이지 사람이 일한 시간이 아니다* — 이 점을 논문에 명시한다.

---
