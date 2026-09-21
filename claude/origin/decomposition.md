# MCP 분리 설계서

> Build-A-Thon-SRM 프로젝트를 MCP 연결 단위로 분리한 결과
> **일정 1단계 산출물** · 2단계(개발계획서)의 입력

---

## 0. 배경과 목표

### 연구 방향

**사람의 개입을 줄이는 자율 네트워크 오케스트레이션.**

기존 시스템은 운영자가 "지금 비상 상황이다"를 직접 알려주어야 동작한다. 이 연구는 그 판단을 AI 에이전트가 관측만으로 수행하게 하고, 확신이 없을 때만 사람을 호출하도록 한다.

- 기존: **human-in-the-loop** — 사람이 루프 안에 상주
- 제안: **human-on-the-loop** — 사람은 루프 위에서 감독, 예외만 처리

### 자율성 수준 (TM Forum Autonomous Networks)

| 레벨 | 정의 | 사람의 역할 |
|---|---|---|
| L0 | Manual | 전부 수동 |
| L1 | Assisted | 반복 작업만 자동 |
| **L2** | **Partial** | **특정 조건 폐루프, 사람이 감독** ← 기존 시스템 |
| **L3** | **Conditional** | **시스템이 인지·판단, 사람은 예외만** ← 목표 |
| L4 | High | 사람은 목표(intent)만 제시 |
| L5 | Full | 완전 자율 |

관련 표준: ETSI ZSM(Zero-touch Service Management), ITU-T FG-AINN

### 아키텍처

```
        ┌─────────────────────────────────────────┐
        │           [신규 AI 오케스트레이터]        │
        │     인지 → 판단 → 실행 → 검증 → 기록      │
        └─────────────────────────────────────────┘
                          │
        ━━━━━━━━━━━━━━ MCP ━━━━━━━━━━━━━━
        │       │       │       │       │
       ①      ②      ③      ④      ⑤
    observe  policy  market  audit  feedback
    관측·실행 정책카탈로그 조달  기록·측정 자기개선
```

### 기존 설계와의 관계

원 설계도(`5g_network_slice_marketplace_architecture.svg`)에는 **AI Agent가 `Ollama(llama2) → Rule-based` 순서로 폴백**하는 구조가 이미 있다. 즉 LLM 도입 자체는 새롭지 않다.

본 연구의 차별점은 **LLM의 역할 승격**이다.

| | 기존 설계 | 본 연구 |
|---|---|---|
| LLM의 위치 | 폴백 체인의 한 단계 | **조정자(orchestrator)** |
| 정책 선택 | 고정된 폴백 순서 | 상황 판단에 따른 선택 |
| 실패 시 | 다음 폴백으로 | 신뢰도 평가 후 에스컬레이션 |

---

## 1. 분리 기준

동작 여부가 아니라 **두 가지**를 기준으로 삼았다.

**기준 1 — 상태를 들고 있는가**

`MLOrchestrator`는 생성자에서 결과 폴더를 만들고 내부에 배분·이용률·히스토리를 누적하는 상태 보유 시뮬레이션이다. 그대로는 MCP 도구로 감쌀 수 없다. 반면 `SliceAllocationPredictor.predict()`나 `engine.py`의 점수 함수들은 순수 함수라 바로 감쌀 수 있다.

**기준 2 — 사람이 어디에 개입하는가**

자율성이 주제이므로 "능력"이 아니라 "개입 지점"으로 서버 경계를 잡았다.

| # | 사람이 하던 일 | 근거 | 담당 서버 |
|---|---|---|---|
| 1 | "지금 비상이다" 알려주기 | `set_emergency_mode()` — CLI `--emergency` | ① |
| 2 | 어떤 알고리즘을 쓸지 선택 | 코드에 고정 | ② |
| 3 | 임계값 설정 | `thresholds = [0.9, 1.2, 0.8]` 하드코딩 | ② |
| 4 | 벤더 조달 승인 | 수동 API 호출 | ③ |
| 5 | 이상 시 원인 분석 | 조용한 폴백으로 로그 수동 추적 | ④ |
| 6 | 언제 사람을 부를지 판단 | 없음 (항상 사람이 감시) | 에이전트 |
| 7 | 실패에서 배워 다음에 반영 | `Feedback Loop`가 설계만 되고 미작동 | ⑤ |

**1번이 가장 큰 개입 지점이자 핵심 기여 지점이다.**

