# B 담당 4건 완료 — 남은 것과 인수인계

작성 2026-09-25 · B(kim) · workplan B-1 ~ B-4

B-3 을 workplan 원문대로 **⑤에서** 구현했다 — `reliability.recent_error(errors, policy)` 가
표본이 없으면 `1 − POLICY_PRIOR[policy]` 를 유도한다 (`const.py`). 그 결과
`get_reliability_table()` 은 **알려진 정책에 대해 더는 `null` 을 내지 않는다**.

실측 (30스텝 normal · 규칙 판단자 · `runs/b3check-normal-s0`):

    "lstm_forecast": {"reliability":0.5, "n":0, "effective":0.5, "recent_error":0.2}
    "dqn":           {"reliability":0.5, "n":0, "effective":0.5, "recent_error":0.6}

바뀐 계약에 맞춰야 하는 곳이 C 소유 파일에 넷 있다. **프롬프트 한 줄만 이번에 같이 고쳤고
(아래 0번) 나머지 셋은 손대지 않았다.**

---

**0. `agent/deciders/llm.py` 정책 선택 기준 — 이번에 수정함**

"처음 쓰는 정책은 recent_error 가 없어 확신이 낮게 나오고, 낮으면 사람이 호출된다" 는
B-3 이후 **거짓**이다. LLM 이 읽는 문장이라 그대로 두면 판단이 오염되므로 한 줄만 고쳤다 —
"n=0 인 정책의 recent_error 는 실측이 아니라 사전값" 으로. 표현은 C 가 다듬어도 된다.

**1. `agent/schema.py:59` `StepContext.recent_error()` 독스트링**

"⑤는 표본이 없으면(n=0) null 을 낸다. 명세상 기본값 대입은 ②의 몫" — 이제 사실이 아니다.
**동작(중계)은 그대로 두면 된다.** `None` 중계 로직은 미지의 정책명일 때만 타므로 무해하다.
독스트링만 현재 계약과 맞춰 주면 된다. `claude/spec/policy.md:44` 는 B 가 이미 갱신했다.

**2. `agent/backends/mock.py:220` · `:442`**

mock 이 ②의 `0.5` 기본값을 자체 복제하고 있고, `_get_reliability_table` 은 n 과 무관하게
`st["err"]` 를 낸다. 실서버와 mock 이 서로 다른 값을 내면 mock 으로 잡은 회귀가 실서버에서
재현되지 않는다. n=0 이면 `1 − POLICY_PRIOR[policy]` 를 내도록 맞추는 것을 권한다.

**3. `tools/check_feedback.py:187` "표본 없으면 null"**

지금도 통과한다 — `recent_error([])` 처럼 `policy` 를 빼고 부르면 종전대로 `None` 이다
(구 호출부를 깨지 않으려고 남긴 경로). 다만 **실제 서버가 타지 않는 경로**를 검증하고 있으므로,
`recent_error([], "lstm_forecast") == 0.2` 를 확인하는 항목으로 바꾸는 편이 낫다.

**4. ⚠️ `agent/deciders/rule.py` `pick_policy()` — B-3 의 완료 판정이 여기서 막힌다**

workplan §5 는 B-3 의 판정을 *"30스텝 후 `lstm_forecast.n > 0`"* 으로 적었는데,
규칙 판단자로는 **B-3 과 무관하게 달성 불가능**하다. `proven = [p for p in candidates if
ctx.samples(p) > 0]` 이 n=0 인 정책을 후보에서 통째로 뺀다(:92). 1스텝에서 rule_based 의
n 이 1 이 되는 순간 lstm 은 영원히 후보 밖이다.

실측: 30스텝 normal · `--decider rule` → `정책 사용 {'rule_based': 30}`.

B-3 이 고친 것은 **"고르면 확신이 τ 아래라 개입으로 튕긴다"** 는 두 번째 자물쇠이고
(`exp(−3×0.2)=0.5488 > τ`), 첫 번째 자물쇠인 후보 필터는 C 의 판단 영역이다.
`rule.py:80~87` 의 주석은 두 자물쇠를 한 덩어리로 보고 필터를 넣은 것인데, 그 근거 중
"recent_error 가 없어 ②가 보수적 기본값을 쓰고 실측 conf 0.2231" 부분은 이제 해소됐다.

