<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 3인 역할 분담

저장소 `DBAJK/SRM-main-mcp` · 브랜치 `feature/kim` · `feature/lee` · `feature/choi`

> `MCP-decomposition.md`(1단계) · `MCP-design.md`(2단계)를 3명이 병렬로 개발하기 위한 작업 분해.
> 저장소: `DBAJK/SRM-main-mcp` · 브랜치 `feature/kim` · `feature/lee` · `feature/choi`

| | 담당 | 범위 | 성격 |
|---|---|---|---|
| **A** | 환경·측정 | ① observe · ④ audit · 실험 하네스 | 기존 코드 해체 + 지표 산출 |
| **B** | 모델·정책 | ② policy · ⑤ feedback · ③ market | ML 적재 + 정책 래핑 |
| **C** | 에이전트 | 오케스트레이터 · 프롬프트 · 도구 호출 루프 | 논문의 주인공 |

---

## 0. 병렬 개발의 전제

3명이 동시에 손대면 **반드시 두 곳에서 막힙니다.**

1. **A의 `Observation` 스키마를 B와 C가 동시에 소비한다.** 이게 안 얼면 아무도 시작할 수 없습니다.
2. **C는 ①~⑤가 다 있어야 루프를 돌릴 수 있다.** 순진하게 짜면 C는 마지막 주까지 대기합니다.

두 문제를 **Day 0 계약 동결**과 **C가 만드는 목 서버**로 풉니다. §1과 §6이 이 문서의 핵심입니다.

---

## 1. Day 0 — 3명이 같이 앉아 끝낼 것 (반나절)

이걸 안 하고 흩어지면 3일 뒤에 합쳤을 때 아무것도 안 맞습니다.

### 1.1 저장소 정리 — 지금 당장 ⚠️

현재 저장소에 병렬 개발을 방해하는 것이 둘 있습니다. 확인한 내용입니다.

**(1) `.gitignore`가 UTF-16으로 저장되어 있어 규칙이 먹지 않습니다.**

```
$ file .gitignore
.gitignore: Unicode text, UTF-16, little-endian text, with CRLF
```

Git은 `.gitignore`를 바이트로 읽습니다. UTF-16이면 모든 ASCII 문자 뒤에 `\x00`이 붙어 패턴이 깨집니다. 실제로 `venv/`가 무시되는 건 pip이 만든 `venv/.gitignore` 덕분이지 루트 규칙 때문이 아닙니다.

**3명이 각자 실행하면 `data/*.json`, `results/`, `.venv310/`이 전부 커밋 대상으로 잡혀 매 병합마다 충돌합니다.** UTF-8로 다시 저장하고 런타임 산출물을 추가하세요.

```bash
# UTF-8(BOM 없음)로 재작성
printf '%s\n' '__pycache__/' '*.pyc' '*.egg-info/' 'venv/' '.venv*/' 'logs/' '*.env' \
  'results/' 'runs/' 'data/decisions.json' 'data/reliability.json' \
  'SRM-main-mcp/' > .gitignore
```

> `models/`와 `*.h5`는 **넣지 마세요.** 이미 추적 중이라 ignore 규칙이 적용되지 않고, 규칙만 보고 "가중치가 없구나" 오해하게 됩니다. 확인 결과 **가중치는 실물입니다** (LFS 스텁 아님, `variables.data-00000-of-00001` = 1.5 MB). B가 clone만 하면 바로 씁니다.

**(2) 저장소 안에 저장소가 클론되어 있습니다.**

```
srm-main_mcp/
└── SRM-main-mcp/     ← 중첩 클론. git status에 ?? 로 뜸
    ├── .git
    └── README.md
```

지우거나 밖으로 옮기세요. 그대로 두면 누군가 `git add .` 할 때 들어갑니다.

**(3) 작업 기준 디렉터리 하나로 고정.** `D:\pj\SRM-main\SRM-main`은 옛 사본입니다. 3명 모두 `srm-main_mcp/`만 씁니다.

### 1.2 계약 동결 — `mcp/common/`

**A가 작성하고, 3명이 같이 읽고, 그 자리에서 확정합니다.** 이후 변경은 PR + 3명 합의.

```
mcp/common/
├── schema.py      # Observation, Decision, PolicyProposal, Outcome  (pydantic)
├── const.py       # 하드코딩 상수 전부
└── store.py       # 원자적 JSON 읽기/쓰기
```

**`const.py`에 들어갈 값** — 흩어지면 3명이 각자 다른 값을 쓰게 됩니다.

| 상수 | 값 | 출처 |
|---|---|---|
| `THRESHOLDS` | `{"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}` | `ml_orchestrator_demo.py:174` |
| `INIT_ALLOCATION` | `{"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}` | `:171` |
| `STABILITY_FACTOR` | `0.7` | `:458` |
| `ALLOC_CLIP` | `(0.1, 0.8)` | `:461` |
| `MINUTES_PER_STEP` | `15` | 신규 (정정 F) |
| `START_HOUR` | **`0`** | 신규. §1.7에서 8 → 0으로 재조정 |
| `SEQUENCE_LENGTH` | `10` | `:190` |
| `TAU` (에스컬레이션 문턱) | `0.45` | 설계서 §6.2 |
| `EMA_ALPHA` | `0.2` | §6.2 |
| `SHRINK_R0`, `SHRINK_M` | `0.5`, `5` | §6.2 |
| `RATING_DELTA` | `(+0.05, -0.20)` | §4 ③ |
| `FEATURE_COLUMNS` | 11개 문자열 리스트 | `:513~526` |
| `CAPACITY_BASE` | **`1.6`** | 신규. 평시 여유 확보 (§1.7) |
| `CAPACITY_MAX` | **`2.6`** | 기본 + 조달 4회분 (§1.7) |
| `REFERENCE_BANDWIDTH` | `{eMBB: 1100, URLLC: 500, mMTC: 120}` | `vendors.json` 중앙값 실측 |
| `GAIN_SCALE` | `0.25` | 신규. 튜닝 가능 |
| `COST_PER_STEP` | `cost × MINUTES_PER_STEP / 60` | 시간당 단가 → 스텝 환산 (W3) |
| `MEMORY_MODE` | `"warm"` | `cold` / `warm`. ③⑤의 실행 간 유지 여부 (W5) |
| `SCENARIO_STEPS` | `{normal:60, emergency:60, special_event:60, iot_surge:60, mixed:120}` | `test_scenarios.py:54` |

**`TAU`는 실험 전에 확정하고 이후 절대 건드리지 않습니다.** 조정하면 개입 횟수를 원하는 값으로 만들 수 있어 결과가 무의미해집니다.

### 1.3 파일 소유권 — 충돌 방지

**한 파일은 한 사람만 수정합니다.** 3인 병합 충돌의 90%가 여기서 예방됩니다.

| 경로 | 소유 | 비고 |
|---|---|---|
| `mcp/common/` | **A** | Day 0 이후 변경은 3인 합의 |
| `mcp/observe/`, `mcp/audit/` | A | |
| `eval/`, `fixtures/`, `tools/record_fixtures.py` | A | |
| `mcp/policy/`, `mcp/market/`, `mcp/feedback/` | **B** | |
| `tools/step0_verify_models.py`, `tools/bootstrap_vendors.py` | B | |
| `mcp/mock/` | **C** | 계약의 실행 가능 명세 (§6) |
| `orchestrator/` | C | |
| `docs/` | 공용 | 섹션 단위로 나눠 쓰기 |
| 기존 코드 (`ml_orchestrator_demo.py` 등) | **아무도 수정 안 함** | 읽기 전용. 로직은 복사해 가져감 |

