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
  → **2026-09-28 기준 281 PASS.** `check_market` 은 이제 `vendors.json` 이 없으면 스스로 만들고,
  실험으로 평판이 움직인 뒤에도 같은 값을 낸다 — 그 전에는 30스텝만 돌려도 9건이 FAIL 했다 (§3.2).
- **kim 실측 재현 — 숫자 일치.** emergency s0 30스텝 · 규칙 판단자 · 산출물은 C 로컬 `runs/b12{on,off}-emergency-s0/`

  | | 개입 | SLA 위반 | `rule_based.n` | `fallback.n` |
  |---|---|---|---|---|
  | 보정 on | 18 | 19 | 12 | 18 |
  | 보정 off | 18 | 20 | 12 | 18 |

- **B-3** — n=0 에서 `recent_error` 가 rule 0.1 · lstm 0.2 · dqn 0.6 (`get_reliability_table` 실측).
- **독립 재현 (2026-09-28 · kim 로컬 · 다른 PC)** — 위 표 네 칸 · §1.5 M-1 emergency "후" 열 ·
  D5 의 `empirical` 0.3183 과 탈출 문턱 0.6362 까지 소수점 일치. §0 의 결정성 전제가 확인됐다.

### 1.3 1차 항목 판정

| 항목 | 판정 | 남은 것 |
|---|---|---|
| B-1 위반 보정 | 1차 §5 충족 (19 < 21, 자율 스텝 배분 8종) · **효과 1스텝** | 평활 뒤 30% 만 남는다 → **D1-b** |
| B-2 개입 귀속 | 충족 (n = 30 − 18) | 개입에서 빠져나오지 못한다 → **D5** |
| B-3 lstm 사전값 | 서버 쪽 충족 · 오케스트레이터에서 **lstm 첫 선택**(C-12 뒤, §1.4) | 규칙 판단자는 설계상 lstm 을 안 고른다(C-13) · 안 써본 정책이 개입의 비상구가 된다 → **D6** |
| B-4 독스트링 | 충족 | |
| A-1 `agent_policy` | 서버 쪽 충족 | 에이전트가 안 넘긴다 → C-11 |
| A-2 confidence 타입 | 실측 사례(`"iot_surge"`) 거부 | 숫자 문자열 · NaN 통과 → A-2b |
| A-3 `features` 블록 | **충족 — 1차 판정이 오래됐다** | `env.py:205` 에 11열 전부 · `features.py:67` 이 그 경로를 탄다. `classify.load()` 후 `available: true` 실측 (2026-09-28). §5 판정은 오케스트레이터에서 한 번 확인만 하면 닫힌다 |
| C-9 오케스트레이터 반복 | 미착수 | |

### 1.4 오케스트레이터 재확인 — 서버 수정 + C-11~C-14 뒤 (special_event s0)

| | `orchcheck2` · 서버 수정 전 · 12스텝 | `orchcheck3` · 12스텝 | `orchcheck4` · 20스텝 |
|---|---|---|---|
| 개입 | 7 | 0 | 1 (19번째) |
| SLA 위반 | 11/12 | 9/12 | 16/20 (배분 탓 11 · 구조적 4 · 판정 불가 1) |
| 상황 판단 | special_event 9 · iot 2 · normal 1 | normal 8 · iot 2 · special_event 2 | normal 20 (정답 0/20) |
| lstm 선택 | 0 | 2 | 9 |
| lstm confidence (표본 0) | 0.2231 | 0.5488 | 0.5488 |
| recent_error 중계 | lstm 0/6 | lstm 6/6 · rule 11/11 · compare 2/2 | lstm 9/9 · rule 15/15 · compare 6/6 |
| chosen_policy 중계 | — (A-1 전) | 개입 없음 | 1/1 · 장부 `agent_policy` = 요약 정책 |
| 심판 | 위반 0 | 위반 0 | 실행 당시 `ignored_escalation` 2 — **심판 오탐**, C-19 로 고친 뒤 재판정하면 0 · `record_after_apply` 1 — 9번째, 실제 순서 위반. 절차 준수 0.85 → **0.95** |

- 세 실행은 첫 스텝부터 상황 판단 경로가 달라 통제된 비교가 아니다 — C-9 반복이 필요하다.
- `orchcheck4` 스텝 종류별 SLA 충족: 자율 rule_based 3/10 · **전환(D6) 1/6** · 자율 lstm 0/3 · 개입 0/1.
  **개입은 1/20 인데 SLA 위반은 16/20** — 개입이 준 것이 SLA 로 이어지지 않았다.
- 개입 판정을 실제로 무시한 스텝은 없다. 기록에 실린 정책의 판정과 맞추면 `ignored_escalation` 은 0 이다.

### 1.5 무료 측정 — M-1 · M-0b (2026-09-26 · 규칙 판단자 · 사용량 0)

**한 줄: B-1~B-3 으로 SLA 는 조금 좋아졌지만 사다리 세 칸은 여전히 막혀 있고, 개입은 오히려 늘었다.**
재현: `tools/compare_matrix.py before-B1 after-B1` · `tools/signal_auc.py m1-normal-s0 m1-emergency-s0`
(전 = `tools/signal_auc.py runs/_matrix/before-B1/raw/proposed_rule-{scenario}-s0 --max-step 30`).
두 매트릭스의 칸별 원본은 `runs/_matrix/{before-B1,after-B1}/raw/` 에 있다(C 로컬).

**M-0b — 60칸, 같은 칸끼리 (15칸 평균 ± 칸 간 표준편차)**

| 비교군 | SLA 위반율 전 → 후 | 칸별 좋아짐 · 같음 · 나빠짐 | 개입률 전 → 후 | 상황 인지 전 → 후 |
|---|---|---|---|---|
| baseline | 0.794 ±0.125 → **0.729 ±0.130** | 15 · 0 · 0 | — | 1.000 |
| arm1 | 0.650 ±0.111 → 0.624 ±0.093 | 10 · 1 · 4 | — | 0.418 → 0.397 |
| arm2 | arm1 과 같음 | 10 · 1 · 4 | — | 0.418 → 0.397 |
| proposed | 0.723 ±0.130 → 0.709 ±0.126 | 9 · 4 · 2 | 0.639 → **0.809** | 0.488 → 0.475 |

| 사다리 (15쌍, 음수가 좋아짐) | 전 | 후 | 읽기 |
|---|---|---|---|
| 상황 인지 arm1 − baseline | −0.144 (12 · 1 · 2) | −0.106 (11 · 2 · 2) | 정답을 아는 쪽(`baseline`)이 여전히 더 나쁘다 — **emergency 칸은 원인 규명됨(목표표가 θ 를 안 나눴다 → D7). 나머지 칸은 미규명** |
| 정책 선택 arm2 − arm1 | ±0 (15 같음) | ±0 (15 같음) | 규칙 판단자는 설계상 lstm 을 안 고른다(C-13) — LLM 칸에서 잰다 |
| 선택적 개입 proposed − arm2 | +0.073 (1 · 0 · 14) | **+0.085** (1 · 1 · 13) | 개입이 더 해로워졌다 → D4 · D5 |

| proposed 칸의 개입 (합계) | 전 | 후 |
|---|---|---|
| 개입 스텝 | 659/1080 (61%) | 866/1080 (**80%**) |
| 개입에서 빠져나온 횟수 | 47 | **21** |
| 첫 개입 뒤 자율 비율 — 예: mixed s0 · normal s0 | 0.44 · 0.35 | 0.01 · 0.02 |

- **개입이 늘어난 이유 — D5 가 60칸 전체에서 확인됐다.** B-2 전에는 폴백이 가끔 SLA 를 지키면 그 성공이
  rule_based 성적으로 **잘못** 올라갔고, 그게 우연히 개입에서 빠져나오는 길이었다. B-2 가 귀속을 고치면서
  그 길도 같이 없어졌다.
- **B-1 효과는 작다.** 60칸 위반 2982 → 2845, 그중 배분 탓 비율 83% → 82%. baseline 이 15/15 칸 좋아져 방향은
  맞지만, 평활에 희석돼 크기가 작다 → D1-b.
- 시나리오별로는 emergency 의 arm1 만 나빠졌다(0.58 → 0.62). 나머지는 조금씩 좋아졌다.
  (D7 과는 별개다 — arm1 은 정답을 안 받는 쪽이다.)

**M-1 — 규칙 판단자 30스텝 · 시드 0 (전 = before-B1 같은 시드 앞 30스텝)**

