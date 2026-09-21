<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 서버별 추출 대상 코드

기존 코드의 어느 함수를 어느 서버로 가져오고 무엇을 고치는가. `mcp/`는 **추출(copy-and-adapt)**이지 import가 아니다.


## ① `slice-observe`

**추출 대상** (`ml_orchestrator_demo.py` → `mcp/observe/env.py`)

| 함수 | 원본 위치 | 조치 |
|---|---|---|
| `generate_traffic()` | `:286` | `datetime.now()` → `sim_time`, `np.random` → `self.rng` (정정 F) |
| `update_utilization()` | `:467` | 그대로 |
| `create_feature_vector()` | `:490` | 동일 치환 |
| `thresholds` `[0.9, 1.2, 0.8]` | `:174` | 그대로 |
| 위반 판정 `util > thresholds` | `:563` | 그대로 |
| `__init__` 상태 | `:162` | `output_dir` 생성·`predictor` 적재 제거 |
| `run()` 루프 | `:840` | **폐기** — `step()`으로 대체 |
| `visualize_*` | `:643`, `:786` | **폐기** |
| 5번째 스텝 벤더 특수처리 | `:580~` | **폐기** |

**도구**

```python
get_observation() -> Observation
step(n: int = 1) -> {"steps_advanced": int, "observation": Observation}
apply_allocation(embb: float, urllc: float, mmtc: float) -> ApplyResult   # §3.2
get_history(n: int = 10) -> {"features": [[float × 11], ...], "columns": [str × 11]}
add_capacity(slice_type: str, amount: float,
             expires_at_step: int, slice_id: str) -> CapacityState        # 정정 K
reset(run_id: str, scenario: str = "normal", seed: int = 0) -> {"observation": Observation}
```

**`Observation` 스키마** — `is_emergency` 계열 3개는 **부재**한다.

```python
{
  "step": 12,
  "sim_time": {"hour_of_day": 11, "day_of_week": 0, "is_weekend": false},
  "traffic":     {"embb": 0.52, "urllc": 0.61, "mmtc": 0.19},
  "allocation":  {"embb": 0.40, "urllc": 0.40, "mmtc": 0.20},   # 현재 적용 중
  "utilization": {"embb": 1.30, "urllc": 1.52, "mmtc": 0.95},   # traffic / allocation
  "thresholds":  {"embb": 0.9,  "urllc": 1.2,  "mmtc": 0.8},    # 노출한다 (정답 아님)
  "violations":  {"embb": true, "urllc": true, "mmtc": true},
  "client_count": 0.63,
  "bs_count": 0.48
}
```

`thresholds`를 노출하는 이유: 사람이 설정하던 값(개입 지점 3번)이고, 이걸 모르면 에이전트가 `violations`의 의미를 해석할 수 없다. 상황 정답과는 무관하다.

**`get_history()` 컬럼 순서 고정** — `create_feature_vector()`(`:513~526`)와 정확히 동일해야 LSTM이 맞는다. 문자열로 함께 반환해 ②가 재유도하지 않게 한다.

```
[traffic_load, hour_of_day, day_of_week,
 embb_alloc, urllc_alloc, mmtc_alloc,
 embb_util, urllc_util, mmtc_util,
 client_count, bs_count]
```

**정답 기록** — `step()` 내부에서 `runs/{run_id}/truth.jsonl`에 append (§5.0).

```json
{"step": 12, "is_emergency": true, "is_special_event": false, "is_iot_surge": false}
```

`_get_ground_truth()`를 파이썬 함수로 두는 것보다 파일 append가 낫다. ①은 별도 프로세스이므로 평가 스크립트가 함수를 부를 수 없고, 파일이면 **`@mcp.tool` 데코레이터가 없는 것만으로 누출 차단이 증명**된다.

**`mixed` 시나리오 변환** — `test_scenarios.py:92`의 `dynamic_changes`는 초 단위(`interval=0.5`)다. 스텝 단위로 옮긴다.

| 원본 `time`(초) | 스텝 | 이벤트 |
|---|---|---|
| 10 → 25 | 20 → 50 | `special_event` on/off |
| 30 → 45 | 60 → 90 | `emergency` on/off |
| 50 → | 100 → | `iot_surge` on |

