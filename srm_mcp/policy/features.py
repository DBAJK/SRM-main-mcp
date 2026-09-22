"""피처 벡터 조립과 분포 판정. (B 소유)

설계서 §2 레이아웃에는 없는 파일이다. `lstm.py` 와 `classify.py` 가 똑같이 필요로 하는
"관측/이력 → 11차원 벡터" 변환을 한 곳에 둔다. 양쪽에 복사하면 컬럼 순서가 갈라진다.

⚠️ 컬럼 이름이 저장소 안에서 두 벌이다.

    ml_orchestrator_demo.py:513 주석   embb_alloc · embb_util · ...
    dqn_training_data.csv              embb_allocation · embb_utilization · ...

순서는 같다. `FEATURE_COLUMNS` 를 정본으로 삼고 나머지는 별칭으로 받는다.
**A의 `get_history()` 가 어느 이름을 내보내는지 Day 0에 확정해야 한다** — 어긋난 채로
조용히 돌면 `in_distribution` 이 전부 false 가 되고, `lstm_forecast` 의 신뢰도가 항상 0이라
에이전트가 그 정책을 영영 고르지 않는다. 그래서 여기서는 못 맞추면 예외를 던진다.
"""
from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from ..common import paths
from ..common.const import FEATURE_COLUMNS

# 정본 이름 ← 받아줄 별칭들
ALIASES: dict[str, str] = {}
for _canonical in FEATURE_COLUMNS:
    ALIASES[_canonical] = _canonical
for _short, _long in (("embb_alloc", "embb_allocation"), ("urllc_alloc", "urllc_allocation"),
                      ("mmtc_alloc", "mmtc_allocation"), ("embb_util", "embb_utilization"),
                      ("urllc_util", "urllc_utilization"), ("mmtc_util", "mmtc_utilization")):
    ALIASES[_long] = _short

_ranges: Optional[dict] = None


class FeatureError(ValueError):
    """피처를 조립할 수 없다. 계약이 어긋난 것이므로 조용히 넘기지 않는다."""


def canonical(columns: Sequence[str]) -> list[str]:
    """받은 컬럼 이름을 정본 이름으로 바꾼다. 모르는 이름이 있으면 예외."""
    unknown = [c for c in columns if c not in ALIASES]
    if unknown:
        raise FeatureError(
            f"알 수 없는 피처 컬럼: {unknown}. 정본 {FEATURE_COLUMNS} "
            f"(또는 *_allocation / *_utilization 별칭)."
        )
    return [ALIASES[c] for c in columns]


def _reorder(row: Sequence[float], columns: Sequence[str]) -> list[float]:
    index = {name: i for i, name in enumerate(canonical(columns))}
    missing = [c for c in FEATURE_COLUMNS if c not in index]
    if missing:
        raise FeatureError(f"피처가 모자란다: {missing}")
    return [float(row[index[c]]) for c in FEATURE_COLUMNS]


def vector_from_observation(observation: dict[str, Any]) -> list[float]:
    """Observation → 11차원. ①이 피처를 어떻게 싣는지에 따라 세 경로를 받는다.

    ⚠️ Observation 은 traffic · allocation · utilization 만으로는 11차원을 못 만든다 —
    time_of_day · day_of_week · client_count · bs_count · traffic_load 가 없다.
    A의 Day 0 판에서 ①이 이 다섯을 어떤 형태로 싣는지 정해야 한다. 여기서는
    `features` 블록 · 평탄화된 키 둘 다 받고, 없으면 무엇이 없는지 말한다.
    """
    block = observation.get("features")
    if isinstance(block, dict):
        return _reorder(list(block.values()), list(block.keys()))
    if isinstance(block, (list, tuple)):
        columns = observation.get("feature_columns", FEATURE_COLUMNS)
        return _reorder(block, columns)

    flat = {ALIASES[k]: v for k, v in observation.items() if k in ALIASES}
    missing = [c for c in FEATURE_COLUMNS if c not in flat]
    if missing:
        raise FeatureError(
            f"Observation 에서 11차원 피처를 만들 수 없다. 없는 것: {missing}. "
            f"①이 features 블록(또는 평탄화된 키)으로 실어 보내야 한다."
        )
    return [float(flat[c]) for c in FEATURE_COLUMNS]


def window_from_history(history: dict[str, Any]) -> list[list[float]]:
    """HistoryBlock → (n, 11). 행 순서는 오래된 것부터."""
    rows = history.get("features")
    if not rows:
        raise FeatureError("history 에 features 가 없다")
    columns = history.get("columns", FEATURE_COLUMNS)
    return [_reorder(row, columns) for row in rows]


# ── 분포 판정 ──────────────────────────────────────────────────
def load_ranges() -> dict:
    """0단계가 만든 `ranges.json` (컬럼별 min/max).

    학습 데이터 통계가 따로 없어 `dqn_training_data/*.csv` 에서 뽑아 고정한 값이다.
    """
    global _ranges
    if _ranges is None:
        with open(paths.POLICY_RANGES_JSON, "r", encoding="utf-8") as f:
            _ranges = json.load(f)["ranges"]
    return _ranges


def ranges_available() -> bool:
    return paths.POLICY_RANGES_JSON.exists()


# 분포 판정에서 제외하는 열.
#
# 학습 데이터(`dqn_training_data.csv`)의 이 두 열은 10,000행이 전부 다른 값이고
# min 0.0000525 / max 0.999974, 평균 0.497 — 실제 시계가 아니라 **U(0,1) 난수**다.
# 반면 ①의 가상 시계는 자정을 정확히 0.0, 월요일을 정확히 0.0 으로 낸다. 눈금이 다른
# 두 값을 min/max 로 비교하면 판정이 시각 자체에 걸려 상시 발화한다 — 측정하면
# day_of_week 100% · time_of_day 6.6% 가 "범위 밖"이고, 10행 창 624개 중 통과가 0개였다.
# `confidence = exp(−3·ē)·𝟙[in_distribution]` (build/formulas.md) 때문에 그 순간
# `lstm_forecast` 의 신뢰도가 영구히 0 이 되어 에이전트가 그 정책을 영영 고르지 않는다.
#
# 모델이 실제로 학습한 신호(traffic_load · alloc · util · client/bs count)로만 판정한다.
# **이용률은 반드시 남긴다** — 조달로 용량이 늘어 분포를 벗어나는 것은 눈금 문제가 아니라
# 정직한 신호다 (rationale/observe.md).
UNGATED_COLUMNS = ("time_of_day", "day_of_week")


def out_of_range(rows: Sequence[Sequence[float]]) -> list[str]:
    """학습 범위를 벗어난 피처 이름. 하나라도 있으면 in_distribution = false.

    `UNGATED_COLUMNS` 는 세지 않는다 — 학습 데이터 쪽이 난수라 기준이 되지 못한다.
    """
    ranges = load_ranges()
    outside = []
    for i, name in enumerate(FEATURE_COLUMNS):
        if name in UNGATED_COLUMNS:
            continue
        bounds = ranges.get(name)
        if bounds is None:
            outside.append(name)
            continue
        values = [row[i] for row in rows]
        if min(values) < bounds["min"] or max(values) > bounds["max"]:
            outside.append(name)
    return outside