| | normal 전 → 후 | emergency 전 → 후 |
|---|---|---|
| 개입 · 최장 연속 · 탈출 | 18 · 18 · 0 → 14 · 14 · 0 | 19 · 19 · 0 → 18 · 17 · 1 |
| SLA 위반 | 21 → 18 | 21 → 19 |
| AUC `combined` (전체) | 0.683 → 0.671 | 0.481 → **0.488** |
| AUC `worst u/θ` (전체) | 0.847 → 0.708 | 0.598 → 0.646 |
| AUC `combined` (자율 스텝만) | 0.611 → 0.556 | 0.533 → 0.629 |

- 1차 D2 기준(0.7 이상 유지 · 0.6 미만 선행 신호 게이트)을 그대로 대면 **emergency 는 게이트 추가, normal 은
  회색 지대.** 두 시나리오 모두 `worst u/θ` 가 `combined` 보다 높다 — 게이트 후보다.
- `worst u/θ` 가 normal 에서 0.85 → 0.71 로 떨어졌다. B-1 보정이 이용률이 높은 스텝에 반응해 배분을 고치므로
  이용률만으로는 위반을 덜 예측하게 된 것으로 보인다(가설 · 확인 안 함).
- ⚠️ **위 AUC 여덟 값은 전부 95%CI 가 0.5 를 포함한다** (반폭 ±0.22, Hanley–McNeil).
  30스텝으로는 어떤 신호도 구분력을 주장할 수 없다 — 방향조차 읽으면 안 된다. D2 의 단서 참조.

### 1.6 결정 반영 뒤 — M-0c · theta 60칸 · Claude 오케스트레이터 (2026-09-29)

**한 줄: D1-b · D4 · D5 로 개입이 80% → 43% 로 줄면서 SLA 도 좋아졌고, theta 목표표(D7)에서 사다리 첫 칸의
부호가 뒤집혀 "상황을 알면 낫다"가 성립했다. Claude 오케스트레이터도 배선은 전부 작동한다.**
재현: `tools/compare_matrix.py after-B1 after-D` · `tools/compare_matrix.py after-D after-D-theta` ·
`tools/signal_auc.py "runs/_matrix/after-D/raw/proposed_rule-*" --pool --quiet`. 원본은 `runs/_matrix/*/raw/` (C 로컬).

**M-0c — after-D 60칸 (규칙 판단자 · 사용량 0 · 반영: B-1b · D1-b · D4 · D5)**

| 비교군 | SLA 위반율 after-B1 → after-D | 개입률 | 조달비 |
|---|---|---|---|
| baseline | 0.729 → 0.642 (15/15 좋아짐) | — | +15% |
| arm1 = arm2 | 0.624 → 0.599 | — | +13% |
| proposed | 0.709 → **0.569** (13 좋아짐 · 1 나빠짐) | 0.809 → **0.451** | +23% |

| 사다리 (15쌍, 음수가 좋아짐) | after-B1 | after-D |
|---|---|---|
| 상황 인지 arm1 − baseline | −0.106 (유의) | −0.043 (0 포함) |
| 정책 선택 arm2 − arm1 | ±0 | ±0 (규칙 판단자 설계상) |
| **선택적 개입 proposed − arm2** | +0.085 (13쌍 악화) | **−0.030** (10쌍 좋아짐, CI [−0.053, −0.007]) |

- 개입 탈출 21 → **88**회. 개입 필요도(가상 채점) 326/467 = 0.698 — 부른 스텝의 70% 는 제안대로면 위반이었다.
- **D2 에 대한 답이 바뀌었다.** 묶은 AUC(1080스텝): `combined` 0.514 → **0.611±0.033**(구분함), `worst u/θ` 0.684 → 0.564.
  귀속(B-2)과 보정(D1-b)이 바로잡히자 현재 공식이 스스로 위반을 가려낸다.
- 주의: 상황 인지 정확도 proposed 0.475 → 0.329 (보정이 증상을 빨리 지워 관측이 평시처럼 보이는 것으로 추정 · 확인 안 함).

**theta 60칸 — after-D-theta (`SLICE_TARGET_TABLE=theta`, 그 외 after-D 와 같음 · 사용량 0)**

| 비교군 | SLA 위반율 원본표 → theta | 개입률 | 조달비 |
|---|---|---|---|
| baseline | 0.642 → **0.509** (14/15) | — | +14% |
| arm1 = arm2 | 0.599 → 0.582 | — | +3% |
| proposed | 0.569 → **0.532** | 0.451 → **0.386** | +2% |

| 사다리 (15쌍) | 원본표 | theta |
|---|---|---|
| **상황 인지 arm1 − baseline** | −0.043 (0 포함) | **+0.073** (15쌍 모두 같은 방향, CI [+0.043, +0.104]) |
| 선택적 개입 proposed − arm2 | −0.030 | **−0.051** (13쌍 좋아짐, CI [−0.071, −0.030]) |

- M-0 부터 줄곧 "정답을 알면 더 나쁘다"던 사다리 첫 칸의 원인이 목표표였음이 확인됐다. 약점: emergency 의 arm1 은
  0.62 → 0.72 (상황을 잘못 맞히면 theta 가 더 손해 — 오히려 상황 인지의 가치를 보여 준다).

**Claude 오케스트레이터 — emergency s0 · 20스텝 · 한 번씩 (사용량 $2.56 + $2.72, 구독)**

| emergency s0 앞 20스텝 | 원본표 | theta |
|---|---|---|
| 규칙 판단자 (proposed_rule) | SLA 위반 11 · 개입 3 | 위반 14 · 개입 7 |
| **Claude (proposed_orch)** | 위반 17 · 개입 3 · lstm 11 · 전환 6 | 위반 **14** · 개입 **0** · lstm 9 · 전환 7 |

- **배선은 전부 작동:** 관측 features 20/20(C-22) · 개입 시 agent_allocation · agent_correction 3/3(D5) · rule_based 적용
  6/6 에 보정량(D1-b, LLM 이 직접 넘김) · 개입 뒤 자율 복귀(D5) · 오류 스텝 0 · `record_after_apply` 경고 3 · 2.
- Claude 는 emergency 를 16 · 17/20 맞힌다(규칙 판단자보다 훨씬 정확). 원본표에서는 그 정확함이 손해였고(URLLC 과배분),
  theta 에서 규칙 판단자와 같은 SLA 가 됐다 — D7 근거.
- theta 에서 Claude 는 **한 번도 사람을 안 부르고** 규칙 판단자(7번)와 같은 SLA 를 냈다. 겉으로는 논문 주장 모양이지만
  **lstm 으로의 전환(D6) 7회가 개입을 대신했다.** 정당한 탐색인지 비상구인지는 반복 측정으로만 가린다.
- 한 번씩 돌린 결과다 — 같은 시드도 실행마다 갈린다(C-9). 차이 3스텝은 우연 범위일 수 있다.

**다음(사용자 결정 대기):** D7 기본값(theta 를 본 조건으로?) · Claude 칸 반복 — 권고 최소안: theta · emergency · normal ·
20스텝 × 2회 = Claude 4칸, 약 $11 · 80분.

---

## 2. 결정 — 한 번의 회의에서

§4 의 M-1 · M-0b(무료, 약 80분)를 먼저 돌리면 아래 일곱 개를 숫자를 들고 한자리에서 정할 수 있다.

> **D7 을 먼저 읽는다.** D1-b(보정 위치) · D2(개입 공식) · D4(폴백 배분)는 전부 "목표표에서
> 나온 배분"을 어떻게 손볼 것인가를 다투는데, D7 은 그 목표표 자체가 ①의 임계값과 어긋나
> 있다는 것이다. 어긋난 크기(최대 0.243)가 D1-b 가 다투는 보정 크기(최대 0.1, 평활 뒤 0.03)
> 보다 한 자릿수 크다.

### D7. 목표표가 임계값을 안 나눴다 (신규 · 2026-09-28 kim) — **C 권고 2026-09-29: theta 를 본 조건 · 원본표는 민감도** (사용자 결정 대기)

> theta 60칸에서 사다리 첫 칸이 −0.043 → **+0.073**(15/15) 으로 뒤집혔고, Claude 오케스트레이터는 상황을 잘 맞힐수록
> 원본표에서 손해였다(§1.6). 원본표로는 상황 인지 칸을 해석할 수 없다. 원본 결과도 나란히 싣고 "원본 목표표는
> 임계를 반영하지 않는다"를 논문에 명시한다. 조달비는 에이전트 쪽 +2~3% · baseline +14%.

