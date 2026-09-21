# B — 모델 · 정책 (`feature/lee`)

② `slice-policy` · ③ `slice-market` · ⑤ `slice-feedback`.
계약은 `claude/spec/{policy,market,feedback}.md`, 설계 근거는 `docs/SRM-MCP-설계서_B_모델·정책.pdf`.

## ⚠️ 패키지 이름이 `srm_mcp/` 다 — 설계서의 `mcp/` 가 아니다

설계서 §2 레이아웃은 `mcp/` 인데 **그 이름으로는 서버가 기동하지 않는다.** `fastmcp` 는
최상위 패키지 `mcp` 를 54곳에서 import 하고(`fastmcp-slim` → `mcp>=2.0`), 저장소 루트의
`mcp/` 가 `sys.path[0]` 에 먼저 잡혀 설치된 SDK를 가린다. 실제로 재현한 결과:

```
$ python -c "from fastmcp import FastMCP"
ModuleNotFoundError: No module named 'mcp.server'
ImportError: FastMCP server support is not installed. Install `fastmcp` or `fastmcp-slim[server]`.
```

두 번째 줄이 특히 고약하다 — 원인은 이름 충돌인데 메시지는 설치 문제라고 말한다.
아무리 `pip install` 해도 고쳐지지 않는다.

**A·C도 `srm_mcp.common` 으로 import 해야 한다.** `mcp/common/schema.py` 를 기대하고
있다면 경로만 바꾸면 된다. 되돌리는 것은 권하지 않는다.

## 소유권

| 경로 | 소유 |
|---|---|
| `srm_mcp/policy/` `srm_mcp/market/` `srm_mcp/feedback/` | **B** |
| `tools/step0_verify_models.py` `tools/bootstrap_vendors.py` | **B** |
| `srm_mcp/common/` | **A** — 아래 참조 |
| `ml_orchestrator_demo.py` · `engine.py` 등 기존 코드 | 아무도 수정 안 함. 추출(copy-and-adapt)만 |

`srm_mcp/common/` 은 A가 Day 0에 작성해 동결한다. 여기 있는 것은 B가 먼저 짜기 위한 **임시 스텁**이고,
A의 판이 들어오면 통째로 교체한다. `const.py` 값은 ROLES.md §1.2 표를 그대로 옮겼으므로
Day 0에서 대조만 하면 된다.

## 작업 순서

| | 내용 | 산출물 | 완료 판정 |
|---|---|---|---|
| **B-0** ◐ | 모델 적재 검증 — 4/6 통과, 2건 SKIP (TF 미설치) | `srm_mcp/policy/ranges.json` ✅ | 6항목 통과 + **3인 공유** |
| **B-1** ✅ | ③ `slice-market` — 도구 5개 구현 완료 | `market/`, `data/vendors.json` | 에이전트가 `score_offerings` → 벤더 5개 점수 (= M1) |
| **B-2** ✅ | ② `slice-policy` — 도구 4개 구현 완료 | `policy/` | `situation` 만 바꾸면 배분이 달라진다 / `recent_error` 가 confidence 를 바꾼다 |
| **B-3** ✅ | ⑤ `slice-feedback` — 도구 2개 구현 완료 | `feedback/` | `warm` 120스텝에서 `reliability.json` 이 움직인다 / `applied`·`requested`·`actuator_delta` 전부 반환 |

```bash
py -3.10 -m venv .venv310
.venv310/Scripts/python -m pip install -r requirements-mcp.txt
.venv310/Scripts/python tools/step0_verify_models.py
```

### B-1 실행

```bash
python tools/bootstrap_vendors.py   # 5G-Marketplace/data/vendors.json → data/vendors.json
python tools/check_market.py        # 설계서 실측치와 대조 (fastmcp 불필요)
python -m srm_mcp.market.server         # ③ 기동 (fastmcp 필요 — 위 패키지 이름 충돌 참조)
```

`check_market.py` 는 `spec/market.md` 의 실측치를 그대로 박아 두었다 — URLLC 순위
99.20 / 98.00 / 97.60 / 91.76 / 86.20, `explain_score` 기여분 5개, `cost_total` 625.0,
`capacity_gain` 0.20·0.25·0.30. `scoring.py` 를 건드리면 여기부터 돌린다.