마지막 줄이 중요합니다. 기존 파일을 고치면 3명이 같은 995줄 파일을 건드리게 됩니다. `mcp/`는 **추출(copy-and-adapt)** 이지 import가 아닙니다.

### 1.4 브랜치 규칙

```
main                 ← 통합. 직접 커밋 금지
├── feature/kim      ← A
├── feature/lee      ← B
└── feature/choi     ← C
```

- 합류 지점(§7)마다 `main`으로 PR. 그 사이에는 각자 브랜치에서 자유롭게.
- `main`이 깨지면 3명이 동시에 막히므로, **PR 머지 전 최소 조건은 "내 서버가 단독 기동되고 도구 목록이 나온다"** 하나입니다. 테스트 통과까지 요구하면 초반에 진도가 안 나갑니다.

---

## 2. A — 환경 · 측정

**한 줄 요약**: 995줄짜리 데모를 관측 가능한 시뮬레이터로 해체하고, 논문의 숫자를 생산한다.

### 2.1 작업 목록

#### A-1. `mcp/common/` 작성 (Day 0, 최우선)

§1.2. **B와 C가 여기서 막혀 있습니다.** 다른 무엇보다 먼저 끝내고 공유하세요.

#### A-2. `mcp/observe/env.py` — 시뮬레이터 추출

`ml_orchestrator_demo.py`에서 가져올 것:

| 대상 | 원본 | 조치 |
|---|---|---|
| `generate_traffic()` | `:286` | `datetime.now()` → `sim_time`, `np.random` → `self.rng` |
| `update_utilization()` | `:467` | 그대로 |
| `create_feature_vector()` | `:490` | 동일 치환 |
| `__init__` 상태 | `:162` | `output_dir` 생성 · `predictor` 적재 **제거** |
| `run()` 루프 | `:840` | **폐기** → `step()` |
| `visualize_*` | `:643`, `:786` | **폐기** (142줄) |
| 5번째 스텝 벤더 특수처리 | `:580~` | **폐기** |

**핵심 작업 1 — 슬라이스별 용량 배수** (정정 K). 조달이 환경에 반영되게 하는 유일한 장치입니다.

```python
self.capacity = {"embb": 1.6, "urllc": 1.6, "mmtc": 1.6}   # CAPACITY_BASE
self.leases   = []      # [{slice_id, slice_type, amount, expires_at_step}]

# 이용률 계산이 바뀝니다
utilization[i] = traffic[i] / (allocation[i] * capacity[i])

# 파생 지표 — Observation에 노출
demand_pressure = sum(traffic[i] / (thresholds[i] * capacity[i]) for i in slices)
```

`step()`에서 **트래픽 생성보다 먼저** 만료 리스를 회수합니다. 순서가 바뀌면 이미 만료된 용량으로 이용률이 계산되어 한 스텝씩 유리해집니다. 도구 `add_capacity()`가 하나 늘어납니다 (`TOOLS.md` §2.6).

**핵심 작업 2 — 가상 시계와 전용 RNG** (정정 F). `datetime.now()` 3곳, 전역 `np.random` 2곳을 치환합니다.

```python
class SliceEnv:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)     # 전역 RNG 사용 금지
        self.step_idx = 0

    @property
    def sim_time(self):
        m = START_HOUR * 60 + self.step_idx * MINUTES_PER_STEP
        return {"hour_of_day": (m // 60) % 24,
                "day_of_week": (m // 1440) % 7,
                "is_weekend": ((m // 1440) % 7) >= 5}
```

수정량은 5줄이지만 **이게 안 되면 실험 전체가 재현 불가**입니다.

#### A-3. `mcp/observe/server.py` — ① 도구 6개

```python
get_observation() -> Observation
step(n: int = 1) -> {"steps_advanced": int, "observation": Observation}
apply_allocation(embb: float, urllc: float, mmtc: float) -> ApplyResult
get_history(n: int = 10) -> {"features": [[float × 11], ...], "columns": [str × 11]}
add_capacity(slice_type: str, amount: float, expires_at_step: int, slice_id: str) -> CapacityState
reset(run_id: str, scenario: str = "normal", seed: int = 0) -> {"observation": Observation}
```

**세 가지 반드시 지킬 것**

1. **`is_emergency` / `is_special_event` / `is_iot_surge`를 어떤 반환값에도 넣지 않습니다.** 연구의 근간입니다.
2. **numpy 금지.** 경계에서 `float()` / `bool()` 변환. `violations`는 `np.bool_`이라 그대로 두면 JSON 직렬화가 터집니다 (확인함).
3. **`apply_allocation()`이 액추에이터입니다.** 평활(0.7) · 클립(0.1~0.8) · 정규화를 여기서 합니다. 정책 쪽에는 두지 않습니다.

#### A-3.5. 실행 경로 분리 (W5) ⚠️

**`reset()`은 ①만 초기화합니다.** ②③④⑤의 상태는 남습니다. 그런데 산출물 경로가 단일 파일이라 **60회 실행이 서로 덮어씁니다.**

```
data/                     ← 실행에 걸쳐 유지
  vendors.json            ③ 소유. 레이팅 누적
  reliability.json        ⑤. warm 모드에서만

runs/{run_id}/            ← 실행마다 새로
  decisions.json          ④ 생성 · ⑤ 추가기입
  truth.jsonl             ① 기록. 도구 미노출
  reliability.json        ⑤. cold 모드에서만
  context/                C의 누출 검사 덤프
```

④는 별도 초기화 도구가 필요 없습니다 — 첫 `record_decision`이 `runs/{run_id}/decisions.json`을 만듭니다. `run_id`는 C가 발급해 `reset()`과 ④에 **같은 값**을 넘깁니다. 상세는 설계서 §5.0.

#### A-4. 정답 기록 — `runs/{run_id}/truth.jsonl`

`step()` 내부에서 매 스텝 append. `@mcp.tool()` 데코레이터를 붙이지 않는 것만으로 누출 차단이 증명됩니다.

```json
{"run_id": "exp-proposed-emergency-s0", "step": 12, "is_emergency": true, "is_special_event": false, "is_iot_surge": false}
```

#### A-5. `mcp/audit/` — ④

```python
record_decision(step, observation, situation, chosen_policy, allocation, confidence, rationale) -> {"decision_id"}
record_escalation(step, observation, situation, reason, confidence)
    -> {"escalation_id", "decision_id", "fallback_policy", "fallback_allocation"}
get_decisions(n=50) -> [Decision]
get_metrics(window=None) -> {...}
```

**V2 — `record_escalation`이 `decision_id`도 함께 발급합니다.** 에스컬레이션한 스텝도 배분은 적용되고 SLA 결과가 나옵니다. `escalation_id`만 주면 `report_outcome`을 호출할 수 없어 **그 스텝이 통계에서 소멸**하고, 비교군마다 표본이 달라집니다. 두 레코드를 한 호출에서 남겨 빠뜨릴 여지를 없애세요.