`duration=60, interval=0.5` → **120스텝**. 시나리오 정의는 `test_scenarios.py:54-102`를 그대로 옮기되 변환표를 `env.py`에 상수로 둔다.

**작업량: 中** (분리 설계서와 동일. 정정 F의 5줄이 추가되지만 `run()`·시각화 폐기로 상쇄)

---

## ② `slice-policy`

**도구**

```python
list_policies() -> [PolicyInfo]

propose_allocation(
    policy: str,
    observation: dict,
    situation: str,                    # ← 필수. "normal"|"emergency"|"special_event"|"iot_surge"
    history: list = None
) -> {
    "policy": str,
    "allocation": {"embb","urllc","mmtc"} | None,
    "confidence": float,
    "in_distribution": bool,
    "status": "ok" | "unavailable" | "error",      # ← 정정 H
    "reason": str,
    "rationale": str
}

compare_policies(observation, situation, history=None) -> [위와 동일 × N]

classify_demand(observation) -> {
    "dominant": "eMBB"|"URLLC"|"mMTC",
    "probabilities": {...}
}
```

**`situation`은 `rule_based`에만 쓰인다.** `lstm_forecast`·`dqn`은 관측 벡터만 본다. 그래도 시그니처를 통일하는 이유: 에이전트가 **상황 판단을 매 결정마다 명시하게 강제**하고, 그 값이 ④에 기록되어 `perception_accuracy` 계산의 입력이 되기 때문이다. `situation`이 없으면 에이전트가 무엇이라 판단했는지 측정할 방법이 없다.

**정책별 구현**

| 정책 | 출처 | 조치 | 가중치 |
|---|---|---|---|
| `rule_based` | `:422` | `self.is_emergency` → 인자 `situation` (정정 E). 평활·클립 제거(→①) | 불필요 |
| `lstm_forecast` | `lstm_predictor.py:426` | 폴백 제거(정정 H). 평활·클립 제거 | **있음** (2.9 MB) |
| `dqn` | `dqn_agent.py` | 2차. 데이터 재생성 선행 | 없음 |
| `classify_demand` | `dqn_classifier.py:359` `classify()` | 그대로 | **있음** (471 KB) |

**모델 적재는 서버 기동 시 1회.** `propose_allocation` 호출마다 적재하면 스텝당 수 초가 든다. 적재 실패 시 서버는 죽지 않고 해당 정책만 `status="unavailable"`로 응답한다 — 실패를 감추지 않으면서 ③④⑤ 실험은 계속 돌게 한다.

**`in_distribution` 판정** — `lstm_forecast`는 `get_history()`의 11차원이 학습 범위 안인지 본다. 학습 데이터 통계가 없으므로 **0단계에서 `dqn_training_data/*.csv`의 컬럼별 min/max를 뽑아 `policy/ranges.json`으로 고정**한다. 범위 밖 차원이 하나라도 있으면 `false`.

**작업량**: `rule_based` 小 / `lstm_forecast` 小~中 / `classify_demand` 小 / `dqn` 大(2차)

---

## ③ `slice-market`

**정정 G에 따라 모델 A 단일화.** 추출 대상 (`engine.py` → `mcp/market/scoring.py`)

| 함수 | 위치 | 조치 |
|---|---|---|
| `_calculate_criteria_weights()` | `:252` | 그대로 |
| `_score_latency/bandwidth/reliability()` | `:328~417` | 그대로 |
| `_calculate_qos_match()` | `:592` | 그대로 |
| `_calculate_price_score()` | `:628` | 그대로 |
| `score_vendor_offering()` | `:719` | `async` 제거, `logger` 정리 |
| `get_score_breakdown()` | `:819` | 그대로 (3중 중복 중 이것만) |
| `query_vendors()` / `find_matching_offerings()` | `:95` / `registry.py:349` | **사용 안 함** (정정 G) |
| `_advanced_score_offer()` | `:185` | **사용 안 함** |
| `_update_vendor_rating()` | `loop.py:218` | 24시간 창 → **스텝 창**으로 변경 |

**도구**

```python
list_offerings(slice_type=None, region=None) -> [Offering]
score_offerings(slice_type, qos_requirements) -> [ScoredOffering]     # 점수 내림차순
explain_score(vendor_id, slice_type, qos_requirements) -> ScoreBreakdown
procure(vendor_id, slice_type, qos_requirements, duration_steps) -> {"slice_id", "status"}
update_rating(vendor_id, outcome) -> {"vendor_id", "rating", "delta"}
```

