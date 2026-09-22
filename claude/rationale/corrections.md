<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 정정 A~K — 코드 대조 검증

기존 코드가 설계 전제와 어긋나는 것 11건

# 1. 코드 대조 검증 — 정정 사항

분리 설계서 §5의 정정 A·B·C에 이어지는 번호를 쓴다.

# 정정 D — ④의 `get_metrics()`가 에이전트에게 정답을 누출한다 ⚠️ 최우선

분리 설계서 ①은 `is_emergency`를 **노출하지 않는다**고 못 박았다. 그런데 ④의 `get_metrics()` 반환값에 다음 두 필드가 있다.

```python
"perception_accuracy": float,      # 정답 대비 적중/오탐/미탐
"escalation_precision": float,     # 사후 판정
```

두 지표 모두 **정답 없이는 계산할 수 없다.** ④가 이걸 계산하려면 ④가 정답을 읽어야 하고, ④의 반환값은 MCP 도구 결과로 **에이전트 컨텍스트에 그대로 들어간다.**

```
에이전트: get_metrics() 호출
       → "perception_accuracy: 0.62" 수신
       → "내가 지금까지 상황 판단을 자주 틀렸구나"
       → 이후 판단을 보정
       → 정답이 우회 경로로 에이전트에 도달함
```

①에서 막은 것을 ④가 열어주는 구조다. 심사에서 지적당하면 실험 전체가 무효가 된다.

**해소안 — 지표를 두 계층으로 분리한다.**

| 계층 | 산출 주체 | 지표 | 에이전트 접근 |
|---|---|---|---|
| **관측 가능 지표** | ④ `get_metrics()` | `steps`, `interventions`, `autonomous_rate`, `sla_violations`, `mean_utilization`, `policy_usage`, `mttr` | 허용 |
| **정답 의존 지표** | `eval/score.py` (오프라인) | `perception_accuracy`, `escalation_precision` | **차단** |

`mttr`(복구 시간)은 이용률이 임계값을 벗어난 구간 길이로 정의되므로 관측 가능하다. 정답이 필요 없다.

정답은 ①이 매 스텝 `runs/{run_id}/truth.jsonl`에 append 하고, **어떤 MCP 도구도 이 파일을 읽지 않는다.** 실험 종료 후 `eval/score.py`가 `truth.jsonl`과 `decisions.json`을 `step` 키로 조인해 정답 의존 지표를 계산한다.

---

# 정정 E — `rule_based`는 "수정 없음"이 아니다. 정답을 직접 읽는다

분리 설계서 §3 ②의 출처 코드 표에 `rule_based` → **수정 없음**으로 적혀 있다. 실제 코드는 다음과 같다.

```python
# ml_orchestrator_demo.py:422
def update_allocation_rule_based(self):
    if self.is_emergency:                      # ← :429
        target_allocation = np.array([0.2, 0.7, 0.1])
    elif self.is_special_event:                # ← :433
        target_allocation = np.array([0.6, 0.3, 0.1])
    elif self.is_iot_surge:                    # ← :436
        target_allocation = np.array([0.3, 0.3, 0.4])
    else:
        target_allocation = np.array([0.4, 0.4, 0.2])
    ...
```

`rule_based`는 **사람이 CLI로 넣어준 상황 판단을 입력으로 받는 함수**다. 이걸 그대로 ②에 옮기면 ②가 정답을 들고 있게 되어 정정 D와 같은 누출이 된다. ②는 무상태이므로 `self.is_emergency`를 가질 수도 없다.

**해소안 — 상황 라벨을 파라미터로 승격한다.** 이것이 오히려 본 연구의 기여를 가장 깨끗하게 보여주는 지점이다.

```python
propose_allocation(
    policy = "rule_based",
    observation = {...},
    situation = "emergency" | "special_event" | "iot_surge" | "normal",   # ← 에이전트가 추론해 넣음
    history = None
)
```