**V6 — `sla_violations`는 `outcome.sla_met`에서 셉니다.** `record_decision`이 받는 `observation`은 `obs_t`이고 그 `violations`는 `a_{t-1}`의 결과입니다. 이걸로 세면 지표가 **1스텝 어긋나고**, 아무 결정의 책임도 아닌 `step 0`이 한 건 섞입니다.

**V7 · V8 — `record_decision`에 판단 흔적 세 개를 더 받습니다.**

| 필드 | 없으면 답할 수 없는 질문 |
|---|---|
| `in_distribution` | *"DQN은 분포 밖에서 신뢰도가 떨어지며 에이전트가 이를 감지해 전환한다"* — 사실인가 |
| `demand_class` | 분류기가 틀린 건가, 에이전트가 분류기를 무시한 건가 |
| `vendor_id` | ⑤가 `update_rating` 중계용 `vendor_id`를 되찾을 수 없음 (W4) |
| `considered` | 에이전트가 왜 이 정책을 골랐나 (탈락 후보는 뭐였나) |

첫 줄은 설계서 §5가 **논문 내용으로 제시한 문장**입니다. 기록하지 않으면 주장은 하되 검증은 못 합니다.

**V10 — 집계 수가 1 차이나는 것은 정상입니다.** 버그로 오해하지 마세요.

```
decisions.json의 결정 수            = 60      (에피소드 60스텝)
그중 outcome 필드가 있는 레코드 수  = 59      (마지막 결정은 채점 불가)
```

**검증은 이 두 숫자로 하세요.** ⑤의 `n`과 비교하면 안 됩니다 — `warm` 모드에서 `n`은 에피소드를 넘어 누적되므로 실행마다 달라집니다. 차이가 2 이상이면 ②의 조용한 폴백이나 `report_outcome` 누락을 의심합니다.

**`get_metrics()`에 `perception_accuracy` · `escalation_precision`을 넣지 마세요** (정정 D). 정답 없이 계산 불가한 지표이고, ④의 반환값은 에이전트 컨텍스트에 그대로 들어갑니다. `eval/score.py`가 오프라인으로 담당합니다.

`get_metrics()`가 돌려줄 것 — 전부 관측만으로 계산됩니다:
`steps`, `interventions`, `autonomous_rate`, `sla_violations`, `mean_utilization`, `policy_usage`, `mttr`, `unresolved`

`mttr`: 위반이 하나라도 `true`인 첫 스텝 → 전부 `false`가 된 스텝까지의 길이. **복구되지 않은 채 끝난 구간은 `unresolved`로 따로 보고합니다.** 조용히 빼면 MTTR이 좋아 보입니다.

`decision_id` = `f"{run_id}-{step:04d}"`. UUID보다 낫습니다 — 정렬 가능하고 `truth.jsonl`과 `step`으로 조인됩니다.

#### A-6. 실험 하네스 — `eval/`

```
eval/
├── run_experiment.py   # 비교군 × 시나리오 × 시드 일괄 실행
├── score.py            # truth.jsonl × decisions.json 조인 → 정답 의존 지표
└── plots.py            # 대표 그래프 (x: 자율성 수준, y: 개입↓ / SLA→)
```

`score.py`가 산출할 것:

| 지표 | 계산 |
|---|---|
| `perception_accuracy` | `decisions[].situation` vs `truth[].is_*` — 적중/오탐/미탐 |
| `escalation_precision` | 에스컬레이션 시점의 정답 상황이 실제로 사람이 필요했는지 |

**V9 — 매핑 규칙을 채점 전에 못 박으세요.** 4값 열거형과 3개 bool의 대응을 나중에 정하면 유리한 쪽으로 해석할 수 있습니다.

| `truth` | 정답 `situation` |
|---|---|
| 전부 `false` | `normal` |
| `is_emergency` 만 `true` | `emergency` |
| `is_special_event` 만 `true` | `special_event` |
| `is_iot_surge` 만 `true` | `iot_surge` |
| 둘 이상 `true` | 발생하지 않음 — ①이 `truth.jsonl` 쓸 때 **assert** |

**전환 경계 제외**: 플래그가 바뀐 **그 스텝**의 결정은 판정에서 뺍니다. 에이전트는 `obs_t`를 보고 판단하는데 `obs_t`는 전환 **직전**의 트래픽을 반영하므로, 미탐으로 세면 원리적으로 맞힐 수 없는 것을 틀렸다고 세는 셈입니다. `mixed` 120스텝에서 제외 대상은 5스텝입니다.

`run_id`로 조인합니다 (V3). 없으면 60회 실행분이 섞입니다.

**실행 규모**: 비교군 4 × 시나리오 5 × 시드 3 = **60회**. `runs/{run_id}/`로 분리 저장. `config`를 `decisions.json`에 박아 산출물이 섞이지 않게 합니다.

### 2.2 산출물과 완료 판정

| # | 산출물 | 완료 판정 |
|---|---|---|
| A-1 | `mcp/common/` | B·C가 import해서 쓴다 |
| A-2~3 | ① 서버 | **동일 시드 2회 → `truth.jsonl` 바이트 단위 동일** |
| A-2 | 용량 반영 | `add_capacity(0.25)` 호출 후 해당 슬라이스 `utilization`이 하락 |
| A-2 | **환경 조율** | `normal` 60스텝 × 시드 10에서 `demand_pressure > 1.0`이 **10% 미만** (§1.7) |
| A-4 | `truth.jsonl` | `grep -r "@mcp.tool" mcp/observe/` 결과에 정답 관련 없음 |
| A-5 | ④ 서버 | `get_metrics()` 반환 키에 `perception`·`escalation_precision` 부재 |
| A-5 | 값 유실 | `record_escalation`이 `decision_id` 반환 (V2) · `sla_violations`가 `outcome.sla_met` 기반 (V6) |
| A-5 | 집계 정합 | `decisions.json`의 결정 수 − `outcome` 있는 수 = **정확히 1** (V10) |
| A-6 | 채점 기준 | 매핑 규칙·전환 경계 제외가 **코드에 고정**되어 있다 (V9) |
| A-6 | 하네스 | 60회 실행이 무인으로 완주 |

**A-2~3의 판정이 가장 중요합니다.** 재현이 안 되면 이후 모든 비교가 무의미합니다. 여기서 반드시 멈추고 확인하세요.

### 2.3 A가 넘겨줘야 하는 것 (병렬화의 열쇠)

**`fixtures/` — B와 C가 ① 없이 개발할 수 있게 하는 녹화본.** ①이 돌아가는 즉시, 완성 전이라도 먼저 내놓으세요.

```
fixtures/
├── obs_normal.jsonl         # 시나리오별 30스텝 관측
├── obs_emergency.jsonl
├── obs_mixed.jsonl
└── history_emergency.jsonl  # (n, 11) 피처 시퀀스 — B의 LSTM 테스트용
```

`tools/record_fixtures.py`로 생성하고 **커밋합니다** (수십 KB). B는 이걸로 `propose_allocation`을, C는 프롬프트를 ① 없이 다듬습니다.

### 2.4 A의 함정

- **`create_feature_vector()`의 컬럼 순서**(`:513~526`)를 바꾸면 B의 LSTM이 조용히 틀립니다. `FEATURE_COLUMNS`로 고정하고 `get_history()`가 `columns`를 함께 반환하세요.
- **`mixed` 시나리오는 초 단위**입니다 (`test_scenarios.py:92`, `interval=0.5`). 스텝으로 변환: 10→20, 25→50, 30→60, 45→90, 50→100. 총 **120스텝**.
- **`MLOrchestrator.__init__`이 `results/` 폴더를 만듭니다**(`:196`). 서버 기동마다 폴더가 생기므로 제거하세요.