| | |
|---|---|
| 무엇 | ②의 `TARGET_BY_SITUATION`(`rule.py:25`)은 **수요 배율**만 보고 나눈다. 그런데 위반이 없어지는 배분은 수요가 아니라 **수요/임계** 에 비례한다 — `a*ₖ ∝ traffic_k/(θₖ·capacityₖ)` (⑤ `scoring.ideal_allocation`). `θ = {embb 0.9, urllc 1.2, mmtc 0.8}` 이고 **`urllc` 만 1.0 을 넘는다** = URLLC 은 초과 가입을 견딘다. emergency 는 URLLC 수요가 2배지만 `2.0/1.2` 라 필요 배분은 0.463 인데, 목표표는 0.7 을 주고 임계가 더 빡빡한 `embb`(0.9)·`mmtc`(0.8)에서 빼앗는다 — **방향이 반대다** |
| 크기 | 네 줄 **모두** `urllc` 과잉 · `mmtc` 과소다. 부호가 일정한 것이 θ 를 안 나눈 증거다.<br>`normal` [−0.072 **+0.137** −0.065] · `emergency` [−0.132 **+0.243** −0.111] · `special_event` [+0.004 **+0.121** −0.125] · `iot_surge` [−0.079 **+0.090** −0.011] |
| 실측 | **정답 라벨이 최악의 배분을 가리킨다.** emergency, 배분으로 피할 수 있던 스텝만: 정답 라벨 **0.950** · 틀린 라벨(`normal` 목표) 0.767 · `a*(obs_t)` 0.767. 네 시나리오 중 emergency 만 이렇게 뒤집힌다 |
| 어디서 왔나 | **kim 의 버그가 아니다.** 목표표 네 줄은 원본 `ml_orchestrator_demo.py:428~438`, `θ` 는 원본 `:174` 그대로다. 원본 설계에 있던 불일치를 충실히 옮긴 결과다. CLAUDE.md 가 원본을 읽기 전용으로 못 박았으므로 조용히 고칠 성격이 아니다 |
| 왜 중요 | **"상황 인지가 도움이 되는가"에 답할 수 없다** — 목표표가 틀린 것과 인지가 틀린 것이 분리되지 않는다. 정답을 받는 칸은 `baseline` 이다(`arms/__init__.py:28`) |
| 어디까지 설명하나 | ⚠️ **사다리 첫 칸을 전부 설명하지는 못한다.** 라벨을 섞는 것이 정답 고정보다 나은 시나리오는 emergency 뿐이다(`target_audit.py` §4). 나머지 칸이 음수인 이유는 미규명 — C-9 반복과 M-0c 몫이다 |
| 선택지 | (a) 발견으로 **보고만** 하고 목표표를 그대로 둔다 (b1) `theta_only` — 원본 표를 θ 로만 나눈다. **정보 우위 없음** (b2) `theta` — `BASE_TRAFFIC × 배율 / θ`. 효과가 크지만 **①의 생성 상수를 쓴다 = 정답지를 본다** (b3) b1 · b2 를 **둘 다 재서 격차를 보고** (c) 목표표를 고친다 — 원본 이탈, CLAUDE.md 와 충돌 |
| **권고** | **(b3).** 처음엔 (b2)를 권했으나 **실측으로 뒤집혔다** — 아래 24칸 참조. (b2) 단독은 "정답지를 본 arm 이 이겼다"로 읽힌다 |
| 24칸 실측 (2026-09-28) | baseline · 4시나리오 × 3시드 × 30스텝 · 위반율: `original` 0.806 → `theta_only` **0.769** → `theta` **0.639**. 쌍대비교 12칸 모두 유의(`theta_only−original` −0.04 [−0.07,−0.00] · `theta−original` −0.17 [−0.21,−0.12]).<br>⚠️ **개선의 3/4 이 정보 우위에서 온다.** 특히 **emergency 에서 `theta_only` 는 거의 무효다**(27.7 → 27.3, `theta` 는 21.0) — emergency 표가 가정한 수요비 2:7:1 이 실제 1.78:3.33:1 과 애초에 달라서, θ 로 나눠도 틀린 비율이 남는다.<br>사다리(arm1−baseline) emergency n=3: `original` −0.19(유의) · `theta_only` −0.13(유의아님) · `theta` +0.01. **`theta_only` 는 emergency 의 뒤집힘을 못 없앤다.**<br>⚠️ 조달비가 같이 오른다: 15,112 → 19,037(+26%) → 21,187(+40%). **비용 고정 비교가 아니다.**<br>원본: `runs/_matrix/{d7check,d7only,d7theta}/` |
| 남은 질문 | "목표표를 고치면 상황 인지가 제값을 한다"는 **정답지를 봐야만 성립한다.** 이걸 논문에 어떻게 자리매김할지가 회의에서 정할 것이다 — 한계로 적을지, 상한(oracle) 으로 제시할지 |
| 검증 | `tools/target_audit.py` (B 신규 · 서버도 에이전트도 안 띄운다 · 무료 · 5초). 4시나리오 × 3시드 · 구조적 스텝 제외:<br>**원본 목표표 217/252 = 0.861 · θ 정규화 151/252 = 0.599 · `a*(obs_t)` 171/252 = 0.679**<br>θ 정규화가 네 시나리오 전부에서 이기고, 잡음을 쫓는 `a*` 보다도 낫다 |
| 전제 검증 | θ 정규화 표는 **슬라이스별 용량이 같다**고 가정한다 — 실측 슬라이스 간 용량 차 최대 `0.000000`(조달 전). `TRAFFIC_CLIP` 이 물리면 비율이 왜곡되는데 실측 270칸 중 3~5칸뿐이라 무시할 수 있다. 위 반사실은 **조달이 없다고 본 값**이다 — 목표표의 모양만 보기 위해서고, 조달까지 켠 비교는 M-0c 에서 한다 |
| 순환 아님 | θ 표와 `a*` 은 같은 식에서 나오지만, **위반 판정은 그 식을 안 쓴다** — ①이 `utilization > θ` 로 직접 센다(`env.py:199`). 그래서 "a* 에 가까우면 위반이 적다"는 가정이 아니라 측정 결과다 |
| 여는 작업 | B-7 → C-21 |

### D1-b. 위반 보정을 어디에 거는가 (B-1 후속 · kim 제기 · **D7 뒤에 읽는다**) — **결정 2026-09-28: (iii) + 게이트웨이 자동 부착** · 구현 A-5 · B-5 · C-16

| | |
|---|---|
| 무엇 | 원본 `update_allocation_rule_based`(`ml_orchestrator_demo.py:422~465`)는 목표(:429~440) → **평활**(:443~444) → **보정**(:446~458) → 클립 · 정규화(:461~462). 지금은 ②가 목표표에 보정을 걸고, ①이 그 **뒤에** 평활 0.7 을 건다 → 적용값에는 보정의 30% 만 남는다(최대 0.1 → 0.03) |
| 실측 | emergency 30스텝 SLA 위반 19 vs 20 — 1스텝 차이. **M-0b 60칸:** 위반 2982 → 2845, 배분 탓 비율 83% → 82% — baseline 은 15/15 칸 좋아졌지만 크기가 작다(§1.5) |
| 선택지 | (i) 현행 유지 (ii) ①이 평활 뒤에 보정 — 원본 순서지만 ①은 정책을 몰라 lstm 제안에도 걸린다. 원본은 규칙 함수에만 있다(`update_allocation_ml`:341 에는 평활만) (iii) ②가 목표와 **보정량**(`correction`)을 따로 내고, ①이 평활 뒤에 그 보정량을 더한다 — rule_based 에만, 원본 수식 그대로 |
| **권고** | **(iii).** 원본 기준을 그대로 재현하고, "정책은 ② · 평활 · 클립은 ①" 경계도 지킨다. 상수를 바꾸지 않는다 |
| 여는 작업 | B-5 · A-5 → C-16 |

### D2. 개입 판정 공식 (1차 그대로 · D5 와 같이) — **권고 2026-09-29: 현행 유지 (a)**

> after-D 1080스텝 묶음 AUC 가 `combined` **0.611±0.033** 으로 0.5 와 구분된다(§1.6). 게이트 후보이던 `worst u/θ` 는
> 0.564 로 내려갔다. 새 상수를 넣을 근거가 사라졌다 — 공식은 그대로 두고 τ 0.3~0.6 민감도만 보고한다.

선택지와 판정 기준(AUC 0.7 / 0.6)은 1차 §2 D2 그대로다. **새 사실 둘:** B-2 이후 empirical 이 동결돼
공식이 개입을 빠져나오지 못하고(D5), 반대로 표본이 적은 정책은 사전값에 기대어 기준을 넘어 개입을 피하는
길이 된다(D6). 둘 다 "empirical 이 표본 수에 따라 어떻게 움직이나"의 문제라 공식을 바꾸면 같이 풀릴 수
있으므로 **D5 · D6 과 한 번에 정한다.** 여는 작업 C-7.