| | 베이스라인 | 제안 기법 |
|---|---|---|
| `situation` 값의 출처 | CLI `--emergency` (사람) | 에이전트 추론 |
| 호출되는 함수 | `update_allocation_rule_based()` | **동일** |
| 배분 로직 | **동일** | **동일** |

**정확히 한 변수만 바뀐다.** 로직이 같으므로 성능 차이는 전부 "상황 인지가 맞았는가"에서 나온다. 비교군 1(상황 인지만 에이전트)이 통제 실험으로 성립한다.

`situation` 파라미터는 필수로 둔다. 기본값을 `"normal"`로 주면 에이전트가 생략했을 때 조용히 평시로 처리되어 미탐이 측정에서 사라진다.

---

# 정정 F — 시뮬레이터가 벽시계를 읽는다. 재현이 불가능하다

```python
# ml_orchestrator_demo.py:297  (generate_traffic)
hour_of_day = datetime.now().hour / 24.0
day_of_week = datetime.now().weekday() / 6.0

# ml_orchestrator_demo.py:500  (create_feature_vector)
hour_of_day = datetime.now().hour / 24.0
```

세 가지 문제가 동시에 발생한다.

1. **재현 불가** — 같은 시나리오를 오후 2시와 새벽 3시에 돌리면 트래픽이 다르다. 비교군 4개를 각각 다른 시각에 돌리면 공정한 비교가 아니다.
2. **관측의 `context.hour_of_day`가 가짜** — 에이전트는 "지금 새벽이니 트래픽이 낮을 것"이라 추론하는데, 100스텝을 1초에 돌리면 시간은 사실상 멈춰 있다.
3. **`reset(seed=)` 무력화** — `np.random.normal`(`:310`, `:512`)이 전역 RNG를 쓴다. 시드를 고정해도 벽시계 항이 남는다.

**해소안 — ①에 가상 시계와 전용 RNG를 넣는다.**

```python
class SliceEnv:
    def __init__(self, seed=0, minutes_per_step=15, start_hour=8):
        self.rng = np.random.default_rng(seed)       # 전역 RNG 사용 금지
        self.step_idx = 0
        self._mps, self._h0 = minutes_per_step, start_hour

    @property
    def sim_time(self):
        total_min = self._h0 * 60 + self.step_idx * self._mps
        return {"hour_of_day": (total_min // 60) % 24,
                "day_of_week": (total_min // 1440) % 7}
```

`datetime.now()` 3곳과 `np.random` 2곳을 위 두 개로 치환한다. **수정량 5줄, 효과는 실험 재현성 전체.**

`minutes_per_step=15`이면 96스텝 = 하루. `mixed` 시나리오(60스텝)가 반나절 이상을 덮어 일간 주기가 관측에 실제로 나타난다.

---

# 정정 G — 벤더 데이터 모델이 두 벌이고 서로 호환되지 않는다

분리 설계서 §3 ③의 도구 시그니처는 두 모델을 섞어 쓰고 있다.

| | 모델 A | 모델 B |
|---|---|---|
| 파일 | `5G-Marketplace/data/vendors.json` | `5G-Marketplace/data/vendor_registry/*.json` |
| 구조 | 리스트 5개, `offerings`가 slice_type으로 중첩 | dict, `offering_id`로 평탄화 (6건 / 벤더 3곳) |
| 위치 필드 | `location`: `"New York, USA"` | `locations`: `["us-east", "us-west"]` |
| **`rating`** | **있음** (4.5 ~ 4.9) | **없음** |
| 가격 | `cost` | `price_per_hour` |
| 소비 함수 | `score_vendor_offering()` `engine.py:719` | `_advanced_score_offer()` `engine.py:185` |

분리 설계서의 `list_offerings(slice_type, region)`은 **모델 B**의 시그니처인데, `rating`을 반환하고 `engine.py:792`를 근거로 든다. `engine.py:792`(`vendor.get("rating", 3.0)`)는 **모델 A**만 읽는다. 모델 B에는 `rating`이 없으므로 항상 기본값 3.0으로 떨어지고, **⑤의 레이팅 갱신이 점수에 전혀 반영되지 않는다.**