---

## 3. B — 모델 · 정책

**한 줄 요약**: TensorFlow를 되살리고, 정책을 나란히 세우고, 결과에서 배우게 한다.

### 3.1 작업 순서 — 0단계부터, 그 다음 ③

**0단계가 전체 프로젝트의 전제입니다** (설계서 §7). 결과에 따라 B 본인의 작업량이 中에서 大로 바뀌고, C의 프롬프트 설계도 달라집니다. **Day 1 오전에 끝내고 즉시 공유하세요.**

#### B-0. 모델 적재 검증 (Day 1 오전) ⚠️

```bash
py -3.10 -m venv .venv310
.venv310/Scripts/python -m pip install "tensorflow==2.15.1" numpy pandas fastmcp pydantic
.venv310/Scripts/python tools/step0_verify_models.py
```

**버전 고정이 핵심입니다.** TF 2.16+는 Keras 3가 기본인데, **Keras 3의 `load_model()`은 SavedModel 디렉터리를 읽지 못합니다.** 가중치가 `saved_model.pb` + `variables/` 형식이라 `pip install tensorflow`만 하면 최신이 깔려 그대로 실패합니다.

`tools/step0_verify_models.py`가 확인할 것 — **적재 성공만으로는 통과가 아닙니다:**

| # | 확인 | 실패 시 |
|---|---|---|
| 1 | `load_model("5G-Network-Slicing/models/lstm_model_20250601_011235")` | TF 버전 재확인 → `TFSMLayer` → 재학습 |
| 2 | 입력이 `(1, 10, 11)`을 받는가 | 피처 차원 재확인 |
| 3 | **출력 3차원, 합 ≈ 1, 각 항 ∈ [0,1]** | **스케일러 필요 → 재학습** |
| 4 | 동일 입력 2회 → 동일 출력 | 비결정 레이어 → 신뢰도 식 변경 |
| 5 | `dqn_model_20250601_012010` 적재 + softmax 합 ≈ 1 | `classify_demand` 제외 |
| 6 | `dqn_training_data/*.csv` 컬럼별 min/max → `mcp/policy/ranges.json` | `in_distribution` 판정 불가 |

**3번이 진짜 관문입니다.** `lstm_model_*/`에는 스케일러 파일이 없습니다 (`models/lstm_single/`에만 `X_scaler.npy` 존재). 적재는 되는데 출력이 `[-3.2, 8.1, 0.4]` 같으면 정규화 전제가 다른 것이고, 복원할 스케일러가 없으므로 재학습입니다.

**결과를 3명 모두에게 즉시 공유하세요:**

| 3번 결과 | 1차 범위 | C에 미치는 영향 |
|---|---|---|
| 통과 | `rule_based` + `lstm_forecast` | "정책 선택" 프롬프트 필요 |
| 실패 | **`rule_based` 단독** | 정책 선택 축 제거, 상황 인지 + 에스컬레이션에 집중 |

`rule_based` 단독이어도 논문은 성립합니다. 정정 E 덕분에 *"동일한 규칙 엔진에 상황 라벨만 사람 → 에이전트로 교체"* 라는 가장 깨끗한 통제 실험이 되고, 에스컬레이션은 정책 개수와 무관합니다.

#### B-1. ③ `slice-market` (Day 1 오후 ~)

**가장 먼저 완성되는 서버입니다.** 목적은 ③ 자체가 아니라 **MCP 배선이 실제로 도는지 확인**하는 것입니다. C의 목 서버를 진짜로 교체하는 첫 대상입니다 (§7 M1).

`engine.py`에서 가져올 것 → `mcp/market/scoring.py`:

| 함수 | 위치 | 조치 |
|---|---|---|
| `_calculate_criteria_weights()` | `:252` | 그대로 |
| `_score_latency/bandwidth/reliability()` | `:328~417` | 그대로 |
| `_calculate_qos_match()` | `:592` | 그대로 |
| `_calculate_price_score()` | `:628` | 그대로 |
| `score_vendor_offering()` | `:719` | `async` 제거 |
| `get_score_breakdown()` | `:819` | 3중 중복 중 이것만 |
| `query_vendors()` / `find_matching_offerings()` | `:95` / `registry.py:349` | **사용 안 함** |

**벤더 데이터가 두 벌이고 호환되지 않습니다** (정정 G).

| | 모델 A (채택) | 모델 B (폐기) |
|---|---|---|
| 파일 | `5G-Marketplace/data/vendors.json` | `5G-Marketplace/data/vendor_registry/*.json` |
| 구조 | 리스트 5개, 중첩 offerings | dict, offering_id 평탄화 (6건) |
| **`rating`** | **있음** (4.5~4.9) | **없음** |

`engine.py:792`의 점수 계산은 모델 A만 읽습니다. 모델 B를 쓰면 rating이 항상 기본값 3.0으로 떨어져 **⑤의 레이팅 갱신이 점수에 전혀 반영되지 않습니다.**

→ `tools/bootstrap_vendors.py`로 모델 A를 `data/vendors.json`에 복사하면서 `regions` 필드만 추가 (벤더 5곳 × 1줄). 부수 효과로 `engine.py:115`의 `await` 누락 버그가 **고칠 필요 없이 사라집니다** (해당 경로 미사용).

도구 5개:
```python
list_offerings(slice_type=None, region=None) -> [Offering]
score_offerings(slice_type, qos_requirements) -> [ScoredOffering]   # 점수 내림차순
explain_score(vendor_id, slice_type, qos_requirements) -> ScoreBreakdown
procure(vendor_id, slice_type, qos_requirements, duration_steps, current_step)
    -> {"slice_id", "status", "capacity_gain", "expires_at_step", "cost_total"}
update_rating(vendor_id, outcome) -> {"vendor_id", "rating", "delta"}
```

`duration_hours` → **`duration_steps`**. ①이 가상 시계를 쓰므로 단위를 섞지 않습니다.

**W2 — `current_step`을 받아야 합니다.** ③은 ①과 별개 프로세스라 시뮬레이션 시각을 모르는데 `expires_at_step = current_step + duration_steps`를 반환해야 합니다.

**W3 — 비용 단위를 환산합니다.** `cost`는 **시간당**, `duration_steps`는 스텝입니다.

```
cost_total = cost × duration_steps × (MINUTES_PER_STEP / 60) = 250 × 10 × 0.25 = 625.0
```

그냥 곱하면(2500.0) **비용이 4배 부풀어** `procurement_cost_total` 지표가 무의미해집니다.

**W4 — `vendor_id`를 반환값에 포함하세요.** ④에 기록되어야 ⑤가 결과 보고 시 되찾습니다.

#### B-2. ② `slice-policy`

```python
list_policies() -> [PolicyInfo]
propose_allocation(policy, observation, situation, history=None) -> PolicyProposal
compare_policies(observation, situation, history=None,
                 recent_errors=None) -> [PolicyProposal]    # W6: 정책별 딕셔너리
classify_demand(observation) -> {"dominant", "probabilities"}
```

**두 가지가 이 서버의 전부입니다.**

