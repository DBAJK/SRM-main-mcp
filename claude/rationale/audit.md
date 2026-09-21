# ④ `slice-audit` — 설계 근거

계약은 `spec/audit.md`.

## 판단을 실행보다 먼저 기록하는 이유

실행 후 기록이면 실패 사례가 사라져 자율 처리율이 과대평가된다.

## `in_distribution` · `demand_class` · `considered`를 기록하는 이유

이 세 필드가 없으면 사후에 답할 수 없는 질문들이 있다.

| 질문 | 필요한 필드 |
|---|---|
| "DQN은 학습 분포 밖에서 신뢰도가 떨어지며 에이전트가 이를 감지해 전환한다" — 사실인가 | `in_distribution` |
| 분류기가 틀린 건가, 에이전트가 분류기를 무시한 건가 | `demand_class` |
| 에이전트가 왜 이 정책을 골랐나 (다른 후보는 뭐였나) | `considered` |

첫 줄은 `MCP-design.md` §5가 논문 내용으로 제시한 문장이다. `in_distribution`을 기록하지 않으면 **주장은 하되 검증은 못 한다.**

## `decision_id`가 `{run_id}-{step:04d}`인 이유

UUID보다 낫다 — 정렬 가능하고, `truth.jsonl`과 `step`으로 조인되며, 사람이 로그를 읽을 수 있다.

## `confidence.combined`가 기하평균인 이유

`combined = sqrt(0.556 × 0.880) = 0.699`. 기하평균이라 한쪽이 낮으면 전체가 낮아진다.

## ⚠️ `record_escalation`이 `decision_id`를 함께 발급하는 이유

에스컬레이션한 스텝도 **배분은 적용되고 SLA 결과가 나온다.** `escalation_id`만 주면 `report_outcome(decision_id=?)`을 호출할 수 없어 **그 스텝의 결과가 통계에서 통째로 사라진다.**

에스컬레이션한 스텝은 정의상 **가장 어려운 스텝**이다. 그것만 빠지면:

- `sla_violations`가 과소 집계된다 → `proposed` arm이 실제보다 좋아 보인다
- 핵심 논증인 *"개입은 줄었는데 SLA 위반은 늘지 않았다"* 가 **편향된 표본 위에서 성립**한다
- `sum(policy_usage) ≠ steps` 가 되어 집계가 어긋난다

한 번의 호출로 두 레코드를 남겨 **빠뜨릴 여지를 없앤다.**

## `fallback`을 서버가 반환하는 이유

모든 비교군이 **동일한 스텝 수를 소화해야** SLA 위반 비교가 공정하다. 에이전트가 사람을 기다리며 멈추면 에피소드 길이가 달라진다. 서버가 다음 행동을 지정해 그 여지를 없앤다.

이 정의 덕분에 실험에 사람이 실제로 필요 없다. *"개입 횟수"는 사람을 부른 횟수이지 사람이 일한 시간이 아니다* — 논문에 명시할 것.

## `get_decisions`의 `n`을 작게 잡아야 하는 이유

각 레코드에 `observation`이 통째로 들어 있고, V7·V8로 필드가 늘었다. `n=50`이면 약 10,500 토큰 (`rationale/context-budget.md`).

## ⚠️ `perception_accuracy` · `escalation_precision`을 반환하지 않는 이유

**④의 반환값은 MCP 도구 결과로 에이전트 컨텍스트에 그대로 들어간다.** 두 지표를 넣으면 에이전트가 *"내가 상황 판단을 자주 틀렸구나"*를 알게 되어, ①에서 막은 정답이 ④를 통해 우회 도달한다. 두 지표는 `eval/score.py`가 `truth.jsonl`과 조인해 **오프라인으로** 계산한다.

**`mttr`은 정답이 필요 없다** — 위반이 시작된 스텝부터 전부 해소된 스텝까지의 길이일 뿐이다. `unresolved`를 따로 보고하는 이유: 복구 못 한 구간을 조용히 빼면 MTTR이 좋아 보인다.

## ⚠️ `sla_violations`를 `observation.violations`로 세면 안 되는 이유

④가 `record_decision`에서 받는 `observation`은 **`obs_t`** 이고, 그 `violations`는 `a_{t-1}`의 결과다. 이걸로 세면 지표 전체가 **1스텝 어긋나고**, 아무 결정의 책임도 아닌 `step 0`의 초기 상태가 한 건 섞여 들어간다.

올바른 출처는 ⑤가 덧붙인 **`outcome.sla_met`** 이다. `outcome`이 없는 레코드(에피소드 마지막 결정)는 제외한다. 그래서 `steps`(채점된 결정 수)가 `sum(policy_usage)`(기록된 결정 수)보다 1 작다.