`duration_hours` → **`duration_steps`**. ①이 가상 시계를 쓰므로 시간 단위를 섞지 않는다.

**`update_rating` 갱신식** — `loop.py`의 24시간 창을 스텝 창으로 옮기되, 단순화한다.

```
rating ← clip(rating + δ, 1.0, 5.0)
δ = +0.05  (sla_met = true)
  = −0.20  (sla_met = false)
```

위반에 4배 가중. 5곳의 초기 레이팅이 4.5~4.9로 좁게 몰려 있어 작은 δ로는 순위가 안 바뀐다. `engine.py:792`에서 `rating/5.0`이 총점의 10~20%를 차지하므로, 0.2 하락 = 총점 0.4~0.8점 하락. 60~120스텝 실험에서 순위 역전이 관측 가능한 크기다.

**부트스트랩** (`tools/bootstrap_vendors.py`, 1회 실행)

```
5G-Marketplace/data/vendors.json  →  data/vendors.json
  + 각 벤더에 "regions": [...] 추가   (location 문자열에서 유도, 5줄)
```

**작업량: 小** — 정정 G로 `await` 수정도 불필요해져 더 줄었다. **1번으로 만든다.**

---

## ④ `slice-audit`

**정정 D에 따라 정답 의존 지표를 제외한다.**

```python
record_decision(
    step: int, observation: dict,
    situation: str,                    # 에이전트의 상황 판단 ← perception 측정의 입력
    chosen_policy: str, allocation: dict,
    confidence: dict,                  # {"intrinsic": .., "empirical": .., "combined": ..}
    rationale: str
) -> {"decision_id": str}

record_escalation(step, observation, situation, reason, confidence) -> {"escalation_id": str}

get_decisions(n: int = 50) -> [Decision]

get_metrics(window: int = None) -> {
    "steps": int,
    "interventions": int,
    "autonomous_rate": float,
    "sla_violations": int,
    "mean_utilization": {...},
    "policy_usage": {...},
    "mttr": float
    # perception_accuracy · escalation_precision  ← 제외. eval/score.py 담당
}
```

`situation`을 기록하는 것이 ④의 가장 중요한 역할이다. 이것과 `truth.jsonl`의 조인이 논문의 핵심 지표를 만든다.

**`decision_id`** = `f"{run_id}-{step:04d}"`. UUID보다 낫다 — 정렬 가능하고, ⑤가 `step`으로 `truth.jsonl`과 대조할 수 있고, 사람이 로그를 읽을 수 있다.

**`mttr` 산출** (정답 불필요): `violations`가 하나라도 `true`인 첫 스텝 → 전부 `false`가 된 스텝까지의 길이. 복구되지 않은 채 끝난 구간은 제외하고 별도로 `unresolved` 카운트로 보고한다. 조용히 빼면 MTTR이 좋아 보인다.

**작업량: 小~中**

---

## ⑤ `slice-feedback`

```python
report_outcome(decision_id: str, observed: dict) -> {
    "sla_met": bool,
    "policy": str,
    "error": float,
    "vendor_id": str | None,          # 있으면 에이전트가 ③.update_rating() 중계
    "reliability_after": float
}

get_reliability_table() -> {
    "rule_based":    {"reliability": 0.91, "n": 120, "effective": 0.88},
    "lstm_forecast": {"reliability": 0.84, "n": 95,  "effective": 0.82},
    "dqn":           {"reliability": 0.42, "n": 60,  "effective": 0.45}
}
```

**`error` 정의** — 분리 설계서의 "기대 대비 실제 오차"를 확정한다.

```
이상 배분  a*_t = normalize( traffic_t / thresholds )     # 위반이 딱 없어지는 배분
error      = L1( a_chosen , a*_t ) / 2                    # [0, 1]
```

`a*`는 관측에서 계산되고 정답을 쓰지 않는다. 정책 간 비교가 가능하고 ②의 LSTM 신뢰도 산출에도 재사용된다 (§6.1).

**`sla_met`** = `observed.violations`의 세 값이 모두 `false`.

**작업량: 中**

---
