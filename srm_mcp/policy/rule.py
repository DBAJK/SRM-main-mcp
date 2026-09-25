"""rule_based 정책 — `ml_orchestrator_demo.py:422` 추출. (B 소유)

정정 E: 원본은 `self.is_emergency` 를 직접 읽는다(:429). 그 분기를 **인자 `situation`** 으로
승격한다. ②는 무상태이므로 정답을 가질 수도 없고, 가지면 누출이다. 베이스라인과 제안 기법이
**같은 이 함수**를 호출하고 `situation` 의 출처만 다르다 — 사람(CLI) vs 에이전트 추론.
정확히 한 변수만 바뀌므로 통제 실험이 성립한다.

평활·클립·정규화(:458~462)는 여기 두지 않는다 — ①의 `apply_allocation()` 소관이다
(설계서 §3.2). 양쪽에 다 있으면 0.7이 두 번 걸려 배분이 거의 안 움직인다.

원본 :446~457 의 **위반 보정**은 되살렸다 (workplan B-1 · D1). 환경변수
`SLICE_RULE_CORRECTION` 으로 켜고 끈다 — 기본 `on` 이 원본 동작이고, `off` 는 상황인지
순도를 논증하기 위한 대조군이다. 보정이 있으면 상황 라벨이 틀려도 관측이 배분을 되돌려
주므로 오판의 대가가 가려진다. 끄면 그 신호가 깨끗해지는 대신 SLA 위반이 는다.
D1 이 뒤집히면 `CORRECTION_DEFAULT` 한 줄만 바꾸면 된다.
"""
from __future__ import annotations

import os
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

# 원본 :449~450 — 초과분의 20%, 한 슬라이스당 최대 0.1.
CORRECTION_CAP = 0.1
CORRECTION_GAIN = 0.2
CORRECTION_DEFAULT = "on"   # D1 권고. 원본 동작


def correction_enabled() -> bool:
    """`SLICE_RULE_CORRECTION=off` 면 끈다. 호출마다 읽는다.

    기동 시 한 번 읽으면 같은 프로세스에서 두 조건을 비교할 수 없고, 무엇보다
    **어느 설정으로 돈 실행인지 장부에서 확인할 길이 없어진다.** `rationale` 에
    매번 적어 `decisions.json` 에 남긴다.
    """
    return os.environ.get("SLICE_RULE_CORRECTION", CORRECTION_DEFAULT).lower() != "off"


def _violation_correction(target: dict[str, float],
                          observation: dict[str, Any]) -> dict[str, float]:
    """원본 :446~457. 임계를 넘은 슬라이스에 주고, 가장 한가한 슬라이스에서 뺀다.

    ⚠️ 원본은 *평활된* 배분(`:444` 의 `new_allocation`)에 걸었다. 여기는 목표표에 건다 —
       ②는 현재 배분을 모르기 때문이다(무상태). 결과가 둘 다르다: ①이 그 뒤에
       `0.7×현재 + 0.3×요청` 을 걸므로 **적용값에 남는 보정은 원본의 30% 뿐이다**
       (최대 0.1 → 0.03). 크기를 1/0.3 으로 되돌리는 것은 상수 조작이라 하지 않는다.
       민감도로 보고한다 (workplan §0 "결과가 좋아질 때까지 상수를 돌리지 않는다").

    합은 보존된다(제로섬). 음수나 0.8 초과가 나올 수 있지만 클립은 ①의 몫이다.
    """
    utilization = observation["utilization"]
    adjusted = dict(target)
    for key in SLICE_KEYS:
        excess = float(utilization[key]) - THRESHOLDS[key]
        if excess <= 0:
            continue
        increase = min(CORRECTION_CAP, excess * CORRECTION_GAIN)
        donor = min((k for k in SLICE_KEYS if k != key),
                    key=lambda k: float(utilization[k]))
        adjusted[key] += increase
        adjusted[donor] -= increase
    return adjusted


def propose(observation: dict[str, Any], situation: str) -> dict[str, float]:
    """목표 배분. 평활·클립 없음. 위반 보정은 `SLICE_RULE_CORRECTION` 에 따른다."""
    target = dict(TARGET_BY_SITUATION[situation])
    if not correction_enabled():
        return target
    return _violation_correction(target, observation)


def margin(observation: dict[str, Any]) -> float:
    """임계값까지의 상대 여유 중 **가장 작은 것**: minᵢ |uᵢ − θᵢ| / θᵢ."""
    utilization = observation["utilization"]
    return min(abs(float(utilization[k]) - THRESHOLDS[k]) / THRESHOLDS[k] for k in SLICE_KEYS)


def confidence(observation: dict[str, Any]) -> float:
    """0.50 + 0.30 · min(1, minᵢ |uᵢ − θᵢ| / θᵢ)  →  [0.50, 0.80]  (설계서 §6.1)

    이용률이 임계값에 바짝 붙어 있으면 규칙의 이산 분기가 자의적이므로 확신이 낮다.
    여유가 크면 어느 쪽 분기인지 명확하다.

    하한 0.50은 의도적이지만, **이 값이 에스컬레이션을 막아주지는 않는다** (workplan B-4).
    개입 판정은 여기 나오는 intrinsic 단독이 아니라 에이전트가 종합한
    `combined = √(intrinsic × empirical)` 로 내려지고, `empirical` 은 ⑤의 `effective` 다.
    즉 intrinsic 이 하한 0.50 이어도 `effective` 가 0.405 아래면 combined 가 τ(0.45) 밑으로
    내려간다 (√(0.5 × 0.405) = 0.450). 실측에서 `rule_based` 의 r 이 0.500 → 0.200 까지
    내려간 적이 있으므로 가정이 아니라 관측된 구간이다.

    이 상수가 정의하는 것은 "규칙이 자기 입력에 대해 갖는 확신의 하한"까지이고,
    "언제 사람을 부를 것인가"는 ⑤의 성적과 함께 정해진다.
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

    mode = "보정 on" if correction_enabled() else "보정 off"
    return f"situation={situation} → 목표 [{triple}] ({mode}). {detail}"
