# ②④⑤ 이슈 8건 — 실측 보고 · 산식 감사

작성 2026-09-23 · C(에이전트) · 대상 B(②③⑤ 소유) · 4번은 ④도 관련

에이전트를 실제 MCP 서버 5개에 붙여 돌린 결과 네 가지가 드러났다. 넷 다
에이전트 쪽에서는 우회만 가능하고 근본 해결은 ②·④·⑤에 있다.

**요약**

| | 증상 | 영향 |
|---|---|---|
| 1 | `lstm_forecast` 를 자율 실행할 수 없다 | 정책 전환 실증 불가 |
| 2 | `rule_based` 의 안전 하한이 지켜지지 않는다 | 개입률이 정책 성적에 끌려간다 |
| 3 | 위반 보정 미이식 결정이 미완 | SLA 위반 63% |
| 4 | 개입 스텝의 **정책 선택**이 장부에서 사라진다 | 정책 선택 측정 불가 |
| 5 | 개입 스텝의 **폴백 성적**이 그 정책 신뢰도에 기록된다 | 성적표 60%가 남의 점수 |
| 6 | `combined` 이 SLA 실패를 예측하지 못한다 | AUC 0.487~0.683. τ=0.45 근거 없음 |
| 7 | `error` 가 `sla_met` 과 거의 무관하다 | 신뢰도 계통 전체에 파급 |
| 8 | 달성 불가능한 스텝이 지표에 섞여 있다 | emergency 위반의 38% |

---

## 1. `lstm_forecast` 가 표본을 영원히 못 쌓는다 (흡수 상태)

### 증상

30스텝 측정에서 스텝 10부터 **20스텝 연속 개입**. 그동안 두 수치가 한 번도
움직이지 않았다.

```
스텝 정책             intr    emp    comb   판정
  9  rule_based      0.512  0.525  0.519  자율
 10  lstm_forecast   0.223  0.500  0.334  개입
 11  lstm_forecast   0.223  0.500  0.334  개입
  …                  (29까지 동일)
```

LLM 판단자로 돌린 120스텝 `mixed` 실행에서는 **47회 선택됐는데 47회 모두
개입됐다.** 끝난 뒤 ⑤ 성적표는 그대로 `lstm_forecast: n=0, errors=[]` 이다.
판단자가 고르든 안 고르든 표본은 쌓이지 않는다 (4번과 겹친다).

### 원인 — 네 단계가 닫힌 고리를 만든다

```
⑤ errors=[]            → recent_error = null        (feedback/reliability.py:60)
② null → 보수적 기본값  → confidence = 0.2231        (실측: null ≡ 0.5)
   combined √(0.2231 × 0.5) = 0.334 < τ(0.45)       → 개입
④ 개입 스텝은 fallback_policy=rule_based 로 기록     (audit/book.py)
⑤ 그 성적을 rule_based 에 붙임                       → lstm.errors 는 여전히 []
```

②의 반응 실측:

```
recent_error=null  → conf 0.2231      ← errors=[] 일 때
recent_error=0.05  → conf 0.8607
recent_error=0.10  → conf 0.7408
recent_error=0.50  → conf 0.2231      ← null 과 같은 값
```

`null` 을 **최악의 관측 오차와 동일하게** 취급한다.

### 가정의 구멍

> `feedback/reliability.py:57`
> *"첫 5스텝은 `lstm_forecast` 가 어차피 `history_insufficient` 로 빠지므로
> 별도 처리가 필요 없다."*

`errors` 는 **정책별**이다. 유예 5스텝이 지나도 `lstm_forecast` 의 리스트는
비어 있다 — 한 번도 실행된 적이 없으므로 채워질 경로가 없다.

### 재현

```bash
python run.py --backend mcp --decider rule --scenario normal \
              --steps 30 --fresh --memory-mode cold
```

`runs/<run_id>/trace.log` 에서 스텝 10 이후 `propose_allocation` 반환값의
`confidence` 가 0.2231 로 고정되는 것을 확인할 수 있다.

### 선택지

| | 고칠 곳 | 내용 | 평가 |
|---|---|---|---|
| **A** | ⑤ | `errors` 가 비면 `reliability` 사전값에서 유도한 오차를 준다 (lstm 0.8 → 0.15) | **권고.** ⑤ 안에서 닫히고 ②의 계약도 명세도 안 바뀐다 |
| B | ② | `recent_error=null` 을 최악이 아니라 중립으로 해석 | ②의 보수성 설계를 뒤집는다 |
| C | ④⑤ | 개입 스텝도 **원래 고른 정책**의 표본으로 센다 | 실행되지 않은 정책을 채점하게 되어 의미가 왜곡된다 |

