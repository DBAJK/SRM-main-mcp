"""에이전트 전용 타입.

서버가 만들지 않는 값만 여기 정의한다. 서버 응답은 dict 그대로 다룬다
(`mcp/common/schema.py`에 의존하지 않기 위함 — 와이어 계약만 알면 된다).

근거: claude/flow/data-chain.md '에이전트가 만들어내는 값'
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol

Situation = Literal["normal", "emergency", "special_event", "iot_surge"]
PolicyName = Literal["rule_based", "lstm_forecast", "dqn"]

# ─── 명세가 고정한 상수. 바꾸면 실험 비교가 깨진다 ───
ESCALATION_THRESHOLD = 0.45  # flow/data-chain.md:107
PROCURE_PRESSURE = 1.0       # spec/observe.md:27
HISTORY_N = 10               # spec/policy.md:24  lstm_forecast 전제조건
NEUTRAL_RELIABILITY = 0.5    # ⑤에 표본이 없을 때 쓸 중립값 (축소 보정의 사전확률)

# ─── empirical 하한 (workplan-2 C-24 · D2 재개 · 2026-09-29) ───
# combined = √(intrinsic × empirical) 는 한쪽이 높으면 다른 쪽이 크게 떨어져도 τ 를 넘긴다.
# lstm 의 intrinsic 은 배분과 a* 의 거리(exp(−3·recent_error))라 SLA 위반을 못 보고 0.8~0.9 에 머문다 —
# intrinsic 0.8 이면 empirical 0.25 까지 τ 를 넘긴다. empirical(⑤ effective)은 실제 SLA 로 쌓는
# 성적이므로, 이 값이 하한 아래면 combined 와 무관하게 사람을 부른다.
# `AGENT_EMPIRICAL_FLOOR` = 숫자(기본 0.40) | off. 호출마다 읽는다 — 매트릭스에서 값을 바꿔 잰다.
EMPIRICAL_FLOOR_DEFAULT = 0.40


def empirical_floor() -> Optional[float]:
    import os  # noqa: PLC0415
    raw = os.environ.get("AGENT_EMPIRICAL_FLOOR", "").strip().lower()
    if raw in ("off", "none", "0"):
        return None
    if not raw:
        return EMPIRICAL_FLOOR_DEFAULT
    try:
        return float(raw)
    except ValueError:
        return EMPIRICAL_FLOOR_DEFAULT


def escalation_check(intrinsic: float, empirical: float) -> dict:
    """개입 판정 — 두 드라이버가 **이 함수 하나**를 쓴다 (CLAUDE.md 규칙 7).

    escalate = combined < τ  또는  empirical < 하한.  이유는 `trigger` 로 남긴다.
    """
    intrinsic = max(0.0, float(intrinsic))
    empirical = max(0.0, float(empirical))
    combined = (intrinsic * empirical) ** 0.5
    floor = empirical_floor()
    low_combined = combined < ESCALATION_THRESHOLD
    low_empirical = floor is not None and empirical < floor
    trigger = ("combined" if low_combined else "") + ("+" if low_combined and low_empirical else "")         + ("empirical_floor" if low_empirical else "")
    return {"combined": combined, "threshold": ESCALATION_THRESHOLD, "empirical_floor": floor,
            "escalate": bool(low_combined or low_empirical), "trigger": trigger or None}


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
        """⑤의 값을 그대로 중계한다. 에이전트가 채우거나 고치지 않는다.

        B-3 이후 ⑤는 표본이 없어도(n=0) null 을 내지 않는다 — `1 − POLICY_PRIOR[policy]` 로
        유도한 **사전값**을 낸다(spec/feedback.md · const.py). 실측이 아닌 것은 같은 행의 n 으로
        구분한다. None 은 ⑤가 모르는 정책명일 때만 나오고, 그때는 ②가 보수적 기본값 0.5 를
        쓴다(spec/policy.md:44~45).
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

    combined 는 저장하지 않고 파생시킨다 — 공식이 명세와 어긋날 수 없게.
    escalate 도 기본은 공식에서 파생되지만, 비교군(agent/arms/)이 `escalation` 으로
    덮어쓸 수 있다. baseline · arm1 · arm2 는 "개입 호출 없음"(roles.md C-2 표)이라
    공식이 뭐라 하든 False 여야 한다 — 파생 속성만으로는 강제할 수 없었다.
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

    # 비교군이 개입 여부를 강제할 때만 채운다. None 이면 공식을 따른다 (proposed).
    escalation: Optional[bool] = None

    # ② rule_based 가 따로 낸 위반 보정량(합 0). ①이 평활 뒤에 더한다 (workplan-2 D1-b).
    # 다른 정책이거나 보정이 꺼져 있으면 None.
    correction: Optional[dict] = None

    @property
    def combined(self) -> float:
        """√(intrinsic × empirical). spec/feedback.md:93"""
        return (max(0.0, self.conf_intrinsic) * max(0.0, self.conf_empirical)) ** 0.5

    @property
    def escalate(self) -> bool:
        """사람을 부르는가.

        배분이 없으면 비교군과 무관하게 부른다 — 적용할 것이 없어 폴백 외에 길이 없다.
        그 외에는 비교군이 정한 값, 없으면 신뢰도 공식.
        """
        if self.allocation is None:
            return True
        if self.escalation is not None:
            return self.escalation
        return escalation_check(self.conf_intrinsic, self.conf_empirical)["escalate"]

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
