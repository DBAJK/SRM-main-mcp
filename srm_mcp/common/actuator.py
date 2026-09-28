"""액추에이터 식 — 정규화 → 평활(0.7) → 클립[0.1, 0.8] → 재정규화 (원본 `ml_orchestrator_demo.py:443~462`).

① `apply_allocation` 이 실제로 적용할 때와, ⑤ `report_outcome` 이 개입 스텝의 에이전트 제안을
가상 채점할 때(workplan-2 D5 · B-6)가 **같은 식**을 써야 한다. 두 곳에 베끼면 언젠가 어긋나
"그 배분이었다면"의 SLA 가 실제 환경과 다른 환경의 값이 된다. 그래서 한 곳에 둔다.

순수 함수다 — 상태도 난수도 없다. 입력 검사(음수 · NaN 거부)는 호출하는 쪽의 몫이다.
"""
from __future__ import annotations

from typing import Any

from .const import ALLOC_CLIP, SLICE_KEYS, STABILITY_FACTOR, THRESHOLDS


def actuate(current: dict[str, Any], requested: dict[str, Any]) -> tuple[dict, dict, bool]:
    """(적용될 배분, 정규화한 요청, 클립이 걸렸나)."""
    total = sum(float(requested[k]) for k in SLICE_KEYS)
    req = {k: float(requested[k]) / total for k in SLICE_KEYS}
    smoothed = {k: STABILITY_FACTOR * float(current[k]) + (1 - STABILITY_FACTOR) * req[k]
                for k in SLICE_KEYS}
    low, high = ALLOC_CLIP
    clipped = {k: min(max(v, low), high) for k, v in smoothed.items()}
    was_clipped = any(abs(clipped[k] - smoothed[k]) > 1e-12 for k in SLICE_KEYS)
    total = sum(clipped.values())
    return {k: v / total for k, v in clipped.items()}, req, was_clipped


def violations(traffic: dict[str, Any], allocation: dict[str, Any],
               capacity: dict[str, Any]) -> dict[str, bool]:
    """utilization = traffic / (allocation × capacity) > θ 인 슬라이스 (① env.py 와 같은 정의)."""
    return {k: float(traffic[k]) / (float(allocation[k]) * float(capacity[k])) > THRESHOLDS[k]
            for k in SLICE_KEYS}
