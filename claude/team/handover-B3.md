# B-3 이후 남은 것 — C(lee) 소유 파일 4곳

작성 2026-09-25 · B(kim) · workplan B-3 · B-4 구현에 딸린 인수인계

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

남은 B 작업: **B-2**(귀속 분리, A-1 뒤) · **B-1**(위반 보정, D1 뒤).
B-1 은 회의에 올릴 쟁점이 둘 있다 — ①의 평활 0.7 에 보정이 1/3 로 희석되는 문제와
`spec/policy.md:78·121` 응답 예시 충돌.
