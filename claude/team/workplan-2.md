# 작업 계획 2 — 1차 수정 이후

작성 2026-09-26 · C(에이전트) · 대상 A·B·C 전원과 이 저장소에서 일하는 AI

## 0. 이 문서를 읽는 AI 에게

**목적.** `workplan.md`(1차)의 B-1~B-4 · A-1 · A-2 가 들어왔다. 그 결과를 검증했고, 남은 막힘과
새로 드러난 막힘을 **담당별로** 다시 엮었다. 앞으로의 순서는 이 문서가 정본이다. 1차 문서의
진단(§1)과 M-0 기준값(§4b)은 그대로 유효하다.

**전제.**
- 담당: **A**=choi(①④) · **B**=kim(②③⑤) · **C**=lee(에이전트 · 오케스트레이터). 측정 도구의 소유는 §3.5 R-2 에서 정한다.
- **자기 담당이 아닌 파일은 고치지 않는다.** 남의 파일에 필요한 변경은 그 담당의 작업으로 적었다.
- 실행은 `.venv310\Scripts\python.exe` 로만 한다.
- **서버에 새 인자를 추가하는 작업은 서버가 먼저, 에이전트가 나중이다.** FastMCP 는 모르는 인자를
  거부한다(`unexpected_keyword_argument`). 반환 필드 추가는 순서와 무관하다.
- 규칙 판단자 실행은 결정적이다 — 같은 시드면 다른 PC 에서도 숫자가 같다(§1.2 에서 확인).

**하지 말 것.**
- 결정(§2) 전에 LLM · 오케스트레이터 칸 본실험을 돌리지 않는다. 사용량이 크고 전부 다시 돌리게 된다.
  규칙 판단자 칸은 무료라 언제 돌려도 된다.
- 결과가 좋아질 때까지 상수(τ · 평활 · 임계 · 보정 크기)를 돌리지 않는다. 민감도로 보고한다.
- 사용량 환산 금액은 구독 한도에서 차감되는 양이다. API 키 · 과금 로그인은 쓰지 않는다.

---

## 1. 지금 상태 (2026-09-26 확인)

### 1.1 브랜치

| 브랜치 | 끝 | 내용 |
|---|---|---|
| `main` | `2cbab17` | C 1차 · 오케스트레이터 수정 |
| `feature/lee` | kim 끝 + C 정리 | kim · choi 병합(fast-forward, 2026-09-26) + C-11~C-15 · **main 미반영 (R-3)** |
| `feature/choi` | `db9d62f` | A-1 · A-2 |
| `feature/kim` | `43de622` | B-1~B-4 + choi 병합 |

### 1.2 검증 (kim 브랜치를 임시 worktree 에서)

- **검사 6종 264 PASS · 0 FAIL** — observe 63 · policy 37 · market 33 · feedback 34 · audit 59 · orchestrator 38.
  `check_market` 은 `data/vendors.json` 이 있어야 돈다. 새로 받은 폴더에서는 `tools/bootstrap_vendors.py` 가 먼저다.
- **kim 실측 재현 — 숫자 일치.** emergency s0 30스텝 · 규칙 판단자 · 산출물은 C 로컬 `runs/b12{on,off}-emergency-s0/`

  | | 개입 | SLA 위반 | `rule_based.n` | `fallback.n` |
  |---|---|---|---|---|
  | 보정 on | 18 | 19 | 12 | 18 |
  | 보정 off | 18 | 20 | 12 | 18 |

- **B-3** — n=0 에서 `recent_error` 가 rule 0.1 · lstm 0.2 · dqn 0.6 (`get_reliability_table` 실측).

### 1.3 1차 항목 판정

| 항목 | 판정 | 남은 것 |
|---|---|---|
| B-1 위반 보정 | 1차 §5 충족 (19 < 21, 자율 스텝 배분 8종) · **효과 1스텝** | 평활 뒤 30% 만 남는다 → **D1-b** |
| B-2 개입 귀속 | 충족 (n = 30 − 18) | 개입에서 빠져나오지 못한다 → **D5** |
| B-3 lstm 사전값 | 서버 쪽 충족 | 규칙 판단자는 설계상 lstm 을 안 고른다 · 오케스트레이터는 값을 안 넘긴다 → C-12 · C-13 |
| B-4 독스트링 | 충족 | |
| A-1 `agent_policy` | 서버 쪽 충족 | 에이전트가 안 넘긴다 → C-11 |
| A-2 confidence 타입 | 실측 사례(`"iot_surge"`) 거부 | 숫자 문자열 · NaN 통과 → A-2b |
| A-3 `features` 블록 | **미착수** | |
| C-9 오케스트레이터 반복 | 미착수 | |