7번은 원 설계도에 `Feedback Loop`(SLA 위반 학습 → 벤더 레이팅 갱신)로 존재하나 구현이 미완이다. **자율성 관점에서 이것이 없으면 "자동화"일 뿐 "자율"이 아니므로** ⑤로 편입한다.

---

## 2. 서버 간 데이터 공유 규약

서버를 기능별로 나눈 결과 **일부 데이터를 둘 이상이 함께 쓴다.** 단일 머신 연구 프로토타입이고 에이전트가 도구를 순차 호출하므로, 아래 규약으로 처리한다.

### 2.1 공유 저장소

```
data/
  decisions.json      ← ④ 기록 · ⑤ 결과 보고    (양쪽 읽기/쓰기)
  reliability.json    ← ⑤ 소유                   (②는 읽지 않음, §2.2 참조)
  vendors.json        ← ③ 소유                   (⑤는 갱신 요청만)
```

| 파일 | 쓰기 | 읽기 |
|---|---|---|
| `decisions.json` | ④ `record_decision()` · ⑤ `report_outcome()` | ④ `get_metrics()` |
| `reliability.json` | ⑤ | ⑤ · (에이전트가 조회) |
| `vendors.json` | ③ | ③ |

- `decision_id`는 **④가 발급하고 ⑤가 참조**한다. 같은 파일을 보므로 문제없다.
- 에이전트가 순차 호출하므로 동시 쓰기가 발생하지 않는다. 락은 두지 않는다.
- 벤더 레이팅의 **소유자는 ③**이다. `vendors.json`의 `rating` 필드가 원래 ③의 데이터이고, `engine.py:792`의 점수 계산이 이를 직접 읽는다. ⑤는 갱신을 요청할 뿐 직접 쓰지 않는다.

### 2.2 신뢰도는 에이전트가 종합한다

②는 무상태이므로 ⑤의 누적 성적을 알 수 없다. **②가 ⑤를 조회하게 하면 서버 간 직접 호출이 되므로 그렇게 하지 않는다.**

신뢰도를 두 종류로 나누고, **종합 판단은 에이전트가 수행**한다. 판단 주체가 에이전트이므로 일관된다.

| 종류 | 제공 | 의미 |
|---|---|---|
| **내재적 신뢰도** | ② `propose_allocation()` | 이번 입력에 대한 확신 |
| **경험적 신뢰도** | ⑤ `get_reliability_table()` | 이 정책이 평소 얼마나 맞았나 |

```
에이전트: ②에서 내재적 신뢰도 + ⑤에서 경험적 신뢰도 → 종합 → 정책 선택
          둘 다 낮으면 → 에스컬레이션
```

---

## 3. 서버 설계

### ① `slice-observe` — 관측 · 실행

**상태 보유.** 시뮬레이션 환경 그 자체. 에이전트가 관측하고 행동을 가하는 대상.

#### 도구

```python
get_observation() -> {
    "step": int,
    "timestamp": str,
    "traffic":      {"embb": float, "urllc": float, "mmtc": float},
    "allocation":   {"embb": float, "urllc": float, "mmtc": float},  # 합 = 1.0
    "utilization":  {"embb": float, "urllc": float, "mmtc": float},  # traffic/allocation
    "violations":   {"embb": bool,  "urllc": bool,  "mmtc": bool},
    "context":      {"hour_of_day": int, "day_of_week": int, "is_weekend": bool},
    "client_count": float,
    "bs_count": float
}

step(n: int = 1) -> {"steps_advanced": int, "observation": {...}}

apply_allocation(embb: float, urllc: float, mmtc: float)
    -> {"accepted": bool, "normalized": {...}, "reason": str}

get_history(n: int = 10) -> [observation, ...]   # LSTM 입력 (n, 11)

reset(scenario: str = None, seed: int = None) -> {"observation": {...}}
```

#### 핵심 설계 원칙

> **`is_emergency` / `is_special_event` / `is_iot_surge` 를 노출하지 않는다.**

이 세 플래그는 환경 내부에 **정답(ground truth)으로 남는다.** `generate_traffic()`에서 실제로 트래픽을 2배로 만드는 원인이므로 환경은 알고 있어야 하지만, 에이전트에게 주면 "사람이 판단한 결과를 받는 것"이 되어 자율성 주장이 무너진다.