**M-1 결과(§1.5):** `combined` AUC normal 0.671 · emergency 0.488. 두 시나리오 모두
`worst u/θ`(0.708 · 0.646)가 더 높다.

> ⚠️ **판정 기준 자체가 이 측정 길이에서 쓸 수 없다 (2026-09-28 kim).** 30스텝(위반 19 ·
> 충족 11)의 AUC 95%CI 는 **±0.22** 다 — M-1 의 여덟 값이 **전부 0.5 를 포함한다**
> (`combined` [0.270, 0.706] · `intrinsic` [0.245, 0.683] · `worst u/θ` [0.445, 0.847]).
> "emergency 는 0.488 이라 게이트가 필요하다" 도, "무작위보다 못하다" 도 주장할 수 없다.
> 기준값 0.7 과 0.6 도 서로 구분되지 않는다 — AUC 0.7 의 CI 가 [0.511, 0.889] 라 0.6 을 덮는다.
> CI 를 ±0.10 으로 줄이려면 **약 120스텝**이 필요하다(시나리오 전체 길이는 60).
> **D2 를 결정하려면 판정 기준을 먼저 고쳐야 한다** — (i) 시드를 묶어 AUC 를 한 번에 내거나
> (ii) AUC 대신 CI 가 좁은 지표로 바꾸거나 (iii) 기준값 간격을 CI 보다 넓게 잡는다.
> `tools/signal_auc.py` 가 이제 ± 와 `(0.5포함)` 을 같이 낸다.

### D3. 조달 시점 (1차 그대로)

권고 (b) — 고정 루프는 1.0 반응형, 오케스트레이터만 추세로 선제 허용. B-1 효과가 작아서, M-0b 에서
"조달과 무관한 위반" 비율을 다시 보고 켠다. 여는 작업 C-8.

### D4. 개입하면 무엇이 적용되는가 (1차 그대로) — **결정 2026-09-28: (c1) expert** · 구현 A-4

권고 (c1) 현재 관측 전문가 `a*(obs_t)`. 여는 작업 A-4. 참고: 폴백 배분도 ①의 평활을 거친다. 액추에이터
제약이라 맞지만, 사람의 배분도 스텝당 30% 씩만 반영된다는 것을 해석에 적는다.

**M-0b 결과(§1.5):** 선택적 개입 칸 proposed − arm2 가 +0.073 → **+0.085**(15쌍 중 13쌍 악화). 상수 폴백인 채로
개입이 61% → 80% 로 늘어 벌점이 커졌다. D5 와 함께 정해야 이 칸이 움직인다.

### D5. 개입에서 빠져나오지 못한다 (신규) — **결정 2026-09-28: (a) 가상 채점** · 구현 A-6 · B-6 · C-17

| | |
|---|---|
| 무엇 | B-2 이후 개입 스텝은 정책 성적을 안 쌓는다 → **empirical 동결.** emergency s0: 13번째 스텝부터 끝까지 연속 개입, empirical 0.318 고정 |
| 수치 | 빠져나오려면 intrinsic ≥ 0.45² / 0.318 = **0.637** (= 여유 0.46 이상). 개입 구간 실측 intrinsic 최대 0.55 |
| B-2 전후 | 전 `...........EEEEEEEEEEEEEEEEEEE` 19회 (성적이 **깎여서**) · 후 `...........E.EEEEEEEEEEEEEEEEE` 18회 (성적이 **얼어서**). **귀속은 고쳐졌고 결과는 같다** |
| 60칸 (M-0b) | proposed 칸 개입 61% → **80%** · 탈출 47 → **21**회. B-2 전의 탈출은 폴백 성공이 정책 성적으로 **잘못** 올라간 덕이었다 — 귀속을 고치자 우연한 출구가 닫혔다(§1.5) |
| 원인 | 1차 B-2 설계(C 작성)가 "개입 스텝은 갱신 제외"만 적고 **복귀 경로를 안 적었다** |
| 왜 중요 | D4 를 (c1)로 바꾸면 개입이 SLA 를 지켜 주지만, 한번 들어가면 안 나오므로 개입률이 높게 고정된다 → *"개입은 줄었다"* 를 쓸 수 없다 |
| 선택지 | (a) **가상 채점** — 개입 스텝에서도 에이전트가 고른 정책의 제안을 ⑤가 다음 관측으로 채점해 그 정책 성적에 반영. 트래픽은 배분과 무관하게 생성되고(`env.py _roll`) 이용률은 `traffic / (allocation × capacity)` 라, "그 배분이었다면"의 SLA 를 정확히 계산할 수 있다 (b) 개입 중 r 을 사전값 쪽으로 조금씩 되돌림 — 되돌림 속도라는 새 상수 (c) k스텝마다 한 번 자율 시도 — 개입 규칙의 예외, 심판의 `ignored_escalation` 과 충돌 (d) D2 에서 공식을 선행 신호로 바꿔, 관측이 가라앉으면 나오게 |
| **권고** | **(a).** 새 상수가 없고, B-2 의 원칙(적용된 것의 성적은 적용된 것에)을 지키면서 정책은 계속 평가된다. 운영에서 말하는 섀도 모드다 |
| 여는 작업 | A-6 · B-6 → C-17 |

### D6. 안 써본 정책이 개입의 비상구가 된다 (신규 · 2026-09-26 오케스트레이터) — **결정 2026-09-28: (a) 막지 않고 센다** · 구현 C-18

| | |
|---|---|
| 무엇 | 쓰던 정책이 기준 미달이면, 표본이 적은 다른 정책으로 바꿔 사람을 안 부른다. 표본이 적으면 empirical 이 축소 보정으로 0.5 근처에 머물고(`(r·n + 0.5·5)/(n + 5)`), B-3 사전값으로 intrinsic 도 0.549 라 combined 0.52 > τ |
| 실측 | `orchcheck3` 12스텝 — 9번째: rule_based 0.443(미달) → lstm(표본 0) 0.524 채택 · 11번째: rule_based 0.395 → lstm(표본 1) 0.472 채택. **두 번 다 SLA 위반.** LLM 근거 원문: "escalate 대상이었지만 lstm_forecast(0.5238)가 임계를 넘어 이를 채택해 escalation 없이 진행". `orchcheck4` 20스텝 — **6스텝이 전환(9 · 11 · 12 · 13 · 14 · 17), SLA 충족 1/6.** 9번째만 lstm 표본 0(사전값)이고 나머지는 표본 2~7 의 실측 성적끼리 비교였다 |
| 규칙상 | 위반이 아니다. 판정은 고른 정책 기준이다. 심판이 처음엔 기록 직전의 **마지막** 판정만 봐서, 미달 정책을 나중에 계산하면 `ignored_escalation` 으로 잘못 셌다 — C-19 로 고쳤다 |
| 얼마나 가나 | 처음엔 "lstm 이 세 번째 실패 뒤 기준 아래"로 계산했으나(intrinsic 고정 가정) **틀렸다.** `orchcheck4` 에서 lstm 이 9번 선택되는 동안 empirical 은 0.50 → 0.32 로 떨어졌는데 intrinsic 이 0.48 → 0.66 으로 올라 combined 가 계속 0.456 이상이었다. intrinsic 은 배분 오차(`exp(−3·recent_error)`, 오차 0.09~0.28), empirical 은 SLA 충족률이라 **둘이 반대로 움직인다** — 그 9스텝 중 SLA 충족은 1번뿐. 정책이 많을수록 비상구도 많다 |
| 왜 중요 | 개입이 줄어도 SLA 가 안 지켜지면 주장의 착시다. 반대로 같은 실행 10번째 스텝에서는 lstm 이 더 높았는데도 "배분이 더 맞다"며 rule_based 를 골랐다 — 진짜 정책 판단도 섞여 있다. **둘을 구분해서 세야** 논문에 쓸 수 있다 |
| 선택지 | (a) 탐색으로 인정하고 **센다** — 기준 미달 판정 뒤 다른 정책으로 자율 기록한 스텝을 심판이 warn 으로, 채점이 그 스텝의 SLA 를 따로 (b) 표본 k 개 미만 정책은 자율 사용 금지 — 새 상수 k (c) 표본이 적을 때 empirical 을 사전값 0.5 대신 보수적으로 — D2(공식) 영역 (d) 프롬프트로 금지 — LLM 의 판단을 막는 것이라 연구 주제와 충돌 |
| **권고** | **(a).** 막지 않고 측정한다 — 심판과 같은 원칙이다(`claude/flow/loop.md` §3.3b). 전환 스텝의 SLA 가 개입 스텝보다 나쁘면 비상구, 비슷하거나 나으면 정당한 탐색으로 보고한다. (b) · (c) 는 D2 와 같이 본다 |
| 여는 작업 | C-18 |