**(1) `situation`을 필수 인자로 받습니다** (정정 E). `update_allocation_rule_based()`(`:422`)는 `self.is_emergency`를 직접 읽습니다(`:429`). 이걸 그대로 옮기면 ②가 정답을 들고 있게 되고, ②는 무상태라 가질 수도 없습니다.

```python
# 원본 :429
if self.is_emergency:                 →   if situation == "emergency":
elif self.is_special_event:           →   elif situation == "special_event":
elif self.is_iot_surge:               →   elif situation == "iot_surge":
```

**기본값을 주지 마세요.** `"normal"`을 기본값으로 두면 에이전트가 생략했을 때 조용히 평시로 처리되어 미탐이 측정에서 사라집니다.

**(2) 폴백 금지** (정정 H). `update_allocation_ml()`(`:341`)은 실패 시 `update_allocation_rule_based()`를 조용히 호출합니다(`:414`, `:419`). 그대로 두면 `propose_allocation(policy="lstm_forecast")`가 **rule_based 결과를 반환하면서 `"policy": "lstm_forecast"`라고 답합니다.** ④의 `policy_usage`가 통째로 거짓이 되고 ⑤가 잘못된 대상을 학습합니다.

```python
{"policy": "lstm_forecast", "allocation": None, "confidence": 0.0,
 "status": "unavailable", "reason": "history_insufficient: 4 < 10"}
```

폴백 여부는 **에이전트가 결정합니다.** 그게 곧 "정책 선택"이고 이 연구의 주제입니다.

**V4 — `recent_error`를 인자로 받습니다.** `lstm_forecast`의 신뢰도 `exp(−3·ē)`에서 `ē`는 **누적 오차**인데, ②는 무상태이고 ⑤를 호출할 수 없습니다. ②가 원리적으로 알 수 없는 값을 식에 넣어 두었던 것입니다.

```
⑤.get_reliability_table() → {"lstm_forecast": {..., "recent_error": 0.112}}
                                                        │ 에이전트가 중계
                                                        ▼
②.propose_allocation(policy="lstm_forecast", ..., recent_error=0.112)
```

②는 여전히 무상태입니다 — 누적값을 들고 있는 건 ⑤이고, ②는 받은 값을 식에 넣을 뿐입니다. `recent_error`가 `null`이면 보수적 기본값 `0.5`를 쓰고 `rationale`에 그 사실을 적으세요.

> 일반 규칙: **무상태 서버의 산출식에 "최근 N회"·"누적"·"평균"이 들어가면 그 값은 반드시 인자여야 합니다.**

**신뢰도 산출식** (설계서 §6.1):

| 정책 | 식 |
|---|---|
| `rule_based` | `0.50 + 0.30 · min(1, minᵢ \|uᵢ − θᵢ\| / θᵢ)` → [0.50, 0.80] |
| `lstm_forecast` | `exp(−3 · ē) · 𝟙[in_distribution]`, `ē` = 최근 5회 `error`의 EMA |

`rule_based`의 하한 0.50은 의도적입니다. 항상 가용한 안전 기본값이므로 다른 정책이 다 실패해도 이것 하나는 τ(0.45) 위에 있습니다.

**모델 적재는 서버 기동 시 1회.** 호출마다 적재하면 스텝당 수 초가 듭니다. 적재 실패 시 서버는 죽지 않고 해당 정책만 `status="unavailable"`로 응답합니다.

**도구 설명 2벌** — `mcp/policy/descriptions.py` (설계서 §6.3):

```python
DESC = {
  "minimal":  {"lstm_forecast": "시계열 모델 기반 배분. 관측 이력 10스텝 필요."},
  "advisory": {"lstm_forecast": "시계열 예측 기반. 평시 효율 우수."},
}
MODE = os.environ.get("SLICE_DESC_MODE", "minimal")
```

MCP는 도구 설명을 LLM 컨텍스트에 그대로 넣습니다. `"평시 효율 우수"`는 사실상 *"언제 이걸 골라라"* 는 조언입니다. 주 실험은 `minimal`, `advisory`는 비교 실행.

#### B-3. ⑤ `slice-feedback`

```python
report_outcome(decision_id, observed) -> {"sla_met", "policy", "error", "vendor_id", "reliability_after"}
get_reliability_table() -> {"rule_based": {"reliability": .., "n": .., "effective": ..}}
```

**`error` 정의** (설계서 §4):
```
a*_t  = normalize(traffic_t / thresholds)      # 위반이 딱 없어지는 배분
error = L1(a_chosen, a*_t) / 2                 # [0, 1]
```
정답을 쓰지 않고 관측만으로 계산됩니다. B-2의 LSTM 신뢰도에도 재사용됩니다.

**갱신식** (§6.2):
```
r ← (1−α)·r + α·s          α = 0.2, s = sla_met
effective = (r·n + 0.5·5) / (n + 5)
```
축소 항이 없으면 첫 성공 1회로 신뢰도가 1.0이 되어 에이전트가 고착됩니다.

**V5 — 요청값과 적용값을 둘 다 기록합니다.** 호출 순서상 `record_decision`(3)이 `apply_allocation`(4)보다 먼저라, ④에는 **요청한 배분만** 남고 액추에이터가 실제 적용한 값은 어디에도 안 남습니다. 그런데 `error`는 적용값 기준입니다.

```
요청 {0.20, 0.70, 0.10} → 평활 후 적용 {0.34, 0.49, 0.17}
이상 배분 {0.426, 0.418, 0.157}

error (적용 기준) = 0.086      ← ⑤가 계산하는 값
error (요청 기준) = 0.316      ← 4배 차이
```

기준이 다르면 *"정책이 나빴나, 액추에이터가 막았나"* 를 구분할 수 없습니다. `report_outcome`이 `applied_allocation` · `requested_allocation` · `actuator_delta`를 함께 남기세요. `requested_allocation`은 `decisions.json`에서 `decision_id`로 조회합니다.

`observed_violations`도 남깁니다 — ④가 가진 건 `obs_t`뿐이라 **에피소드 마지막 관측이 유실**되고, MTTR의 마지막 구간이 잘립니다.

**V4 — `get_reliability_table()`이 `recent_error`를 함께 반환합니다.** ②의 신뢰도 공급선입니다 (위 B-2 참조).

**⑤는 `vendors.json`에 직접 쓰지 않습니다.** `vendor_id`를 결과에 실어 보내면 에이전트가 ③의 `update_rating()`을 호출합니다. `loop.py:330`의 `self.ai_agent.update_vendor_ratings()` 같은 직접 호출은 MCP에서 불가능합니다.

**에피소드 간 유지 모드 2개**를 지원하세요 — 실험 변수입니다.

| 모드 | `reliability.json` | 보이는 것 |
|---|---|---|
| `cold` | 시나리오마다 초기화 | 단일 에피소드 내 적응 |
| `warm` | 전체 실행에 걸쳐 누적 | **장기 자기 개선** (주 결과) |

### 3.2 완료 판정

| # | 판정 |
|---|---|
| B-0 | 6개 항목 통과. `ranges.json` 생성. **결과를 3명에게 공유** |
| B-1 | 에이전트가 `score_offerings` 호출 → 벤더 5개 점수 수신 |
| B-2 | **같은 관측에 `situation`만 바꾸면 배분이 달라진다.** LSTM 실패 시 `status="unavailable"` |
| B-3 | `warm` 120스텝에서 `reliability.json` 값이 실제로 움직인다 |
| B-2 | `recent_error=null`과 `=0.3`이 **다른 confidence**를 낸다 (V4) |
| B-3 | `report_outcome`이 `applied` · `requested` · `actuator_delta`를 모두 반환 (V5) |