B-0의 3번(출력 합 ≈ 1)이 관문이다. 실패하면 1차 범위가 `rule_based` 단독이 되고
C의 프롬프트에서 "정책 선택" 축이 빠진다. 결과를 즉시 공유할 것.

### B-0 결과 — 6/6 통과 · 1차 범위 확정

`.venv310` (Python 3.10.11 + TF 2.15.1 + Keras 2.15.0) 에서 전부 통과했다.

| # | 결과 | 실측 |
|---|---|---|
| 1 LSTM 적재 | **PASS** | TF 2.15.1 로 SavedModel 직접 적재 (정정 I 확인) |
| 2 입력 (1, 10, 11) | **PASS** | `model.input_shape = [None, 10, 11]` |
| 3 출력 3차원·합≈1 ⚠️ | **PASS** | `[0.4412, 0.2737, 0.2851]`, 합 1.000000 |
| 4 결정성 | **PASS** | 동일 입력 2회 → 동일 출력 (Dropout 은 inference 에서 비활성) |
| 5 분류기 softmax | **PASS** | 합 1.000000 |
| 6 `ranges.json` | **PASS** | 11개 피처 · 10,000행 |

**→ 1차 범위는 `rule_based` + `lstm_forecast`. C에 "정책 선택" 프롬프트가 필요하다.**

스케일러 부재는 문제가 되지 않았다. 마지막 층이 softmax 라 출력 범위가 구조적으로
보장되고, 스케일러는 *입력* 정규화 문제라 정확도에만 영향을 준다.

TF 없이도 `step0_verify_models.py` 는 **정적 모드**로 2·3·5 를 답한다 —
`keras_metadata.pb` 안의 모델 config 를 읽는다. 1·4는 SKIP 이 되고 종료 코드가 2다.

### 두 모델의 실제 거동 (600행 표본)

| | 관측 |
|---|---|
| `classify_demand` | dominant 분포 URLLC 144 · eMBB 40 · mMTC 16. margin 0.005~0.9999 |
| `lstm_forecast` | 배분 표준편차 0.03~0.04, embb 0.296~0.441 범위 |

둘 다 입력에 반응한다 — 한 클래스로 붙박이지 않고, 배분도 고정값이 아니다.
다만 **`lstm_forecast` 의 출력 폭이 좁다.** `rule_based` 의 emergency 목표
`{0.2, 0.7, 0.1}` 같은 치우친 배분은 내지 않으므로, 비상 상황에서 두 정책의 성적이
갈릴 가능성이 높다. 정책 선택 실험에는 오히려 유리한 성질이다.

### B-2 실행

```bash
python tools/check_policy.py        # 완료 판정 2개 포함 (fastmcp·TF 불필요)
python -m srm_mcp.policy.server         # ② 기동
```

`rule.py` 에서 **원본 `:446~457` 의 위반 보정을 옮기지 않았다.** `spec/policy.md` 의 응답
예시가 보정 없는 목표 `{0.20, 0.70, 0.10}` 이고(보정을 걸면 `{0.224, 0.686, 0.090}`),
원본에서 그 보정은 *평활된* 배분에 걸리는데 평활이 ①로 빠져 걸 자리가 없어졌다.
측정 관점에서도 이쪽이 낫다 — 위반 보정은 상황 라벨이 틀렸을 때 그 영향을 되돌려
상황 인지 정확도의 신호를 흐린다. **원본 동작을 유지할지는 Day 0 결정 사항이다.**

### B-3 실행

```bash
python tools/check_feedback.py      # 완료 판정 2개 포함. 합성 관측으로 120스텝 돌린다
SLICE_MEMORY_MODE=warm python -m srm_mcp.feedback.server
```

**`decision_id` 에서 `run_id` 를 되돌린다.** `report_outcome(decision_id, observed)` 에는
`run_id` 인자가 없는데 `runs/{run_id}/decisions.json` 을 읽어야 한다. §5.0의 형식
`{run_id}-{step:04d}` 를 역이용해 잘라낸다. C가 `record_decision` 에서 다른 형식을 쓰면
여기서 `malformed_decision_id` 가 난다 — Day 0 체크리스트의 `run_id` 형식 합의 항목이다.