---

## 3. 담당별 작업

형식: **ID · 파일** — 의존 → 변경 → 검증

### 3.1 A · choi (①④)

**A-2b · `srm_mcp/audit/book.py` `bad_confidence` · 저장** — 의존 없음
→ `_is_floatable` 이 `"0.52"` 같은 숫자 문자열과 NaN 을 통과시키고, 장부에는 받은 값 그대로(문자열)
  저장한다(`book.py:174 · 250 · 261`). 저장 전에 float 로 바꾸거나 int · float 만 받는다. NaN · inf 는 거부.
→ 검증: `confidence.situation="0.5"` 로 기록 → 장부 값이 `0.5`(float), 또는 `malformed_confidence`.
→ **완료 2026-09-28 (C 가 고침):** `_is_floatable` 이 NaN · inf 도 거부하고, 검사를 통과한 네 값은
  `clean_confidence` 가 float 로 바꿔 저장한다(숫자 문자열은 받아서 고친다 — LLM 이 다시 부르지 않아도 된다).
  목도 같은 함수를 쓴다. `check_audit` 7번 · `check_mock` 2항목 추가, 각각 61 · 14 통과.

**A-3 · `srm_mcp/observe/` `features` 블록** — 의존 없음 · **①은 이미 충족** (`env.py` 관측에 `features`)
→ 그런데도 오케스트레이터에서 `classify_demand` 가 26번 중 24번 실패했다 — **LLM 이 관측을 옮겨 적으며
  `features` 를 뺐다**(`orchcheck3` · `orchcheck4` calls.jsonl, features 가 있던 2번만 available). → C-22.

**A-4 · `book.py:242` 폴백 배분** — 의존 **D4** · **완료 2026-09-28**
→ 결과: `fallback_allocation(observation)` — 기본 `SLICE_FALLBACK=expert` 는 ⑤ `ideal_allocation(obs_t)`(순수 함수를
  가져다 쓴다, 식은 한 곳), `init` 은 예전 상수. 레코드 · 반환에 `fallback_mode`. 목도 같은 함수. `claude/spec/audit.md` 갱신.
→ (c1)이면 `fallback = dict(INIT_ALLOCATION)` 을 `a*(obs_t)` 로. `a*` 는 ⑤ `feedback/scoring.py`
  `ideal_allocation` 과 같은 식이다 — 같은 식을 두 곳에 두지 않도록 어디서 가져올지 A · B 가 정한다.
→ 검증: 개입 레코드의 `fallback_allocation` 이 스텝마다 다르고 ⑤ `ideal(obs_t)` 와 같다.

**A-5 · `srm_mcp/observe/env.py:231` `apply_allocation(correction=)`** — 의존 **D1-b (iii)** · **완료 2026-09-28** (식은 `common/actuator.py`, 원본 대조 200입력 최대 오차 9.5e-7)
→ 선택 인자 `correction: dict | None` 을 평활(`:247`) 뒤 · 클립(`:250`) 앞에 더한다. 없으면 지금과 같다.
→ 검증: 원본 `update_allocation_rule_based` 와 같은 입력에 같은 출력(소수 6자리) — 단위 검사 1개.

**A-6 · `book.py` `record_escalation(agent_allocation=)`** — 의존 **D5 (a)** · **완료 2026-09-28** (④ 서버 인자 · 도구 설명 포함)
→ A-1 의 `chosen_policy` 와 같은 방식으로 에이전트가 적용하려던 배분을 받아 남긴다.
→ 검증: 개입 레코드에 `agent_allocation`. 안 주면 `null` 이고 다른 동작은 그대로.

### 3.2 B · kim (②③⑤)

**B-1b · `srm_mcp/policy/rule.py` 보정이 음수 요청을 만들어 ①이 거부** — 의존 없음 · **완료 2026-09-28 (C 가 고침)**
→ B-1 명세는 "음수는 ②가 안 고치고 ①이 클립"이었는데, ①의 `apply_allocation` 은 음수를 클립하지 않고
  **거부**한다(`env.py _reject_reason` — 이전 배분 유지). after-B1 · M-1 · 오케스트레이터 실행 4412회 중 4회가
  이렇게 버려졌다(`arm1_rule` · `arm2_rule` emergency s2, mmtc −0.0025 · −1e-06).
→ ①이 음수를 받게 바꾸면 LLM 의 잘못된 값도 조용히 통과하므로 ②를 고쳤다: 보정량은 그대로, 음수는 0 으로 자르고
  합 1 로 다시 나눈다(원본 `:461~462` 의 "보정 뒤 클립 · 재정규화" 순서). [0.1, 0.8] 클립은 여전히 ①.
  `claude/spec/policy.md` 예시 `{0.2463, 0.7537, 0.0}` · `check_policy` 1b 갱신.
→ 검증: check_policy 46 · check_mock 12 · check_orchestrator 42 통과. 거부가 났던 두 칸을 같은 조건으로 다시 —
  음수 요청 2 → 0 · 거부 2 → 0 · SLA 위반 38 → 37/60. after-B1 요약의 이 두 칸은 수정 전 값이다(차이 1스텝).

**B-3b · `tools/check_feedback.py:187`** — 의존 없음 · **완료 2026-09-28**
→ `handover-B.md` 3번 항목. 그 문서에는 C 파일로 적혀 있으나 **kim 이 작성한 파일**이다.
  `recent_error([], "lstm_forecast") == 0.2` 를 확인하는 항목으로 바꾼다.
→ 결과: 항목 1개를 5개로 (`check_feedback` 34 → 37).

**B-5 · `srm_mcp/policy/rule.py` 보정량 분리** — 의존 **D1-b (iii)** · **완료 2026-09-28** (`SLICE_CORRECTION_STAGE=post`(기본)|`target`, `correction_delta` · `correction`)
→ `propose` 가 목표(보정 없음)와 `correction`(합 0 인 dict)을 따로 낸다. `PolicyProposal` 에 필드 추가 —
  반환 필드라 에이전트는 안 깨진다. `SLICE_RULE_CORRECTION=off` 면 correction 은 0.
→ 검증: `check_policy` 1b 를 "목표 + correction = 지금의 on 값" 으로.

**B-6 · `srm_mcp/feedback/server.py` `report_outcome` 가상 채점** — 의존 **D5 (a)** · A-6 · **완료 2026-09-28**
→ 결과: 액추에이터 식을 `srm_mcp/common/actuator.py` 한 곳으로 옮겨 ①(`env.apply_allocation`)과 ⑤가 같이 쓴다.
  `scoring.shadow_outcome` 이 반사실 SLA · 오차를 내고 `report_outcome` 이 `agent_policy` 에 쌓는다. 스위치
  `SLICE_SHADOW_SCORING`(기본 on) — `scoring.shadow_enabled` 에 둬서 목이 fastmcp 없이 읽는다. `check_feedback` 9번.
→ 개입 레코드에 `agent_allocation` 이 있으면: ①과 같은 평활 · 클립으로 "그 배분이 적용됐을 값"을 만들고,
  obs_{t+1} 의 `traffic` · `capacity` 로 이용률 · SLA · error 를 계산해 **`agent_policy`** 의 r · n · errors 를
  갱신한다. 실제 적용된 폴백의 성적은 지금처럼 `fallback` 에. 반환과 장부에 `shadow: true`.
  평활 · 클립 식을 ①에서 가져올지 복사할지는 A · B 가 정한다.
→ 검증: emergency s0 30스텝 — 개입 스텝에서도 `agent_policy` 의 n 이 늘고 empirical 이 고정되지 않는다.

**`tools/check_market.py`** — **완료 2026-09-28**
→ 원래 항목(없으면 멈추는 대신 부트스트랩)은 `bootstrap()` 직접 호출로 끝 →
  **C 에게: `agent/README.md:150` 이 이제 거짓이다.**
→ ⚠️ **같이 발견: 이 검사는 실험을 한 번만 돌려도 깨졌다.** 점수 검사가 실행용
  `data/vendors.json` 을 읽는데 그 `rating` 은 ⑤→③ 되먹임으로 움직인다. 30스텝 2회 직후
  재실행하니 9건 FAIL (`vendor-1` 4.80 → 4.25). 산술 검사의 기준을 읽기 전용 원본으로
  옮겼고, 움직이는 값은 새 §0 에서 정보로만 보고한다.
→ **§1.2 의 "264 PASS" 는 깨끗한 트리에서만 성립하는 숫자였다.**

