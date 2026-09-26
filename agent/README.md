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

orchestrator 는 **기본으로 콘솔에 호출 추적을 쏟는다** — `[MCP→LLM] ② propose_allocation({…}) → {…}`
처럼 경로 · 서버 · 함수(인자) · 반환이 한 호출당 두 줄이다. `[host    ]` 는 호스트 직통(reset · get_metrics).
서버가 예외를 내면 `✗ 예외 — <메시지>`, 상한에 걸리면 `✗ 상한 초과`. 끄려면 `--quiet`.

**결과는 `runs/<run_id>/report.html` 을 브라우저로 열어 본다.** 실행이 끝나면 자동 생성되고
(`--backend mcp` 고정 루프도 같다), 다시 만들려면 `python -m eval.report <run_id>`. KPI 타일 ·
스텝 타임라인(정답/판단/일치/SLA/개입/조달) · 신뢰도 추이 · 도구 호출 · 혼동 행렬 · 스텝 상세 표.
정답 파일을 읽으므로 에이전트 컨텍스트 밖(`eval/`)에 있다.

산출물은 `runs/<run_id>/orchestrator/` — `calls.jsonl`(호출 하나하나) · `referee.jsonl`(스텝별 판정) ·
`steps.jsonl`(LLM 요약 · 비용) · `summary.json` · `servers.json`(CLI 가 읽은 MCP 설정).
설계 근거는 `claude/flow/loop.md` §3.3b.

---

## 구조 — 주입점 2개 (fixed 드라이버)

```
run.py                                  시나리오 · 시드 · arm
   │
   ├─ Tools(backend, guard)             도구 21개 창구
   │     ├─ MockBackend                 인프로세스 가짜 (계약 확인용)
   │     └─ McpBackend                  실제 서버 5개 stdio
   │            ↑ 주입점 ①: 전송
   │
   └─ run_episode(tools, decide, ..., config)
         └─ run_step()                  9스텝 골격 — 고정
               └─ decide(ctx, proposer)
                     ├─ rule_decider    LLM 없음
                     ├─ LlmDecider      Claude CLI (agent/llm/)
                     │      ↑ 주입점 ②: 판단 · ③: LLM
                     └─ arms.make()     비교군 — 판단자를 감싼다
                            baseline · arm1 · arm2 · proposed
```

`loop.py`에 `if arm == ...` 도 `if backend == ...` 도 **없다.** 백엔드를 갈면 목 ↔ 실제 서버가, 판단자를 감싸는 방식이 바뀌면 비교군이 바뀐다. 루프 코드는 그대로다.

두 번째 드라이버 `--driver orchestrator`(`agent/orchestrator/`)는 LLM 이 도구를 직접 든다. 위 구조의 대조군이다.

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
| `--backend` | `mock` · `mcp` |
| `--decider` | `rule` · `llm` |
| `--driver` | `fixed` · `orchestrator` |
| `--arm` | `baseline` · `arm1` · `arm2` · `proposed` (첫 `_` 앞 토큰으로 판정. 그 외 라벨은 proposed) |

실행은 `.venv310\Scripts\python.exe` 로 한다. 웹 UI는 `web\serve.py`, 본실험 배치는 `tools\run_matrix.py`.

**새로 받은 폴더에서 검사부터 돌릴 때** — `data/vendors.json` 은 git 에 없다(C-6). `run.py` 는 없으면
만들지만 `tools/check_market.py` 는 멈춘다. `tools/bootstrap_vendors.py` 를 먼저 돌린다.

**B-2(2026-09-25) 이전에 warm 으로 돌린 적이 있으면** `data/reliability.json` 을 `data/reliability.pre-B2.json`
으로 옮긴다(`.gitignore` 가 막는다). 그 파일에는 개입 스텝 성적이 정책에 잘못 붙어 있어, 이어 쓰면 처음부터
개입으로 흐른다. 옮기면 ⑤가 다음 실행에서 초기값으로 새로 만든다. `run.py` 기본이 `--memory-mode warm`
이므로, 실험은 `--fresh --memory-mode cold` 로 격리한다(웹 UI 기본은 cold).

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

**계약이 바뀌는 식은 서버 모듈을 그대로 부른다** (2026-09-26) — ② rule_based(위반 보정 B-1 포함) ·
⑤ 신뢰도(개입 귀속 분리 B-2 · 사전값 B-3) · ④ confidence 검사(A-2) · ④ 폴백 상수. 전부 표준 라이브러리만
쓰는 순수 함수라 서버를 띄우지 않는다. 베껴 두었을 때는 B-1~B-3 이 들어온 뒤 목만 옛 계약으로 남았다.
시뮬레이션(용량 1.0 · sin 트래픽)은 여전히 가짜다 — **목은 배선 검증용이고 수치 비교에 쓰지 않는다.**

---

## 남은 작업

**정본은 `claude/team/workplan-2.md`** 다(1차는 `workplan.md`). 여기는 에이전트 쪽 현황만 적는다 (2026-09-26).

| | 상태 |
|---|---|
| `escalate` 필드화 | 완료 — `Decision.escalation` |
| `deciders/llm.py` · LLM 출력 검증 | 완료 — 형식 위반은 1회 재질의 후 중단 |
| `arms/` 4종 | 완료 — baseline 만 truth.jsonl 을 연다 |
| `backends/mcp.py` | 완료 |
| 실행 조건을 장부에 | 완료 — `config` (scenario·seed·arm·intent …) |
| 개입 공식(C-7) · 선제 조달(C-8) | **팀 결정 D2 · D5 · D3 대기** |
| `chosen_policy` 중계 | 완료 (C-11) — 고정 루프는 `loop.py` 가, 오케스트레이터는 프롬프트로 LLM 이 넘긴다 |
| `recent_error` 중계 | 고정 루프는 `StepContext` 가 · 오케스트레이터는 프롬프트로 (C-12) |
| 목을 실서버 계약에 | 완료 (C-14) — B-1 · B-2 · B-3 · A-1 · A-2 |
| 보정 위치 · 개입 복귀 경로 | **팀 결정 D1-b · D5 대기** — 결정되면 C-16 · C-17 |

### 유효성 검사가 없다

`guard.py`는 정답 누출만 본다. 타입·범위·필수 필드를 검사하지 않는다.

| 대상 | 검증 주체 |
|---|---|
| 서버 **입력** | FastMCP/pydantic (`claude/flow/errors.md:15`) |
| 서버 **출력** | 없음 — 계약을 신뢰 |
| **LLM 출력** | `deciders/llm.py` `_validate` — situation·policy 범위, confidence 0~1, procure bool |

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