### 3.3 B의 함정

- **`from tensorflow.keras...`가 모듈 최상단에 있습니다** (`lstm_predictor.py:20`, `dqn_classifier.py:15`). TF가 없으면 import만으로 죽습니다. ② 서버는 TF 없이도 기동되어 `rule_based`는 서빙해야 합니다 — 적재를 `try` 안에 넣고 실패를 상태로 들고 있으세요.
- **`requirements.txt`에 tensorflow가 없습니다.** 추가하되 `==2.15.1`로 고정.
- **평활·클립을 ②에 두지 마세요.** ①의 `apply_allocation()` 소관입니다. 양쪽에 다 있으면 0.7이 두 번 걸려 배분이 거의 안 움직입니다.

---

## 4. C — 에이전트

**한 줄 요약**: 논문의 주인공. 코드량은 적고 반복 튜닝이 많다.

### 4.1 작업 목록

#### C-0. 목 서버 5개 (Day 1) ⚠️ 최우선

**C는 ①~⑤가 다 있어야 루프를 돌릴 수 있습니다.** 그대로 기다리면 마지막 주까지 아무것도 못 합니다.

`mcp/mock/`에 **고정 응답만 돌려주는 5개 서버**를 Day 1에 만드세요. `mcp/common/schema.py`만 있으면 됩니다.

```python
# mcp/mock/observe.py — 30줄이면 충분
@mcp.tool()
def get_observation() -> dict:
    return {"step": 12, "sim_time": {...},
            "traffic": {"embb": 0.52, "urllc": 0.61, "mmtc": 0.19},
            "utilization": {"embb": 1.30, "urllc": 1.52, "mmtc": 0.95},
            "violations": {"embb": True, "urllc": True, "mmtc": True}, ...}
```

A의 `fixtures/`가 나오면 목이 그걸 재생하게 바꿉니다. 그러면 **실제 시나리오 전개에 대고 프롬프트를 다듬을 수 있습니다.**

> **목 서버가 계약의 실행 가능한 명세가 됩니다.** A·B가 진짜 서버를 완성한 뒤 목과 응답 형식이 다르면 그게 계약 위반입니다. 3인 병렬 개발에서 스키마 불일치를 잡는 가장 값싼 장치입니다.

#### C-1. 오케스트레이터 루프 — `orchestrator/run.py`

설계서 §3.1의 순서를 그대로 구현합니다. **순서가 곧 지표의 정의입니다.**

```
1.  obs_t   = ①.get_observation()          # util_t 는 a_{t-1}의 성적표
2.  [판단]  ②.classify_demand / propose_allocation · ⑤.get_reliability_table
3.  ④.record_decision(...) → decision_id   # 판단을 먼저 기록 (실행 전)
4.  ①.apply_allocation(a_t)
5.  ①.step()
6.  ⑤.report_outcome(decision_id, obs_{t+1})
```

**규칙 셋:**
1. **채점은 1스텝 지연됩니다.** `report_outcome`은 반드시 `step()` **이후**에.
2. **에피소드 마지막 결정은 채점 불가.** 집계에서 제외 (60스텝 → 유효 59).
3. **기록(3)이 실행(4)보다 먼저.** 실행 후 기록이면 실패 사례가 사라져 자율 처리율이 과대평가됩니다.

#### 루프는 파이썬이 돌립니다 — LLM에게 순서를 맡기지 마세요 ⚠️

**MCP는 도구를 줄 뿐 호출 순서를 강제하지 않습니다.** 스텝당 6~10회 × 120스텝 × 60회 동안 LLM은 반드시 `report_outcome`을 빠뜨리고, 순서를 뒤집고, 20~30스텝 뒤 드리프트합니다. **호출하지 않은 것은 오류를 내지 않으므로 대부분 조용히 누락됩니다.**

```python
for t in range(total_steps):
    obs = observe.get_observation()
    rel = feedback.get_reliability_table()

    j = ask_llm(obs, rel, recent)      # ← LLM은 여기서만
    #   situation · confidence.situation · policy · procure? · escalate?

    if j.procure: ...                   # 2b
    audit.record_decision(...)          # 3   ← 파이썬이 보장
    observe.apply_allocation(...)       # 4
    observe.step()                      # 5
    feedback.report_outcome(...)        # 6
```

LLM이 답할 것은 **네 가지뿐**입니다. §1.5의 *"`AGENT`가 생산자인 값은 네 개"* 와 정확히 일치합니다.

**논문에도 유리합니다.** 자율성 주장은 **판단**에 관한 것이지 도구 호출 순서가 아닙니다. 루프를 고정하면 비교군 간 차이가 전부 판단에서 나오고, *"루프를 잘못 돌아서 SLA가 나빴다"* 는 반론이 차단됩니다.

#### 컨텍스트는 스텝마다 재구성합니다

120스텝 대화를 누적하면 후반에 **100k 토큰**을 넘습니다. 대화 이력을 이어붙이지 마세요.

```
시스템 프롬프트 (고정) + 현재 관측 1건 + 신뢰도 표 + 최근 5스텝 요약(한 줄씩)
```

최근 이력은 **원본이 아니라 요약**입니다. `get_decisions(n=5)`를 그대로 넣으면 관측이 딸려와 5배가 됩니다.

**중계 책임 — 서버끼리 대화하지 않으므로 값을 옮겨 심는 건 전부 C의 일입니다.**

| 옮길 값 | 출처 | 목적지 | 빠뜨리면 |
|---|---|---|---|
| `run_id` | **C가 발급** | ①.`reset` · ④ 전체 | `truth.jsonl` 조인 불가 (V3) |
| `recent_error` | ⑤.`get_reliability_table` | ②.`propose_allocation` | LSTM 신뢰도 계산 불가 (V4) |
| `in_distribution` | ②.`propose_allocation` | ④.`record_decision` | 논문 주장 검증 불가 (V7) |
| `demand_class` | ②.`classify_demand` | ④.`record_decision` | 분류기/판단 오류 구분 불가 (V8) |
| `capacity_gain` | ③.`procure` | ①.`add_capacity` | 조달이 환경에 무반영 (정정 K) |
| `observation.step` | ①.`get_observation` | ③.`procure` (`current_step`) | 만료 시점 계산 불가 (W2) |
| `recent_errors` (전체) | ⑤.`get_reliability_table` | ②.`compare_policies` | 전 정책이 같은 오차 공유 (W6) |
| `vendor_id` | ⑤.`report_outcome` | ③.`update_rating` | 벤더 레이팅 미갱신 |

**`run_id`는 C가 만듭니다.** 형식은 `{arm}-{scenario}-s{seed}` — 예: `proposed-emergency-s0`. ①과 ④에 **같은 값**을 넘겨야 `decision_id`(`{run_id}-{step:04d}`)가 `truth.jsonl`과 `step`으로 조인됩니다.

**W1 — 조달은 `record_decision` 전, `step()` 전에 합니다.**

