# agent — LLM 에이전트

MCP 서버 5개를 조합해 자원 배분을 판단한다. **판단은 전부 여기서 하고, 서버는 능력만 제공한다.**

도구 계약은 `claude/spec/`, 데이터 연쇄는 `claude/flow/data-chain.md`. 이 문서는 그 명세를 코드로 옮긴 구조만 설명한다.

---

## 이 에이전트가 만들어내는 값

어느 서버도 생산하지 않는다. `claude/flow/data-chain.md:101` — **"이 네 가지가 연구의 기여 지점 전체다."**

| 값 | 어디서 | 근거 |
|---|---|---|
| `situation` | `deciders/*.py` | 관측으로부터 **추론**. ①이 정답을 주지 않는다 |
| `confidence.combined` | `schema.py` 파생 속성 | `√(intrinsic × empirical)` |
| 에스컬레이션 판단 | `deciders/*.py` | `combined < 0.45` |
| 정책 선택 | `deciders/*.py` | 신뢰도 비교 |

---

## 드라이버 둘 — 누가 다음 도구를 정하나

| | `--driver fixed` (아래 전부) | `--driver orchestrator` (`orchestrator/`) |
|---|---|---|
| 도구 호출 순서 | 파이썬 `loop.py` 9스텝 고정 | **LLM** 이 게이트웨이의 도구를 직접 부른다 |
| LLM 이 답하는 것 | situation · 확신 · 정책 · 조달 여부 | 위 넷 + 어느 도구를 언제 · 벤더 선택 · 에스컬레이션 호출 |
| `combined` · 에스컬레이션 판정 | `schema.py` 파생 속성 | 게이트웨이 도구 `compute_confidence` (같은 공식) |
| 절차 위반 | 정의상 0 | 심판 `referee.py` 가 **기록** (`procedure_adherence`) |
| LLM 연결 | `claude -p` 텍스트 1회 | `claude -p --mcp-config` 게이트웨이(HTTP) |
| 서버 · Guard · 장부 · 채점기 | 같다 | 같다 |

```bash
.venv/Scripts/python run.py --driver orchestrator --scenario mixed --seed 0 --fresh
.venv/Scripts/python tools/check_orchestrator.py     # LLM 없이 게이트웨이·심판 검사
```

산출물은 `runs/<run_id>/orchestrator/` — `calls.jsonl`(호출 하나하나) · `referee.jsonl`(스텝별 판정) ·
`steps.jsonl`(LLM 요약 · 비용) · `summary.json` · `servers.json`(CLI 가 읽은 MCP 설정).
설계 근거는 `claude/flow/loop.md` §3.3b.

---

## 구조 — 주입점 2개 (fixed 드라이버)

```
run.py                                  시나리오 · 시드 · arm
   │
   ├─ Tools(backend, guard)             도구 21개 창구
   │     ├─ MockBackend                 ← 현재 (인프로세스 가짜)
   │     └─ McpBackend                  ← 미구현 (실제 서버)
   │            ↑ 주입점 ①: 전송
   │
   └─ run_episode(tools, decide, ...)
         └─ run_step()                  9스텝 골격 — 고정
               └─ decide(ctx, proposer)
                     ├─ rule_decider    ← 현재 (LLM 없음)
                     └─ llm_decider     ← 미구현 (본체)
                            ↑ 주입점 ②: 판단
```

`loop.py`에 `if arm == ...` 도 `if backend == ...` 도 **없다.** 백엔드를 갈면 목 ↔ 실제 서버가, 판단자를 갈면 비교군이 바뀐다. 루프 코드는 그대로다.

### 파일

| 파일 | 역할 |
|---|---|
| `schema.py` | `Decision` · `StepContext` · `Proposer`. 에이전트가 만드는 값의 정의 |
| `guard.py` | FORBIDDEN 누출 검사. **유효성 검사가 아니다** |
| `tools.py` | 도구 21개 얇은 래퍼. 반환값마다 guard 통과 |
| `loop.py` | 9스텝 순서·시점 보장 |
| `backends/mock.py` | 5서버 인프로세스 가짜 (임시) |
| `deciders/rule.py` | 임계값 규칙 판단자 (임시) |

---

## 한 스텝

```
run_step(tools, decide, run_id)

 1  ①.get_observation                                → obs
 2  ②.classify_demand  ⑤.get_reliability_table  ①.get_history
                                                     → StepContext
 3  decide(ctx, proposer)              ← 판단
       └ proposer.propose(policy, situation) → ②     → Decision
 4  [procure & pressure ≥ 1.0]
       ③.score_offerings → ③.procure → ①.add_capacity
 5  escalate ? ④.record_escalation : ④.record_decision  → decision_id
 6  ①.apply_allocation
 7  ①.step                                           → obs₊₁
 8  ⑤.report_outcome(decision_id, obs₊₁)
 9  [vendor_id] ③.update_rating
```

스텝당 도구 **9회**. 조달이 걸리면 12회, 벤더 평판까지 13회.

**중계 3곳이 모두 루프를 통과한다** — `recent_error`(⑤→②) · `capacity_gain`(③→①) · `vendor_id`(⑤→③). 서버가 서로를 직접 호출하는 코드는 없다.

### 에스컬레이션도 온전한 스텝이다

기록만 하고 끝나지 않는다. `record_escalation`이 `decision_id`와 `fallback_allocation`을 주므로, 사람을 기다리지 않고 폴백으로 진행한 뒤 그 결정도 채점한다.