**B-7 · `srm_mcp/policy/rule.py` θ 정규화 목표표** — 의존 **D7** · **플래그까지 구현 2026-09-28**
→ `SLICE_TARGET_TABLE` 로 세 판을 고른다. **기본 `original`** 이라 D7 전까지 동작이 안 바뀐다.
  `theta` = `BASE_TRAFFIC × 배율 / θ` (생성 상수 사용) · `theta_only` = 원본 표 ÷ θ (생성 상수
  미사용). 어느 표로 돌았는지는 `rationale` 에 실어 장부에 남는다.
→ 세 판 24칸씩 측정 완료 — 결과와 해석은 §2 D7. **`theta_only` 가 emergency 를 못 고친다**는
  것이 이 측정의 핵심이고, D7 권고가 (b2)에서 (b3)으로 바뀐 근거다.
→ ⚠️ `theta` 판은 ①의 생성 상수에서 유도한 값이라 리터럴로 박았다. `common/const.py` 로
  올릴지 ②가 자기 표를 둘지는 **A · B 합의 사항**이다.
→ 검증: `check_policy` 1c 9항목 (기본이 원본 · 세 판 값 · 리터럴==유도식 · 오타는 원본).
  채택 여부는 회의가 정한다 — 구현은 **재기 위한 것**이다.

**`tools/target_audit.py`** — **신규 · 완료 2026-09-28.** D7 의 근거를 재현한다. 서버도
  에이전트도 안 띄우고 5초. 전제 검증 · 목표표 vs a\* · 반사실 비교 · D7 의 설명 범위.

### 3.3 C · lee (에이전트)

**C-10 · 통합** — 의존 **R-3** · **lee 까지 완료 2026-09-26**
→ kim(`43de622`, choi 포함) → lee fast-forward → 검사 6종 → main 은 R-3 에서 정한 방식으로.
→ 결과: lee 병합 완료(병합 커밋 없음). main 은 R-3 합의 뒤.

**C-11 · `chosen_policy` 중계 (A-1 연결)** — 의존 C-10 · **완료 2026-09-26**
→ 결과: 고정 루프 실서버 emergency s0 30스텝 — 개입 레코드 18건 전부 `agent_policy = rule_based`,
  배분 · SLA · 개입은 수정 전(`b12on`)과 30스텝 모두 같다. 오케스트레이터(`orchcheck4` 20스텝) — 개입 1회에서
  LLM 이 `chosen_policy` 를 넘겼고 장부 `agent_policy` 가 요약의 정책과 같다(표본 1).
→ `agent/tools.py:207 record_escalation` 에 인자 추가 · `agent/loop.py:125` 개입 경로에서 판단자가 고른
  정책을 넘김 · `agent/backends/mock.py` 같은 인자. 오케스트레이터 프롬프트에 "사람을 부를 때도 고르려던
  정책을 `chosen_policy` 로 넘긴다" 한 줄(④ 도구 설명에는 이미 있다).
→ 검증: 1차 §5 A-1 판정 — 개입 레코드의 `agent_policy` 집계와 루프 요약의 정책 사용이 같다.

**C-12 · `recent_error` 중계 (오케스트레이터)** — 의존 C-10 · **완료 2026-09-26**
→ 결과(`orchcheck3-special_event-s0` 12스텝): lstm 제안 6/6 · rule_based 11/11 · `compare_policies` 2/2 가
  ⑤ 표 값을 그대로 넘겼다. lstm confidence(표본 0) 0.2231 → **0.5488**. lstm 이 처음으로 선택됐다(2/12) —
  그 방식이 D6 이다.
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

**C-16 · `correction` 중계** — 의존 **B-5 · A-5** (서버 둘이 먼저) · **완료 2026-09-28**
→ 결과: 고정 루프는 `Decision.correction` 을 ① 에 넘기고, 개입 기록에는 `agent_correction`(⑤ 가상 채점이 같이 더함).
  오케스트레이터는 **게이트웨이가 붙인다** — 이번 시도에 ②가 낸 rule_based 배분과 같은 배분이 `apply_allocation` ·
  `record_escalation(agent_allocation)` 에 오면 그 보정량을 끼운다(LLM 이 넣었으면 건드리지 않음, 호출 기록에
  `correction_injected`). 프롬프트 · 도구 설명에도 한 줄. 검사 `check_orchestrator` 3항목.
→ 실측(규칙 판단자 30스텝, 수정 전 → D4·D5 → +D1-b): emergency 개입 18 → 16 → **11** · 최장 연속 17 → 15 → **7** ·
  탈출 1 → 2 → **3** · SLA 위반 19 → 19 → **16** / normal 개입 14 → 14 → **11** · SLA 위반 18 → 14 → 15.
  시드 하나 — M-0c 에서 60칸으로 확인한다.
→ 고정 루프: ②의 `correction` 을 ① `apply_allocation` 에. 오케스트레이터: 프롬프트 한 줄.
→ 검증: 같은 관측에서 적용값이 원본 `update_allocation_rule_based` 출력과 같다.

**C-17 · 개입 시 제안 중계** — 의존 **A-6 · B-6** · **완료 2026-09-28**
→ 결과: `loop.py` 가 `agent_allocation=decision.allocation` · `tools.py` 인자 · 목 · 오케스트레이터 프롬프트 한 줄.
  실측(규칙 판단자 30스텝, D4 + D5 전 → 후): emergency 개입 18 → 16 · 탈출 1 → 2 · SLA 위반 19 → 19 /
  normal 개입 14 → 14 · SLA 위반 18 → **14**. 개입 필요도(C-20e) 0.69 · 0.79. 여전히 대부분 끝까지 개입하는 것은
  rule_based 의 가상 성적이 실제로 나빠서다(목표표 — D7 · D1-b).
→ 고정 루프: 개입 경로에서 판단자의 제안 배분을 `agent_allocation` 으로. 오케스트레이터: 프롬프트 한 줄.

**C-19 · 심판 `ignored_escalation` 오탐** — 의존 없음 · **완료 2026-09-26**
→ 결과: `check_orchestrator` 42/42(새 4항목). 남아 있는 오케스트레이터 실행 5개를 다시 판정 — 바뀐 곳은
  `orchcheck4` 13 · 17번째뿐(`ignored_escalation` → 없음), 9번째 `record_after_apply` 는 남는다. 나머지 4개는
  판정 그대로. `confidence_unmatched` 는 한 번도 없었다 — LLM 은 늘 계산한 값 그대로 기록했다.
  반대 방향(`escalation_without_trigger`)도 같은 원인이라 같이 고쳤다. 실행 당시의 `referee.jsonl` 은 그대로 둔다.
→ `agent/orchestrator/referee.py` 의 C-3 규칙이 기록 직전의 **마지막** `compute_confidence` 를 고른 정책의
  판정으로 가정한다. LLM 이 두 정책을 계산하면서 미달 정책을 나중에 계산하면, 통과한 정책으로 기록해도
  "개입 판정 무시"로 센다. `orchcheck4` 13 · 17번째가 이 경우다 — 논문의 핵심 지표를 부풀린다.
→ 기록 도구 인자의 `confidence`(intrinsic · empirical)와 **값이 같은** 판정을 그 기록의 판정으로 쓴다.
  맞는 판정이 없으면 지금처럼 마지막 판정을 보고, `confidence_unmatched`(warn)를 따로 남긴다.
→ 검증: `check_orchestrator` 에 "통과 정책 → 미달 정책 순서로 계산 후 통과 정책 기록 → 위반 0" 추가,
  `orchcheck4` 의 `calls.jsonl` 을 다시 판정하면 13 · 17번째 `ignored_escalation` 이 사라지고 9번째
  `record_after_apply` 는 남는다.

**C-20b · `tools/run_matrix.py` 의 파이썬 경로** — **kim 이 고침 · C 확인 2026-09-28** (lee 병합 때 검토)
→ `:49` 가 `.venv310` 을 하드코딩해 `.venv` 를 쓰는 트리에서는 첫 칸부터 `WinError 2` 로 죽는다.
  `web/serve.py:32` 는 커밋 `b78f6d6` 에서 이미 고쳤는데 여기가 빠져 있었다. 같은 규칙으로 맞췄다.

**C-20e · `escalation_precision` 이 4/5 시나리오에서 정보가 없다** — **새 지표 추가 2026-09-28** (옛 지표는 그대로 둔다)
→ `eval/breakdown.py` `escalation_need` — 개입 스텝에서 **에이전트 제안대로였으면 위반이었나**(D5 가상 채점)로 센
  `need_precision` · 자율 위반 수. 가상 채점이 없는 실행은 None.
→ 정의가 "개입한 스텝의 정답이 `normal` 이 아니었나"(`eval/score.py:107`)라, 정답 라벨이
  한 종류인 시나리오에서는 **에이전트 행동과 무관하게 시나리오 이름만으로 정해진다** —
  `normal` 이면 0.0, 나머지면 1.0. 실측: emergency s0 에서 개입 18회 중 SLA 를 지킨 것이
  6회인데도 정밀도 1.0. `mixed` 에서만 값이 움직인다.
