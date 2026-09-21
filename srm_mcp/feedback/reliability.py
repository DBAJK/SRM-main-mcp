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

from ..common.const import (EMA_ALPHA, RECENT_ERROR_ALPHA, RECENT_ERROR_N,
                            SHRINK_M, SHRINK_R0)

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


def recent_error(errors: Sequence[float]) -> Optional[float]:
    """최근 N회 `error` 의 EMA. ②의 `propose_allocation(recent_error=...)` 공급선(V4).

    표본이 없으면 `null` 을 돌려준다 — ②가 보수적 기본값 0.5 를 쓰고 그 사실을
    `rationale` 에 적는다. 첫 5스텝은 `lstm_forecast` 가 어차피
    `history_insufficient` 로 빠지므로 별도 처리가 필요 없다.
    """
    if not errors:
        return None
    ema = float(errors[0])
    for value in errors[1:]:
        ema = (1 - RECENT_ERROR_ALPHA) * ema + RECENT_ERROR_ALPHA * float(value)
    return ema


def view(entry: dict[str, Any]) -> dict[str, Any]:
    """저장 형식 → `get_reliability_table()` 이 내보내는 형식."""
    r, n = float(entry["r"]), int(entry["n"])
    return {
        "reliability": round(r, 4),
        "n": n,
        "effective": round(effective(r, n), 4),
        "recent_error": (None if (value := recent_error(entry.get("errors", []))) is None
                         else round(value, 4)),
    }
