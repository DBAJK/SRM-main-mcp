# 컨텍스트 예산 (에이전트 런타임)

도구 설명과 반환값이 매 턴 LLM 컨텍스트를 차지한다. **21개 도구의 설명만으로 이미 상당하다.**

| 항목 | 대략 |
|---|---|
| 도구 21개의 이름 + 설명 + 스키마 | 2,600 ~ 3,700 토큰 (상주) |
| `Observation` 1건 | 약 210 토큰 (`capacity` · `demand_pressure` 추가분 포함) |
| `PolicyProposal` 1건 | 약 120 토큰 |
| `compare_policies` (3정책) | 약 360 토큰 |
| `score_offerings` (벤더 5) | 약 250 토큰 |
| `get_decisions(n=50)` | **약 10,500 토큰** ⚠️ |
| `explain_score` (`neural_network` 포함 시) | 약 500 토큰 (제거하면 200) |

## 주의할 호출 세 개

- `get_decisions(n=50)` — 각 레코드에 `observation`이 통째로 들어 있고, V7·V8로 필드가 늘었다. 에이전트용은 `n ≤ 10`.
- `compare_policies` — `propose_allocation`의 3배. 정책 전환을 고민할 때만.
- `record_decision` — **입력**이 크다. `observation` + `considered` + `demand_class`를 매 스텝 보낸다. 출력은 `decision_id` 하나뿐이지만 요청 토큰이 관측 1건 이상이다.

## 규모

스텝당 3~5회 × 120스텝 × 60회 실행 ≈ **2~3만 호출**. 모델 선정 전에 예산을 산정해야 한다 (`MCP-design.md` §9-5, 미해소).
