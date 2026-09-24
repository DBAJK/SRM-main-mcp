"""비교군 — 4개 중 무엇으로 돌지 여기서 정한다.

`agent/loop.py` 에는 arm 분기가 없다. 비교군은 **서로 다른 판단자를 넘기는 것**으로만
구분된다. 같은 루프 · 같은 서버 · 같은 장부 · 같은 채점기를 쓴다.

    run.py --arm baseline   상황=정답(사람)   정책=rule     개입 없음
    run.py --arm arm1       상황=에이전트     정책=rule     개입 없음
    run.py --arm arm2       상황=에이전트     정책=에이전트 개입 없음
    run.py --arm proposed   상황=에이전트     정책=에이전트 개입=신뢰도

`--arm` 은 run_id 에도 박히는 이름이다. 첫 `_` 앞 토큰이 넷 중 하나면 그 동작이다 —
`arm1_llm` · `arm1_rule` 처럼 같은 비교군을 판단자만 바꿔 돌려도 run_id 가 겹치지 않게
(tools/run_matrix.py). 그 외 이름(예: `prompttest`)은 `proposed` 동작으로 돈다. 실행기가
어느 동작인지 첫 줄에 찍는다.

사다리와 근거는 supervised.py 머리말. baseline 의 정답 격리는 baseline.py 머리말.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .supervised import ArmDecider, arm1, arm2

KINDS = ("baseline", "arm1", "arm2", "proposed")

DESCRIBE = {
    "baseline": "상황=정답(사람) · 정책=rule_based · 조달=규칙 · 개입 없음",
    "arm1":     "상황=에이전트 · 정책=rule_based · 조달=규칙 · 개입 없음",
    "arm2":     "상황=에이전트 · 정책=에이전트 · 조달=판단자 · 개입 없음",
    "proposed": "상황=에이전트 · 정책=에이전트 · 조달=판단자 · 개입=신뢰도 기반",
}


def kind_of(label: str) -> str:
    """라벨 → 비교군 동작. 첫 `_` 앞이 넷 중 하나면 그것, 아니면 proposed.

    `arm1_llm` → arm1 · `baseline` → baseline · `prompttest` → proposed
    """
    head = label.split("_", 1)[0]
    return head if head in KINDS else "proposed"


def needs_base_decider(kind: str) -> bool:
    """baseline 은 판단자가 필요 없다 — 사람이 답을 줬다. LLM 로그인도 요구하지 않는다."""
    return kind != "baseline"


def make(kind: str, base=None, root: Optional[Path] = None):
    if kind == "baseline":
        from .baseline import BaselineDecider   # 이 경로에서만 불러온다
        if root is None:
            raise ValueError("baseline 은 runs/ 위치(root)가 필요하다")
        return BaselineDecider(root)
    if base is None:
        raise ValueError(f"{kind} 는 판단자가 필요하다")
    if kind == "arm1":
        return arm1(base)
    if kind == "arm2":
        return arm2(base)
    return base                                  # proposed — 판단자 그대로


__all__ = ["KINDS", "DESCRIBE", "ArmDecider", "kind_of", "needs_base_decider", "make"]