---

## 2. 결정 — 한 번의 회의에서

§4 의 M-1 · M-0b(무료, 약 80분)를 먼저 돌리면 아래 다섯 개를 숫자를 들고 한자리에서 정할 수 있다.

### D1-b. 위반 보정을 어디에 거는가 (B-1 후속 · kim 제기)

| | |
|---|---|
| 무엇 | 원본 `update_allocation_rule_based`(`ml_orchestrator_demo.py:422~465`)는 목표(:429~440) → **평활**(:443~444) → **보정**(:446~458) → 클립 · 정규화(:461~462). 지금은 ②가 목표표에 보정을 걸고, ①이 그 **뒤에** 평활 0.7 을 건다 → 적용값에는 보정의 30% 만 남는다(최대 0.1 → 0.03) |
| 실측 | emergency 30스텝 SLA 위반 19 vs 20 — 1스텝 차이 |
| 선택지 | (i) 현행 유지 (ii) ①이 평활 뒤에 보정 — 원본 순서지만 ①은 정책을 몰라 lstm 제안에도 걸린다. 원본은 규칙 함수에만 있다(`update_allocation_ml`:341 에는 평활만) (iii) ②가 목표와 **보정량**(`correction`)을 따로 내고, ①이 평활 뒤에 그 보정량을 더한다 — rule_based 에만, 원본 수식 그대로 |
| **권고** | **(iii).** 원본 기준을 그대로 재현하고, "정책은 ② · 평활 · 클립은 ①" 경계도 지킨다. 상수를 바꾸지 않는다 |
| 여는 작업 | B-5 · A-5 → C-16 |

### D2. 개입 판정 공식 (1차 그대로 · D5 와 같이)

선택지와 판정 기준(AUC 0.7 / 0.6)은 1차 §2 D2 그대로다. **새 사실:** B-2 이후 empirical 이 동결돼
공식이 개입을 빠져나오지 못한다(D5). 공식을 선행 신호로 바꾸면 D5 가 같이 풀릴 수도 있으므로 **D5 와
한 번에 정한다.** 여는 작업 C-7.

### D3. 조달 시점 (1차 그대로)

권고 (b) — 고정 루프는 1.0 반응형, 오케스트레이터만 추세로 선제 허용. B-1 효과가 작아서, M-0b 에서
"조달과 무관한 위반" 비율을 다시 보고 켠다. 여는 작업 C-8.

### D4. 개입하면 무엇이 적용되는가 (1차 그대로)

권고 (c1) 현재 관측 전문가 `a*(obs_t)`. 여는 작업 A-4. 참고: 폴백 배분도 ①의 평활을 거친다. 액추에이터
제약이라 맞지만, 사람의 배분도 스텝당 30% 씩만 반영된다는 것을 해석에 적는다.

### D5. 개입에서 빠져나오지 못한다 (신규)

| | |
|---|---|
| 무엇 | B-2 이후 개입 스텝은 정책 성적을 안 쌓는다 → **empirical 동결.** emergency s0: 13번째 스텝부터 끝까지 연속 개입, empirical 0.318 고정 |
| 수치 | 빠져나오려면 intrinsic ≥ 0.45² / 0.318 = **0.637** (= 여유 0.46 이상). 개입 구간 실측 intrinsic 최대 0.55 |
| B-2 전후 | 전 `...........EEEEEEEEEEEEEEEEEEE` 19회 (성적이 **깎여서**) · 후 `...........E.EEEEEEEEEEEEEEEEE` 18회 (성적이 **얼어서**). **귀속은 고쳐졌고 결과는 같다** |
| 원인 | 1차 B-2 설계(C 작성)가 "개입 스텝은 갱신 제외"만 적고 **복귀 경로를 안 적었다** |
| 왜 중요 | D4 를 (c1)로 바꾸면 개입이 SLA 를 지켜 주지만, 한번 들어가면 안 나오므로 개입률이 높게 고정된다 → *"개입은 줄었다"* 를 쓸 수 없다 |
| 선택지 | (a) **가상 채점** — 개입 스텝에서도 에이전트가 고른 정책의 제안을 ⑤가 다음 관측으로 채점해 그 정책 성적에 반영. 트래픽은 배분과 무관하게 생성되고(`env.py _roll`) 이용률은 `traffic / (allocation × capacity)` 라, "그 배분이었다면"의 SLA 를 정확히 계산할 수 있다 (b) 개입 중 r 을 사전값 쪽으로 조금씩 되돌림 — 되돌림 속도라는 새 상수 (c) k스텝마다 한 번 자율 시도 — 개입 규칙의 예외, 심판의 `ignored_escalation` 과 충돌 (d) D2 에서 공식을 선행 신호로 바꿔, 관측이 가라앉으면 나오게 |
| **권고** | **(a).** 새 상수가 없고, B-2 의 원칙(적용된 것의 성적은 적용된 것에)을 지키면서 정책은 계속 평가된다. 운영에서 말하는 섀도 모드다 |
| 여는 작업 | A-6 · B-6 → C-17 |