```
[환경]  is_emergency = True        ← 정답. 환경만 앎
            ↓
        URLLC 트래픽 ×2.0
            ↓
        원시 지표만 노출  ──────→  [에이전트]  "이건 비상이군"
        (트래픽·이용률·위반)                        ↑ 스스로 추론
```

평가 스크립트는 정답에 접근해야 하므로 **MCP 도구가 아닌 별도 경로**로 노출한다.

```python
# MCP 도구 아님. 평가 전용.
_get_ground_truth() -> {"is_emergency": bool, "is_special_event": bool, "is_iot_surge": bool}
```

이 구조 덕분에 **상황 인지 정확도**(비상을 놓쳤는가 / 평시를 비상으로 오인했는가)를 정량 측정할 수 있다.

#### 출처 코드

| 재사용 | 위치 | 수정 |
|---|---|---|
| `generate_traffic()` | `ml_orchestrator_demo.py:286` | 없음 |
| `update_utilization()` | `:467` | 없음 |
| `create_feature_vector()` | `:490` | 없음 |
| `thresholds`, 위반 판정 | `:174` | 없음 |
| `MLOrchestrator` 상태 관리 | `:162` | `run()` 루프 분리, 시각화·파일 I/O 제거 |

**작업량: 中**

---

### ② `slice-policy` — 정책 카탈로그

**무상태.** 배분 정책 여러 개를 나란히 노출한다. 어느 하나가 항상 최선이 아니라는 것이 핵심 전제.

#### 도구

```python
list_policies() -> [
    {"name": "rule_based",    "description": "이용률 임계값 기반. 항상 가용, 보수적",
     "always_available": true, "requires": null},
    {"name": "lstm_forecast", "description": "시계열 예측 기반. 평시 효율 우수",
     "requires": "history >= 10"},
    {"name": "dqn",           "description": "강화학습 정책. 학습 분포 내에서 우수",
     "requires": "trained weights"}
]

propose_allocation(policy: str, observation: dict, history: list = None) -> {
    "policy": str,
    "allocation": {"embb": float, "urllc": float, "mmtc": float},
    "confidence": float,          # 내재적 신뢰도 (§2.2)
    "in_distribution": bool,
    "rationale": str
}

compare_policies(observation: dict, history: list = None) -> [
    {"policy": str, "allocation": {...}, "confidence": float}, ...
]
```

> **주의 — 도구 설명도 프롬프트의 일부다.**
> MCP는 도구 이름·설명·파라미터 설명을 전부 LLM 컨텍스트에 넣는다. 위 `list_policies()`의
> *"평시 효율 우수"*, *"학습 분포 내에서 우수"* 같은 문구는 사실상 **"언제 이걸 골라라"는 조언**이며,
> 그대로 두면 심사에서 *"에이전트가 판단한 것인가, 설명대로 고른 것인가"*를 지적받을 수 있다.
> 설명을 **최소판(성격만)과 조언판(현재)** 두 벌로 준비해 비교하면 오히려 자율성의 직접 증거가 된다.
> 구현 전 확정할 것 — §9 미결 사항 8번.

#### 내재적 신뢰도 산출

| 정책 | 산출 |
|---|---|
| `rule_based` | 고정값 (항상 동작하지만 최적은 아님) |
| `lstm_forecast` | 예측 분산 또는 최근 예측 오차 |
| `dqn` | Q값 분포의 마진 + 학습 분포 내 여부 |

> 누적 성적(경험적 신뢰도)은 ⑤가 관리한다. ②는 이번 입력에 대한 확신만 낸다. §2.2 참조.

#### 인지 보조 도구

정책과 별개로, **관측을 해석하는 데 쓰는 학습된 분류기**를 같은 서버에 둔다. 에이전트의 상황 인지를 돕되 답을 주지는 않는다.

```python
classify_demand(observation: dict) -> {
    "dominant": "eMBB" | "URLLC" | "mMTC",
    "probabilities": {"eMBB": float, "URLLC": float, "mMTC": float}
}
```

출처: `slicesim/ai/dqn_classifier.py` `TrafficClassifier` (11 → 3 softmax)
**학습된 가중치 있음** — `5G-Network-Slicing/models/dqn_model_20250601_012010/` (471 KB)

> 이 도구는 "지금 어떤 종류의 수요가 지배적인가"만 알려준다. "비상 상황인가"는 여전히 에이전트가 판단한다. ①의 설계 원칙을 위반하지 않는다.