**cold 모드의 `get_reliability_table()`.** 이 도구는 인자가 없는데 cold 에서는
`reliability.json` 이 실행 폴더 안에 있다. `report_outcome` 이 본 마지막 `run_id` 를 쓰고,
`SLICE_RUN_ID` 환경변수로 덮어쓸 수 있게 했다. warm(주 결과)에서는 무관하다.

**설계서의 숫자 하나가 재현되지 않는다.** ROLES.md §3.1과 설계서는 요청 기준 `error` 를
0.316 이라 적었지만, 같은 문서의 입력에 `L1/2` 를 적용하면 **0.282** 다. 적용 기준 0.086 과
`actuator_delta` 0.210 은 정확히 재현되므로 산식은 맞고 0.316 쪽이 어긋난 것으로 본다.
주장("기준이 다르면 배 넘게 벌어진다")은 3.3배로 그대로 성립한다.

### 피처 컬럼명이 두 벌이다 — A와 맞출 것

`dqn_training_data.csv` 는 `embb_allocation` · `embb_utilization`, `ml_orchestrator_demo.py:513`
주석은 `embb_alloc` · `embb_util` 이다. 순서는 같다. `ranges.json` 의 키는 `FEATURE_COLUMNS`
쪽으로 통일했고 변환표는 `step0_verify_models.py` 의 `CSV_ALIAS` 에 있다.
**A의 `get_history()` 가 어느 이름으로 컬럼을 내보내는지 Day 0에 못 박아야 한다** —
어긋나면 ②의 `in_distribution` 이 조용히 전부 `false` 가 된다.

## 이 세 서버에 걸린 절대 규칙

1. **정답 비노출** — `is_emergency` 등 `FORBIDDEN` 문자열이 도구 설명·반환값·오류에 0건.
2. **서버 간 직접 호출 금지** — `recent_error`(⑤→②), `vendor_id`(⑤→③), `capacity_gain`(③→①)
   는 전부 에이전트가 중계한다.
3. **조용한 폴백 금지** — 실패는 `allocation: null` + `status`. `policy` 필드를 바꾸지 않는다.
4. **`situation` 기본값 없음** — ②의 필수 인자.
5. **numpy → 파이썬 기본형** — 반환 전 `store.to_builtin()`. `violations` 가 `np.bool_` 이다.
6. **평활·클립을 ②에 두지 않는다** — ①의 `apply_allocation()` 소관.

## 환경변수

| 이름 | 값 | 쓰는 곳 |
|---|---|---|
| `SLICE_DESC_MODE` | `minimal`(주 실험) / `advisory` | ② 도구 설명 |
| `SLICE_MEMORY_MODE` | `warm`(주 결과) / `cold` | ③⑤ 상태 유지 위치 |

## 통합 스모크 — 3개 프로세스 stdio 왕복

```bash
python tools/smoke_servers.py
```

`check_*.py` 는 도구 함수를 파이썬으로 직접 부르지만 이쪽은 **실제 MCP 전송**을 탄다 —
프로세스 분리 · 핸드셰이크 · JSON 직렬화 · 스키마 검증까지 걸린다. `spec/tools.md` 의
1스텝 표준 호출 순서를 ②③⑤ 구간만 그대로 밟고, ①④ 자리는 합성값으로 메운다.
**M1(배선 검증)의 증거로 쓸 수 있다.** `fastmcp` 가 필요하다.

끝나면 `data/vendors.json` 의 레이팅과 `runs/_smoke-s0/` 를 되돌린다.

## 구현할 때 걸릴 것 하나 더

FastMCP 는 **함수 docstring 을 그대로 도구 설명으로 써서 LLM 컨텍스트에 넣는다.**
골격의 docstring 은 구현 지침이라 그대로 두면 §6.3 의 `desc_mode` 실험이 오염되고
C의 누출 검사에도 걸린다. `@mcp.tool(description=...)` 로 설명을 분리하고
docstring 은 개발자용으로만 남긴다.