---

## 3. 담당별 작업

형식: **ID · 파일** — 의존 → 변경 → 검증

### 3.1 A · choi (①④)

**A-2b · `srm_mcp/audit/book.py` `bad_confidence` · 저장** — 의존 없음
→ `_is_floatable` 이 `"0.52"` 같은 숫자 문자열과 NaN 을 통과시키고, 장부에는 받은 값 그대로(문자열)
  저장한다(`book.py:174 · 250 · 261`). 저장 전에 float 로 바꾸거나 int · float 만 받는다. NaN · inf 는 거부.
→ 검증: `confidence.situation="0.5"` 로 기록 → 장부 값이 `0.5`(float), 또는 `malformed_confidence`.

**A-3 · `srm_mcp/observe/` `features` 블록** — 의존 없음 · 1차 문서 그대로

**A-4 · `book.py:242` 폴백 배분** — 의존 **D4**
→ (c1)이면 `fallback = dict(INIT_ALLOCATION)` 을 `a*(obs_t)` 로. `a*` 는 ⑤ `feedback/scoring.py`
  `ideal_allocation` 과 같은 식이다 — 같은 식을 두 곳에 두지 않도록 어디서 가져올지 A · B 가 정한다.
→ 검증: 개입 레코드의 `fallback_allocation` 이 스텝마다 다르고 ⑤ `ideal(obs_t)` 와 같다.

**A-5 · `srm_mcp/observe/env.py:231` `apply_allocation(correction=)`** — 의존 **D1-b (iii)**
→ 선택 인자 `correction: dict | None` 을 평활(`:247`) 뒤 · 클립(`:250`) 앞에 더한다. 없으면 지금과 같다.
→ 검증: 원본 `update_allocation_rule_based` 와 같은 입력에 같은 출력(소수 6자리) — 단위 검사 1개.

**A-6 · `book.py` `record_escalation(agent_allocation=)`** — 의존 **D5 (a)**
→ A-1 의 `chosen_policy` 와 같은 방식으로 에이전트가 적용하려던 배분을 받아 남긴다.
→ 검증: 개입 레코드에 `agent_allocation`. 안 주면 `null` 이고 다른 동작은 그대로.

### 3.2 B · kim (②③⑤)

**B-3b · `tools/check_feedback.py:187`** — 의존 없음
→ `handover-B.md` 3번 항목. 그 문서에는 C 파일로 적혀 있으나 **kim 이 작성한 파일**이다.
  `recent_error([], "lstm_forecast") == 0.2` 를 확인하는 항목으로 바꾼다.

**B-5 · `srm_mcp/policy/rule.py` 보정량 분리** — 의존 **D1-b (iii)**
→ `propose` 가 목표(보정 없음)와 `correction`(합 0 인 dict)을 따로 낸다. `PolicyProposal` 에 필드 추가 —
  반환 필드라 에이전트는 안 깨진다. `SLICE_RULE_CORRECTION=off` 면 correction 은 0.
→ 검증: `check_policy` 1b 를 "목표 + correction = 지금의 on 값" 으로.

**B-6 · `srm_mcp/feedback/server.py` `report_outcome` 가상 채점** — 의존 **D5 (a)** · A-6
→ 개입 레코드에 `agent_allocation` 이 있으면: ①과 같은 평활 · 클립으로 "그 배분이 적용됐을 값"을 만들고,
  obs_{t+1} 의 `traffic` · `capacity` 로 이용률 · SLA · error 를 계산해 **`agent_policy`** 의 r · n · errors 를
  갱신한다. 실제 적용된 폴백의 성적은 지금처럼 `fallback` 에. 반환과 장부에 `shadow: true`.
  평활 · 클립 식을 ①에서 가져올지 복사할지는 A · B 가 정한다.