#### 출처 코드

| 정책 | 출처 | 수정 | 가중치 |
|---|---|---|---|
| `rule_based` | `ml_orchestrator_demo.py:422` `update_allocation_rule_based()` | 없음 | 불필요 |
| `lstm_forecast` | `slicesim/ai/lstm_predictor.py:426` `predict()` | 거의 없음 (§5 정정 C) | **있음** — `models/lstm_model_20250601_011235/` (2.9 MB) |
| `dqn` | `dqn_agent.py` | 데이터 재생성 + 학습 | **없음** |

**작업량: `rule_based` 小 / `lstm_forecast` 小~中 / `dqn` 大**

---

### ③ `slice-market` — 조달

**읽기 위주.** 내부 재배분으로 부족할 때 외부에서 슬라이스를 조달한다. **벤더 레이팅의 소유자**이기도 하다.

#### 도구

```python
list_offerings(slice_type: str = None, region: str = None) -> [
    {"vendor_id": str, "name": str, "slice_type": str,
     "latency": float, "bandwidth": float, "reliability": float,
     "cost": float, "region": str, "rating": float}
]

score_offerings(slice_type: str, qos_requirements: dict) -> [
    {"vendor_id": str, "name": str, "score": float, ...}   # 점수 내림차순
]

explain_score(vendor_id: str, slice_type: str, qos_requirements: dict) -> {
    "total": float,
    "weights": {"latency": 0.35, "reliability": 0.25, ...},
    "criteria_scores": {"latency": 1.0, "bandwidth": 0.83, ...},
    "explanation": str
}

procure(vendor_id: str, slice_type: str, qos_requirements: dict,
        duration_hours: int) -> {"slice_id": str, "status": str}

update_rating(vendor_id: str, outcome: dict) -> {"vendor_id": str, "rating": float}
```

`update_rating()`은 ⑤의 결과 보고를 에이전트가 중계해 호출한다. 레이팅은 `vendors.json`에 있고 `engine.py:792`의 점수 계산이 직접 읽으므로, **③이 소유하고 ③이 갱신한다.**

#### 출처 코드

| 재사용 | 위치 | 수정 |
|---|---|---|
| 가중치 테이블 | `engine.py:252` `_calculate_criteria_weights()` | 없음 |
| 점수 곡선 | `engine.py:328~430` `_score_*()` | 없음 |
| 점수 분해 | `engine.py:819` `get_score_breakdown()` | 3중 중복 중 1벌만 채택 |
| 벤더 데이터 | `data/vendors.json` | 없음 |
| 후보 조회 | `engine.py:95` `query_vendors()` | **`:115` `await` 누락 수정** |
| 레이팅 갱신 | `feedback_loop/loop.py:218` `_update_vendor_rating()` | 로직 이식 |

**작업량: 小** — 가장 먼저 만들 수 있는 서버.

---

### ④ `slice-audit` — 기록 · 측정

**상태 보유(로그).** 논문의 측정 지표를 생산한다. 이 서버가 없으면 실험이 성립하지 않는다.

#### 도구

```python
record_decision(observation: dict, chosen_policy: str, allocation: dict,
                confidence: dict, rationale: str) -> {"decision_id": str}

record_escalation(observation: dict, reason: str,
                  confidence: dict) -> {"escalation_id": str}

get_decisions(n: int = 50) -> [...]

get_metrics(window: int = None) -> {
    "steps": int,
    "interventions": int,              # 사람 호출 횟수
    "autonomous_rate": float,          # 자율 처리 비율
    "sla_violations": int,             # 품질 방어선
    "perception_accuracy": float,      # 상황 인지 정확도
    "escalation_precision": float,
    "mean_utilization": {...},
    "policy_usage": {"rule_based": 12, "lstm_forecast": 45, "dqn": 33},
    "mttr": float                      # 평균 복구 시간
}
```

`decision_id`를 발급하고 `data/decisions.json`에 기록한다. ⑤가 같은 파일에 결과를 덧붙인다 (§2.1).

#### 출처 코드

기록 구조는 `save_history()`(`ml_orchestrator_demo.py:905`)를 참고하되 새로 잡는다. 측정 지표 집계는 신규.

**작업량: 小~中**

---

### ⑤ `slice-feedback` — 자기 개선