**해소안 — 모델 A로 단일화하고 모델 B와 그 경로를 버린다.**

- ③은 `score_vendor_offering(vendor, slice_type, qos)`만 쓴다. 모델 A의 shape와 정확히 일치하고 `rating`을 읽는다.
- 부트스트랩 시 모델 A를 `data/vendors.json`으로 복사하면서 `regions` 필드만 추가한다(벤더 5곳 × 1줄).
- `query_vendors()` / `find_matching_offerings()` / `_advanced_score_offer()`는 **사용하지 않는다.**

부수 효과: 분리 설계서가 지적한 `engine.py:115`의 `await` 누락(→ `query_vendors()`가 항상 `[]` 반환)이 **고칠 필요 없이 사라진다.** 해당 경로를 안 쓰기 때문이다. ③의 작업량이 한 단계 더 내려간다.

---

# 정정 H — ②의 LSTM 경로에 조용한 폴백이 박혀 있다

```python
# ml_orchestrator_demo.py:341  update_allocation_ml
    try:
        if len(self.feature_history) >= self.sequence_length:
            ...
        else:
            logger.info("Not enough history...")
            return self.update_allocation_rule_based()      # ← :414 조용한 폴백
    except Exception as e:
        logger.error(f"Error in ML allocation: {e}")
        return self.update_allocation_rule_based()          # ← :419 조용한 폴백
```

분리 설계서 §1의 개입 지점 5번이 *"이상 시 원인 분석 — 조용한 폴백으로 로그 수동 추적"*이다. **이 코드가 바로 그 조용한 폴백이다.**

이 상태로 ②에 이식하면 `propose_allocation(policy="lstm_forecast")`가 **실제로는 rule_based 결과를 반환하면서 `"policy": "lstm_forecast"`라고 답한다.** ④의 `policy_usage` 집계가 통째로 거짓이 되고, ⑤의 정책 신뢰도는 lstm의 성적으로 rule의 성적을 기록한다. 자기 개선 루프가 잘못된 대상을 학습한다.

**해소안 — ②는 폴백하지 않는다. 실패를 실패로 반환한다.**

```python
propose_allocation(policy="lstm_forecast", ...) -> {
    "policy": "lstm_forecast",
    "allocation": None,
    "confidence": 0.0,
    "status": "unavailable",
    "reason": "history_insufficient: 4 < 10"
}
```

폴백 여부는 **에이전트가 결정한다.** 그것이 곧 "정책 선택"이고, 이 연구의 주제다. 대체 정책을 고르는 것 자체가 ④에 별도 결정으로 기록되어야 한다.

---

# 정정 I — TensorFlow가 의존성에 아예 없고, 모델은 SavedModel 형식이다

```
requirements.txt  →  tensorflow 항목 없음  (numpy, torch, fastapi, ... 만 존재)
현재 환경         →  Python 3.12.0 / tensorflow 미설치
```

그런데 `lstm_predictor.py:20`과 `dqn_classifier.py:15`는 `from tensorflow.keras.models import load_model`을 최상단에서 import 한다. **분리 설계서 §7의 0단계가 실패하면 ②의 절반이 날아간다.** 이건 단순 설치 문제가 아니라 형식 문제도 겸한다.

| 모델 | 경로 | 형식 |
|---|---|---|
| `SliceAllocationPredictor` | `5G-Network-Slicing/models/lstm_model_20250601_011235/` | **SavedModel** (`saved_model.pb` + `variables/`) |
| `TrafficClassifier` | `5G-Network-Slicing/models/dqn_model_20250601_012010/` | **SavedModel** |
| `AutoregressiveLSTMPredictor` | `5G-Network-Slicing/models/enhanced_lstm/` | `.h5` |
| 단일 LSTM | `models/lstm_single/best_model.h5` | `.h5` (+ `X_scaler.npy`) |