```
2b. [조달 분기]  obs.demand_pressure ≥ 1.0 일 때만
      ③.score_offerings → ③.procure(..., current_step=obs.step)
      ①.add_capacity(amount=capacity_gain, expires_at_step)
3.  ④.record_decision(..., slice_id, vendor_id)
4.  ①.apply_allocation
5.  ①.step()
```

`add_capacity`가 `step()` **뒤로 가면 조달한 바로 그 스텝이 효과를 못 봅니다.** 에이전트 입장에서 *"샀는데 아무 일도 안 일어났다"* 가 되어 조달 학습이 왜곡됩니다.

조달이 기록(3)보다 앞서는 것은 규칙 3("기록이 실행보다 먼저")의 **유일한 예외**입니다 — `record_decision`이 `slice_id`·`vendor_id`를 인자로 받기 때문입니다. 조달에 실패해도 `slice_id=null`과 `rationale`로 기록하세요. **시도했다는 사실 자체가 판단의 증거**입니다.

**에스컬레이션한 스텝도 루프를 끝까지 돕니다** (V2). `record_escalation`이 `decision_id`와 `fallback_allocation`을 함께 주므로, 그걸로 `apply_allocation` → `step()` → `report_outcome`을 평소대로 호출하세요. 여기서 멈추면 그 스텝이 통계에서 사라집니다.

**신뢰도 종합은 에이전트만 합니다** — 어느 서버에도 이 코드가 없습니다.
```
combined = sqrt(intrinsic × effective)
escalate if combined < TAU (0.45)
```

#### C-2. 비교군 스위치

`--arm` 하나로 4개 비교군을 만듭니다. **A의 하네스가 이걸 호출합니다.**

| `--arm` | 상황 인지 | 정책 선택 | 에스컬레이션 |
|---|---|---|---|
| `baseline` | **`truth.jsonl`에서 주입** | 고정 `rule_based` | 없음 |
| `arm1` | 에이전트 | 고정 `rule_based` | 없음 |
| `arm2` | 에이전트 | 에이전트 | 없음 |
| `proposed` | 에이전트 | 에이전트 | **신뢰도 기반** |

**`baseline`만 `truth.jsonl`을 읽습니다.** 기존 시스템(CLI `--emergency`)의 재현이므로 정당하지만, **코드 경로를 물리적으로 분리하세요.** 같은 함수에 `if arm == "baseline"`으로 두면 실수로 다른 비교군에 새어 들어갑니다.

#### C-3. 프롬프트 설계 — `orchestrator/prompts/`

**여기에 시간이 가장 많이 듭니다.** 서버 개발과 리듬이 다릅니다.

도구 설명과 **정확히 같은 문제가 프롬프트에도 있습니다** (설계서 §9-9). 시스템 프롬프트에 *"URLLC 이용률이 높으면 비상 상황일 수 있다"* 라고 적으면, 에이전트가 판단한 게 아니라 받아쓴 것이 됩니다.

```
prompts/
├── system_minimal.md     # 역할·도구 사용 규약만. 판단 기준 없음
├── system_advisory.md    # 배경 지식 포함
└── step.md               # 스텝별 사용자 메시지 템플릿
```

**주 실험은 `minimal`.** `PROMPT_HASH`를 `decisions.json`의 `config`에 기록해 사후 추적 가능하게 하세요.

**LLM은 `confidence.situation`도 함께 답해야 합니다.** `intrinsic`·`empirical`은 둘 다 *정책*에 대한 확신이라 **상황을 잘못 읽었을 가능성이 어디에도 반영되지 않습니다.**

```
combined = (situation × intrinsic × empirical)^(1/3)
escalate if combined < 0.45
```

실측상 상황 인지의 상한이 약 72%, `normal`은 51%입니다 (`TOOLS.md` §10). **오탐이 구조적으로 많다**는 뜻이므로, 이 경로가 없으면 *"무슨 일인지 모르겠다"* 는 이유로는 영영 사람을 부르지 않습니다.

#### C-4. 누출 검사 — `orchestrator/leak_check.py`

**C만 할 수 있는 일입니다.** A가 자기 코드를 아무리 봐도 못 찾습니다. 에이전트의 실제 컨텍스트를 덤프해서 금지어를 찾습니다.

```python
FORBIDDEN = ["is_emergency", "is_special_event", "is_iot_surge",
             "perception_accuracy", "escalation_precision", "ground_truth"]
```

`baseline`을 제외한 모든 실행에서 **0건이어야 합니다.** 1건이라도 나오면 그 실행은 폐기입니다.

#### C-5. 계약 검사 — `docs/contract.json` + `tools/check_contract.py`

도구 계약 검증에서 **값 유실 9건**이 나왔습니다 (설계서 §1.5). 도구는 앞으로도 늘어나고(이미 20 → 21), 사람이 매번 역추적하면 또 놓칩니다.

기계가 읽을 계약을 두고 검사기를 돌립니다. 목 서버와 같은 성격 — **계약의 실행 가능한 명세**이고, C는 A·B의 서버를 소비하는 쪽이라 불일치를 가장 먼저 만납니다.

```json
{"propose_allocation": {
   "server": "policy", "order": 2,
   "requires": {"observation": "observe.get_observation",
                "situation":   "AGENT",
                "recent_error":"feedback.get_reliability_table"},
   "produces": ["policy","allocation","confidence","in_distribution","status"]}}
```

검사 4개:

| # | 검사 | 차단하는 유형 |
|---|---|---|
| 1 | 모든 필수 입력에 생산자가 있는가 (`AGENT` 명시 포함) | V3 · V4 |
| 2 | 생산자의 호출 순서가 소비자보다 **앞인가** | V5 · V6 |
| 3 | 명세의 모든 식별자에 **발급 도구**가 있는가 | V2 |
| 4 | 아무도 소비하지 않는 출력 필드 목록 (경고) | V7 · V8 |

**추가 검사 — `AGENT`가 생산자인 값은 네 개뿐이어야 합니다.**

```
situation · confidence.combined · 에스컬레이션 판단 · 정책 선택
```

**이 넷이 연구의 기여 지점 전체입니다.** 목록이 늘어나면 에이전트가 해야 할 판단이 서버로 새고 있다는 뜻이므로, 넷을 넘으면 경고하도록 하세요. 줄어들어도 경고입니다 — 기여가 사라진 겁니다.

### 4.2 완료 판정

| # | 판정 |
|---|---|
| C-0 | 목 5개로 루프 1회전 완주 |
| C-1 | 진짜 서버 5개로 60스텝 무인 완주 |
| C-2 | 비교군 4개가 동일 시드에서 **동일 스텝 수**를 소화 |
| C-3 | `minimal` / `advisory` 두 벌 실행 가능 |
| C-4 | `proposed` 실행의 컨텍스트 덤프에서 금지어 **0건** |
| C-5 | `check_contract.py`가 검사 4개 통과. `AGENT` 생산 값이 **정확히 4개** |
| C-1 | 120스텝 실행에서 `report_outcome` 누락 **0건** (파이썬이 보장하므로 자동) |
| C-1 | 스텝당 프롬프트 토큰이 **스텝 수에 무관하게 일정** |
| C-1 | 에스컬레이션한 스텝도 `outcome`이 붙는다 (V2) |

