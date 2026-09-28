"""채점 산식 — 관측만으로 계산한다. (B 소유)

정답(`truth.jsonl`)을 쓰지 않는 것이 핵심이다. `is_emergency` 계열을 한 번도 읽지 않으므로
정책 간 비교가 가능하고, ②의 lstm 신뢰도(`exp(−3·ē)`)에도 그대로 재사용된다.

    a*    = normalize(traffic / (thresholds × capacity))   # 위반이 딱 없어지는 배분
    error = L1(applied_allocation, a*) / 2                 # [0, 1]

⚠️ `capacity` 를 빼면 안 된다. 조달로 용량이 늘어난 스텝에서는 같은 트래픽에 필요한
   배분 비율이 줄어드는데, 이를 무시하면 조달한 정책이 부당하게 나쁜 점수를 받는다.
"""
from __future__ import annotations

import math
import os
from typing import Any, Optional

from ..common.actuator import actuate, violations
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


def shadow_outcome(record: dict[str, Any], observed: dict[str, Any]) -> Optional[dict[str, Any]]:
    """개입 스텝에서 **에이전트 제안이 적용됐다면**의 SLA · 오차 (workplan-2 D5 · 가상 채점).

    트래픽은 배분과 무관하게 생성되고(① env._roll), 이용률은 traffic / (allocation × capacity) 다.
    그래서 obs_t 의 배분에서 ①과 같은 액추에이터 식(common/actuator.py)으로 "적용됐을 배분"을 만들고
    obs_{t+1} 의 traffic · capacity 로 위반을 다시 계산하면 반사실이 정확히 나온다. 조달로 늘어난 용량도
    capacity_{t+1} 에 이미 들어 있다. 계산할 수 없으면(제안 없음 · 관측 결손 · 비정상 값) None.
    """
    agent = record.get("agent_allocation")
    current = (record.get("observation") or {}).get("allocation")
    if not isinstance(agent, dict) or not isinstance(current, dict):
        return None
    if not observed.get("traffic") or not observed.get("capacity"):
        return None
    try:
        values = [float(agent[k]) for k in SLICE_KEYS]
        if any(not math.isfinite(v) or v < 0 for v in values) or sum(values) <= 0:
            return None
        applied, _, _ = actuate(current, agent)
        viol = violations(observed["traffic"], applied, observed["capacity"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return {
        "policy": record.get("agent_policy"),
        "applied_allocation": {k: round(v, 6) for k, v in applied.items()},
        "sla_met": not any(viol.values()),
        "error": distance(applied, ideal_allocation(observed)),
        "violations": viol,
    }


# 개입 스텝의 가상 채점 스위치 (workplan-2 D5). off 면 B-2 그대로 — 개입 중 정책 성적이 멈춘다
# (after-B1 과 비교용). ⑤ 서버와 목이 같이 읽으므로 서버 모듈이 아니라 여기 둔다(목은 fastmcp 없이 돈다).
SHADOW_DEFAULT = "on"


def shadow_enabled() -> bool:
    return os.environ.get("SLICE_SHADOW_SCORING", SHADOW_DEFAULT).lower() != "off"