에이전트 쪽 우회는 이미 넣었다 — `pick_policy` 가 검증된 정책 안에서만
고른다. 부작용으로 규칙 판단자는 `lstm_forecast` 를 영영 쓰지 않는다.

---

## 2. `rule_based` 의 안전 하한이 실제로는 지켜지지 않는다

### 설계 의도

> `policy/rule.py` `confidence()` 독스트링
> *"하한 0.50은 의도적이다. 항상 가용한 안전 기본값이므로 다른 정책이 전부
> 실패해도 이것 하나는 에스컬레이션 문턱 τ(0.45) 위에 있다."*

### 실제

`combined = √(intrinsic × empirical)` 이므로 **`empirical` 이 함께 곱해진다.**
`intrinsic` 하한 0.50 만으로는 τ 위를 보장하지 못한다.

```
empirical 1.00 → combined √(0.50 × 1.00) = 0.707   ✓
empirical 0.50 → combined √(0.50 × 0.50) = 0.500   ✓ (겨우)
empirical 0.20 → combined √(0.50 × 0.20) = 0.316   ✗
empirical 0.07 → combined √(0.50 × 0.07) = 0.187   ✗
```

12스텝 실행에서 `rule_based` 의 `effective` 가 실제로 이렇게 떨어졌다.

```
n     0     1     2     3     4     5     6     7     8     9    10    11
rel  .500  .400  .520  .416  .333  .266  .213  .170  .136  .109  .087  .070
eff  .500  .483  .506  .469  .426  .383  .344  .308  .276  .249  .225  .204
```

스텝 5부터 개입이 시작됐고, 45스텝 시점에 34회(76%)가 됐다.

### 논점

"안전 기본값"이라는 개념 자체가 성립하려면 셋 중 하나를 정해야 한다.

- `combined` 를 `intrinsic` 만으로 정의한다 (⑤의 기여를 버린다)
- `rule_based` 의 `empirical` 에 하한을 둔다
- **"안전 기본값은 없다"** 고 명시하고 독스트링을 고친다 — 성적이 나쁘면
  기본값도 못 믿는 게 맞다는 입장

셋째가 타당해 보이나 **③의 판단이 필요하다.** 현재 독스트링은 지켜지지 않는
보장을 약속하고 있어, 그대로 두면 다음 사람이 같은 오해를 한다.

---

## 3. 위반 보정 미이식 — Day 0 결정이 미완

### 현황

> `policy/rule.py` 모듈 독스트링
> *"⚠️ 원본 :446~457 의 **위반 보정**은 옮기지 않았다. … **원본 동작을
> 유지할지는 Day 0에서 3인이 정할 사항이다.**"*

이 결정이 이루어지지 않았다.

### 측정된 대가

`propose()` 는 `observation` 을 읽지 않는다. `situation` 하나로 표를 찾을 뿐이라
**출력이 4가지뿐**이다.

```python
def propose(observation, situation):
    return dict(TARGET_BY_SITUATION[situation])   # observation 미사용
```

12스텝 실행 스텝 0:

```
② 분류기      eMBB 0.9897 (압도적)
② rule_based  요청 {embb 0.600, urllc 0.300, mmtc 0.100}
① 적용        {embb 0.460, …}                    (평활 0.7)
⑤ 채점        ideal {embb 0.4095, …}  error 0.1287  sla_met=false
```

목표 0.60 에 대해 실제 최적은 0.41 이었다. 매 스텝 같은 방향으로 빗나간다.

```
12스텝 실행    SLA 위반 11/12  (92%)
120스텝 mixed  SLA 위반 76/120 (63%)
```

### 논점

위반 보정을 되살리면 `situation` 라벨이 틀렸을 때 그 영향이 상쇄되어
**상황 인지 정확도의 신호가 흐려진다** — 독스트링의 지적이 맞다.

다만 지금은 반대쪽 대가가 크다. SLA 위반 63% 는 `rule_based` 를 사실상
쓸 수 없는 정책으로 만들고, 그 결과 ⑤ 성적이 `r=0.200` 까지 붕괴해 개입률이
50% 가 된다. **"개입은 줄었는데 SLA 위반은 늘지 않았다"** 를 보이려는 실험에서
두 지표가 동시에 나빠진다.

### 제안

