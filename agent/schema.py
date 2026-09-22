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
NEUTRAL_RELIABILITY = 0.5    # ⑤에 표본이 없을 때 쓸 중립값 (축소 보정의 사전확률)


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

    # 사람이 에피소드 시작에 **한 번** 준 자연어 상황. 사람의 개입은 여기서
    # 끝난다 — 이후 스텝마다의 판단은 에이전트가 한다. 규칙 판단자는 무시하고
    # LLM 판단자만 읽는다.
    intent: Optional[str] = None

    @property
    def demand_pressure(self) -> float:
        return float(self.observation.get("demand_pressure", 0.0))

    def effective(self, policy: str) -> float:
        """경험적 신뢰도. ⑤의 축소 보정값을 쓴다 (spec/feedback.md:74)."""
        v = self.reliability.get(policy, {}).get("effective")
        return NEUTRAL_RELIABILITY if v is None else float(v)

    def samples(self, policy: str) -> int:
        """⑤가 이 정책을 몇 번 채점했나.

        n=0 이면 effective 는 성적이 아니라 사전값(0.5)이다. 둘을 같은 자로
        비교하면 안 된다 — 아래 pick_policy 주석 참고.
        """
        return int(self.reliability.get(policy, {}).get("n", 0) or 0)

    def recent_error(self, policy: str) -> Optional[float]:
        """None 을 그대로 중계한다.

        ⑤는 표본이 없으면(n=0) null 을 낸다. 명세상 기본값 대입은 ②의 몫이고
        (spec/policy.md:44 — 보수적 기본값 0.5 + rationale 에 명시), 에이전트가
        미리 채우면 ②가 "이력 없음"을 구분하지 못한다.
        """
        v = self.reliability.get(policy, {}).get("recent_error")
        return None if v is None else float(v)

    def recent_errors(self) -> dict:
        """②.compare_policies 에는 ⑤의 테이블을 **그대로** 넘긴다.

        스칼라로 눌러 넘기면 정책별 오차 이력이 뭉개진다 (policy/server.py:163).
        ②가 dict 든 float 든 받아 처리한다.
        """
        return self.reliability


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
    conf_intrinsic: float        # ②가 낸 값. 이번 입력에 대한 확신
    conf_empirical: float        # ⑤의 effective. 이 정책의 평소 성적
    conf_situation: float        # 상황 추론에 대한 확신. 에이전트가 만든다
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
        """④.record_decision 의 confidence 객체.

        spec/audit.md:16~18 은 3개(intrinsic·empirical·combined)를 적었으나 ④의
        구현은 situation 까지 4개를 필수로 요구한다 (audit/book.py:20, :96 —
        "상황 오판이 combined 에 반영되지 않아 에스컬레이션이 일어나지 않는다").

        ⚠️ combined 는 명세 공식 그대로 2항이다. situation 을 곱에 넣을지는
        미결 — audit.md:47 의 계산 예시(0.556 × 0.880 → 0.699)와 임계 0.45 의
        보정이 2항 기준이므로 임의로 바꾸지 않는다.
        """
        return {
            "situation": round(self.conf_situation, 6),
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
