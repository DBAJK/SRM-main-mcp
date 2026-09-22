# 인수인계 — B(②③⑤) → A(①④) · C(에이전트)

기준: `feature/kim` · 커밋 `5b96cdc` · 2026-09-22 검토

읽는 순서는 §0 → 자기 절(§2 또는 §3) → §4. **§4는 3명이 같이 읽는다.**

---

## 0. 30초 요약

| | |
|---|---|
| 구현됨 | **도구 21개 중 11개** — ② policy 4 · ③ market 5 · ⑤ feedback 2 |
| 안 됨 | **① observe 6 · ④ audit 4** — `srm_mcp/observe/` · `srm_mcp/audit/` 디렉터리 자체가 없다. `feature/choi` · `feature/lee` · `origin/main` 어느 브랜치에도 없다 |
| 검증됨 | `tools/check_market.py` · `check_policy.py` · `check_feedback.py` **3개 전부 통과**. spec의 실측치가 그대로 재현된다 |
| 미검증 | **실제 MCP stdio 왕복(M1)** 과 **LSTM/분류기 추론 경로**. 검토 머신에 `fastmcp` · `tensorflow` 가 없어 `smoke_servers.py` · `pingpong.py` 를 못 돌렸다 |
| 막힌 곳 | ①④가 없어 루프를 끝까지 못 돈다. B는 `tools/pingpong.py` 의 **모의 ①④** 로 우회 중이고 그 모의는 실험에 쓸 수 없다 |

**착수 전에 §4의 7건을 정해야 한다.** 그 중 2건(컬럼명·`Observation` 피처)은 **정하지 않고 시작하면 ②가 조용히 죽는다.**

---

## 1. 지금 무엇이 되는가

| 서버 | 도구 | 상태 | 검증 |
|---|---|---|---|
| ① observe | `get_observation` `step` `apply_allocation` `get_history` `add_capacity` `reset` | **없음** | — |
| ② policy | `list_policies` `propose_allocation` `compare_policies` `classify_demand` | 완료 | `python tools/check_policy.py` |
| ③ market | `list_offerings` `score_offerings` `explain_score` `procure` `update_rating` | 완료 | `python tools/check_market.py` |
| ④ audit | `record_decision` `record_escalation` `get_decisions` `get_metrics` | **없음** | — |
| ⑤ feedback | `report_outcome` `get_reliability_table` | 완료 | `python tools/check_feedback.py` |

`check_*.py` 는 `fastmcp` · TF 없이 도는 순수 파이썬 검사다. 재현된 실측치:

- ③ URLLC 순위 `99.20 / 98.00 / 97.60 / 91.76 / 86.20`, `explain_score` 기여분 합 = `total`(정정 J 회피), `cost_total` 625.0(4배 부풀림 없음), `capacity_gain` 0.20·0.25·0.30
- ② `situation` 만 바꾸면 배분이 갈린다 / `recent_error` 가 `confidence` 를 바꾼다 / 폴백 시 `policy` 필드 불변
- ⑤ warm 120스텝에서 `reliability` 가 0.4 → 0.0 → 1.0 으로 실제로 움직인다 / `premature_scoring` · `already_scored` · `malformed_decision_id` 방어 동작

**지금 이 환경에서는 `lstm_forecast` 가 `model_not_loaded` 로 내려가 사실상 `rule_based` 단독이다.** `srm_mcp/README.md` 의 B-0 6/6 통과는 `.venv310`(TF 2.15.1)이 있는 다른 환경의 기록이다. §5의 세팅을 먼저 밟을 것.

---

## 2. A에게 — ① observe · ④ audit

### 2.1 먼저 읽을 것 (이 3개면 된다)

`claude/spec/observe.md` · `claude/spec/audit.md` · `claude/build/store.md`.
막히면 `claude/rationale/observe.md` · `rationale/audit.md`. **`claude/` 전체를 읽지 않는다.**

