"""점수 계산 — `5G-Marketplace/src/slice_selection/engine.py` 에서 추출.

import 하지 않고 복사해 온다 (설계서 §2). `SliceSelectionEngine` 은 __init__ 에서
vendor_registry · ai_agent · ndt 를 붙들고 logger 를 돌리므로, 점수 계산에 필요한
순수 함수만 떼어 왔다. `self` 없음 · `async` 없음 · logger 없음.

추출 대조표

    _calculate_criteria_weights()   engine.py:252      그대로
    _score_latency()                engine.py:328      그대로
    _score_bandwidth()              engine.py:356      그대로
    _score_reliability()            engine.py:385      그대로
    _calculate_qos_match()          engine.py:592      그대로 (점수 경로에는 안 쓰임 — 주석 참조)
    _calculate_price_score()        engine.py:628      그대로
    score_vendor_offering()         engine.py:719      async 제거, logger 제거
    get_score_breakdown()           engine.py:819      ⚠️ 쓰지 않는다 — 정정 J
    query_vendors() / find_matching_offerings()        사용 안 함 (정정 G)
    _advanced_score_offer()         engine.py:185      사용 안 함

정정 J — `get_score_breakdown()` 은 `vendor["rating"]` 대신 존재하지 않는
`reputation_score` 키를 읽어 기본값 3.0 으로 떨어진다. URLLC 평판 가중치
0.2 × (4.8 − 3.0)/5 × 100 = 7.2점 차이로 총점이 99.20 vs 92.00 이 된다.
그래서 `breakdown()` 은 `score_offering()` 의 실제 계산을 분해해 새로 구현했고,
`total` 이 `score_offering()` 과 정확히 일치한다.

1차 범위에서 `advanced_params` 는 쓰지 않는다. 고급 기준(availability · deterministic ·
packet_size · group_comm · mission_critical)은 `advanced_attributes` 가 있는 벤더에만
의미가 있는데 모델 A 에는 그 필드가 없다. 키가 들어오면 가중치 조정만 반영된다.
"""
from __future__ import annotations

import math
from typing import Any

# 핵심 QoS 기준 3개. 이것만 항상 채점된다.
CORE_CRITERIA = ("latency", "bandwidth", "reliability")

# engine.py:637~647 의 슬라이스별 기준가 (시간당)
REFERENCE_PRICE = {"URLLC": 250.0, "eMBB": 150.0, "mMTC": 75.0}


# ── engine.py:252 ──────────────────────────────────────────────
def criteria_weights(slice_type: str,
                     advanced_params: dict[str, Any] | None = None) -> dict[str, float]:
    """슬라이스 타입별 기준 가중치. advanced_params 가 있으면 조정 후 정규화."""
    if slice_type == "URLLC":
        weights = {"latency": 0.35, "reliability": 0.25, "bandwidth": 0.10,
                   "price": 0.10, "reputation": 0.05, "availability": 0.05,
                   "deterministic": 0.05, "packet_size": 0.02,
                   "group_comm": 0.01, "mission_critical": 0.02}
    elif slice_type == "mMTC":
        weights = {"latency": 0.10, "reliability": 0.15, "bandwidth": 0.10,
                   "price": 0.25, "reputation": 0.05, "availability": 0.10,
                   "deterministic": 0.05, "packet_size": 0.10,
                   "group_comm": 0.05, "mission_critical": 0.05}
    else:  # eMBB
        weights = {"latency": 0.15, "reliability": 0.15, "bandwidth": 0.30,
                   "price": 0.15, "reputation": 0.05, "availability": 0.05,
                   "deterministic": 0.02, "packet_size": 0.05,
                   "group_comm": 0.05, "mission_critical": 0.03}

    if advanced_params:
        if advanced_params.get("missionCritical") and advanced_params["missionCritical"] != "none":
            weights["mission_critical"] *= 2.0
            weights["reliability"] *= 1.5
            weights["latency"] *= 1.2
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}

        if advanced_params.get("deterministic") == "yes":
            weights["deterministic"] *= 3.0
            weights["latency"] *= 1.5
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}

    return weights


# ── engine.py:328 ──────────────────────────────────────────────
def score_latency(offering: dict, qos_params: dict, slice_type: str) -> float:
    """0~1. URLLC 만 지수 페널티, 나머지는 선형."""
    required = float(qos_params.get("latency", 50))
    offered = float(offering.get("latency", 100))

    if slice_type == "URLLC":
        if offered <= required:
            return 1.0
        return max(0.0, math.exp(-0.5 * (offered - required) / required))
    if offered <= required:
        return 1.0
    return max(0.0, 1.0 - (offered - required) / required)


