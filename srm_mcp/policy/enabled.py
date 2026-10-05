"""이번 실험에서 쓰는 정책 집합 — `SLICE_POLICIES`. (C · 2026-10-05)

결정 (2026-10-05 · 교수님 상의): **LSTM 을 쓰지 않고 rule_based(theta_z) 고정으로 진행한다.**
근거는 workplan-2 §1.7 — 원본 자체 비교에서도 모델이 고정 배분보다 나빴고, 우리 측정에서도 lstm 스텝의
위반율이 rule 의 두 배 가까이 됐다(Claude mixed 120: 5/7 vs 33/107).

꺼진 정책은 지우지 않는다. ②가 `available=false` · `status="unavailable"` 로 **값으로** 알린다 —
dqn 이 "no trained weights" 로 내려가 있는 것과 같은 방식이고, 실패를 감추지 않는다는 원칙(정정 H)도 그대로다.

    SLICE_POLICIES=rule_based              기본 — 이 결정
    SLICE_POLICIES=all                     예전 동작 (rule_based · lstm_forecast · dqn 모두 후보)
    SLICE_POLICIES=rule_based,lstm_forecast

호출마다 읽는다 — `rule.correction_enabled()` 와 같은 이유(같은 프로세스에서 두 조건을 잴 수 있게).
"""
from __future__ import annotations

import os

POLICY_NAMES = ("rule_based", "lstm_forecast", "dqn")
POLICY_SET_DEFAULT = "rule_based"


def enabled_policies() -> tuple[str, ...]:
    raw = os.environ.get("SLICE_POLICIES", POLICY_SET_DEFAULT).strip().lower()
    if raw in ("all", "*"):
        return POLICY_NAMES
    names = tuple(p for p in POLICY_NAMES if p in {s.strip() for s in raw.split(",")})
    return names or (POLICY_SET_DEFAULT,)


def disabled_reason(policy: str) -> str | None:
    """꺼진 정책이면 사유 문자열, 켜져 있으면 None."""
    on = enabled_policies()
    if policy in on:
        return None
    return f"disabled_by_config: SLICE_POLICIES={','.join(on)}"
