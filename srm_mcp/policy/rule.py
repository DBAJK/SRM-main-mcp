"""rule_based 정책 — `ml_orchestrator_demo.py:422` 추출. (B 소유)

정정 E: 원본은 `self.is_emergency` 를 직접 읽는다(:429). 그 분기를 **인자 `situation`** 으로
승격한다. ②는 무상태이므로 정답을 가질 수도 없고, 가지면 누출이다. 베이스라인과 제안 기법이
**같은 이 함수**를 호출하고 `situation` 의 출처만 다르다 — 사람(CLI) vs 에이전트 추론.
정확히 한 변수만 바뀌므로 통제 실험이 성립한다.

평활·클립·정규화(:458~462)는 여기 두지 않는다 — ①의 `apply_allocation()` 소관이다
(설계서 §3.2). 양쪽에 다 있으면 0.7이 두 번 걸려 배분이 거의 안 움직인다.

⚠️ 원본 :446~457 의 **위반 보정**은 옮기지 않았다. `spec/policy.md` 의 응답 예시가
   util {1.300, 1.525, 0.950} · emergency 에 대해 보정 없는 목표 {0.20, 0.70, 0.10} 이기
   때문이다(보정을 넣으면 {0.224, 0.686, 0.090} 이 나온다). 원본에서 그 보정은 *평활된*
   배분에 걸리는데 평활이 ①로 빠졌으므로 걸 자리도 사라졌다. 측정 관점에서도 이쪽이 낫다 —
   위반 보정은 상황 라벨이 틀렸을 때 그 영향을 되돌려 상황 인지 정확도의 신호를 흐린다.
   **원본 동작을 유지할지는 Day 0에서 3인이 정할 사항이다.**
"""
from __future__ import annotations

from typing import Any

from ..common.const import SLICE_KEYS, THRESHOLDS

# 원본 :429~:440 의 목표 배분 표. 상황 라벨 하나가 배분을 정한다.
TARGET_BY_SITUATION: dict[str, dict[str, float]] = {
    "emergency":     {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1},
    "special_event": {"embb": 0.6, "urllc": 0.3, "mmtc": 0.1},
    "iot_surge":     {"embb": 0.3, "urllc": 0.3, "mmtc": 0.4},
    "normal":        {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
}

CONFIDENCE_FLOOR = 0.50
CONFIDENCE_SPAN = 0.30


def propose(observation: dict[str, Any], situation: str) -> dict[str, float]:
    """목표 배분. 평활·클립 없음."""
    return dict(TARGET_BY_SITUATION[situation])


def margin(observation: dict[str, Any]) -> float:
    """임계값까지의 상대 여유 중 **가장 작은 것**: minᵢ |uᵢ − θᵢ| / θᵢ."""
    utilization = observation["utilization"]
    return min(abs(float(utilization[k]) - THRESHOLDS[k]) / THRESHOLDS[k] for k in SLICE_KEYS)


def confidence(observation: dict[str, Any]) -> float:
    """0.50 + 0.30 · min(1, minᵢ |uᵢ − θᵢ| / θᵢ)  →  [0.50, 0.80]  (설계서 §6.1)

    이용률이 임계값에 바짝 붙어 있으면 규칙의 이산 분기가 자의적이므로 확신이 낮다.
    여유가 크면 어느 쪽 분기인지 명확하다.

    하한 0.50은 의도적이다. 항상 가용한 안전 기본값이므로 다른 정책이 전부 실패해도
    이것 하나는 에스컬레이션 문턱 τ(0.45) 위에 있다. 이 상수가 곧 "언제 사람을 부를
    것인가"의 하한을 정의한다.
    """
    return CONFIDENCE_FLOOR + CONFIDENCE_SPAN * min(1.0, margin(observation))


def rationale(observation: dict[str, Any], situation: str,
              allocation: dict[str, float]) -> str:
    """사람이 읽는 근거. 어느 슬라이스가 임계를 얼마나 넘었는지까지 적는다."""
    utilization = observation["utilization"]
    triple = ", ".join(f"{allocation[k]:.1f}" for k in SLICE_KEYS)

    over = [(k, float(utilization[k]) / THRESHOLDS[k] - 1.0)
            for k in SLICE_KEYS if float(utilization[k]) > THRESHOLDS[k]]
    if over:
        worst, excess = max(over, key=lambda item: item[1])
        detail = (f"{worst.upper()} 이용률 {float(utilization[worst]):.3f} 이 "
                  f"임계 {THRESHOLDS[worst]} 를 {excess * 100:.0f}% 초과.")
    else:
        detail = "임계 초과 슬라이스 없음."

    return f"situation={situation} → 목표 [{triple}]. {detail}"
