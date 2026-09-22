# ②④⑤ 이슈 4건 — 실측 보고

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
