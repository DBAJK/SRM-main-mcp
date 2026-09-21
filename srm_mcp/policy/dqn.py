"""dqn 정책 — **2차 범위**. 1차에서는 available=False 로만 내린다.

dqn_agent.py 의 이산 액션 27개를 배분 벡터로 바꾸는 작업. 학습 데이터 재생성이 선행한다.
신뢰도 식은 σ(Q₍₁₎ − Q₍₂₎) · 𝟙[in_distribution] (설계서 §6.1).
"""
from __future__ import annotations

from typing import Optional

UNAVAILABLE_REASON = "no trained weights"


def available() -> tuple[bool, Optional[str]]:
    return False, UNAVAILABLE_REASON


def propose(observation: dict) -> dict:
    raise NotImplementedError("2차 범위")
