# 설계 문서 — 지도

MCP 서버 5개 · 도구 21개로 5G 슬라이스 오케스트레이션을 분해하고, LLM 에이전트가
상황 판단 · 정책 선택 · 조달 · 에스컬레이션을 수행하는 실험 환경.

**`claude/`가 정본이다.** `docs/`에 있던 `TOOLS.md` · `MCP-design.md` · `ROLES.md` ·
`MCP-decomposition.md`는 전부 이쪽으로 이관·병합했다.

## 5계층

| 계층 | 위치 | 내용 | 언제 읽나 |
|---|---|---|---|
| **spec** | `spec/` | 입출력 표 · 열거형 · 공식 · 규칙 · 최소 예시 | 도구를 **구현하거나 호출**할 때 |
| **flow** | `flow/` | 제어 루프 · 데이터 연쇄 · 오류 규약 · 금지 필드 | 에이전트 루프나 채점기를 만들 때 |
| **build** | `build/` | 런타임 구조 · 저장 규약 · 산출식 · 0단계 · 구현 순서 | 환경을 세우거나 순서를 정할 때 |
| **rationale** | `rationale/` | 왜 그렇게 정했나 · 실측 증거 · 검증 이력 | 설계를 **바꾸거나 의문이 생길** 때만 |
| **team** | `team/` | 3인 역할 분담 · 완료 판정 · 합류 지점 | 작업을 나누거나 진도를 볼 때 |

spec에는 "무엇을/하지 말 것"만 있고 "왜"는 없다. spec의 규칙이 이상해 보이면 `rationale/`을 연다.

## 파일 목록

### spec — 도구 계약

| 파일 | 내용 |
|---|---|
| `spec/common.md` | `SliceTriple` · 열거형 · numpy 변환 규약 |
| `spec/tools.md` | 21개 도구 한 표 · 부작용 · **1스텝 표준 호출 순서** |
| `spec/observe.md` | ① `get_observation` `step` `apply_allocation` `get_history` `add_capacity` `reset` |
| `spec/policy.md` | ② `list_policies` `propose_allocation` `compare_policies` `classify_demand` |
| `spec/market.md` | ③ `qos_requirements` `list_offerings` `score_offerings` `explain_score` `procure` `update_rating` |
| `spec/audit.md` | ④ `record_decision` `record_escalation` `get_decisions` `get_metrics` |
| `spec/feedback.md` | ⑤ `report_outcome` `get_reliability_table` |

### flow — 값이 어떻게 흐르나

| 파일 | 내용 |
|---|---|
| `flow/loop.md` | 시간 규약 · 액추에이터 · **고정 루프(LLM은 판단만)** · 컨텍스트 재구성 · 에스컬레이션 정의 |
| `flow/data-chain.md` | 1스텝 도식 · 조달 분기 · 출력→입력 대응표 · **LLM이 만드는 값 4개** |
| `flow/errors.md` | 값 vs 예외 · 호출 순서 위반 처리 |
| `flow/forbidden.md` | `FORBIDDEN` 목록 · `baseline` 예외 · `situation`↔`truth` 매핑 · 전환 경계 |

### build — 무엇을 어떻게 세우나

| 파일 | 내용 |
|---|---|
| `build/extract.md` | **서버별 추출 대상 코드** — 어느 함수를 어디로, 무엇을 고치나 |
| `build/runtime.md` | 프로세스 구성 · 저장소 레이아웃 · 기술 스택 (Python 3.10 / TF 2.15.1) |
| `build/store.md` | **실행 생명주기** · `runs/{run_id}/` · decisions · reliability · truth · vendors |
| `build/formulas.md` | 내재적 신뢰도 · 경험적 신뢰도(EMA + 축소) · 도구 설명 수위 |
| `build/step0.md` | 모델 적재 검증 6항목 · 실패 시 분기 |
| `build/order.md` | 구현 순서와 완료 판정 · ③ 서버 골격 · 남은 미결 |

### rationale — 왜

| 파일 | 내용 |
|---|---|
| `rationale/corrections.md` | **정정 A~K** — 기존 코드가 설계 전제와 어긋나는 것 11건 |
| `rationale/verification.md` | **값 유실 20건** (V2~V10 · W1~W11) · 근본 원인 3패턴 · 계약 검사기 |
| `rationale/environment.md` | 시나리오별 압력 실측 · 상수 재조정 · **상황 인지 상한 71.7%** |
| `rationale/observe.md` | `demand_pressure` 근거 · LSTM `capacity` 한계 · `run_id` 필요성 |
| `rationale/policy.md` | 폴백 금지 근거 · `recent_error` 중계 경로 · `situation` 기본값 없음 |
| `rationale/market.md` | 정정 J (99.20 vs 92.00) · `capacity_gain` 환산 · `GAIN_SCALE` 튜닝 · δ 비대칭 |
| `rationale/audit.md` | 에스컬레이션이 `decision_id`를 내는 이유 · `sla_violations` 집계 출처 |
| `rationale/feedback.md` | 요청값/적용값 둘 다 기록 · `capacity` 포함 · 축소 보정 |
| `rationale/context-budget.md` | 에이전트 런타임 토큰 예산 · 주의할 호출 3개 |

### team · origin

| 파일 | 내용 |
|---|---|
| `team/roles.md` | A 환경·측정 / B 모델·정책 / C 에이전트 · Day 0 · 병렬화 · 합류 지점 M1~M5 |
| `origin/decomposition.md` | 1단계 분리 설계서 원본 (이력 보존용. 현행 값과 다를 수 있음) |

## 읽기 규칙

- **한 서버 작업** → `spec/common.md` + 해당 `spec/<server>.md`. 다른 서버는 열지 않는다.
- **에이전트 루프 작성** → `spec/tools.md`(호출 순서) + `flow/loop.md` + `flow/data-chain.md`.
- **채점기(`eval/score.py`)** → `flow/forbidden.md` + `spec/audit.md`의 `get_metrics` + `spec/feedback.md`.
- **환경 세팅** → `build/runtime.md` + `build/step0.md`.
- **"왜 이렇게?"** → 그때만 `rationale/`.
- 전체를 한 번에 읽지 않는다.

## 값이 막히기 쉬운 곳 — 구현 전 확인

검증에서 실제로 나온 것들이다. 자세한 것은 `rationale/verification.md`.

| 빠뜨리면 | 증상 |
|---|---|
| `①.get_history()` 호출 | `lstm_forecast`가 영영 `unavailable` → 정책 선택 축이 죽는다 |
| `procure` → `record_decision` 순서 | `vendor_id`가 안 남아 ⑤→③ 레이팅 되먹임이 죽는다 |
| 에스컬레이션 후 `record_decision` 건너뛰기 | 같은 스텝에 decision 레코드가 둘 |
| `confidence.situation` | 상황 오판 시 에스컬레이션이 안 된다 |
| `run_id` | `truth.jsonl` × `decisions.json` 조인 불가 |
| `recent_error` 중계 | ②의 LSTM 신뢰도를 계산할 수 없다 |
| `capacity_gain` 중계 | 조달이 환경에 반영되지 않는다 |

## 원문 표기

①②③④⑤ = observe · policy · market · audit · feedback.
`:341` 같은 줄 번호는 `ml_orchestrator_demo.py`, `engine.py:719`처럼 파일이 붙은 것은 해당 파일.