보정을 켜고 끄는 **환경변수 하나**로 두고 양쪽을 다 측정한다.
`SLICE_DESC_MODE` · `SLICE_MEMORY_MODE` 와 같은 자리다.

```
SLICE_RULE_CORRECTION=off   현재 동작. 상황 인지 신호가 깨끗하다
SLICE_RULE_CORRECTION=on    원본 동작. SLA 가 개선될 것으로 예상
```

그러면 Day 0 결정을 미루지 않고 **데이터로 답할 수 있다.**

---

## 영향 범위

넷이 함께 걸려 현재 상태는 이렇다 (120스텝 `mixed` · LLM 판단자).

```
LLM 이 상황을 다양하게 읽는다   normal 57 · iot_surge 27 · special_event 24 · emergency 12
정책도 실제로 갈아탄다           rule_based 73 · lstm_forecast 47
그런데 lstm 을 고른 47회가 전부 개입되고 (1번)
       그 사실이 장부에 안 남는다 (4번)
       쓸 수 있었던 rule_based 는 SLA 를 63% 놓친다 (3번)
→ ⑤ 성적 r=0.200 붕괴 → 개입 50%
```

**판단은 살아 있는데 그 판단이 결과로도 기록으로도 이어지지 않는다.**
1·4번이 풀리지 않으면 "에이전트가 정책을 선택한다"는 논문의 서사를 ④의
장부로 입증할 수 없다.

---

## 에이전트 쪽에서 이미 한 것

참고로 C 쪽 우회·수정은 다음과 같다. ②⑤ 는 건드리지 않았다.

- `pick_policy` 가 검증된 정책 안에서만 고른다 (1번 우회)
- `record_escalation` 에 조달 3필드를 중계한다 — 누락 시 ④의 비용 집계와
  ⑤→③ 레이팅 되먹임이 끊겼다 (`audit/server.py:84` 의 경고대로)
- `--fresh` 가 `bootstrap_vendors.py --force` 를 부른다 — ③의 평판이
  실행 간에 남아 같은 시드에서 결과가 갈렸다 (`market/server.py:9~10`)
- 실행마다 `runs/<run_id>/trace.log` 와 `servers/*.log` 를 남긴다

---

## 4. 개입 스텝에서 **에이전트가 고른 정책**이 장부에서 사라진다

### 증상

120스텝 `mixed` · LLM 판단자 실행에서 두 집계가 어긋난다.

```
에이전트가 고른 것   rule_based 73 · lstm_forecast 47
④ 장부에 남은 것     rule_based 120 · lstm_forecast 0
⑤ 최종 성적표        lstm_forecast  n=0  errors=[]
```

### 원인

`record_escalation` 이 폴백 결정 레코드를 쓸 때 `chosen_policy` 를
`FALLBACK_POLICY` 로 덮는다. 에이전트가 원래 무엇을 골랐는지 남는 자리가 없다.

```python
# audit/book.py
"situation": situation,              # 에이전트 판단 — 보존됨 ✅
"chosen_policy": FALLBACK_POLICY,    # 에이전트 선택 — 덮임 ❌
"fallback_situation": FALLBACK_SITUATION,
"fallback_allocation": fallback,
```

`situation` 에 대해서는 이미 올바르게 처리돼 있다.

> `audit/book.py:185`
> *"폴백 결정 레코드의 `situation` 에는 **에이전트의 판단**을 그대로 남긴다.
> 폴백이 정책에 먹인 라벨로 덮으면 상황 인지 측정의 입력이 사라진다."*

**같은 논리가 `chosen_policy` 에는 적용되지 않았다.**

### 영향

- `get_metrics.policy_usage` 가 정책 선택을 실제와 다르게 보고한다
- 논문의 **"에이전트가 정책을 선택한다"** 를 장부로 입증할 수 없다.
  47회 선택한 증거가 ④ 어디에도 없다
- 1번(흡수 상태)과 겹쳐 `lstm_forecast` 는 선택 기록도, 성적 표본도 남지 않는다

### 제안

`situation` 과 같은 방식. 한 줄이면 된다.

```python
"chosen_policy": FALLBACK_POLICY,
"agent_policy": chosen_policy,   # 추가 — 에이전트가 원래 고른 것
```

`record_escalation` 시그니처에 `chosen_policy` 인자를 받는다. 에이전트 쪽은
이미 그 값을 들고 있으므로 중계만 하면 된다.

---

## 실측 보강 (120스텝 `mixed` · LLM 판단자 · 2026-09-23)

