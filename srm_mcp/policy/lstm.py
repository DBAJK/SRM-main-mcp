"""lstm_forecast 정책 — `slicesim/ai/lstm_predictor.py:426` 추출. (B 소유)

두 가지를 반드시 제거한다.

  · **조용한 폴백** (정정 H) — 원본 `update_allocation_ml()` 은 이력이 모자라거나 예외가
    나면 `update_allocation_rule_based()` 를 호출하고 그 결과를 자기 이름으로 돌려준다
    (`:414`, `:419`). 그대로 옮기면 ④의 `policy_usage` 가 통째로 거짓이 되고 ⑤가 lstm의
    성적으로 rule의 성적을 기록한다. 폴백 여부는 **에이전트가 정한다** — 그게 곧 "정책 선택"이다.
  · **평활·클립** (`:401~407`) — ①의 `apply_allocation()` 소관.

⚠️ 원본은 `from tensorflow.keras.models import load_model` 이 모듈 최상단에 있어
   (`lstm_predictor.py:20`) TF가 없으면 import 만으로 죽는다. 여기서는 적재를 `try` 안에
   넣고 실패를 상태로 들고 있는다 — TF 없이도 ② 서버는 기동해 `rule_based` 를 서빙해야 한다.

모델 구조(0단계 확인): 입력 `(None, 10, 11)`, 마지막 층 `Dense(3, softmax)`.
출력이 그대로 배분 삼중항이므로 후처리가 필요 없다.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from ..common import paths
from ..common.const import SEQUENCE_LENGTH, SLICE_KEYS
from . import features

_model: Any = None
_load_error: Optional[str] = None

# recent_error 가 null 일 때 쓰는 보수적 기본값. exp(−3 × 0.5) = 0.223 으로
# τ(0.45) 아래라 에이전트가 근거 없이 lstm 을 고르는 것을 막는다.
DEFAULT_RECENT_ERROR = 0.5


def load() -> None:
    """서버 기동 시 **1회**. 호출마다 적재하면 스텝당 수 초가 든다."""
    global _model, _load_error
    try:
        import tensorflow as tf  # noqa: PLC0415
        _model = tf.keras.models.load_model(str(paths.LSTM_MODEL_DIR))
        _load_error = None
    except Exception as exc:  # noqa: BLE001 — 실패를 상태로 들고 간다
        _model = None
        _load_error = f"model_load_failed: {type(exc).__name__}: {exc}"


def available() -> tuple[bool, Optional[str]]:
    """(available, unavailable_reason). 적재에 실패해도 서버는 죽지 않는다."""
    if _model is not None:
        return True, None
    return False, _load_error or "model_not_loaded"


def confidence(recent_error: Optional[float], in_distribution: bool) -> float:
    """exp(−3 · ē) · 𝟙[in_distribution]   (설계서 §6.1)

    ē 는 ⑤가 들고 있는 누적값(최근 5회 `error` 의 EMA)이다. ②는 무상태라 ⑤를 조회할 수
    없으므로 에이전트가 중계한다(V4). 추론 시 dropout 이 없어 분산 추정이 불가능하고,
    최근 실적이 유일하게 값싼 대리 지표다. ē=0.1 → 0.74, ē=0.3 → 0.41.
    """
    if not in_distribution:
        return 0.0
    error = DEFAULT_RECENT_ERROR if recent_error is None else float(recent_error)
    return math.exp(-3.0 * error)


def propose(observation: dict[str, Any], history: Optional[dict],
            recent_error: Optional[float]) -> dict[str, Any]:
    """PolicyProposal 의 재료를 만든다. **실패해도 다른 정책을 부르지 않는다.**

    반환하는 dict 는 `{allocation, confidence, in_distribution, status, reason, rationale}`.
    `policy` 는 호출자가 요청받은 값 그대로 채운다.
    """
    def fail(status: str, reason: str, rationale: str) -> dict[str, Any]:
        return {"allocation": None, "confidence": 0.0, "in_distribution": False,
                "status": status, "reason": reason, "rationale": rationale}

    ok, reason = available()
    if not ok:
        return fail("error", reason, "모델을 적재하지 못해 추론 불가.")

    n = 0 if not history else int(history.get("n", len(history.get("features") or [])))
    if n < SEQUENCE_LENGTH:
        return fail("unavailable", f"history_insufficient: {n} < {SEQUENCE_LENGTH}",
                    "시퀀스 길이 미달로 추론하지 않음.")

    if not features.ranges_available():
        return fail("error", f"ranges_missing: {paths.POLICY_RANGES_JSON.name}",
                    "학습 분포 기준이 없어 in_distribution 을 판정할 수 없다. "
                    "tools/step0_verify_models.py 를 먼저 실행할 것.")

    try:
        window = features.window_from_history(history)[-SEQUENCE_LENGTH:]
    except features.FeatureError as exc:
        return fail("error", f"feature_mismatch: {exc}", "이력에서 피처를 만들지 못했다.")

    outside = features.out_of_range(window)
    in_distribution = not outside

    try:
        import numpy as np  # noqa: PLC0415
        x = np.array(window, dtype="float32").reshape(1, SEQUENCE_LENGTH, len(window[0]))
        y = _model.predict(x, verbose=0).reshape(-1)
    except Exception as exc:  # noqa: BLE001
        return fail("error", f"inference_failed: {type(exc).__name__}: {exc}",
                    "추론 중 예외.")

    if len(y) != len(SLICE_KEYS):
        return fail("error", f"unexpected_output_dim: {len(y)}",
                    "출력 차원이 3이 아니다.")

    # 마지막 층이 softmax 라 합 = 1, 각 항 ∈ [0,1] 이 보장된다. 후처리 없음.
    allocation = {k: float(v) for k, v in zip(SLICE_KEYS, y)}

    note = ("학습 분포 안." if in_distribution
            else f"학습 범위를 벗어난 피처: {outside} → 신뢰도 0.")
    source = ("recent_error 미제공 → 보수적 기본값 "
              f"{DEFAULT_RECENT_ERROR}" if recent_error is None
              else f"recent_error={float(recent_error):.3f}")

    return {
        "allocation": allocation,
        "confidence": confidence(recent_error, in_distribution),
        "in_distribution": in_distribution,
        "status": "ok",
        "reason": None,
        "rationale": f"최근 {SEQUENCE_LENGTH}스텝 시계열 예측. {note} {source}.",
    }