→ **"선택적 개입이 정확했다"를 이 지표로 주장할 수 없다.** `eval/breakdown.py` 출력에
  경고 한 줄만 붙여 뒀다. 정의를 바꿀지(예: 개입 스텝의 SLA 결과나 반사실 비교로)는
  `score.py` 소유자(A)와 C 가 정한다.

**C-20d · `tools/signal_auc.py` 가 AUC 를 맨숫자로 낸다** — **kim 이 고침 · C 확인 2026-09-28** (lee 병합 때 검토)
→ 30스텝 AUC 의 95%CI 는 ±0.22 인데 `0.488` 처럼만 찍혀서, M-1 의 여덟 값이 전부 0.5 와
  구분 안 되는데도 결론에 쓰였다(§1.5 · D2). Hanley–McNeil 반폭과 `(0.5포함)` 표시를 붙였다.
→ 남은 문제: 시드별로만 내고 **묶지 못한다.** 120스텝이 필요한데 시나리오 길이가 60 이라,
  시드를 합쳐 한 번에 AUC 를 내는 기능이 있어야 D2 를 판정할 수 있다 — C 작업으로 남긴다.
→ **남은 문제 완료 2026-09-28:** `--pool`(실행을 합쳐 AUC 한 번 더) · `*` 패턴(PowerShell 용) · `--quiet`.
  한 실행 안의 스텝은 독립이 아니라 묶은 CI 는 낙관적이라고 출력에 적는다.
  **첫 결과 — after-B1 proposed 15칸(1080스텝):** `combined` 0.514±0.037 **(0.5포함)** · `intrinsic`
  0.514±0.037 (0.5포함) · `empirical` 0.497±0.037 (0.5포함) · `worst u/θ` **0.684±0.032**. 자율 스텝만(214):
  `combined` 0.641±0.074 · `worst u/θ` 0.588±0.076. → 개입 판정 공식은 전체 스텝에서 위반을 못 가려내고,
  관측의 `worst u/θ` 만 가려낸다. D2 의 첫 판정 근거다(`tools/signal_auc.py "runs/_matrix/after-B1/raw/proposed_rule-*" --pool --quiet`).

**C-22 · 오케스트레이터가 관측을 줄여서 넘긴다** — 의존 없음 · **완료 2026-09-28**
→ A-3 참고. LLM 이 `get_observation` 결과를 옮겨 적으며 `features` 를 빼 `classify_demand` 가 실패했고, 한 번은
  피처 11개를 직접 만들어 넣었다(D6 기록 · `orchcheck2`). 프롬프트 값의 규칙에 "observation 은 받은 그대로,
  피처를 만들지 않는다" 한 줄 · ② `classify_demand` 도구 설명에 "features 블록을 읽는다 · 없으면 feature_mismatch".
→ 검증: 오케스트레이터 special_event s0 6스텝에서 `classify_demand` 호출의 observation 에 `features` 가 있고 available.

**C-20c · `tools/compare_matrix.py` 가 오독을 유도한다** — **kim 이 고침 · C 확인 2026-09-28** (lee 병합 때 검토)
→ 셋이 문제였다. (i) 조달비를 아예 안 낸다 — SLA 만 보면 "돈을 더 써서 좋아진 것"과 구별이
  안 된다. (ii) 사다리가 평균만 찍힌다 — 산포·CI 가 없어 유의하지 않은 값을 결과로 읽게 된다.
  (iii) 시드·칸 수가 문자열에 박혀 있어 시드를 늘린 매트릭스를 못 읽는다.
→ 조달비 줄 추가 · 사다리에 ±sd 와 t분포 95%CI 와 "0 포함 ← 방향 주장 불가" 경고 ·
  **사다리를 시나리오별로도** 낸다(풀링하면 한 시나리오의 효과가 희석된다) ·
  구성은 요약에서 유도한다.

**C-20 · `tools/run_matrix.py` 가 칸별 원본을 매트릭스 폴더에 보관** — 의존 없음 · **완료 2026-09-28**
→ 매트릭스는 칸마다 `run.py --fresh` 를 부르고 run_id 가 `{arm}-{scenario}-s{seed}` 라, 다음 매트릭스가 앞
  매트릭스의 `runs/<run_id>/` 를 **지우고 덮어쓴다.** 요약(`summary.json`)은 남지만 개입 패턴 · 탈출 같은
  칸별 원본이 사라진다. M-0b 직전에 알아채 before-B1 · after-B1 은 손으로 `raw/` 에 옮겼다.
→ 칸이 끝날 때마다 `runs/<run_id>/` 를 `runs/_matrix/<이름>/raw/<run_id>/` 로 복사한다. `tools/compare_matrix.py`
  는 이미 `raw/` 를 먼저 찾는다.
→ 검증: 무료 3칸 매트릭스 두 번(이름만 다르게) 뒤 두 `raw/` 가 각자 남아 있다.
→ 결과: 칸이 끝나면(실패한 칸도) `runs/<run_id>/` 를 `raw/<run_id>/` 로 복사하고 `state.json` 에 `raw` 경로를
  적는다. 요약(`collect`)도 보관본이 있으면 그것을 읽는다 — `--resume` 으로 안 돈 칸이 다른 매트릭스에
  덮인 `runs/` 를 읽던 문제가 같이 사라진다(`summary.json` 의 `source` 칸이 어디서 읽었는지 보인다).
  실측: emergency s0 5스텝 3칸 매트릭스 두 번(c20-a · c20-b) → 두 `raw/` 각자 보존, 같은 시드라 장부가 바이트
  단위로 같고, `runs/` 가 두 번째 매트릭스에 덮인 뒤 `c20-a --resume` 요약이 자기 `raw/` 를 읽었다.
  파이썬 경로는 병합 때 kim 의 규칙(C-20b — `.venv310` → `.venv` → 스크립트 인터프리터)으로 합쳤고, 보관은 한 곳(`archive_cell`)에서만 하며 kim 의 "보관 실패가 실험을 죽이지 않게" 처리를 더했다.

**C-18 · 비상구 전환을 센다** — 의존 **D6 (a)** · **완료 2026-09-28**
→ 결과: 위반(warn)이 아니라 **사실**로 셌다 — `Verdict.switched_under_threshold`, 절차 준수율에 안 들어간다(합법적인
  전환이 준수율을 깎지 않게). `breakdown.switch_split` 이 전환 · 개입 · 자율의 SLA 를 나란히. 검사 3항목.
  저장된 실행 재판정: orchcheck3 전환 9 · 11번째(SLA 0/2) · orchcheck4 9 · 11 · 12 · 13 · 14 · 17번째(SLA 1/6).
→ `agent/orchestrator/referee.py`: 기록 전 `compute_confidence` 중 escalate=true 가 하나라도 있고 마지막이
  false 인데 `record_decision` 을 불렀으면 `policy_switch_under_threshold`(warn). `compute_confidence` 는
  정책명을 받지 않으므로 판정의 순서만 본다. 기록된 정책은 `record_decision.chosen_policy`.
  `eval/breakdown.py`: 그 스텝 수와 SLA 를 개입 스텝 · 일반 자율 스텝과 나란히 낸다. 오케스트레이터만 —
  고정 루프는 고른 정책 하나만 판정하므로 전환이 보이지 않는다.
→ 검증: `orchcheck3-special_event-s0` 의 `calls.jsonl` 을 `judge` 에 다시 넣으면 9 · 11번째 스텝이 잡힌다.

**C-9 · `tools/run_matrix.py` 오케스트레이터 · LLM 칸 반복** — 의존 C-5 · **완료 2026-09-28**
→ `--repeats N`: llm · orch 변형만 N 회 (run_id `-rK` 접미 · `run.py --repeat K` 신설 · 장부 config 에 `repeat`).
  규칙 칸은 결정적이라 1회 — `--repeat-rule` 은 배선 검증용(sd 0). 요약은 칸당 한 행으로 접는다(`fold`):
  숫자 지표는 반복 평균, `sla_violation_sd` · `intervention_rate_sd` · `perception_accuracy_sd` 는 표본
  표준편차, `n_repeats` · `n_failed` · `repeat_run_ids`. 반복별 행은 `summary_repeats.json`. `compare_matrix` 가
  읽는 (variant, scenario, seed) 키는 그대로다.
→ 실측: 규칙 칸 2회(무료) — 두 반복 장부 동일, sd 0. 오케스트레이터 emergency s0 2스텝 × 2회(haiku, $0.31) —
  `n_repeats 2` · `sla_violation_sd 0.0` · 상황 인지 0.5 vs 0.0 (`perception_accuracy_sd 0.354`) — 같은 시드
  두 실행이 첫 스텝부터 갈렸다. 1차 C-9 의 관찰 그대로.
