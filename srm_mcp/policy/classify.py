"""classify_demand — `slicesim/ai/dqn_classifier.py:359` 의 `classify()` 를 그대로 쓴다. (B 소유)

TrafficClassifier: 입력 `(None, 11)`, 마지막 층 `Dense(3, softmax)` (0단계 확인).
가중치 471 KB, 실물 존재.

⚠️ 이 도구는 "비상 상황인가" 를 말하지 않는다. 어떤 수요가 지배적인지만 알려준다.
   상황 판단은 에이전트의 몫이고, 그게 이 연구의 측정 대상이다. `dominant` 를
   상황 라벨로 쓰면 `situation` 이 도구에서 나온 것이 되어 실험이 무너진다.
"""
from __future__ import annotations

from typing import Any, Optional

from ..common import paths
from ..common.const import SLICE_TYPES
from . import features

_model: Any = None
_load_error: Optional[str] = None


def load() -> None:
    """서버 기동 시 1회."""
    global _model, _load_error
    try:
        import tensorflow as tf  # noqa: PLC0415
        _model = tf.keras.models.load_model(str(paths.DQN_MODEL_DIR))
        _load_error = None
    except Exception as exc:  # noqa: BLE001
        _model = None
        _load_error = f"model_load_failed: {type(exc).__name__}: {exc}"


def available() -> tuple[bool, Optional[str]]:
    if _model is not None:
        return True, None
    return False, _load_error or "model_not_loaded"


def _empty(reason: str) -> dict[str, Any]:
    return {"dominant": None, "probabilities": {}, "margin": 0.0,
            "available": False, "reason": reason}


def classify(observation: dict[str, Any]) -> dict[str, Any]:
    """-> {dominant, probabilities, margin, available}

    `probabilities` 합 = 1.0 (softmax), `margin` = 1등 − 2등.
    numpy 값은 반환 전 파이썬 기본형으로 바꾼다 — `float(v)` (spec/common.md).
    """
    ok, reason = available()
    if not ok:
        return _empty(reason)

    try:
        vector = features.vector_from_observation(observation)
    except features.FeatureError as exc:
        return _empty(f"feature_mismatch: {exc}")

    try:
        import numpy as np  # noqa: PLC0415
        x = np.array(vector, dtype="float32").reshape(1, -1)
        y = _model.predict(x, verbose=0).reshape(-1)
    except Exception as exc:  # noqa: BLE001
        return _empty(f"inference_failed: {type(exc).__name__}: {exc}")

    probabilities = {name: float(p) for name, p in zip(SLICE_TYPES, y)}
    ordered = sorted(probabilities.values(), reverse=True)

    return {
        "dominant": max(probabilities, key=probabilities.__getitem__),
        "probabilities": probabilities,
        "margin": float(ordered[0] - ordered[1]),
        "available": True,
    }
