"""EMA 신뢰도 갱신 (설계서 §6.2). (B 소유)

    r ← (1 − α)·r + α·s              α = 0.2,  s = 1 if sla_met else 0
    n ← n + 1
    effective = (r·n + r₀·m) / (n + m)       r₀ = 0.5, m = 5

α = 0.2 — 반감기 약 3스텝. 시나리오가 전환되는 `mixed`(120스텝, 5회 전환)에서 전환 후
5~10스텝 내에 신뢰도가 따라붙는다. α가 작으면 자기 개선이 안 보이고, 크면 잡음을 학습한다.

축소 항 m=5 — n 이 작을 때 r 이 0 또는 1로 튀는 것을 막는다. 첫 성공 1회로 신뢰도가
1.0이 되면 에이전트가 그 정책에 고착된다.

종합은 **에이전트만** 한다 (서버 간 직접 호출 금지):

    combined = sqrt(intrinsic × effective)      # ②의 confidence × ⑤의 effective
    escalate if combined < τ (0.45)
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from ..common.const import (EMA_ALPHA, POLICY_PRIOR, RECENT_ERROR_ALPHA,
                            RECENT_ERROR_N, SHRINK_M, SHRINK_R0)

POLICIES = ("rule_based", "lstm_forecast", "dqn")


def initial_entry() -> dict[str, Any]:
    """첫 기록 전의 상태. r₀ = 0.5 는 축소 항의 기준값과 같다."""
    return {"r": SHRINK_R0, "n": 0, "alpha": EMA_ALPHA, "errors": []}


def initial_table() -> dict[str, dict[str, Any]]:
    return {name: initial_entry() for name in POLICIES}


def update(r: float, n: int, sla_met: bool) -> tuple[float, int]:
    """r ← (1−α)·r + α·s,  n ← n + 1."""
    s = 1.0 if sla_met else 0.0
    return (1 - EMA_ALPHA) * r + EMA_ALPHA * s, n + 1


def effective(r: float, n: int) -> float:
    """축소 보정값. **에이전트는 이걸 쓴다** — ④ `confidence.empirical` 로 간다."""
    return (r * n + SHRINK_R0 * SHRINK_M) / (n + SHRINK_M)


def push_error(errors: Sequence[float], error: float) -> list[float]:
    """최근 N회만 남긴다. 오래된 것부터 정렬된 리스트."""
    return [*errors, float(error)][-RECENT_ERROR_N:]


def recent_error(errors: Sequence[float], policy: Optional[str] = None) -> Optional[float]:
    """최근 N회 `error` 의 EMA. ②의 `propose_allocation(recent_error=...)` 공급선(V4).

    표본이 없으면 정책 사전값에서 유도한다 — `1 − POLICY_PRIOR[policy]` (workplan B-3).
    이전에는 `null` 을 돌려주고 ②가 보수적 기본값 0.5 를 쓰게 했는데, 그 유예 가정에
    구멍이 있었다. `errors` 는 **정책별**로 쌓이므로 한 번도 선택되지 않은 정책은
    영영 비고, 비면 ②의 `exp(−3×0.5)=0.2231` 이 τ(0.45) 아래라 또 선택되지 않는다.
    `lstm_forecast` 가 30스텝 내내 n=0 으로 남은 원인이 이것이다.

    ⚠️ 여기서 나온 값은 **사전값이지 실측이 아니다.** 같은 행의 `n` 으로 구분한다
       (n=0 이면 사전값). `policy` 를 주지 않으면 종전대로 `None` 을 돌려준다 —
       ⑤ 밖에서 EMA 만 쓰는 호출부(검증 스크립트)의 계약을 바꾸지 않기 위해서다.
    """
    if not errors:
        prior = POLICY_PRIOR.get(policy) if policy is not None else None
        return None if prior is None else 1.0 - float(prior)
    ema = float(errors[0])
    for value in errors[1:]:
        ema = (1 - RECENT_ERROR_ALPHA) * ema + RECENT_ERROR_ALPHA * float(value)
    return ema


def view(policy: str, entry: dict[str, Any]) -> dict[str, Any]:
    """저장 형식 → `get_reliability_table()` 이 내보내는 형식.

    `policy` 는 `recent_error` 의 사전값 유도에 쓴다 (B-3). 정책명을 모르면
    어느 사전값을 쓸지 정할 수 없으므로 인자로 받는다.
    """
    r, n = float(entry["r"]), int(entry["n"])
    return {
        "reliability": round(r, 4),
        "n": n,
        "effective": round(effective(r, n), 4),
        "recent_error": (None if (value := recent_error(entry.get("errors", []), policy)) is None
                         else round(value, 4)),
    }