C-2의 "동일 스텝 수"가 중요합니다. 에스컬레이션 후에도 에이전트는 **`rule_based` + `situation="normal"`로 계속 진행합니다.** 사람을 기다리지 않습니다. 그래야 모든 비교군이 같은 스텝을 소화해 SLA 위반 비교가 공정해집니다.

### 4.3 C의 함정

- **도구 호출 루프가 발산할 수 있습니다.** 스텝당 호출 횟수 상한(예: 8회)을 두고, 초과하면 강제 에스컬레이션 처리하세요.
- **비용**: 스텝당 3~5회 × 120스텝 × 60회 ≈ **2~3만 호출**. 모델 선정 전에 토큰 예산을 산정하세요 (설계서 §9-5, 현재 미해소).
- **LLM은 비결정적입니다.** 환경은 시드로 고정되지만 에이전트는 아닙니다. 그래서 시드 3개 × 반복이 필요합니다. "동일 시드 → 동일 결과"를 요구할 수 있는 건 **A의 ①까지**입니다.

---

## 5. 왜 이렇게 묶었나

**A — 실험 인프라를 한 사람이.** `MLOrchestrator`에서 `run()` 루프를 떼어내는 게 이 프로젝트에서 제일 까다롭습니다 (시뮬레이션·추론·시각화가 995줄에 뒤엉킴). ④ audit은 ①의 관측 스키마를 그대로 기록하니 같은 사람이 하면 손발이 맞습니다. 실험 하네스도 ④가 지표를 뽑으니 자연스럽게 따라옵니다.

**B — TensorFlow를 한 사람이.** ②와 ⑤ 모두 "정책"을 알아야 합니다. ⑤의 신뢰도 갱신은 ②가 어떤 정책을 노출하는지에 달려 있어서, 나누면 소통 비용만 늘어납니다. ③ market은 가볍게(`engine.py` 거의 그대로) 얹어도 부담이 적습니다.

**C — 판단 로직에 집중.** 오케스트레이터는 코드량은 적은데 반복 튜닝이 많습니다. 프롬프트 고치고 돌려보고 또 고치는 일이라, 서버 개발과 리듬이 다릅니다. 한 사람이 전담하는 게 맞습니다.

**부하 균형**: A와 B가 비슷하게 큽니다. C는 코드량이 가장 적은 대신 반복 횟수가 많고, 초반에 비는 시간을 목 서버(C-0)와 누출 검사(C-4)로 채웁니다. 둘 다 C가 아니면 하기 어려운 일입니다.

---

## 6. 병렬화 장치 — 누가 누구를 기다리는가

```
Day 0  ├─ A: mcp/common/ 작성 ────────────┐  (전원 대기)
       └─ 3인: 계약 동결 · 저장소 정리      │
                                          ▼
Day 1  ├─ A: env.py 추출 시작
       ├─ B: 0단계 검증 → 결과 공유 → ③ 착수
       └─ C: 목 서버 5개 → 루프 골격
                    │
Day 2  ├─ A: fixtures/ 배포 ──────────┬──→ B: ② 개발 (① 불필요)
       │                             └──→ C: 목이 fixture 재생
       ├─ B: ③ 완성
       └─ C: 목 ③ → 진짜 ③ 교체  ★ M1
                    │
 ...   ├─ A: ① 완성 → 재현성 검증  ★ M2
       ├─ B: ② 완성 → ⑤ 착수
       └─ C: 프롬프트 반복
```

**막히지 않는 이유 세 가지**

1. **A의 `common/`이 Day 0에 나온다** — 그 전까지 아무도 못 움직이므로 최우선.
2. **A의 `fixtures/`가 Day 2에 나온다** — B는 ① 없이 ②를, C는 ① 없이 프롬프트를 개발.
3. **C의 목 서버가 Day 1에 나온다** — C는 A·B를 기다리지 않고, 동시에 계약 검증 장치가 생김.

**교차 검증 — 자기 영역은 자기가 못 본다**

| 검증 대상 | 검증자 | 방법 |
|---|---|---|
| ①④의 정답 누출 (정정 D) | **C** | 컨텍스트 덤프 금지어 grep. A는 못 찾음 |
| ②의 `situation` 반영 (정정 E) | **A** | `baseline`과 `arm1`의 배분이 정답 일치 시 동일한가 |
| ②의 조용한 폴백 (정정 H) | **A** | ④ `policy_usage`와 ⑤ `reliability`의 `n`이 어긋나면 폴백 의심 |
| ①의 재현성 (정정 F) | A 자체 | 동일 시드 2회 → `truth.jsonl` 바이트 비교 |

---

## 7. 합류 지점

날짜 대신 **조건**으로 정의합니다. 각 지점에서 `main`으로 PR.

| | 조건 | 확인 방법 |
|---|---|---|
| **M1** 배선 | C의 루프가 **진짜 ③**을 호출해 벤더 5개 점수 수신 | 목 하나가 진짜로 교체됨 |
| **M2** 환경 | ① 동일 시드 2회 → `truth.jsonl` 동일. `fixtures/` 배포 완료 | `cmp` 통과 |
| **M3** 폐루프 | ①②④⑤ 전부 진짜로 **1스텝 왕복** + `report_outcome` 기록 | `decisions.json`에 `outcome` 필드 존재 |
| **M3.5** 계약 | `check_contract.py` 검사 4개 통과 | 값 유실 0건 (§1.5) |
| **M4** 비교군 | 4개 arm이 `mixed` 120스텝 완주. 누출 검사 0건 | `leak_check.py` 통과 |
| **M5** 결과 | 60회 실행 + `score.py` 지표 산출 + 대표 그래프 | 개입↓ / SLA→ 확인 |

**M1을 가장 먼저, 가장 작게 만드세요.** FastMCP 서버 하나, stdio 연결 하나, 도구 호출 하나가 왕복하면 나머지 20개는 같은 패턴의 반복입니다. ③이 중요해서가 아니라 배선 검증이 목적입니다.

**M2에서 반드시 멈추고 확인하세요.** 재현이 안 되는 채로 M3~M5를 쌓으면 마지막에 전부 다시 돌려야 합니다.

---

## 8. Day 0 체크리스트

셋이 같이 앉아 순서대로.

```
[ ] SRM-main-mcp/ 중첩 클론 제거
[ ] .gitignore UTF-8로 재작성 (models/, *.h5 는 넣지 말 것)
[ ] 작업 기준 디렉터리 srm-main_mcp/ 하나로 합의
[ ] docs/ 에 MCP-decomposition.md · MCP-design.md · ROLES.md 배치 후 커밋
[ ] A/B/C ↔ kim/lee/choi 브랜치 매핑 확정
[ ] mcp/common/const.py 값 13개 확정 (§1.2) — 특히 TAU = 0.45
[ ] mcp/common/schema.py 확정 — Observation에 is_emergency 계열 부재 확인
[ ] docs/contract.json 초안 — 도구 21개의 requires/produces (C가 작성, 3인 검토)
[ ] run_id 형식 합의: {arm}-{scenario}-s{seed}  (V3)
[ ] situation ↔ truth 매핑·전환 경계 제외 규칙 확정 (V9) — 채점 전에 못 박을 것
[ ] 파일 소유권 표 합의 (§1.3)
[ ] 기존 코드는 아무도 수정하지 않는다 — 합의
[ ] B: Day 1 오전 0단계 착수, 결과 즉시 공유 — 합의
```

마지막 두 줄이 사고를 가장 많이 막습니다.