---

## 명세 위반을 구조로 막은 3곳

**① `situation` 없이 ②를 부를 수 없다**
판단자는 `tools`에 접근하지 못한다. `BoundProposer`만 받고, 그 메서드가 `situation`을 필수로 요구한다.

**② `combined` 공식이 어긋날 수 없다**
저장 필드가 아니라 파생 속성이다. 다른 값을 대입하는 것이 불가능하다.

**③ baseline 물리 분리가 공짜다**
루프에 arm 분기가 없으므로, `arms/baseline.py`가 `truth.jsonl`을 읽어도 그 import가 다른 파일에 등장하지 않는다. `claude/flow/forbidden.md:17`의 요구가 구조로 충족된다.

---

## 실행

표준 라이브러리만 쓴다. 목 백엔드이므로 venv·의존성이 필요 없다.

```bash
py -3.10 run.py --scenario emergency --steps 20
py -3.10 run.py --scenario mixed --seed 1
```

| 옵션 | 값 |
|---|---|
| `--scenario` | `normal` `emergency` `special_event` `iot_surge` `mixed` |
| `--backend` | `mock`(현재) · `mcp`(미구현) |
| `--decider` | `rule`(현재) · `llm`(미구현) |

---

## ⚠️ `backends/mock.py`는 가짜다

**A·B의 서버 5개를 전부 대체한 임시물이다.** 시뮬레이션 충실도는 목표가 아니고, 응답 형태가 명세와 맞는지·호출 순서가 성립하는지만 검증한다.

| 도구 | 목의 구현 | 실제로 필요한 것 |
|---|---|---|
| ①`get_observation` | sin 함수 트래픽 | `ml_orchestrator_demo.py:286` 해체 |
| ①`truth.jsonl` | **안 씀** | 정답 기록 (채점의 전제) |
| ②`propose_allocation` lstm | `normalize(traffic/θ)` — **LSTM 아님** | 실제 모델 적재 |
| ②`classify_demand` | 이용률 비율 나눗셈 | `TrafficClassifier` 신경망 |
| ③`score_offerings` | `60 + rating×6 + bw/100` — **임의 식** | `engine.py:719~790` |
| ④`get_metrics` | `mttr`·`mean_utilization` 전부 0 | 실제 집계 |

**따라서 목으로 나온 숫자는 논문에 쓸 수 없다.** 다만 21개 도구의 시그니처와 반환 형태가 명세대로 박혀 있으므로, **A·B가 이걸 계약서로 쓸 수 있다.** 실제 서버가 나오면 `backends/mcp.py`만 추가하면 되고 나머지는 바뀌지 않는다.

---

## 남은 작업

| | 상태 |
|---|---|
| `escalate`를 파생 속성 → **필드로 수정** | **선행 조건.** 현재는 arm1·arm2(에스컬레이션 없음)를 만들 수 없다 |
| `deciders/llm.py` + **LLM 출력 유효성 검증** | 본체. LLM 제공자 미정 |
| `arms/` 4종 | baseline · arm1 · arm2 · proposed |
| `prompts/system.md` | 배경 지식 범위가 자율성 주장의 경계선 |
| `backends/mcp.py` | A·B 서버 대기 |

### 유효성 검사가 없다

`guard.py`는 정답 누출만 본다. 타입·범위·필수 필드를 검사하지 않는다.

| 대상 | 검증 주체 |
|---|---|
| 서버 **입력** | FastMCP/pydantic (`claude/flow/errors.md:15`) |
| 서버 **출력** | 없음 — 계약을 신뢰 |
| **LLM 출력** | **없음** ← `llm.py` 만들 때 필수 |

LLM은 `"situation": "위급"`, `"policy": "rule-based"`(하이픈), `mmtc` 누락, `confidence: 1.3` 같은 걸 태연히 뱉는다. 검증 실패를 재시도할지 에스컬레이션으로 셀지는 **연구상 결정**이다.

---

## 발견한 함정 — 자기 행동이 관측을 오염시킨다

`emergency` 시나리오 20스텝에서 상황 판단이 `emergency` 3회 / `normal` 15회로 나왔다. 버그가 아니다.

```
비상 발생 → urllc 트래픽 ×2 → 이용률 1.7 → "emergency" 판정
                                  ↓
                        배분을 urllc 0.7로 올림
                                  ↓
                        이용률 0.97로 정상화 → "normal" 판정   ← 여기
                                  ↓
                        (트래픽은 여전히 ×2)
```

**대응이 성공한 순간 증상이 사라져 상황을 놓친다.** 그런데 정답은 계속 비상이라 인지 정확도가 떨어진다.

`utilization`은 자기 행동에 오염된 신호다. `traffic`은 배분과 무관하게 유지되므로 오염되지 않는다. **프롬프트를 짤 때 이용률만 보게 하면 이 함정에 빠진다.**

---

## 명세 불일치 2건 — 팀 확인 필요

| 항목 | 불일치 | 현재 구현 |
|---|---|---|
| 조달 순서 | `spec/tools.md:41`은 `record_decision → 조달`. 그런데 `spec/audit.md:20`은 `slice_id`·`vendor_id`를 `record_decision`에 기록하라고 한다 | **조달을 앞으로** 옮김. `loop.py`에 주석 |
| 파라미터명 | `spec/tools.md`는 `qos`, `spec/market.md`는 `qos_requirements` | 상세 계약인 `market.md` 채택 |