**상태 보유.** 결과에서 배워 다음 결정을 바꾼다. **자율성 주장의 핵심**이며, 이것이 없으면 "자동화"에 그친다.

원 설계도의 `Feedback Loop`(SLA 위반 학습 → 벤더 레이팅 갱신)를 자율성 관점으로 확장한 것이다.

#### 도구

```python
report_outcome(decision_id: str, observed: dict) -> {
    "sla_met": bool,
    "policy": str,
    "error": float,                 # 기대 대비 실제 오차
    "vendor_id": str | None         # 조달 결정이었다면 → 에이전트가 ③에 중계
}

get_reliability_table() -> {
    "rule_based":    {"reliability": 0.91, "n": 120},
    "lstm_forecast": {"reliability": 0.84, "n": 95},
    "dqn":           {"reliability": 0.42, "n": 60}
}
```

- `report_outcome()`은 `data/decisions.json`에서 `decision_id`를 찾아 결과를 덧붙이고, `reliability.json`의 정책 신뢰도를 갱신한다.
- 벤더 레이팅은 직접 쓰지 않는다. 결과에 `vendor_id`를 실어 보내면 **에이전트가 ③의 `update_rating()`을 호출**한다.

#### 자기 개선 루프

```
정책 실행 → 결과 관측 → 신뢰도 갱신 → 다음 정책 선택에 반영
    ▲                                          │
    └──────────── 에이전트가 중계 ───────────────┘
```

에이전트가 **"어떤 상황에서 어느 정책이 잘 듣는지"를 경험으로 축적**한다. 실험에서 시간에 따라 정책 선택 분포가 변하는 것을 보여주면 자기 개선을 입증할 수 있다.

DQN 신뢰도가 낮게 수렴하면 그 자체가 결과다 — *"에이전트가 학습 분포 밖의 정책을 스스로 회피하게 되었다."*

#### 출처 코드

| 재사용 | 위치 | 수정 |
|---|---|---|
| 피드백 구조 | `5G-Marketplace/src/feedback_loop/loop.py` | 위반 보고 흐름 참고. 정책 신뢰도는 신규 |
| 위반 탐지 | `src/compliance_monitor/monitor.py` | 30초 주기 → 스텝 단위로 변경 |

> 주의: `loop.py:330`은 `self.ai_agent.update_vendor_ratings()`처럼 **다른 컴포넌트 객체를 직접 호출**한다. MCP로 쪼개면 이 방식은 쓸 수 없으므로 §2의 규약으로 대체한다.

**작업량: 中**

---

## 4. 기존 코드 재사용 현황

### 그대로 쓰는 것 (수정 없음)

| 자산 | 위치 |
|---|---|
| 트래픽 생성기 | `ml_orchestrator_demo.py:286` |
| 이용률 계산 | `:467` |
| 룰 기반 배분 | `:422` |
| 피처 벡터 생성 | `:490` |
| QoS 임계값·위반 판정 | `:174` |
| 벤더 점수화 전체 | `engine.py:252~430` |
| 벤더·슬라이스 데이터 | `data/*.json` |
| 실험 시나리오 정의 | `test_scenarios.py:54-102` |

### 수정이 필요한 것

| 자산 | 문제 | 작업량 |
|---|---|---|
| `MLOrchestrator` | `run()` 루프에 시뮬레이션·추론·시각화가 뒤엉킴. 구조는 살리고 루프만 `step()`으로 분리 | 中 |
| LSTM 예측 | 가중치·학습·메인 추론 모두 정상. **TensorFlow 적재 검증만 필요** | 小~中 |
| `TrafficClassifier` | 가중치 있음. 적재 검증 필요 | 小 |
| `Feedback Loop` | 벤더 레이팅만 구현. **정책 신뢰도는 신규** | 中 |
| DQN (배분용) | 가중치 없음 + 학습 데이터 품질 불량 | 大 |

### 버리는 것

- 시각화 전부 (`visualize_state` 142줄, 스텝마다 PNG 생성)
- 5번째 스텝 특수처리 (데모 연출이 로직에 박힌 것)
- `orchestrator_demo.py` (`ml_orchestrator_demo.py`와 91.3% 중복)
- 비교·데모 스크립트 15개
- `Context_Model` (가중치가 134바이트 LFS 스텁)
- `ndt/simulator.py` (①과 역할 중복)
- 프론트엔드 (일정 6단계 웹화면에서 재검토)

