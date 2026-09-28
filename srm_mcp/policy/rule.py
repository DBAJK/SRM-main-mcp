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
from typing import Any, Optional

from ..common.const import SLICE_KEYS, THRESHOLDS

# 원본 :429~:440 의 목표 배분 표. 상황 라벨 하나가 배분을 정한다.
TARGET_BY_SITUATION: dict[str, dict[str, float]] = {
    "emergency":     {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1},
    "special_event": {"embb": 0.6, "urllc": 0.3, "mmtc": 0.1},
    "iot_surge":     {"embb": 0.3, "urllc": 0.3, "mmtc": 0.4},
    "normal":        {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
}

# ── D7 (workplan-2 §2) — 목표표와 임계값의 불일치. **기본값은 `original`** ────────
#
# 위 표는 수요 배율만 보고 나눴는데, 위반이 없어지는 배분은 수요/임계에 비례한다
# (a*ₖ ∝ traffic_k/(θₖ·capacityₖ), ⑤ scoring.ideal_allocation). θ 는 urllc 만 1.0 을
# 넘어서, 네 줄 모두 urllc 과잉·mmtc 과소다. 근거와 측정은 tools/target_audit.py.
#
# 아래는 튜닝이 아니라 BASE_TRAFFIC × EVENT_MULTIPLIERS / THRESHOLDS 의 유도값이다.
# 리터럴로 두는 것은 ②가 ①의 상수를 import 하지 않기 위해서고, target_audit.py 가
# 유도식과 같은지 매번 검사한다. 공유 상수로 올릴지는 A · B 합의 사항이다.
TARGET_BY_SITUATION_THETA: dict[str, dict[str, float]] = {
    "emergency":     {"embb": 0.3290, "urllc": 0.4627, "mmtc": 0.2082},
    "special_event": {"embb": 0.5970, "urllc": 0.1791, "mmtc": 0.2239},
    "iot_surge":     {"embb": 0.3721, "urllc": 0.2093, "mmtc": 0.4186},
    "normal":        {"embb": 0.4706, "urllc": 0.2647, "mmtc": 0.2647},
}
# 위 표는 ①의 생성 상수에서 유도한 것이라 시뮬레이터의 정답지를 본 셈이다. 운영자가
# 실제로 아는 것은 θ 뿐이므로, 원본 표를 θ 로만 나눈 판을 따로 둔다 — 셋을 나란히 재면
# "θ 만 아는 경우" 와 "수요까지 아는 경우" 가 갈린다.
TARGET_BY_SITUATION_THETA_ONLY: dict[str, dict[str, float]] = {
    situation: {k: (target[k] / THRESHOLDS[k])
                   / sum(target[j] / THRESHOLDS[j] for j in SLICE_KEYS)
                for k in SLICE_KEYS}
    for situation, target in TARGET_BY_SITUATION.items()
}

TARGET_TABLES = {
    "original":   TARGET_BY_SITUATION,             # 원본 재현. 기본값
    "theta_only": TARGET_BY_SITUATION_THETA_ONLY,  # θ 만 씀 — 정보 우위 없음
    "theta":      TARGET_BY_SITUATION_THETA,       # θ + 생성 수요비 — 정보 우위 있음
}
TARGET_TABLE_DEFAULT = "original"   # D7 전까지 원본 동작


def target_table_name() -> str:
    """`SLICE_TARGET_TABLE` 이 고르는 표 이름. 호출마다 읽는다.

    `correction_enabled()` 와 같은 이유다 — 어느 표로 돈 실행인지 `rationale` 을 통해
    장부에 남는다. 모르는 값은 원본으로 떨어진다.
    """
    name = os.environ.get("SLICE_TARGET_TABLE", TARGET_TABLE_DEFAULT).lower()
    return name if name in TARGET_TABLES else TARGET_TABLE_DEFAULT


def targets(situation: str) -> dict[str, float]:
    return dict(TARGET_TABLES[target_table_name()][situation])


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


# 보정을 **어디에** 거나 (workplan-2 D1-b, 결정 2026-09-28 (iii)).
#   post    ②는 목표표와 보정량(correction)을 따로 내고, ①이 평활 **뒤에** 보정량을 더한다 — 원본
#           update_allocation_rule_based(:443~462) 와 같은 식. 보정이 100% 적용된다.
#   target  예전 동작(B-1 · B-1b). 목표표에 보정을 섞어 ①이 평활하므로 적용값엔 30% 만 남는다.
CORRECTION_STAGE_DEFAULT = "post"


def correction_stage() -> str:
    stage = os.environ.get("SLICE_CORRECTION_STAGE", CORRECTION_STAGE_DEFAULT).lower()
    return stage if stage in ("post", "target") else CORRECTION_STAGE_DEFAULT


def _violation_correction(target: dict[str, float],
                          observation: dict[str, Any]) -> dict[str, float]:
    """원본 :446~457. 임계를 넘은 슬라이스에 주고, 가장 한가한 슬라이스에서 뺀다.

    ⚠️ 원본은 *평활된* 배분(`:444` 의 `new_allocation`)에 걸었다. 여기는 목표표에 건다 —
       ②는 현재 배분을 모르기 때문이다(무상태). 결과가 둘 다르다: ①이 그 뒤에
       `0.7×현재 + 0.3×요청` 을 걸므로 **적용값에 남는 보정은 원본의 30% 뿐이다**
       (최대 0.1 → 0.03). 크기를 1/0.3 으로 되돌리는 것은 상수 조작이라 하지 않는다.
       민감도로 보고한다 (workplan §0 "결과가 좋아질 때까지 상수를 돌리지 않는다").

    **음수는 0 으로 자르고 합이 1 이 되게 다시 나눈다.** 처음에는 "음수 · 0.8 초과의 클립은
    ①의 몫"으로 두었는데, ①의 `apply_allocation` 은 음수 요청을 클립하지 않고 **거부**한다
    (`env.py _reject_reason` — 이전 배분이 그대로 남는다). 2026-09-26 실측 4412회 중 4회가
    그렇게 버려졌다(`arm1_rule-emergency-s2` 등, mmtc −0.0025 · −1e-06). 원본도 보정 뒤에
    클립 · 재정규화를 하므로(`:461~462`) 같은 순서를 따르되, ②가 낼 수 있는 하한은 0 이다 —
    [0.1, 0.8] 클립은 평활 뒤라야 뜻이 있어 여전히 ①의 몫이다. 보정량 자체는 줄이지 않는다.
    """
    clipped = {k: max(0.0, target[k] + d) for k, d in correction_delta(target, observation).items()}
    total = sum(clipped.values())
    return {k: v / total for k, v in clipped.items()}


def correction_delta(target: dict[str, float], observation: dict[str, Any]) -> dict[str, float]:
    """원본 :446~458 의 보정량만. 임계를 넘은 슬라이스 +min(0.1, 초과×0.2), 가장 한가한 슬라이스 −같은 양.

    합은 0 이다. 자르지 않는다 — post 방식에서는 ①이 평활 뒤에 더하고 [0.1, 0.8] 로 클립 · 재정규화한다
    (원본 :461~462 와 같은 순서). target 방식에서는 `_violation_correction` 이 목표표 위에서 0 으로 자른다.
    """
    utilization = observation["utilization"]
    delta = {k: 0.0 for k in SLICE_KEYS}
    for key in SLICE_KEYS:
        excess = float(utilization[key]) - THRESHOLDS[key]
        if excess <= 0:
            continue
        increase = min(CORRECTION_CAP, excess * CORRECTION_GAIN)
        donor = min((k for k in SLICE_KEYS if k != key),
                    key=lambda k: float(utilization[k]))
        delta[key] += increase
        delta[donor] -= increase
    return delta


def propose(observation: dict[str, Any], situation: str) -> dict[str, float]:
    """목표 배분. 평활·클립 없음.

    위반 보정은 `SLICE_RULE_CORRECTION`, 목표표는 `SLICE_TARGET_TABLE` 에 따른다.
    둘 다 기본값이 원본 동작이다.
    """
    target = targets(situation)
    if not correction_enabled() or correction_stage() == "post":
        return target                       # post: 보정량은 correction() 이 따로 낸다
    return _violation_correction(target, observation)


def correction(observation: dict[str, Any], situation: str) -> Optional[dict[str, float]]:
    """①이 평활 뒤에 더할 보정량 (post 방식에서만). 끄거나 target 방식이면 None."""
    if not correction_enabled() or correction_stage() != "post":
        return None
    return {k: round(v, 6) for k, v in correction_delta(targets(situation), observation).items()}


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

    mode = (("보정 on · 평활 뒤" if correction_stage() == "post" else "보정 on · 목표표")
            if correction_enabled() else "보정 off")
    table = target_table_name()
    return f"situation={situation} → 목표 [{triple}] ({mode} · 목표표 {table}). {detail}"
