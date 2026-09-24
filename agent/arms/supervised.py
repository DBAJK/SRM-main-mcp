"""arm1 · arm2 — 에이전트가 판단하되 사람을 부르지 않는 비교군.

설계서의 표(origin/decomposition.md §6)는 이 둘의 에스컬레이션을 "항상 사람 감시"로
적고, 운영 명세(team/roles.md C-2)는 "없음"으로 적는다. 뜻은 같다 — 사람이 늘
지켜보는 L2 체계라 **에이전트가 개입을 요청할 일이 없다.** 코드상으로는
`escalation=False` 다.

이게 중요한 이유는 표본이다 (rationale/verification.md V2). 에스컬레이션한 스텝은
폴백이 대신 돌아 판단의 결과가 채점되지 않는다. 비교군마다 개입 수가 다르면 채점
표본이 달라져 SLA 비교가 편향된다. 이 둘은 모든 스텝이 자기 판단으로 채점된다.

사다리 — 각 비교군은 앞의 것에 에이전트 능력 하나를 더한다 (rationale/corrections.md:82
"정확히 한 변수만 바뀐다").

    baseline   상황=정답(사람)  정책=rule   조달=규칙   개입=없음
    arm1       상황=에이전트    정책=rule   조달=규칙   개입=없음    ← 상황 인지
    arm2       상황=에이전트    정책=에이전트 조달=판단자  개입=없음  ← 정책 선택
    proposed   상황=에이전트    정책=에이전트 조달=판단자  개입=신뢰도 ← 선택적 개입

조달을 arm1 까지 규칙으로 묶는 건 baseline 과 arm1 이 상황 출처 하나만 다르게 하기
위해서다. 판단자가 LLM 이면 조달 판단도 LLM 이 하는데, 그걸 arm1 에 풀어두면 baseline
대비 두 변수가 바뀐다. 루프가 압력 ≥ 1.0 으로 거르므로(agent/loop.py) `procure=True` 는
"규칙대로 산다"는 뜻이다.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Optional

from ..schema import Decision, StepContext


class _ForcedPolicy:
    """② 호출 창구를 감싸 정책을 하나로 묶는다.

    판단자가 어떤 정책을 요청하든 이 정책으로 부른다. 판단자 코드는 그대로 두고
    "정책 선택"이라는 능력 하나만 빼내는 방법이다. 반환된 `policy` 가 실제로 쓴 정책이므로
    Decision 에도 그게 남는다 (두 판단자 모두 `policy=prop["policy"]` 를 쓴다).
    """

    def __init__(self, inner: Any, policy: str):
        self._inner = inner
        self._policy = policy

    def propose(self, policy: str, situation: str) -> dict:
        return self._inner.propose(self._policy, situation)

    def compare(self, situation: str) -> list:
        return self._inner.compare(situation)

    def __getattr__(self, name: str) -> Any:     # proposals 등은 원래 창구의 것
        return getattr(self._inner, name)


class ArmDecider:
    """판단자를 감싸 비교군의 제약을 씌운다. loop.py 는 이게 무엇인지 모른다.

    감싼 판단자의 속성(`_llm` · `malformed` …)은 그대로 보인다 — 실행 요약이 읽는다.
    """

    def __init__(self, base: Callable[[StepContext, Any], Decision], name: str, *,
                 force_policy: Optional[str] = None,
                 escalation: Optional[bool] = None,
                 force_procure: Optional[bool] = None):
        self._base = base
        self.arm = name
        self._force_policy = force_policy
        self._escalation = escalation
        self._force_procure = force_procure

    def __call__(self, ctx: StepContext, proposer: Any) -> Decision:
        if self._force_policy:
            proposer = _ForcedPolicy(proposer, self._force_policy)
        d = self._base(ctx, proposer)
        changes: dict = {}
        if self._escalation is not None:
            changes["escalation"] = self._escalation
        if self._force_procure is not None:
            changes["procure"] = self._force_procure
        return replace(d, **changes) if changes else d

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def arm1(base) -> ArmDecider:
    """상황 인지만 에이전트. 정책·조달은 규칙, 개입 없음."""
    return ArmDecider(base, "arm1", force_policy="rule_based",
                      escalation=False, force_procure=True)


def arm2(base) -> ArmDecider:
    """상황 인지 + 정책 선택이 에이전트. 개입 없음."""
    return ArmDecider(base, "arm2", escalation=False)