→ 검증: emergency s0 30스텝 — 개입 스텝에서도 `agent_policy` 의 n 이 늘고 empirical 이 고정되지 않는다.

**(선택) `tools/check_market.py`** — `data/vendors.json` 이 없으면 멈추는 대신 부트스트랩. kim 판단.

### 3.3 C · lee (에이전트)

**C-10 · 통합** — 의존 **R-3** · **lee 까지 완료 2026-09-26**
→ kim(`43de622`, choi 포함) → lee fast-forward → 검사 6종 → main 은 R-3 에서 정한 방식으로.
→ 결과: lee 병합 완료(병합 커밋 없음). main 은 R-3 합의 뒤.

**C-11 · `chosen_policy` 중계 (A-1 연결)** — 의존 C-10 · **완료 2026-09-26 (오케스트레이터는 실행 검증 전)**
→ 결과: 고정 루프 실서버 emergency s0 30스텝 — 개입 레코드 18건 전부 `agent_policy = rule_based`,
  배분 · SLA · 개입은 수정 전(`b12on`)과 30스텝 모두 같다. 오케스트레이터는 프롬프트 한 줄까지.
→ `agent/tools.py:207 record_escalation` 에 인자 추가 · `agent/loop.py:125` 개입 경로에서 판단자가 고른
  정책을 넘김 · `agent/backends/mock.py` 같은 인자. 오케스트레이터 프롬프트에 "사람을 부를 때도 고르려던
  정책을 `chosen_policy` 로 넘긴다" 한 줄(④ 도구 설명에는 이미 있다).
→ 검증: 1차 §5 A-1 판정 — 개입 레코드의 `agent_policy` 집계와 루프 요약의 정책 사용이 같다.

**C-12 · `recent_error` 중계 (오케스트레이터)** — 의존 C-10 · **프롬프트 반영 2026-09-26 (실행 검증 전)**
→ 오케스트레이터 3회 실행에서 LLM 이 lstm 제안에 `recent_error` 를 넘긴 적이 **0/10** 이다(rule_based 는
  18/33). `propose_allocation` 도구 설명에도 프롬프트에도 없다. 안 넘기면 lstm 은 0.2231 → 곧바로 개입이라
  B-3 이 오케스트레이터에서는 효과가 없다. `agent/orchestrator/prompt.md` 값의 규칙에 "`propose_allocation`
  에는 `get_reliability_table` 의 그 정책 `recent_error` 를, `compare_policies` 에는 표 전체를 넘긴다" 한 줄.
→ 검증: 오케스트레이터 12스텝 — lstm 제안 전부에 `recent_error`, confidence 0.549 근처.

**C-13 · 독스트링 2곳 + B-3 판정 문구** — 의존 C-10 · **완료 2026-09-26**
→ `agent/schema.py:59` "⑤는 n=0 이면 null" → 사전값을 낸다. `agent/deciders/rule.py:77~87` 의 0.2231 근거를
  지운다. **필터 동작은 유지한다** — 규칙 판단자는 기준선으로 고정하고, 정책 선택의 효과는 LLM · 오케스트레이터
  칸에서 잰다(kim 권고 (a)). 그래서 1차 §5 B-3 판정("30스텝 후 lstm n > 0")은 이 문서 §5 로 바꾼다.

**C-14 · `agent/backends/mock.py` 를 실서버 계약에 맞춤** — 의존 C-10 · **완료 2026-09-26**
→ 셋이 어긋난다: `_report_outcome`(:407~416)이 개입 레코드도 정책에 귀속(B-2 미반영) · rule_based 제안에
  보정 없음(B-1) · n=0 사전값 lstm 0.15 · dqn 0.4(:66~68, 실서버 0.2 · 0.6). 셋 다 맞춘다.
  목은 배선 검증용이고 수치 비교에는 쓰지 않는다는 문장을 README 에 넣는다.
→ 결과: 식을 베끼지 않고 서버의 순수 함수를 그대로 부른다 — ② `rule` · ⑤ `reliability` · ④ `bad_confidence` ·
  `INIT_ALLOCATION`(전부 표준 라이브러리). 그래서 A-1 · A-2 도 같이 맞춰졌고, 폴백도 ④처럼 상수가 됐다
  (전에는 rule_based 제안이라 B-1 뒤 보정이 섞일 뻔했다). 검사 `tools/check_mock.py` 12항목 — 서버를 안 띄운다.

