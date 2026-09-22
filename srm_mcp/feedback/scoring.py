"""채점 산식 — 관측만으로 계산한다. (B 소유)

정답(`truth.jsonl`)을 쓰지 않는 것이 핵심이다. `is_emergency` 계열을 한 번도 읽지 않으므로
정책 간 비교가 가능하고, ②의 lstm 신뢰도(`exp(−3·ē)`)에도 그대로 재사용된다.

    a*    = normalize(traffic / (thresholds × capacity))   # 위반이 딱 없어지는 배분
    error = L1(applied_allocation, a*) / 2                 # [0, 1]

⚠️ `capacity` 를 빼면 안 된다. 조달로 용량이 늘어난 스텝에서는 같은 트래픽에 필요한
   배분 비율이 줄어드는데, 이를 무시하면 조달한 정책이 부당하게 나쁜 점수를 받는다.
"""
from __future__ import annotations

from typing import Any

from ..common.const import SLICE_KEYS, THRESHOLDS


def _triple(source: Any, default: float = 1.0) -> dict[str, float]:
    if not isinstance(source, dict):
        return {k: default for k in SLICE_KEYS}
    return {k: float(source.get(k, default)) for k in SLICE_KEYS}


def ideal_allocation(observed: dict[str, Any]) -> dict[str, float]:
    """위반이 딱 없어지는 배분. 이용률이 전 슬라이스에서 임계와 같아지는 지점이다."""
    traffic = _triple(observed.get("traffic"), 0.0)
    capacity = _triple(observed.get("capacity"), 1.0)

    need = {k: traffic[k] / (THRESHOLDS[k] * capacity[k]) for k in SLICE_KEYS}
    total = sum(need.values())
    if total <= 0:
        return {k: 1 / len(SLICE_KEYS) for k in SLICE_KEYS}
    return {k: need[k] / total for k in SLICE_KEYS}


def distance(a: dict[str, float], b: dict[str, float]) -> float:
    """L1 / 2. 두 배분 모두 합이 1이므로 [0, 1] 로 떨어진다."""
    return sum(abs(float(a[k]) - float(b[k])) for k in SLICE_KEYS) / 2


def sla_met(violations: Any) -> bool:
    """세 값이 모두 false 여야 충족이다.

    ⚠️ `violations` 는 원본에서 정확히 `np.bool_` 이다 (ml_orchestrator_demo.py:563).
    `bool()` 로 감싸지 않으면 JSON 직렬화에서 죽는다 (spec/common.md).
    """
    if not isinstance(violations, dict):
        return False
    return not any(bool(violations.get(k, False)) for k in SLICE_KEYS)


def violations_view(violations: Any) -> dict[str, bool]:
    """MTTR 재구성용. ④가 가진 건 obs_t 뿐이라 에피소드 마지막 관측이 유실된다."""
    return {k: bool(violations.get(k, False)) if isinstance(violations, dict) else False
            for k in SLICE_KEYS}