→ 추정(`--repeats 3`, sonnet): 120칸 · 실행 240 · 약 87시간 · 사용량 환산 $758 (llm 135 · orch 45). N 은 회의에서.

**C-21 · θ 정규화 목표표를 매트릭스 칸으로** — 의존 **D7 (b)** · B-7
→ `tools/run_matrix.py` 에 변형을 더한다 — `arm1_rule` · `arm2_rule` · `proposed_rule` 의
  `SLICE_TARGET_TABLE=theta` 짝. 사다리 첫 칸(`arm1 − baseline`)이 표를 고치면 부호가
  바뀌는지가 D7 의 판정이다. 에이전트 코드는 안 바뀐다 — ②의 환경변수라 `run.py` 가
  자식 프로세스에 넘기기만 하면 된다(`SLICE_RULE_CORRECTION` 과 같은 경로).
→ 검증: 무료 매트릭스에서 `arm1_rule_theta − baseline_theta` 가 음수에서 벗어나는가.

**C-7 · C-8** — 1차 그대로. C-7 은 D2 · D5 · D6 뒤, C-8 은 D3 뒤.

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
│  A  A-2b  (A-3 은 이미 충족 — §1.3)                                │
│  B  B-3b ✓  check_market ✓  target_audit ✓  (2026-09-28)          │
│  C  C-10 통합 → C-11 · C-12 · C-13 · C-14 · C-15 · C-19           │
│  모두  Z-1 · R-1 ✓ · R-2~R-4 합의                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌ 1. 무료 측정 — 규칙 판단자 · 약 80분 · 완료 2026-09-26 (§1.5) ──┐
│  M-1   normal · emergency 30스텝 → AUC · 개입 연속 길이          │
│  M-0b  after-B1 60칸 → before-B1 과 쌍 비교                       │
│  M-3   tools/target_audit.py — 목표표 감사 · 5초 · 완료 09-28    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌ 2. 팀 회의 — **D7 먼저** · D1-b · D2 · D3 · D4 · D5 · D6 ───────┐
└──────────────────────────────────────────────────────────────────┘
                              ↓
   3. 구현 — 서버 먼저, 에이전트 나중
      B-7 → C-21 (D7)   A-4 (D4)   A-5 · B-5 → C-16 (D1-b)
      A-6 → B-6 → C-17 (D5)   C-7 (D2)   C-8 (D3)   C-18 (D6)   C-9 ✓  C-20 ✓
                              ↓
   4. M-0c  규칙 60칸 재측정 — 사다리 세 칸이 각각 움직이는가
      (D7 (b) 를 채택했으면 θ 짝 60칸을 같이 — 첫 칸의 부호가 바뀌는지)
                              ↓
   5. M-2   본실험 — LLM · 오케스트레이터 칸 시드당 반복 (C-9). --go 없이 추정부터
```

| 측정 | 명령 | 시간 · 사용량 | 무엇을 보나 |
|---|---|---|---|
| **M-1** · 완료 | `run.py --backend mcp --decider rule --arm m1 --scenario {normal,emergency} --seed 0 --steps 30 --fresh --memory-mode cold` → `tools/signal_auc.py m1-normal-s0 m1-emergency-s0` | 2분 · 무료 | `combined` · `intrinsic` · `worst u/θ` 의 AUC(1차 §6 식) + 최장 연속 개입 · 개입 탈출 횟수 |
| **M-0b** · 완료 | `tools\run_matrix.py --name after-B1 --variants baseline,arm1_rule,arm2_rule,proposed_rule --go` → `tools/compare_matrix.py before-B1 after-B1` | 약 75분 · 무료 | before-B1 과 같은 칸끼리 쌍 비교. B-1 은 전 비교군, B-2 는 proposed 에만 영향 |
| **M-3** · 완료 | `tools/target_audit.py` | 5초 · 무료 | ②의 목표표가 ①의 임계값과 어긋난 크기 · θ 정규화 표의 반사실 위반율 (D7) |
| **M-4** · 완료 | `SLICE_TARGET_TABLE={original,theta_only,theta}` 로 `run_matrix --name d7{check,only,theta} --variants baseline,arm1_rule --scenarios normal,emergency,special_event,iot_surge --seeds 0,1,2 --steps 30 --go` | 24분 × 3 · 무료 | 세 목표표의 실측 비교 (D7). ⚠️ `mixed` 없음 · 30/60 스텝 · 시드 3 — **논문 품질이 아니다** |
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
| B-3b | `check_feedback` 에 `recent_error([], "lstm_forecast") == 0.2` — **충족 2026-09-28** |
| B-7 | 기본값은 원본 표 그대로 · `SLICE_TARGET_TABLE=theta` 면 `propose_allocation` 출력이 `target_audit.py` 의 θ 줄과 같다 · `rationale` 에 어느 표인지 남는다 |
| C-21 | θ 짝 60칸에서 `arm1 − baseline` 를 **시나리오별로** 본다. D7 의 예측은 "emergency 칸에서 부호가 뒤집힌다(baseline 이 arm1 보다 나빠지는 것이 사라진다)"이고, 나머지 칸은 예측하지 않는다. emergency 가 안 움직이면 D7 (b) 가 틀린 것이고, emergency 만 움직이고 전체 평균이 그대로면 **나머지 칸의 원인이 따로 있다는 것이 확정된다** — 어느 쪽이든 논문에 쓸 수 있는 답이다 |
| B-5 | 보정 on 이면 rule_based 제안의 `correction` 합이 0, off 면 전부 0 |
| B-6 | emergency s0 30스텝 — 개입 스텝에서도 `agent_policy` 의 n 증가 · 반환에 `shadow: true` |
| C-10 | lee 가 kim · choi 끝을 포함 · 검사 6종 통과 · main 반영은 R-3 뒤 |
| C-11 | 개입 레코드 `agent_policy` 가 null 이 아니고 루프 요약의 정책 사용과 같다 |
| C-12 | 오케스트레이터 12스텝 — lstm 제안 전부에 `recent_error` |
| C-14 | `tools/check_mock.py` 전부 통과 — 목으로 emergency 30스텝에서 개입 스텝이 정책 n 을 안 올리고, n=0 `recent_error` 가 실서버와 같다 |
| C-16 | 고정 루프 적용값이 같은 관측의 원본 함수 출력과 같다 |
| C-17 | 개입 레코드에 `agent_allocation` 이 있고 ⑤가 가상 채점한다 |
| C-18 | `orchcheck3-special_event-s0` 재판정에서 9 · 11번째가 `policy_switch_under_threshold` · 채점에 전환 스텝 SLA 가 따로 나온다 |
| C-19 | `orchcheck4` 재판정에서 `ignored_escalation` 0 · `record_after_apply` 1 · 새 검사 항목 통과 |
| Z-1 | 각자 `data/reliability.json` 이 B-2 이후 값으로 새로 시작했다 |
| M-1 | 두 시나리오의 AUC 3종과 최장 연속 개입이 기록됐다 — 값이 무엇이든 · **완료 2026-09-26 (§1.5)** |
| M-0b | `runs/_matrix/after-B1/summary.csv` 60행 + before-B1 과의 쌍 비교표 · **완료 2026-09-26 (§1.5)** |
| C-20 | 이름이 다른 매트릭스 두 번 뒤 각자의 `raw/` 가 남아 있다 |
| C-9 | `summary.json` 의 orch 행에 `n_repeats ≥ 2` 와 `sla_violation_sd` · **완료 2026-09-28** |
| D7 · D1-b~D6 | 선택과 근거가 이 문서 §2 에 추가됐다 |

---

## 6. 참조

- 1차 계획 · 진단 · M-0 기준값: `claude/team/workplan.md`
- kim 완료 보고 · C 에게 넘긴 4건: `claude/team/handover-B.md` (kim 브랜치에만 있음 — C-10 뒤 로컬에 생긴다)
- 역할 · 파일 소유: `claude/team/roles.md`
- 원본 규칙 배분: `ml_orchestrator_demo.py:422~465` (읽기 전용)
- 재현 산출물: C 로컬 `runs/b12{on,off}-emergency-s0/` · `runs/orchcheck*-s0/` ·
  kim 로컬 `runs/b12{on,off}-emergency-s0/` (2026-09-28 독립 재현, §1.2)
- D7 근거 재현: `tools/target_audit.py` (B · 무료 5초)
- 오케스트레이터 흐름 검증(명세 §3.1 대조 12/12): `claude/flow/loop.md` §3.1 · §3.3b