**핵심 위험**: TF 2.16부터 Keras 3가 기본이 되며, **Keras 3의 `load_model()`은 SavedModel 디렉터리를 직접 적재하지 못한다.** `TFSMLayer`로 감싸거나 `tf.saved_model.load()`를 써야 하고, 후자는 `.predict()` 인터페이스를 주지 않는다. 즉 `pip install tensorflow`만 하면 **최신 버전이 깔려서 두 모델 다 실패한다.**

**해소안 — 버전을 고정한다.**

```
Python 3.10  +  tensorflow==2.15.1        # Keras 2. load_model()이 SavedModel을 그대로 읽음
```

분리 설계서 §8의 "Python 3.10"은 맞다. 여기에 **TF 버전 상한이 빠져 있었다.** `tensorflow>=2.x`로 적으면 0단계에서 바로 막힌다.

**추가 미확인 항목 — 스케일러**: `lstm_model_20250601_011235/`에는 스케일러 파일이 없다(`models/lstm_single/`에만 `X_scaler.npy` 존재). 학습 시 정규화를 했는지, 했다면 어떤 스케일인지 불명이다. 0단계 검증 스크립트가 **적재 성공만이 아니라 출력이 그럴듯한지(합 ≈ 1, 각 항 0~1)까지** 확인해야 한다. 적재는 되는데 출력이 `[-3.2, 8.1, 0.4]` 같은 값이면 스케일러가 필요하다는 뜻이고, 없으면 재학습이다.

---

# 정정 J — `explain_score`와 `score_offerings`의 총점이 어긋난다

도구 명세(`TOOLS.md`) 작성 중 두 함수를 실행해 확인했다. **같은 벤더 · 같은 QoS인데 결과가 다르다.**

| 함수 | 결과 |
|---|---|
| `score_vendor_offering()` `:719` | **99.20** |
| `get_score_breakdown()` `:819` | **92.00** |

레이팅을 읽는 키가 서로 다르기 때문이다.

```python
# engine.py:792   (score_offerings 경로)
reputation_score = vendor.get("rating", 3.0) / 5.0            # 4.8 / 5.0 = 0.96

# engine.py:891   (get_score_breakdown 내부)
reputation_score = offer.get("reputation_score", 3.0) / 5.0   # 키 없음 → 3.0 / 5.0 = 0.60
```

`vendors.json`에는 `rating`만 있고 `reputation_score`는 없다. URLLC의 평판 가중치 0.2 × (4.8−3.0)/5 × 100 = **7.2점** — 관측된 차이와 정확히 일치한다.

그대로 노출하면 에이전트가 **모순된 두 숫자**를 받고, 근거 기록(④)에도 잘못된 값이 남는다.

→ `explain_score`는 `score_vendor_offering`의 계산을 분해해 새로 구현한다(약 30줄). `get_score_breakdown()`을 호출하지 않는다. 반환값의 `neural_network` 키(601바이트, UI용 장식)도 버린다.

# 정정 K — 조달이 환경에 아무 영향을 주지 못한다

원 모델은 `utilization = traffic / allocation`이고 `allocation`은 **비율**이라 합이 항상 1.0이다. 코드에 `capacity` / `total_resource` 계열 변수가 하나도 없다(확인함). 따라서 `procure()`를 호출해도 분모가 커지지 않는다.

- 조달해도 이용률이 안 내려간다 → SLA가 개선되지 않는다
- SLA 결과가 벤더와 무관하다 → `update_rating`의 δ가 **의미 없는 신호**가 된다
- ⑤ → ③ 피드백 루프 전체가 **공회전**한다

설계서 ③의 역할은 *"내부 재배분으로 부족할 때 외부에서 조달"* 인데, 재배분은 파이를 다시 자를 뿐 총량을 늘리지 못한다.

**결정 — ①에 슬라이스별 용량 배수를 도입한다.**

