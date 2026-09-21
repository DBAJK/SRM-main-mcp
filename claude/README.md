# MCP 도구 명세 — 문서 지도

5개 서버 · 도구 21개의 입출력 계약. 예시 값은 **실제 코드를 실행해 얻은 실측치**다.
근거와 설계 배경은 `MCP-design.md` 참조 (현재 저장소에 없음 — 참조만 남아 있다).

## 3계층

| 계층 | 위치 | 내용 | 언제 읽나 |
|---|---|---|---|
| **spec** | `spec/` | 입출력 표 · 열거형 · 공식 · 규칙 · 최소 예시 | 도구를 **구현하거나 호출**할 때 |
| **flow** | `flow/` | 서버 간 데이터 연쇄 · 오류 규약 · 금지 필드 | 에이전트 루프나 채점기를 만들 때 |
| **rationale** | `rationale/` | 왜 그렇게 정했나 · 실측 증거 · 논문 연결 | 설계를 **바꾸거나 의문이 생길** 때만 |

spec에는 "무엇을/하지 말 것"만 있고 "왜"는 없다. spec의 규칙이 이상해 보이면 같은 이름의 `rationale/` 파일을 연다.

## 파일 목록

| 파일 | 대략 토큰 | 내용 |
|---|---|---|
| `spec/common.md` | 0.5K | `SliceTriple` · 열거형 · numpy 변환 규약 |
| `spec/tools.md` | 1.1K | 21개 도구 한 표 · 부작용 · **1스텝 표준 호출 순서** |
| `spec/observe.md` | 3.4K | ① `get_observation` `step` `apply_allocation` `get_history` `reset` `add_capacity` |
| `spec/policy.md` | 2.1K | ② `list_policies` `propose_allocation` `compare_policies` `classify_demand` |
| `spec/market.md` | 3.0K | ③ `qos_requirements` `list_offerings` `score_offerings` `explain_score` `procure` `update_rating` |
| `spec/audit.md` | 2.2K | ④ `record_decision` `record_escalation` `get_decisions` `get_metrics` |
| `spec/feedback.md` | 1.4K | ⑤ `report_outcome` `get_reliability_table` |
| `flow/data-chain.md` | 1.8K | 1스텝 도식 · 조달 분기 · 출력→입력 대응표 · 에이전트가 만드는 값 4개 |
| `flow/errors.md` | 0.7K | 값 vs 예외 · 호출 순서 위반 처리 |
| `flow/forbidden.md` | 0.8K | `FORBIDDEN` 목록 · `baseline` 예외 · `situation`↔`truth` 매핑 · 전환 경계 |
| `rationale/observe.md` | 1.6K | `demand_pressure` 근거 · LSTM `capacity` 한계 · `run_id` 필요성 |
| `rationale/policy.md` | 1.3K | 폴백 금지 근거 · `recent_error` 중계 경로 · `situation` 기본값 없음 |
| `rationale/market.md` | 1.9K | 정정 J (99.20 vs 92.00) · `capacity_gain` 환산 · `GAIN_SCALE` 튜닝 · δ 비대칭 |
| `rationale/audit.md` | 1.3K | 에스컬레이션이 `decision_id`를 내는 이유 · `sla_violations` 집계 출처 |
| `rationale/feedback.md` | 0.9K | 요청값/적용값 둘 다 기록 · `capacity` 포함 · 축소 보정 |
| `rationale/context-budget.md` | 0.4K | 에이전트 런타임 토큰 예산 · 주의할 호출 3개 |

## 읽기 규칙

- **한 서버 작업** → `spec/common.md` + 해당 `spec/<server>.md`. 다른 서버는 열지 않는다.
- **에이전트 루프 작성** → `spec/tools.md`(호출 순서) + `flow/data-chain.md`. 개별 spec은 필요한 도구만.
- **채점기(`eval/score.py`)** → `flow/forbidden.md` + `spec/audit.md`의 `get_metrics` + `spec/feedback.md`.
- **"왜 이렇게?"** → 그때만 `rationale/`.
- 전체를 한 번에 읽지 않는다. 원본 단일 파일은 약 23K 토큰이었다.

## 원문 표기

①②③④⑤ = observe · policy · market · audit · feedback. `:341` 같은 줄 번호는 `ml_orchestrator_demo.py`, `engine.py:719`처럼 파일이 붙은 것은 해당 파일.
