"""하드코딩 상수 전부. (A 소유 · 임시 스텁)

출처는 ROLES.md §1.2 표. 흩어지면 3명이 각자 다른 값을 쓰게 된다.
"""
from __future__ import annotations

# ── 환경 (ml_orchestrator_demo.py) ─────────────────────────────
THRESHOLDS = {"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}        # :174
INIT_ALLOCATION = {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}   # :171
STABILITY_FACTOR = 0.7                                        # :458
ALLOC_CLIP = (0.1, 0.8)                                       # :461
SEQUENCE_LENGTH = 10                                          # :190
CAPACITY_MAX = 2.0                                            # 신규 (정정 K)

# ── 가상 시계 (정정 F) ──────────────────────────────────────────
MINUTES_PER_STEP = 15
START_HOUR = 8

# ── 에스컬레이션 · 신뢰도 (설계서 §6.1~6.2) ─────────────────────
TAU = 0.45          # ⚠️ 실험 전 확정. 이후 절대 건드리지 않는다
EMA_ALPHA = 0.2     # 경험적 신뢰도 r 의 EMA 계수. 반감기 약 3스텝
SHRINK_R0 = 0.5
SHRINK_M = 5

# recent_error 는 "최근 5회 error 의 EMA" 로만 정의되어 있고 계수가 명시되지 않았다
# (설계서 §6.1). 창 N=5 에 대응하는 표준 계수 2/(N+1) 을 쓴다. ②의 lstm 신뢰도
# exp(−3·ē) 에 그대로 들어가므로 Day 0에 확정할 것. — B 추가
RECENT_ERROR_N = 5
RECENT_ERROR_ALPHA = 2 / (RECENT_ERROR_N + 1)

# ── ③ 마켓 ─────────────────────────────────────────────────────
RATING_DELTA = (+0.05, -0.20)                                  # (sla_met, 위반)
REFERENCE_BANDWIDTH = {"eMBB": 1100.0, "URLLC": 500.0, "mMTC": 120.0}
GAIN_SCALE = 0.25


def cost_per_step(cost_per_hour: float) -> float:
    """시간당 단가 → 스텝 단가 (W3). 그냥 곱하면 4배 부풀어 오른다."""
    return cost_per_hour * (MINUTES_PER_STEP / 60)


# ── 실행 ────────────────────────────────────────────────────────
MEMORY_MODE = "warm"          # "cold" | "warm". ③⑤의 실행 간 유지 여부 (W5)
SCENARIO_STEPS = {"normal": 60, "emergency": 60, "special_event": 60,
                  "iot_surge": 60, "mixed": 120}               # test_scenarios.py:54

# ── ML 피처 11개 (ml_orchestrator_demo.py:513~526) ─────────────
FEATURE_COLUMNS = [
    "traffic_load", "time_of_day", "day_of_week",
    "embb_alloc", "urllc_alloc", "mmtc_alloc",
    "embb_util", "urllc_util", "mmtc_util",
    "client_count", "bs_count",
]

# ── 금지 문자열 (flow/forbidden.md) ─────────────────────────────
FORBIDDEN = ["is_emergency", "is_special_event", "is_iot_surge",
             "ground_truth", "perception_accuracy", "escalation_precision"]

SLICE_KEYS = ("embb", "urllc", "mmtc")
SLICE_TYPES = ("eMBB", "URLLC", "mMTC")
# 소문자 키 ↔ vendors.json 대소문자 키 대응. 섞으면 조용히 틀린다.
SLICE_KEY_TO_TYPE = {"embb": "eMBB", "urllc": "URLLC", "mmtc": "mMTC"}