# ── engine.py:356 ──────────────────────────────────────────────
def score_bandwidth(offering: dict, qos_params: dict, slice_type: str) -> float:
    """0~1. eMBB 만 초과분 보너스(상한 1.0) · 미달 시 제곱 페널티."""
    required = float(qos_params.get("bandwidth", 100))
    offered = float(offering.get("bandwidth", 100))

    if slice_type == "eMBB":
        if offered >= required:
            return min(1.0, 1.0 + 0.2 * (offered - required) / required)
        return max(0.0, (offered / required) ** 2)
    if offered >= required:
        return 1.0
    return max(0.0, offered / required)


# ── engine.py:385 ──────────────────────────────────────────────
def score_reliability(offering: dict, qos_params: dict, slice_type: str) -> float:
    """0~1. 실패율(100 − reliability)로 환산해 비교한다."""
    required = float(qos_params.get("reliability", 99.0))
    offered = float(offering.get("reliability", 99.0))

    required_failure = 100 - required
    offered_failure = 100 - offered

    if slice_type in ("URLLC", "mMTC"):
        if offered_failure <= required_failure:
            return 1.0
        return max(0.0, math.exp(-2.0 * (offered_failure / required_failure - 1.0)))

    if offered_failure <= required_failure:
        return 1.0
    return max(0.0, 1.0 - (offered_failure - required_failure) / required_failure)


# ── engine.py:592 ──────────────────────────────────────────────
def qos_match(offering: dict, qos_params: dict, slice_type: str) -> float:
    """QoS 3개를 슬라이스별 고정 가중치로 합친 값.

    ⚠️ `score_offering()` 은 이 함수를 쓰지 않는다 — 원본도 그렇다. 총점 경로는
    `criteria_weights()` 를 쓰고, 이쪽은 별도의 고정 가중치(0.5/0.4/0.1 등)를 쓴다.
    두 가중치가 다르므로 섞으면 값이 어긋난다. 참고용으로만 남긴다.
    """
    latency = score_latency(offering, qos_params, slice_type)
    bandwidth = score_bandwidth(offering, qos_params, slice_type)
    reliability = score_reliability(offering, qos_params, slice_type)

    if slice_type == "URLLC":
        w = {"latency": 0.5, "reliability": 0.4, "bandwidth": 0.1}
    elif slice_type == "eMBB":
        w = {"latency": 0.2, "reliability": 0.2, "bandwidth": 0.6}
    else:
        w = {"latency": 0.3, "reliability": 0.4, "bandwidth": 0.3}

    return (latency * w["latency"] + bandwidth * w["bandwidth"]
            + reliability * w["reliability"])


# ── engine.py:628 ──────────────────────────────────────────────
def price_score(offering: dict, slice_type: str) -> float:
    """0~1. 기준가 이하면 보너스(상한 1.0), 초과하면 절반 기울기로 감점."""
    price = float(offering.get("cost", 100))
    reference = REFERENCE_PRICE.get(slice_type, REFERENCE_PRICE["mMTC"])

    if price <= reference:
        return min(1.0, 1.0 + 0.2 * (reference - price) / reference)
    return max(0.0, 1.0 - 0.5 * (price - reference) / reference)


# ── 총점 구성 요소 (engine.py:719~810 을 분해) ──────────────────
def _reputation_weight(slice_type: str) -> float:
    """중요 용도일수록 평판 비중이 크다. URLLC 0.2 / 그 외 0.1."""
    return 0.2 if slice_type == "URLLC" else 0.1


def _price_weight(advanced_params: dict[str, Any] | None) -> float:
    """price_sensitivity: high 0.3 / low 0.1 / 기본 0.2."""
    if advanced_params and "price_sensitivity" in advanced_params:
        sensitivity = advanced_params["price_sensitivity"]
        if sensitivity == "high":
            return 0.3
        if sensitivity == "low":
            return 0.1
    return 0.2


