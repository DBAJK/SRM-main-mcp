# SRM-main-mcp

5G 네트워크 슬라이싱 오케스트레이터(`ml_orchestrator_demo.py`)를 MCP 서버 5개로 분해하고, LLM 에이전트가 정책 선택·상황 판단·조달·에스컬레이션을 수행하는 실험 환경.

## 문서 — 필요한 파일만 읽는다

전체 지도는 `claude/README.md`. 아래 규칙으로 바로 가도 된다.

| 작업 | 읽을 것 |
|---|---|
| 도구 이름·순서 확인 | `claude/spec/tools.md` |
| 서버 하나 구현/수정 | `claude/spec/common.md` + `claude/spec/<observe\|policy\|market\|audit\|feedback>.md` |
| 에이전트 루프 | `claude/spec/tools.md` + `claude/flow/loop.md` + `claude/flow/data-chain.md` |
| 환경 세팅 · 구현 순서 | `claude/build/runtime.md` + `claude/build/step0.md` + `claude/build/order.md` |
| 저장 경로 · 실행 생명주기 | `claude/build/store.md` |
| 신뢰도 산출식 | `claude/build/formulas.md` |
| 오류 처리 | `claude/flow/errors.md` |
| 채점 / 정답 노출 검사 | `claude/flow/forbidden.md` |
| 누가 무엇을 맡나 | `claude/team/roles.md` |
| 설계 이유가 궁금할 때만 | `claude/rationale/<같은 이름>.md` |

`claude/` 전체를 한 번에 읽지 않는다.

## 절대 규칙

1. **정답 비노출** — `is_emergency` 등 `FORBIDDEN` 문자열이 도구 설명·반환값·오류에 나오면 안 된다. `baseline` arm만 예외, 코드 경로 물리 분리.
2. **서버 간 직접 호출 금지** — 모든 값은 에이전트가 중계한다 (`recent_error`, `capacity_gain`, `vendor_id`).
3. **조용한 폴백 금지** — 정책 실패는 `allocation: null` + `status`로 반환. `policy` 필드를 바꾸지 않는다.
4. **`situation` 기본값 없음** — ②·④의 필수 인자.
5. **numpy → 파이썬 기본형** — 반환 전 `bool()` · `.tolist()`. `violations`가 `np.bool_`이다.
6. **`report_outcome`은 `step()` 이후**, **`record_decision`은 `apply_allocation` 이전**, **조달은 `record_decision` 이전.** 에스컬레이션한 스텝도 조달을 건너뛰지 않고, `slice_id`·`vendor_id`·`cost_total`을 `record_escalation`에 넘긴다.
7. **루프는 파이썬이 돌린다** — LLM이 답하는 값은 `situation` · `confidence.situation` · 정책 선택 · 조달 여부 넷뿐. `combined`와 에스컬레이션 여부는 파이썬이 계산한다.
8. **`get_history()`를 빠뜨리지 않는다** — `history=null`이면 `lstm_forecast`가 영영 `unavailable`.

## 코드 참조

- 원본 시뮬레이터: `ml_orchestrator_demo.py` (배분 파이프라인 `:458~462`, 피처 `:513~526`)
- 마켓 엔진: `5G-Marketplace/src/slice_selection/engine.py`, 벤더 데이터 `5G-Marketplace/data/vendors.json`
- 시나리오: `test_scenarios.py:54-102`