**개략 비율** — `ml_orchestrator_demo.py` 995줄 중 약 220줄 그대로, 400줄 폐기, 170줄 수정.

---

## 5. 모델 자산 현황 (정정 포함)

### 정정 A: "DQN"이라는 이름의 서로 다른 두 모델이 있다

원 설계도에 `AI Agent — DQN 슬라이스 분류 (eMBB/URLLC/mMTC)`라고 적혀 있으나, 이는 자원 배분용 DQN이 아니다.

| 이름 | 위치 | 실제 정체 | 입출력 | 가중치 |
|---|---|---|---|---|
| `DQNAgent` | `dqn_agent.py` (루트) | Q-learning 강화학습. **자원 배분** | 14 → 27 액션 | **없음** |
| `TrafficClassifier` | `slicesim/ai/dqn_classifier.py` | 이름만 DQN. **실제로는 softmax 분류기** | 11 → 3 클래스 | **있음** (471 KB) |

원 설계도가 말하는 "DQN 슬라이스 분류"는 후자다. **강화학습이 아니다.**

→ 후자는 ②의 인지 보조 도구(`classify_demand`)로 편입. 전자만 ②의 `dqn` 정책에 해당한다.

### 정정 B: 학습된 가중치가 실제로 존재한다

| 모델 | 경로 | 크기 |
|---|---|---|
| `SliceAllocationPredictor` | `5G-Network-Slicing/models/lstm_model_20250601_011235/` | 2.9 MB |
| `TrafficClassifier` | `5G-Network-Slicing/models/dqn_model_20250601_012010/` | 471 KB |
| `AutoregressiveLSTMPredictor` | `5G-Network-Slicing/models/enhanced_lstm/` | 4.0 MB |
| 단일 LSTM | `models/lstm_single/best_model.h5` | 428 KB |

앞선 런타임 점검에서 `loaded: false`, `fallback_mode: true`로 나온 것은 **모델이 없어서가 아니라 TensorFlow를 설치하지 않았기 때문**이다. 경로는 존재한다(`model_dir_exists: true`).

→ **TensorFlow 설치 후 실제 적재 가능 여부를 검증할 것.** (미검증 항목)

### 정정 C: LSTM 피처 버그의 영향 범위가 제한적이다

당초 "입력 11개 중 7개가 난수"라고 판단했으나, 재확인 결과 **학습과 메인 추론 경로는 정상**이다.

| 경로 | 컬럼명 | 상태 |
|---|---|---|
| **학습** `train_lstm_model.py:107` | `embb_allocation` 등 — CSV와 일치 | **정상** |
| **메인 추론** `create_feature_vector()` `:490` | 내부 상태에서 직접 생성 | **정상** |
| 벤더 CSV 데모 `load_vendor_data()` `:64` | `embb_alloc` 등 — **CSV와 불일치** | 깨짐 |
| 웹 서버 `lstm_web_server.py:67` | 동일 | 깨짐 |

깨진 것은 **벤더 CSV를 읽는 경로뿐**이며, 이 경로는 ②에서 사용하지 않는다(①의 `get_history()`가 내부 상태에서 시퀀스를 만든다).

→ **`lstm_forecast` 정책의 작업량을 中~大에서 小~中으로 하향 조정한다.**

### DQN(배분용) 확인 사항

#### `state_dim=14`는 버그가 아니었다

`dqn_training_data.csv`의 상태 컬럼이 정확히 14개이며 `DQNAgent(state_dim=14)`와 정합한다.

```
traffic_load, time_of_day, day_of_week,
embb_allocation, urllc_allocation, mmtc_allocation,
embb_utilization, urllc_utilization, mmtc_utilization,
client_count, bs_count, qos_violations,
is_emergency, is_special_event
```

어긋나는 것은 `preprocess_state()`(17차원)이며, 이는 데이터셋을 쓰지 않는 별도 경로다. **`preprocess_state()`를 사용하지 않으면 그대로 학습 가능하다.**

> 주의: 이 상태 정의에 `is_emergency`가 포함되어 있다. ①의 설계 원칙에 따라 에이전트에게 정답을 주지 않으려면, DQN 입력에서 해당 차원을 제거하거나 **에이전트가 추론한 값**을 넣어야 한다. 재학습 시 결정할 것.

#### 데이터셋 품질 문제