def _components(vendor: dict, slice_type: str, qos_params: dict) -> dict[str, Any] | None:
    """총점의 재료를 한 번에 계산한다. 벤더가 해당 슬라이스를 안 팔면 None."""
    offering = vendor.get("offerings", {}).get(slice_type)
    if offering is None:
        return None

    advanced_params = qos_params.get("advanced_params", {})
    weights = criteria_weights(slice_type, advanced_params)

    scores = {
        "latency": score_latency(offering, qos_params, slice_type),
        "bandwidth": score_bandwidth(offering, qos_params, slice_type),
        "reliability": score_reliability(offering, qos_params, slice_type),
    }
    # 고급 기준은 벤더에 advanced_attributes 가 있을 때만 의미가 있다.
    # 모델 A 에는 없으므로 1차 범위에서는 채점 대상에 넣지 않는다 (가중치 조정만 반영).

    qos_score, total_weight = 0.0, 0.0
    for criterion, score in scores.items():
        if criterion in weights:
            qos_score += score * weights[criterion]
            total_weight += weights[criterion]
    qos_score = qos_score / total_weight if total_weight > 0 else 0.5

    reputation_weight = _reputation_weight(slice_type)
    price_weight = _price_weight(advanced_params)

    return {
        "offering": offering,
        "scores": scores,
        "weights": weights,
        "total_weight": total_weight,
        "qos_score": qos_score,
        "qos_weight": 1.0 - (reputation_weight + price_weight),
        "reputation_score": float(vendor.get("rating", 3.0)) / 5.0,
        "reputation_weight": reputation_weight,
        "price_score": price_score(offering, slice_type),
        "price_weight": price_weight,
    }


# ── engine.py:719 (async 제거) ─────────────────────────────────
def score_offering(vendor: dict, slice_type: str, qos_params: dict) -> float:
    """0~100. 벤더가 해당 슬라이스를 안 팔면 0.0 (원본과 동일).

        qos_score = Σ(scoreᵢ × weightᵢ) / Σ(weightᵢ)
        total     = (qos_score × qos_w + reputation × rep_w + price × price_w) × 100
    """
    c = _components(vendor, slice_type, qos_params)
    if c is None:
        return 0.0
    return (c["qos_score"] * c["qos_weight"]
            + c["reputation_score"] * c["reputation_weight"]
            + c["price_score"] * c["price_weight"]) * 100


def breakdown(vendor: dict, slice_type: str, qos_params: dict) -> dict[str, Any]:
    """`score_offering()` 의 분해. `total` 은 `score_offering()` 과 반드시 일치한다.

    기여분(contributions)의 합 = total. 기준 i 의 기여분은

        (scoreᵢ × weightᵢ / Σweight) × qos_weight × 100

    이고 평판·가격은 각자의 가중치를 그대로 쓴다. `neural_network` 키(UI용 장식)는
    반환하지 않는다 (정정 J).
    """
    c = _components(vendor, slice_type, qos_params)
    if c is None:
        return {"total": 0.0, "criteria_scores": {}, "weights": {}, "contributions": {},
                "explanation": f"{vendor.get('name')} 에 {slice_type} 오퍼링이 없다."}

    criteria_scores = dict(c["scores"])
    criteria_scores["reputation"] = c["reputation_score"]
    criteria_scores["price"] = c["price_score"]

    weights = {k: c["weights"][k] for k in c["scores"] if k in c["weights"]}
    weights["reputation"] = c["reputation_weight"]
    weights["price"] = c["price_weight"]

    contributions = {}
    for criterion, score in c["scores"].items():
        if criterion in c["weights"] and c["total_weight"] > 0:
            share = c["weights"][criterion] / c["total_weight"]
            contributions[criterion] = score * share * c["qos_weight"] * 100
    contributions["reputation"] = c["reputation_score"] * c["reputation_weight"] * 100
    contributions["price"] = c["price_score"] * c["price_weight"] * 100

    total = sum(contributions.values())
    offering = c["offering"]
    reference = REFERENCE_PRICE.get(slice_type, REFERENCE_PRICE["mMTC"])

    explanation = (
        f"지연 {offering['latency']}ms / 요구 {qos_params.get('latency', 50)}ms "
        f"→ {criteria_scores['latency']:.2f}. "
        f"대역 {offering['bandwidth']}Mbps → {criteria_scores['bandwidth']:.2f}, "
        f"신뢰도 {offering['reliability']}% → {criteria_scores['reliability']:.2f}. "
        f"평판 {vendor.get('rating')}/5.0 이 {contributions['reputation']:.1f}점 기여. "
        f"가격 {offering['cost']} 은 {slice_type} 기준가 {reference:g} 대비 "
        f"{contributions['price']:.1f}점."
    )

    return {
        "total": total,
        "criteria_scores": criteria_scores,
        "weights": weights,
        "contributions": contributions,
        "explanation": explanation,
    }