```
스텝 120 · 개입 60 (50%) · SLA 위반 76 · 조달 12 · 비용 3137.5
상황 판단  normal 57 · iot_surge 27 · special_event 24 · emergency 12
정책 선택  rule_based 73 · lstm_forecast 47   (장부에는 rule_based 120)
LLM        120회 · 스텝당 17.4초 · 형식위반 0 · 토큰 입출력 4.67M · $5.78

eval/score.py
  perception_accuracy   0.591  (68/115, 전환 경계 5스텝 제외)
  escalation_precision  0.767  (46/60)
```

단일 시나리오(0.20~0.47)보다 나아졌다. `mixed` 라야 지표가 포화되지 않는다.

혼동 행렬에서 가장 큰 오류는 **`emergency` → `normal` 14회** 다. 비상을 평시로
본 것이라 위험한 방향의 오류다. 1·3번이 풀리면 개선 여지가 있다.

---

# 산식 감사 (2026-09-23 추가)

`measure-normal-s0` · `measure-emergency-s0`(각 30스텝, 규칙 판단자, 실서버)의
장부를 산식과 대조했다. **구현 버그는 없다** — EMA 갱신과 축소 보정을 30스텝 전부
손으로 재현했고 장부 값과 소수점까지 일치한다.

```
r ← 0.8·r + 0.2·s          effective = (r·n + 0.5·5)/(n+5)
전 스텝 일치. 최종 r=0.3787(normal) · 0.2655(emergency)
```

문제는 계산이 아니라 **무엇을 무엇에 귀속시키는가**다. 셋을 더 보고한다.

---

## 5. 개입 스텝의 폴백 성적이 그 정책의 신뢰도에 기록된다

### 증상

```
measure-normal-s0     개입 18/30 — 적용 배분이 폴백과 동일 18/18
measure-emergency-s0  개입 19/30 — 동일 19/19
chosen_policy 기록: ['rule_based']
```

**성적표의 60%가 그 정책이 하지 않은 일에 대한 점수다.**

### 원인

`record_escalation` 은 `fallback = dict(INIT_ALLOCATION)` 이라는 **상수**를 적용
배분으로 남기고 `chosen_policy` 를 `FALLBACK_POLICY`(= `rule_based`)로 적는다.
⑤ `report_outcome` 은 그 레코드를 읽어 `rule_based` 의 `r` 을 갱신한다.

```
② rule_based 가 제안   {0.6, 0.3, 0.1}   (situation=special_event)
① 실제로 적용된 것     {0.4, 0.4, 0.2}   ← INIT_ALLOCATION 상수
⑤ 채점 대상           rule_based        ← 제안한 쪽
```

`situation=normal` 일 때만 둘이 우연히 같다. 그 외 상황에서는 **다른 정책의 결과를
기록하는 것**이다.

### 파급 — 자기강화 하강

```
신뢰도 하락 → 개입 → 폴백 적용 → 폴백이 못 맞춤 → 그 실패가 정책에 기록
          ↑                                                    │
          └────────────────────────────────────────────────────┘
```

`r` 이 0.379 · 0.266 까지 내려간 것은 정책이 나빠서가 아니라 **개입했기 때문**이다.
1번(lstm 흡수 상태)과 같은 뿌리이고, 4번(`chosen_policy` 유실)과 같은 지점이다.

### 선택지

| | 내용 | 평가 |
|---|---|---|
| **A** | 개입 스텝은 ⑤의 `r` 갱신에서 제외한다. 실행되지 않은 정책을 채점하지 않는다 | **권고.** ⑤ 안에서 닫힌다 |
| B | 폴백을 `fallback` 이라는 별도 정책 이름으로 채점한다 | 폴백 성능도 측정치가 된다. 표가 하나 늘어난다 |
| C | 지금 유지 | 신뢰도가 개입 빈도의 함수가 되어 해석 불가 |

어느 쪽이든 **4번(`agent_policy` 기록)이 선행**해야 한다. 그 필드가 없으면 ⑤가
"실제 실행된 것"과 "제안된 것"을 구분할 근거가 없다.

---

## 6. `combined` 이 SLA 실패를 예측하지 못한다

### 측정

에스컬레이션 임계 τ=0.45 의 전제는 *"combined 이 낮으면 실패할 가능성이 높다"* 이다.
그 전제를 AUC 로 쟀다.

```
measure-normal-s0     AUC 0.683   약한 예측력
measure-emergency-s0  AUC 0.487   무작위(0.5)와 같음
```

`emergency` 에서는 방향이 뒤집힌다.