선택지: (a) 규칙 판단자는 그대로 두고 B-3 판정을 **LLM 판단자 기준**으로 바꾼다
(b) `proven` 필터에 "n=0 인 정책도 k스텝에 한 번은 시험" 을 넣는다.
B 의 권고는 (a) — 미검증 정책을 언제 시험할지는 판단의 영역이고 그게 이 연구의 주제다.
어느 쪽이든 workplan §5 의 B-3 판정 문구를 고쳐야 한다.

---

---

# B-1 · B-2 도 넣었다 (같은 날)

**B-2 (귀속 분리)** — `report_outcome` 이 `escalated` 레코드에서 정책의 `r`·`n`·`errors` 를
갱신하지 않는다. 채점은 그대로 하고(④ `outcome`·`sla_met`·반환값 모두 남는다), 그 성적은
`reliability.json` 의 **`fallback` 항목**에 따로 쌓인다. `fallback` 은 `POLICIES` 가 아니므로
`get_reliability_table()` 출력에서 뺐다 — 에이전트에게 고를 수 있는 정책처럼 보이면 안 된다.
반환값과 ④ 레코드에 `counted_in_reliability` 를 남겨 "왜 n 이 안 늘었나" 를 장부에서 읽을 수 있다.

실측 (`runs/b12on-emergency-s0`, 30스텝 emergency · 개입 18):
`rule_based.n = 12 = 30 − 18` · `fallback.n = 18` · `counted {True:12, False:18}`.
workplan §5 판정 충족.

**B-1 (위반 보정)** — D1 권고대로 환경변수 `SLICE_RULE_CORRECTION`(기본 `on`) 스위치로 넣었다.
뒤집히면 `rule.py` 의 `CORRECTION_DEFAULT` 한 줄이다. 적용 설정은 매 스텝 `rationale` 끝에
`(보정 on|off)` 로 남아 `decisions.json` 에서 확인된다.

실측 (emergency 30스텝 · 같은 시드):

| | SLA 위반 | 자율 스텝의 서로 다른 요청 배분 |
|---|---|---|
| 보정 on  | **19** / 30 | 8 종 |
| 보정 off | 20 / 30 | 3 종 |

판정(`< 21/30`, 배분이 스텝마다 다름)은 충족했지만 **효과가 1스텝뿐이다.** 원인 둘:

1. **평활에 희석된다.** 원본은 *평활된* 배분에 보정을 걸었는데(`:444` 이후), ②는 현재 배분을
   모르므로 목표표에 건다. ①이 그 뒤 `0.7×현재 + 0.3×요청` 을 걸어 **적용값에 남는 보정은 30%**
   (최대 0.1 → 0.03). 크기를 `1/0.3` 으로 되돌리는 것은 상수 조작이라 하지 않았다(§0).
2. **30스텝 중 18스텝이 개입이라 보정이 아예 안 걸린다.** 개입 스텝의 배분은 ④의 폴백 상수다.
   즉 B-1 의 효과 상한은 자율 스텝 12개뿐이고, 개입률이 내려가야 같이 커진다.

→ **D1 회의에 올릴 것**: 보정을 목표표(현행)에 둘지, ①의 `apply_allocation()` 에서 평활 뒤에
걸지. 후자가 원본 재현이지만 "평활·클립은 ①, 정책은 ②" 경계를 넘고 A 담당 파일이 된다.
지금 값(19/30)은 그 결정 전의 하한으로 읽어야 한다.

`spec/policy.md` 응답 예시는 `off` 기준임을 명시하고 `on` 값을 병기했다.
`tools/check_policy.py` 에 보정 검사(1b)를 넣었다 — 셋 다 초과인 예시 관측에서
`{0.250, 0.765, −0.015}`. **음수를 ②가 고치지 않는 것은 의도다** — 클립·재정규화는 ①의 몫이다.

---

남은 B 작업: 없음. B-1 은 위 D1 후속 결정에 따라 한 번 더 손댈 수 있다.