**C-15 · `agent/README.md`** — 의존 없음 · **완료 2026-09-26**
→ 새로 받은 뒤 검사 전에 `tools/bootstrap_vendors.py`(C-6 의 부작용) · B-2 이후 warm 파일 초기화(Z-1).

**C-16 · `correction` 중계** — 의존 **B-5 · A-5** (서버 둘이 먼저)
→ 고정 루프: ②의 `correction` 을 ① `apply_allocation` 에. 오케스트레이터: 프롬프트 한 줄.
→ 검증: 같은 관측에서 적용값이 원본 `update_allocation_rule_based` 출력과 같다.

**C-17 · 개입 시 제안 중계** — 의존 **A-6 · B-6**
→ 고정 루프: 개입 경로에서 판단자의 제안 배분을 `agent_allocation` 으로. 오케스트레이터: 프롬프트 한 줄.

**C-7 · C-8 · C-9** — 1차 그대로. C-7 은 D2 · D5 뒤, C-8 은 D3 뒤.

### 3.4 모두

**Z-1 · 로컬 `data/reliability.json` 초기화** — 의존 C-10 · **C 로컬 완료 2026-09-26** · A · B 는 각자
→ B-2 이전 방식으로 쌓인 성적이 남아 있다(C 로컬: rule_based r 0.45 · n 36). `run.py` 기본이 `warm` 이라
  그대로 이어 쓴다(웹 UI 기본은 `cold`). `data/reliability.pre-B2.json` 으로 옮기면 ⑤가 다음 실행에서
  초기값으로 새로 만든다(`_load_table`). 옮긴 파일은 `.gitignore` 가 막는다.

### 3.5 역할 정리 — `roles.md` 와 실제가 다른 곳

| ID | 무엇 | 정할 것 |
|---|---|---|
| R-1 | `roles.md` §1.4 브랜치 표가 `feature/kim ← A` · `feature/lee ← B` · `feature/choi ← C` 로 적혀 있다. 실제는 kim=B · choi=A · lee=C | 작성자(kim)가 정정 |
| R-2 | `roles.md` §1.3 · A-6 은 `eval/` 과 실험 하네스를 A 소유로 적었다. 실제로 `tools/run_matrix.py` · `eval/breakdown.py` · `eval/report.py` 는 C 가, `eval/score.py` 는 A 가 썼다 | (a) `roles.md` 를 실제대로 (b) A 로 이관. **권고 (a)** — 셋 다 오케스트레이터 산출물(`referee.jsonl` · `steps.jsonl`)과 `run.py` 에 묶여 있다. 측정 실행은 C, 채점 기준(`score.py`)은 A 가 검토 |
| R-3 | `roles.md` §1.4 는 "main 은 PR, 직접 커밋 금지". 지금까지는 C 가 lee → main 을 직접 올렸다 | 누가 · 어떻게 합칠지. 권고: 각자 브랜치 → main PR, 리뷰어 1인 |
| R-4 | kim 이 C 파일 `agent/deciders/llm.py` 한 문단을 고쳤다(B-3 으로 거짓이 된 문장 — 내용은 맞다, 유지) | "한 파일은 한 사람" 재확인. 남의 파일은 인수인계 문서로 넘긴다 |

---

## 4. 순서와 측정

```
┌ 0. 정리 — 결정 무관 · 병렬 · 반나절 ─────────────────────────────┐
│  A  A-2b  A-3                                                     │
│  B  B-3b                                                          │
│  C  C-10 통합 → C-11 · C-12 · C-13 · C-14 · C-15                  │
│  모두  Z-1 · R-1~R-4 합의                                          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌ 1. 무료 측정 — 규칙 판단자 · 약 80분 ───────────────────────────┐
│  M-1   normal · emergency 30스텝 → AUC · 개입 연속 길이          │
│  M-0b  after-B1 60칸 → before-B1 과 쌍 비교                       │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌ 2. 팀 회의 — D1-b · D2 · D3 · D4 · D5 ──────────────────────────┐
└──────────────────────────────────────────────────────────────────┘
                              ↓
   3. 구현 — 서버 먼저, 에이전트 나중
      A-4 (D4)   A-5 · B-5 → C-16 (D1-b)   A-6 → B-6 → C-17 (D5)
      C-7 (D2)   C-8 (D3)   C-9
                              ↓
   4. M-0c  규칙 60칸 재측정 — 사다리 세 칸이 각각 움직이는가
                              ↓
   5. M-2   본실험 — LLM · 오케스트레이터 칸 시드당 반복 (C-9). --go 없이 추정부터
```

