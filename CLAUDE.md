# SRM-main-mcp

5G 네트워크 슬라이싱 오케스트레이터(`ml_orchestrator_demo.py`)를 MCP 서버 5개로 분해하고, LLM 에이전트가 정책 선택·상황 판단·조달·에스컬레이션을 수행하는 실험 환경.

## 문서 — 필요한 파일만 읽는다

전체 지도는 `claude/README.md`. 아래 규칙으로 바로 가도 된다.

| 작업 | 읽을 것 |
|---|---|
| 도구 이름·순서 확인 | `claude/spec/tools.md` |
| 서버 하나 구현/수정 | `claude/spec/common.md` + `claude/spec/<observe\|policy\|market\|audit\|feedback>.md` |
| 에이전트 루프 | `claude/spec/tools.md` + `claude/flow/data-chain.md` |
| 오류 처리 | `claude/flow/errors.md` |
| 채점 / 정답 노출 검사 | `claude/flow/forbidden.md` |
| 설계 이유가 궁금할 때만 | `claude/rationale/<같은 이름>.md` |

`claude/` 전체를 한 번에 읽지 않는다.

## 절대 규칙

1. **정답 비노출** — `is_emergency` 등 `FORBIDDEN` 문자열이 도구 설명·반환값·오류에 나오면 안 된다. `baseline` arm만 예외, 코드 경로 물리 분리.
2. **서버 간 직접 호출 금지** — 모든 값은 에이전트가 중계한다 (`recent_error`, `capacity_gain`, `vendor_id`).
3. **조용한 폴백 금지** — 정책 실패는 `allocation: null` + `status`로 반환. `policy` 필드를 바꾸지 않는다.
4. **`situation` 기본값 없음** — ②·④의 필수 인자.
5. **numpy → 파이썬 기본형** — 반환 전 `bool()` · `.tolist()`. `violations`가 `np.bool_`이다.
6. **`report_outcome`은 `step()` 이후**, **`record_decision`은 `apply_allocation` 이전.**

## 코드 참조

- 원본 시뮬레이터: `ml_orchestrator_demo.py` (배분 파이프라인 `:458~462`, 피처 `:513~526`)
- 마켓 엔진: `5G-Marketplace/src/slice_selection/engine.py`, 벤더 데이터 `5G-Marketplace/data/vendors.json`
- 시나리오: `test_scenarios.py:54-102`