```
combined 구간   n     SLA 위반률
0.00~0.35       5     0.20      ← 신뢰도 최저인데 위반 최소
0.35~0.45      14     1.00
0.45~0.55       7     0.57
0.55~1.01       4     0.50
```

### 뜻

**지금 τ=0.45 로 사람을 부르는 데 근거가 없다.** 이 값은 설계서가 정한 상수이고
(`flow/data-chain.md:107`), 데이터로 검증된 적이 없다.

5번의 귀속 오류가 `empirical` 을 오염시키고 있으므로, **5번을 고친 뒤 다시 재야**
진짜 예측력을 알 수 있다. 그 전에 τ 를 조정하면 오염된 신호에 맞추는 것이 된다.

### 제안

5번 수정 후 같은 AUC 를 다시 잰다. 그래도 0.5 근처면 에스컬레이션 기제 자체를
다시 설계해야 한다 — 그 경우 "개입을 줄였다"는 주장의 근거가 사라진다.

---

## 7. `error` 가 `sla_met` 과 거의 무관하다

### 측정

```
measure-normal-s0
  SLA 충족 스텝 평균 error 0.1265  (n=9)
  SLA 위반 스텝 평균 error 0.1277  (n=21)      차이 0.0012

measure-emergency-s0
  SLA 충족 0.0593 · SLA 위반 0.0874            차이 0.028
```

`normal` 에서는 **사실상 구분되지 않는다.**

### 원인 — `a*` 는 "위반이 없어지는 배분"이 아니다

```python
need_k = traffic_k / (θ_k × capacity_k)
a*     = normalize(need)        # 합을 1로
```

SLA 를 지키려면 **모든 k 에서 `a_k ≥ need_k`** 여야 한다. `normalize` 는 합만 1로
맞출 뿐 그 조건과 다르다. `Σ need = demand_pressure` 이므로, 압력이 0.6 이면 `a*`
는 `need` 를 약 1.67배로 부풀린 값이고 거기서 멀어져도 SLA 는 충족될 수 있다.

```
error    이상적 비율에서 얼마나 벗어났나
sla_met  임계를 넘었나
```

둘은 다른 것을 재고 있고, 상관이 약한 것은 정의상 당연하다.

### 파급

`error` 는 ⑤ `recent_error` 로 집계되어 ②의 lstm 신뢰도 `exp(−3·ē)` 입력이 된다.
SLA 와 무관한 값이 신뢰도 계통 전체를 타고 흐른다.

### 논점

`error` 를 버리자는 것이 아니다. **둘 중 무엇을 신뢰도의 근거로 삼을지** 정해야 한다.

- `error` 유지 — "이상적 배분에 얼마나 가까운가". 연속값이라 신호가 풍부하다
- `sla_met` 기반으로 교체 — 논문 지표와 일치한다. 이진값이라 신호가 성기다
- 둘 다 보고 — `recent_error` 와 별도로 `recent_sla` 를 둔다

`spec/feedback.md` 가 `error` 를 쓰기로 정해 뒀으므로 변경은 명세 수정을 수반한다.

---

## 8. 달성 불가능한 스텝이 지표에 섞여 있다

```
measure-emergency-s0  SLA 위반 21/30
                      그중 demand_pressure > 1.0 인 스텝 8건
measure-normal-s0     21/30 중 2건
```

`Σ need = demand_pressure` 이므로 **압력이 1을 넘으면 어떤 배분으로도 SLA 를 지킬 수
없다.** 조달로 `capacity` 를 올리는 것이 유일한 해법이다.

이 스텝들의 실패를 정책 신뢰도에 기록하면 **조달이 필요한 상황에서 정책만 벌을 받는다.**
`emergency` 에서 위반의 38% 가 여기 해당한다.

### 제안 (C 몫)

`eval/score.py` 와 지표 보고에서 `demand_pressure > 1.0` 인 스텝을 **따로 센다.**
제외가 아니라 분리다 — 조달 판단을 평가하는 데는 오히려 이 스텝들이 핵심이다.

```
SLA 위반  21 = 배분 탓 13 + 구조적 8(조달로만 해소 가능)
```

---

## 우선순위 갱신

5번이 1·4번과 같은 뿌리이고 6번의 측정을 오염시키므로, 순서는 다음과 같다.

```
4번 (agent_policy 기록)          ← 5번의 전제
5번 (개입 스텝 귀속)              ← 6번 측정의 전제
1번 (lstm 흡수 상태)
그다음 6번을 다시 측정 → τ 재검토
7·8번은 병행 가능
```