| 항목 | 값 | 판정 |
|---|---|---|
| 전이 수 | 10,000 | 충분 |
| 저장된 가중치 | **없음** | `.h5` 4개는 전부 LSTM |
| 양의 보상 비율 | **3.9%** | 불량 |
| 평균 보상 | -5.37 | 불량 |
| 이용률 상한(2.0) 포화 | **56.7%** | 불량 |
| `action 26` 비중 | **43.6%** | 편향 (균등분할) |

거의 전부 "망이 이미 과부하된 상태"의 데이터다. 최적 구간(이용률 0.7~0.9, 보상 +2.0) 예시가 4% 미만이므로 **에이전트가 좋은 상태를 학습할 신호가 없다.**

→ **DQN을 쓰려면 `generate_dqn_dataset.py`의 트래픽 생성 로직 수정 후 데이터 재생성이 선행되어야 한다.**

#### 권고: 단계적 도입

1차 범위에서 DQN을 제외하고 `rule_based + lstm_forecast` 두 정책으로 시작해도 **"에이전트가 상황을 보고 정책을 고른다"**는 주장은 성립한다. DQN은 2차로 추가한다.

일정 위험이 크게 줄어들며, 추가 시 *"DQN은 학습 분포 밖에서 신뢰도가 떨어지며 에이전트가 이를 감지해 전환한다"*가 오히려 논문 내용이 된다.

---

## 6. 실험 설계

### 비교군

| 구분 | 상황 인지 | 정책 선택 | 에스컬레이션 |
|---|---|---|---|
| 베이스라인 | 사람 (`--emergency`) | 고정 | 항상 사람 감시 |
| 비교군 1 | **에이전트** | 고정 | 항상 사람 감시 |
| 비교군 2 | **에이전트** | **에이전트** | 항상 사람 감시 |
| **제안 기법** | **에이전트** | **에이전트** | **신뢰도 기반 선택적** |

베이스라인이 **실재하는 기존 시스템**이므로 비교가 공정하다.

### 시나리오

`test_scenarios.py:54-102`의 정의를 그대로 사용한다.

| 시나리오 | 내용 |
|---|---|
| `normal` | 평시 |
| `emergency` | 비상 (URLLC 급증) |
| `special_event` | 특별 이벤트 (eMBB 급증) |
| `iot_surge` | IoT 급증 (mMTC 급증) |
| `mixed` | 혼합 (구간별 상황 전환) |

### 측정 지표

| 지표 | 정의 | 방향 |
|---|---|---|
| **시간당 개입 횟수** | 에이전트가 처리 못 해 사람에게 전달된 이벤트 수 | ↓ |
| **자율 처리율** | 사람 없이 해결한 사건 / 전체 사건 | ↑ |
| **상황 인지 정확도** | 정답 대비 적중/오탐/미탐 | ↑ |
| **에스컬레이션 정확도** | 불렀어야 할 때 불렀는가 · 불필요하게 불렀는가 | ↑ |
| **SLA 위반 횟수** | 품질 방어선 | 유지 또는 ↓ |
| 평균 복구 시간 (MTTR) | 이상 발생 → 정상화 | ↓ |

### 핵심 논증

> **개입은 줄었는데 SLA 위반은 늘지 않았다.**

자율성만 높이고 품질이 나빠지면 의미가 없다. 대표 그래프는 x축 자율성 수준, y축 두 개(개입 횟수 ↓ / SLA 위반 →)로 구성한다.

### 조작적 정의 (사전 확정 필요)

심사 방어를 위해 미리 못 박아 둔다.

- **개입 1회** = 에이전트가 처리하지 못해 사람에게 전달된 이벤트 1건
- **사건(event)** = 이용률이 임계값을 벗어난 시점부터 정상 복귀까지의 구간
- **에스컬레이션이 옳았는가** = 정답 상황에서 사람의 판단이 실제로 필요했는지 사후 판정

---

## 7. 구현 순서

| 순서 | 대상 | 작업량 | 근거 |
|---|---|---|---|
| **0** | **TensorFlow 적재 검증** | 小 | **선행 조건.** 실패 시 이후 계획이 전부 바뀜 |
| 1 | ③ `slice-market` | 小 | 동작하는 코드. **MCP 배선 자체를 먼저 검증** |
| 2 | ① `slice-observe` | 中 | 나머지 전부의 전제 |
| 3 | ④ `slice-audit` | 小~中 | 실험 측정 기반 |
| 4 | ② `slice-policy` (rule + lstm + classify) | 中 | 가중치가 있으므로 부담 하향 |
| 5 | ⑤ `slice-feedback` | 中 | ②④가 있어야 의미가 생김 |
| 6 | ② `slice-policy` (dqn 추가) | 大 | 선택. 데이터 재생성 선행 |