### 2.2 ②⑤가 이미 기대하고 있는 인터페이스 — 어기면 **조용히** 죽는다

구현이 끝난 ②⑤가 ①④의 출력을 이미 특정 형태로 읽는다. 아래 5건은 **코드에 박혀 있는 계약**이다.

#### (1) `get_history().columns` — `hour_of_day` 를 내보내면 ②가 즉시 죽는다 ⚠️

`spec/observe.md` 의 컬럼 예시는 `hour_of_day` 인데, ②의 별칭표
[features.py:31](../../srm_mcp/policy/features.py#L31)은 정본 `time_of_day` 와 `*_allocation` · `*_utilization` 만 받는다.
**`hour_of_day` 는 별칭에 없어서** `FeatureError: 알 수 없는 피처 컬럼: ['hour_of_day']` → `lstm_forecast` 가 매 스텝 `status: "error"` 로 떨어진다.

| 정본 (`const.FEATURE_COLUMNS`) | 받는 별칭 | spec/observe.md 예시 |
|---|---|---|
| `time_of_day` | — | **`hour_of_day`** ← 불일치 |
| `embb_alloc` 외 2 | `embb_allocation` 외 2 | `embb_allocation` ✅ |
| `embb_util` 외 2 | `embb_utilization` 외 2 | `embb_utilization` ✅ |

**깨지는 이름은 정확히 하나다.** §4-①에서 정한다. B 제안: ①이 `time_of_day` 로 내보낸다(모델 학습 데이터 쪽 이름). 반대면 `features.py` 별칭 한 줄 추가로 끝난다.

#### (2) `Observation` 에 11차원 피처를 실어야 `classify_demand` 가 산다 ⚠️

`spec/observe.md` 의 `Observation` 필드만으로는 11차원을 못 만든다 — `traffic_load` 와 `time_of_day` 가 없고, 시각은 `sim_time.hour_of_day` 로 **중첩**되어 있다. ②는 `observation["features"]`(dict 또는 list) 또는 **평탄화된 키**를 찾고, 없으면 예외를 던진다([features.py:59](../../srm_mcp/policy/features.py#L59)).

→ ①이 `Observation` 에 `features` 블록을 추가하는 것이 가장 싸다.

```json
"features": {"traffic_load": 0.515, "time_of_day": 0.125, "day_of_week": 0.0,
             "embb_alloc": 0.4, "urllc_alloc": 0.4, "mmtc_alloc": 0.2,
             "embb_util": 0.624, "urllc_util": 1.283, "mmtc_util": 1.015,
             "client_count": 0.631, "bs_count": 0.482}
```

#### (3) `decision_id` 형식 `{run_id}-{step:04d}` 는 ⑤가 정규식으로 되판다

[feedback/server.py:44](../../srm_mcp/feedback/server.py#L44) — `^(?P<run_id>.+)-(?P<step>\d{4})$`.
`report_outcome(decision_id, observed)` 에 `run_id` 인자가 없어서 여기서 잘라 `runs/{run_id}/decisions.json` 을 찾는다. **④가 다른 형식을 쓰면 전 스텝이 `malformed_decision_id` 로 반환된다.** 스텝은 반드시 4자리 제로패딩.

#### (4) `decisions.json` 은 ④가 만들고 ⑤가 **같은 파일에 덧쓴다**

⑤가 읽는 키: `decisions[]` 배열 · `decision_id` · `step` · `kind` · `chosen_policy` · `allocation` · `vendor_id`.
⑤가 쓰는 키: 해당 레코드의 `outcome`(`sla_met` `error` `scored_at_step` `applied_allocation` `requested_allocation` `actuator_delta` `observed_violations`).
`kind: "escalation"` 레코드는 `fallback_allocation` 을 요청값으로 읽는다([feedback/server.py:88](../../srm_mcp/feedback/server.py#L88)).

- ④는 **첫 `record_decision` 에서 파일을 만든다**(별도 도구 없음). ⑤가 파일을 못 찾으면 `unknown_run`.
- `outcome` 이 이미 있으면 ⑤가 `already_scored` 로 거부한다. 재채점 없음.
- `store.md` 의 `decisions.json` 예시는 `confidence` 에 `situation` 이 빠져 있다 — **`spec/audit.md` 쪽이 맞다**(4개 필수). 문서 정정 필요.

#### (5) `get_metrics.procurement_cost_total` 의 공급선이 끊겨 있다 ⚠️

`spec/audit.md:128` 은 ④가 이 값을 내라고 하는데, `record_decision` 인자에 **`cost_total` 이 없다.** ③의 조달 원장 `_procurements` 는 메모리에만 있고 노출 도구도 없다. §4-③에서 정한다 — `record_decision(cost_total=...)` 추가가 가장 싸다.

### 2.3 `const.py` 상수 3개가 문서와 어긋난다 — A가 확정해 동결할 것 ⚠️

`srm_mcp/common/const.py` 는 **A 소유의 임시 스텁**이고 `roles.md §1.2` 표를 옮겼다고 적혀 있지만, §1.7 재조정분이 반영되지 않았다.

| 상수 | 현재 코드 | 문서(`roles.md §1.2`, `spec/observe.md`, `rationale/environment.md`) |
|---|---|---|
| `CAPACITY_MAX` | [2.0](../../srm_mcp/common/const.py#L13) | **2.6** (기본 1.6 + 조달 4회분) |
| `CAPACITY_BASE` | **없음** | **1.6** |
| `START_HOUR` | [8](../../srm_mcp/common/const.py#L17) | **0** (자정 시작) |

그대로 쓰면 평시 압력 분포가 문서의 실측치(`normal` 5.6%)와 달라져 **조달·에스컬레이션 빈도가 통째로 바뀐다.** `tools/pingpong.py:183` 이 이미 `CAPACITY_MAX=2.0` 으로 상한을 걸고 있다.

같이 정정할 문서: `flow/loop.md` 의 `reset` 도식이 `cap ← [1, 1, 1]` 로 적혀 있다 — `[1.6, 1.6, 1.6]` 이 맞다.

### 2.4 완료 판정 (`build/order.md`)

| 단계 | 판정 |
|---|---|
| **2 (①)** | **동일 시드 2회 실행 → `truth.jsonl` 바이트 단위 동일.** 여기서 반드시 멈추고 확인한다 — 재현이 안 되면 이후 60회 비교가 전부 무의미 |
| **3 (④)** | `get_metrics()` 반환 필드에 `perception_accuracy` · `escalation_precision` **부재** 확인 |

추가로 ②⑤ 연결 확인: ①의 `get_history(10)` 출력을 그대로 `propose_allocation(history=...)` 에 넣었을 때 `status: "ok"` 가 나오면 (1)(2)가 해결된 것이다.

---

## 3. C에게 — 오케스트레이터

### 3.1 지금 바로 할 수 있는 것

**②③⑤는 진짜 서버로 붙는다.** `tools/pingpong.py` 가 ①④를 모의로 세우고 ②③⑤와 **실제 stdio** 로 `spec/tools.md` 의 1스텝 표준 순서를 끝까지 돈다 — 오케스트레이터 골격의 출발점으로 그대로 쓸 수 있다.

```bash
python tools/smoke_servers.py                      # 3프로세스 stdio 1스텝 왕복 (M1 증거)
python tools/pingpong.py --scenario emergency --steps 40
```

⚠️ **`pingpong.py` 의 모의 ①은 A의 ①이 아니다.** 난수 모델·시나리오 강도가 임의값이라 실험 산출물로 못 쓴다. A의 판이 오면 그 자리만 갈아끼운다.

기동 명령과 환경변수:

| 서버 | 명령 | 환경변수 |
|---|---|---|
| ② | `python -m srm_mcp.policy.server` | `SLICE_DESC_MODE` = `minimal`(주 실험) / `advisory` |
| ③ | `python -m srm_mcp.market.server` | — (`data/vendors.json` 필요 → §5) |
| ⑤ | `python -m srm_mcp.feedback.server` | `SLICE_MEMORY_MODE` = `warm`(주 결과) / `cold`, `SLICE_RUN_ID`(cold 보조) |

### 3.2 LLM이 답하는 값은 넷뿐이다

`situation` · `confidence.situation` · **정책 선택** · **조달 여부**.
`combined = (situation × intrinsic × empirical)^(1/3)` 과 **에스컬레이션 여부는 파이썬이 계산한다**(`flow/loop.md §3.3`). 루프 순서를 LLM에 맡기지 않는다 — 대부분의 위반은 오류를 내지 않고 조용하다.

### 3.3 `run_id` 는 C가 발급한다 — 파급이 크다

형식 `{arm}-{scenario}-s{seed}` (예: `exp-proposed-emergency-s0`).
①의 `reset(run_id=...)` 과 ④의 모든 기록에 **같은 값**이 들어가야 `truth.jsonl` × `decisions.json` 이 `step` 으로 조인된다. §2.2-(3)의 `decision_id` 형식도 여기에 걸린다.

### 3.4 프롬프트 제약

- **누출 금지** — `is_emergency` 등 `FORBIDDEN` 6개가 프롬프트·도구 설명·컨텍스트에 나오면 안 된다. *"URLLC 이용률이 높으면 비상일 수 있다"* 같은 **조언도 같은 문제**다(`order.md §9-9`). 최소판/조언판 2벌을 준비하고 `decisions.json` 의 `config` 에 기록한다.
- **컨텍스트는 매 스텝 재구성한다** — 대화 이력을 이어붙이지 않는다. `get_decisions(n=5)` 를 통째로 넣으면 `observation` 이 딸려와 5배가 된다. 최근 N=5는 한 줄 요약으로.
- ②의 도구 설명은 이미 `descriptions.py` 한 곳으로 분리되어 있다(`SLICE_DESC_MODE`). C가 프롬프트에서 같은 조언을 반복하면 실험 변수가 오염된다.

### 3.5 호출 순서 — 조용히 죽는 자리 5개

| 빠뜨리면 | 증상 |
|---|---|
| `①.get_history(10)` | `lstm_forecast` 가 영영 `unavailable` → **정책 선택 축이 죽는다** |
| `③.procure` → `④.record_decision` 순서 역전 | `vendor_id` 가 안 남아 ⑤→③ 레이팅 되먹임이 통째로 죽는다 |
| 에스컬레이션 후 `record_decision` 을 또 호출 | 같은 스텝에 decision 레코드가 둘 → `sum(policy_usage)` 불변식이 깨진다 |
| `①.add_capacity` 를 `step()` 뒤로 | 조달한 그 스텝이 효과를 못 본다 |
| `⑤.report_outcome` 을 `step()` 전에 | `premature_scoring` 으로 거부(이건 시끄럽게 죽는다) |

---

## 4. 3인이 같이 정할 것 — Day 0 잔여 7건

| # | 항목 | 지금 상태 | B 제안 | 안 정하면 |
|---|---|---|---|---|
| ① | `get_history().columns` 이름 | spec는 `hour_of_day`, ②는 `time_of_day` | ①이 `time_of_day` 로 내보낸다 | **`lstm_forecast` 가 매 스텝 `error`** |
| ② | `Observation` 의 11차원 피처 적재 형태 | 현재 스펙으로는 조립 불가 | `features` 블록 추가 | **`classify_demand` 가 매 스텝 `feature_mismatch`** |
| ③ | `procurement_cost_total` 공급선 | 끊김 | `record_decision(cost_total=...)` 추가 | ④가 조달 비용 지표를 못 낸다 |
| ④ | `CAPACITY_BASE` 1.6 / `CAPACITY_MAX` 2.6 / `START_HOUR` 0 | `const.py` 가 구버전 | 문서값으로 동결 | 평시 압력이 실측치와 달라진다 |
| ⑤ | `rule_based` 위반 보정(원본 `:446~457`) 유지 여부 | **옮기지 않았다** | 현행 유지(미보정) | 원본 대비 배분이 다름 — 논문에 적을 항목 |
| ⑥ | `RECENT_ERROR_ALPHA = 2/(N+1)` | 설계서에 계수 없음, B가 표준값 채움 | 승인 | ②의 LSTM 신뢰도 산식이 문서화되지 않은 채 남는다 |
| ⑦ | `qos_requirements` 기본값 vs 예외 | spec은 기본값, ③은 **키가 하나도 없으면 예외** | 예외 유지 + spec 정정 | 전 벤더 동점으로 조용히 무의미해질 위험 |

부수 정정 1건 — `ROLES.md §3.1` 과 설계서의 요청 기준 `error` **0.316** 은 같은 문서의 입력으로 재현되지 않는다(계산하면 **0.282**). 적용 기준 0.086 과 `actuator_delta` 0.210 은 정확히 재현되므로 산식은 맞고 0.316 쪽이 어긋난 것으로 본다. 주장("기준이 다르면 배 넘게 벌어진다")은 3.3배로 그대로 성립.

**실행 순서 주의** — `warm` 실행들 사이에 `cold` 실행이 끼면 누적 레이팅이 오염된다. **모드별로 묶어서 돌린다.**

---

## 5. 환경 세팅 (그대로 복붙)

```bash
py -3.10 -m venv .venv310
.venv310/Scripts/python -m pip install -r requirements-mcp.txt
.venv310/Scripts/python tools/step0_verify_models.py    # 6항목. TF 없으면 정적 모드 3/6
python tools/bootstrap_vendors.py                       # data/vendors.json 생성 (git 에 없다)
python tools/check_market.py && python tools/check_policy.py && python tools/check_feedback.py
```

- **`data/vendors.json` 은 추적되지 않는다.** clone 직후 부트스트랩부터. 없이 ③을 기동하면 `FileNotFoundError` 가 부트스트랩을 가리킨다.
- 패키지 이름이 `srm_mcp/` 다 — 설계서의 `mcp/` 로 만들면 `fastmcp` 가 최상위 `mcp` 를 가려 **서버가 기동하지 않는다.** A·C도 `srm_mcp.common` 으로 import 한다.
- TF는 **2.15.1 고정**(Keras 2). 2.16+ 는 SavedModel 적재 실패. cp39~cp311 휠만 있어 Python 3.10/3.11 필요.

---

## 6. B 쪽 알려진 이슈 (B가 고친다 — A·C는 알고만 있으면 된다)

| # | 위치 | 내용 |
|---|---|---|
| 1 | ~~[market/server.py:228](../../srm_mcp/market/server.py#L228)~~ | **해소.** `_last_step` 가드가 프로세스 전역이라 warm 모드에서 다음 에피소드의 모든 조달이 `stale_step` 으로 거부됐다. 도구를 늘리지 않고 후퇴 **폭**으로 구분한다 — `MAX_STEP_REWIND = 10` (한 번의 `step()` 최대 전진폭) 이내면 순서 실수라 거부하고, 그보다 크면 새 에피소드로 보고 가드를 리베이스한다 |
| 2 | [feedback/reliability.py:15](../../srm_mcp/feedback/reliability.py#L15) | 주석의 `combined = sqrt(intrinsic × effective)` 가 구식. 현행은 `situation` 포함 **세 값의 기하평균** |
| 3 | [policy/server.py:138](../../srm_mcp/policy/server.py#L138) | docstring 에 `perception_accuracy` 가 있다. `@mcp.tool(description=...)` 덕에 지금은 안 새지만, `description=` 을 빼는 순간 누출 검사에 걸린다 |
