"""도구 설명 2벌 (설계서 §6.3).

MCP는 도구 설명을 LLM 컨텍스트에 그대로 넣는다. "평시 효율 우수" 는 사실상
"언제 이걸 골라라" 는 조언이므로 그 자체가 실험 변수다.

주 실험은 minimal. advisory 는 비교 실행. desc_mode 를 decisions.json 의 config 에 기록한다.
"""
from __future__ import annotations

import os

DESC = {
    "minimal": {
        "rule_based":    "임계값 기반 배분. 상황 라벨을 입력으로 받는다.",
        "lstm_forecast": "시계열 모델 기반 배분. 관측 이력 10스텝 필요.",
        "dqn":           "강화학습 정책 기반 배분.",
    },
    "advisory": {
        "rule_based":    "이용률 임계값 기반. 항상 가용, 보수적.",
        "lstm_forecast": "시계열 예측 기반. 평시 효율 우수.",
        "dqn":           "강화학습 정책. 학습 분포 내에서 우수.",
    },
}

REQUIRES = {
    "rule_based": None,
    "lstm_forecast": "history >= 10",
    "dqn": "trained weights",
}

MODE = os.environ.get("SLICE_DESC_MODE", "minimal")


def describe(policy: str) -> str:
    return DESC[MODE][policy]