```
utilization[i] = traffic[i] / (allocation[i] × capacity[i])
capacity_gain  = (bandwidth / REFERENCE_BANDWIDTH[slice_type]) × GAIN_SCALE
```

| 상수 | 값 | 근거 |
|---|---|---|
| `REFERENCE_BANDWIDTH` | `{eMBB: 1100, URLLC: 500, mMTC: 120}` | `vendors.json` 슬라이스별 **중앙값 실측** |
| `GAIN_SCALE` | `0.25` | 조달 1회 = 압력 20% 감소, 완전 해소는 불가 |
| `CAPACITY_BASE` | `1.6` | 기본 용량. §1.7 |
| `CAPACITY_MAX` | `2.6` | 슬라이스당 상한. §1.7 |

파생 지표 `demand_pressure = Σᵢ traffic / (θ × capacity)`를 `Observation`에 노출한다. **1.0을 넘으면 어떤 배분으로도 전 슬라이스 SLA를 지킬 수 없다** — 재배분과 조달의 경계를 가르는 유일한 근거이며, 이게 없으면 에이전트는 모든 값이 비율이라 **얼마나 부족한지 절대량을 알 수 없다.**

상세는 `TOOLS.md` §2.1 · §2.6 · §4.5.

# 정정 요약

| # | 내용 | 영향 | 조치 시점 |
|---|---|---|---|
| **D** | ④ `get_metrics()`가 정답 누출 | **실험 유효성** | ④ 구현 전 (필수) |
| **E** | `rule_based`가 상황 플래그를 직접 읽음 | 통제 실험 성립 여부 | ② 구현 전 (필수) |
| **F** | 벽시계·전역 RNG 사용 | 재현성 | ① 구현 시 |
| **G** | 벤더 데이터 모델 두 벌 | ⑤→③ 피드백 단절 | ③ 구현 전 |
| **H** | ②의 조용한 폴백 | ④⑤ 집계 오염 | ② 구현 시 |
| **I** | TF 미설치 + SavedModel 형식 | 0단계 성패 | **최우선** |
| **J** | `explain_score` 총점 7.2점 불일치 | 에이전트가 모순된 값 수신 | ③ 구현 시 |
| **K** | 조달이 환경에 영향 없음 | **③⑤ 피드백 루프 공회전** | ① 구현 전 (필수) |

D · E · K는 **논문 주장의 근거를 직접 무너뜨린다.** 나머지는 고치지 않으면 결과가 지저분해지는 수준이다.

---

---

## 부록 — 1단계 분리 설계서 대비 변경점

원본은 `origin/decomposition.md`.

| 분리 설계서 | 이 문서 | 사유 |
|---|---|---|
| ④ `get_metrics()`에 `perception_accuracy` 포함 | **제외.** `eval/score.py`로 이관 | 정답 누출 (정정 D) |
| `propose_allocation(policy, observation, history)` | **`situation` 인자 추가 (필수)** | `rule_based`가 상황 플래그 의존 (정정 E) |
| ① `get_observation()`에 `context` | **`sim_time`.** 가상 시계 기반 | 벽시계 사용 (정정 F) |
| ③ `list_offerings(..., region)` + `rating` | **모델 A 단일화.** registry 경로 폐기 | 두 모델 비호환 (정정 G) |
| ② 실패 시 동작 미정 | **`status` 필드. 폴백 금지** | 조용한 폴백 (정정 H) |
| §8 "Python 3.10" | **+ `tensorflow==2.15.1` 고정** | SavedModel × Keras 3 (정정 I) |
| `procure(duration_hours)` | **`duration_steps`** | 가상 시계와 단위 통일 |
| 평활·클립이 정책 내부 | **①의 `apply_allocation()`으로 이관** | 정책 비교 공정성 (§3.2) |
| `engine.py:115` `await` 수정 필요 | **수정 불필요** | 해당 경로 미사용 (정정 G) |
| `lstm_forecast` 작업량 小~中 | **0단계 3번 결과에 종속** | 스케일러 부재 (정정 I) |
