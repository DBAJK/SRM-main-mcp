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

# ── 용량 배수 (정정 K · rationale/environment.md 재조정) ────────
# handover §4-④ 에서 동결. 구버전 스텁은 CAPACITY_MAX = 2.0 · CAPACITY_BASE 없음이었다.
CAPACITY_BASE = 1.6   # 조달 전 기본 용량. 평시 여유를 만들어 normal 압력 초과를 5.6% 로 내린다
CAPACITY_MAX = 2.6    # 기본 + 조달 4회분. 3.6 이면 모든 스텝이 조달로 해소되어 에스컬레이션이 무의미해진다

# ── 가상 시계 (정정 F) ──────────────────────────────────────────
MINUTES_PER_STEP = 15
START_HOUR = 0        # 자정 시작. 8 이면 하필 고부하 구간이라 평시 압력 초과가 53% 로 뛴다
# 학습 데이터의 day_of_week · time_of_day 는 10,000행 전부가 서로 다른 U(0,1) 난수라
# 실제 시계에서 온 값이 아니다. 가상 시계(월요일 0.0 · 자정 0.0)와 비교할 수 없으므로
# ②가 분포 판정에서 두 열을 제외한다 (policy/features.py UNGATED_COLUMNS).
START_DAY_OF_WEEK = 0  # 0 = 월요일 (spec/observe.md sim_time.day_of_week)

# ── 단말·기지국 피처 분포 정합 ─────────────────────────────────
# 원본 :507~508 의 `0.4 + 0.3·sin`, `0.5 + 0.1·randn` 은 dqn_training_data.csv 의
# client_count [0.3509, 1.0] (평균 0.80) · bs_count [0.4490, 0.99986] (평균 0.77) 보다
# 체계적으로 낮게 뽑힌다. 행 단위 이탈률이 14.8% · 28.4% 라 10행 창 하나가 통과하지 못하고
# lstm_forecast 의 신뢰도가 영구히 0 이 된다 (측정: 4시나리오 × 3시드, 624창 중 0창 통과).
# 두 값은 트래픽·이용률에 관여하지 않는 피처 전용 값이라, 모양은 두고 중심만 옮긴다.
# ⚠️ 난수 소비 횟수와 순서는 그대로다 (observe/env.py 파일 docstring).
CLIENT_COUNT_BASE = 0.68        # 원본 0.4
CLIENT_COUNT_AMPLITUDE = 0.20   # 원본 0.3. 학습 범위 안에서 ±3σ 여유를 남긴다
CLIENT_COUNT_BAND = (0.36, 0.99)
BS_COUNT_BASE = 0.72            # 원본 0.5
BS_COUNT_BAND = (0.46, 0.99)

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

# 정책별 사전 신뢰도. `errors` 가 빈 동안 ⑤가 `recent_error = 1 − prior` 로 유도한다
# (workplan B-3). 유예 가정에 구멍이 있었다 — `errors` 는 정책별로 쌓이는데 lstm 은
# 한 번도 선택되지 않으면 영영 비고, 비면 ②가 보수적 기본값 0.5 를 써서
# exp(−3×0.5)=0.2231 < τ 가 되어 또 선택되지 않는다. 닫힌 고리라 스스로 못 빠져나온다.
# lstm 0.8 → ē=0.2 → exp(−0.6)=0.549 > τ(0.45) 로 한 번은 시험대에 오른다.
# ⚠️ 사전값이지 실측이 아니다. n=0 인 동안의 `recent_error` 는 성적이 아니다
#    (`get_reliability_table` 의 같은 행 `n` 으로 구분한다).
POLICY_PRIOR = {"rule_based": 0.9, "lstm_forecast": 0.8, "dqn": 0.4}

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