| 측정 | 명령 | 시간 · 사용량 | 무엇을 보나 |
|---|---|---|---|
| **M-1** | `run.py --backend mcp --decider rule --arm m1 --scenario {normal,emergency} --seed 0 --steps 30 --fresh --memory-mode cold` | 2분 · 무료 | `combined` · `intrinsic` · `worst u/θ` 의 AUC(1차 §6 식) + 최장 연속 개입 · 개입 탈출 횟수 |
| **M-0b** | `tools\run_matrix.py --name after-B1 --variants baseline,arm1_rule,arm2_rule,proposed_rule --go` | 약 75분 · 무료 | before-B1 과 같은 칸끼리 쌍 비교. B-1 은 전 비교군, B-2 는 proposed 에만 영향 |
| **M-0c** | 같은 명령 `--name after-D` | 약 75분 · 무료 | 결정 구현 후 사다리 세 칸의 차이 |
| **M-2** | `run_matrix` 전체 + 반복(C-9) | 사용량 환산 수백 달러 — `--go` 없이 추정 먼저 | 논문 표 |

M-1 · M-0b 는 R-2 가 정해지기 전까지 C 가 돌린다.

---

## 5. 완료 판정

| ID | 판정 |
|---|---|
| A-2b | 숫자 문자열 confidence 가 float 로 저장되거나 거부된다 · NaN 은 거부 |
| A-3 | 1차 §5 그대로 — 오케스트레이터 12스텝에서 `classify_demand` 첫 호출이 `available: true` |
| A-4 | 개입 레코드 `fallback_allocation` == ⑤ `ideal(obs_t)`, 스텝마다 다르다 |
| A-5 | 원본 `update_allocation_rule_based` 와 같은 입력 → 같은 출력 |
| A-6 | 개입 레코드에 `agent_allocation` |
| B-3 | **(1차 판정 대체)** n=0 에서 lstm `recent_error` 0.2 · 그 값을 넘긴 제안의 confidence > τ. "실제로 lstm 을 고르는가"는 판정이 아니라 M-2 의 측정 대상 |
| B-3b | `check_feedback` 에 `recent_error([], "lstm_forecast") == 0.2` |
| B-5 | 보정 on 이면 rule_based 제안의 `correction` 합이 0, off 면 전부 0 |
| B-6 | emergency s0 30스텝 — 개입 스텝에서도 `agent_policy` 의 n 증가 · 반환에 `shadow: true` |
| C-10 | lee 가 kim · choi 끝을 포함 · 검사 6종 통과 · main 반영은 R-3 뒤 |
| C-11 | 개입 레코드 `agent_policy` 가 null 이 아니고 루프 요약의 정책 사용과 같다 |
| C-12 | 오케스트레이터 12스텝 — lstm 제안 전부에 `recent_error` |
| C-14 | `tools/check_mock.py` 전부 통과 — 목으로 emergency 30스텝에서 개입 스텝이 정책 n 을 안 올리고, n=0 `recent_error` 가 실서버와 같다 |
| C-16 | 고정 루프 적용값이 같은 관측의 원본 함수 출력과 같다 |
| C-17 | 개입 레코드에 `agent_allocation` 이 있고 ⑤가 가상 채점한다 |
| Z-1 | 각자 `data/reliability.json` 이 B-2 이후 값으로 새로 시작했다 |
| M-1 | 두 시나리오의 AUC 3종과 최장 연속 개입이 기록됐다 — 값이 무엇이든 |
| M-0b | `runs/_matrix/after-B1/summary.csv` 60행 + before-B1 과의 쌍 비교표 |
| D1-b~D5 | 선택과 근거가 이 문서 §2 에 추가됐다 |

---

## 6. 참조

- 1차 계획 · 진단 · M-0 기준값: `claude/team/workplan.md`
- kim 완료 보고 · C 에게 넘긴 4건: `claude/team/handover-B.md` (kim 브랜치에만 있음 — C-10 뒤 로컬에 생긴다)
- 역할 · 파일 소유: `claude/team/roles.md`
- 원본 규칙 배분: `ml_orchestrator_demo.py:422~465` (읽기 전용)
- 재현 산출물: C 로컬 `runs/b12{on,off}-emergency-s0/` · `runs/orchcheck*-s0/`
- 오케스트레이터 흐름 검증(명세 §3.1 대조 12/12): `claude/flow/loop.md` §3.1 · §3.3b