0단계를 반드시 먼저 한다. 모델 적재 여부에 따라 4단계의 성격이 완전히 달라진다.

③으로 MCP 연결이 실제로 되는지 확인한 뒤 ①을 세우는 것이 위험이 가장 적다.

---

## 8. 기술 스택

- **MCP 서버**: Python (기존 코드·Keras 모델을 그대로 import)
- **권장 라이브러리**: FastMCP — 서버당 100줄 내외
- **Python 버전**: 3.10 (TensorFlow 호환. 동봉된 `venv/`는 3.14 + 타 PC 경로로 사용 불가)

---

## 9. 미결 사항

| # | 항목 | 결정 필요 시점 |
|---|---|---|
| **0** | **TensorFlow 설치 후 모델 적재 검증** | **최우선. 나머지 견적의 전제** |
| 1 | DQN(배분용)을 1차 범위에 포함할 것인가 | 2단계 개발계획서 작성 전 |
| 2 | DQN 상태에서 `is_emergency` 차원 처리 방식 | DQN 재학습 시 |
| 3 | 정책별 내재적 신뢰도 산출식 확정 | ② 구현 전 |
| 4 | 경험적 신뢰도 갱신식 (지수이동평균 등) | ⑤ 구현 전 |
| 5 | 신규 오케스트레이터의 LLM 선택 및 호출 비용 | 2단계 |
| 6 | 문헌 조사 — 유사 연구 확인 | 3단계 교수님 컨펌 전 |
| 7 | `Dashboard API`를 일정 6단계 웹화면으로 재활용할지 | 6단계 |
| 8 | **도구 설명 수위** — 최소판 / 조언판 (§3 ② 주의 참조) | 각 서버 구현 전 |
| 9 | 에이전트 프롬프트에 넣을 배경 지식 범위 | 오케스트레이터 구현 전 |

문헌 조사 키워드: `zero-touch network management`, `autonomous network levels`, `LLM agent network operations`, `intent-based networking`, `human-on-the-loop network`

---

## 부록 A: 개입 지점 → 담당 매핑

```
[사람이 하던 일]                    [담당]

"지금 비상이다"          ────────▶  에이전트 (① 원시 지표만 받아 추론)
어떤 알고리즘을 쓸까      ────────▶  에이전트 (② 카탈로그 + ⑤ 누적 성적)
임계값 얼마로 할까        ────────▶  에이전트 (② 상황별 적응)
벤더에서 사올까          ────────▶  에이전트 (③ 조건부 자동 조달)
왜 이렇게 됐지           ────────▶  ④ 기록·근거 자동 축적
지금 사람을 불러야 하나   ────────▶  에이전트 (신뢰도 기반 자체 판단)
이번 실패에서 뭘 배우지   ────────▶  ⑤ 정책 신뢰도 · ③ 벤더 레이팅 갱신
```

---

## 부록 B: 원 설계도 대조

`5g_network_slice_marketplace_architecture.svg` (680×720)의 컴포넌트와 본 설계의 대응 관계.

| 원 설계 컴포넌트 | 본 설계 | 비고 |
|---|---|---|
| Customer API | — | 신규 오케스트레이터가 대체 |
| Vendor API | ③ | 등록 기능은 범위 밖 |
| Slice Selection Engine | ③ | 점수화 로직 그대로 |
| Vendor Registry | ③ | 데이터 그대로 |
| AI Agent (DQN 분류 + LSTM) | ② | **"DQN"은 실제로 softmax 분류기** (§5 정정 A) |
| AI Agent (Ollama → Rule 폴백) | 에이전트 | **폴백 체인 → 조정자로 승격** |
| Network Digital Twin | ① | 역할 중복. ①로 통합 |
| Compliance Monitor (30s) | ① + ⑤ | 탐지는 ①의 `violations`, 학습 연결은 ⑤ |
| Feedback Loop | ⑤ | **자율성 핵심으로 확장** |
| Dashboard API | 범위 밖 | 일정 6단계 웹화면에서 재검토 |
