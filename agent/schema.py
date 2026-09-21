"""에이전트 전용 타입.

서버가 만들지 않는 값만 여기 정의한다. 서버 응답은 dict 그대로 다룬다
(`mcp/common/schema.py`에 의존하지 않기 위함 — 와이어 계약만 알면 된다).

근거: claude/flow/data-chain.md '에이전트가 만들어내는 값'
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

Situation = Literal["normal", "emergency", "special_event", "iot_surge"]
PolicyName = Literal["rule_based", "lstm_forecast", "dqn"]

# ─── 명세가 고정한 상수. 바꾸면 실험 비교가 깨진다 ───
ESCALATION_THRESHOLD = 0.45  # flow/data-chain.md:107
PROCURE_PRESSURE = 1.0       # spec/observe.md:27
HISTORY_N = 10               # spec/policy.md:24  lstm_forecast 전제조건
DEFAULT_RECENT_ERROR = 0.5   # spec/policy.md:44  recent_error 가 null 일 때


@dataclass
class StepContext:
    """한 스텝에서 판단자가 받는 재료 전부.

    situation 을 정하기 전에 얻을 수 있는 것만 들어 있다.
    ② 호출은 situation 이 필요하므로 Proposer 를 통해 나중에 한다.
    """

    run_id: str
    step: int
    observation: dict           # ①.get_observation()
    history: Optional[dict]     # ①.get_history(10)
    reliability: dict           # ⑤.get_reliability_table()
    demand_class: Optional[dict]  # ②.classify_demand()

    @property
    def demand_pressure(self) -> float:
        return float(self.observation.get("demand_pressure", 0.0))

    def effective(self, policy: str) -> float:
        """경험적 신뢰도. ⑤의 축소 보정값을 쓴다 (spec/feedback.md:74)."""
        return float(self.reliability.get(policy, {}).get("effective", 0.5))

    def recent_error(self, policy: str) -> float:
        return float(
            self.reliability.get(policy, {}).get("recent_error", DEFAULT_RECENT_ERROR)
        )

    def recent_errors(self) -> dict:
        """②.compare_policies 는 정책별 딕셔너리를 받는다 (spec/policy.md:113)."""
        return {p: self.recent_error(p) for p in ("rule_based", "lstm_forecast", "dqn")}


class Proposer(Protocol):
    """② 호출 창구.

    situation 을 정한 뒤에만 쓸 수 있다. 판단자가 직접 ②를 부르지 않고
    이걸 통하게 해서 루프가 호출 횟수를 셀 수 있게 한다.
    """

    def propose(self, policy: str, situation: str) -> dict: ...

    def compare(self, situation: str) -> list[dict]: ...


@dataclass
class Decision:
    """에이전트가 만들어내는 값. 어느 서버도 이걸 생산하지 않는다.

    combined 와 escalate 는 저장하지 않고 파생시킨다 — 공식이 명세와 어긋날 수 없게.
    """

    situation: Situation
    policy: PolicyName
    allocation: Optional[dict]   # None 이면 정책 실패
    conf_intrinsic: float
    conf_empirical: float
    rationale: str

    procure: bool = False
    in_distribution: bool = True
    considered: list = field(default_factory=list)
    demand_class: Optional[dict] = None

    @property
    def combined(self) -> float:
        """√(intrinsic × empirical). spec/feedback.md:93"""
        return (max(0.0, self.conf_intrinsic) * max(0.0, self.conf_empirical)) ** 0.5

    @property
    def escalate(self) -> bool:
        """배분이 없거나 신뢰도가 임계 미달이면 사람을 부른다."""
        return self.allocation is None or self.combined < ESCALATION_THRESHOLD

    def confidence(self) -> dict:
        """④.record_decision 의 confidence 객체 (spec/audit.md:16~18)."""
        return {
            "intrinsic": round(self.conf_intrinsic, 6),
            "empirical": round(self.conf_empirical, 6),
            "combined": round(self.combined, 6),
        }


@dataclass
class StepResult:
    """한 스텝의 결과. 실험 로그와 디버깅용."""

    step: int
    decision: Decision
    decision_id: str
    escalated: bool
    applied: Optional[dict]        # ①.apply_allocation 응답
    outcome: Optional[dict]        # ⑤.report_outcome 응답
    procurement: Optional[dict] = None
    episode_done: bool = False
    tool_calls: int = 0

    @property
    def sla_met(self) -> Optional[bool]:
        return None if self.outcome is None else bool(self.outcome.get("sla_met"))
