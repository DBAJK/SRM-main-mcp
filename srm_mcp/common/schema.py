"""공통 pydantic 모델. (A 소유 · 임시 스텁)

spec/common.md — SliceTriple 은 **배열이 아니라 딕셔너리**다.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Situation = Literal["normal", "emergency", "special_event", "iot_surge"]
PolicyName = Literal["rule_based", "lstm_forecast", "dqn"]
SliceType = Literal["eMBB", "URLLC", "mMTC"]
Status = Literal["ok", "unavailable", "error"]


class SliceTriple(BaseModel):
    embb: float
    urllc: float
    mmtc: float


class SliceFlags(BaseModel):
    embb: bool
    urllc: bool
    mmtc: bool


class Observation(BaseModel):
    """①.get_observation() 출력. ②⑤가 그대로 받는다.

    ⚠️ is_emergency 계열 필드가 **없어야** 한다 (flow/forbidden.md).
    실제 필드는 A의 Day 0 판을 따른다 — 아래는 최소 골격.
    """
    step: int
    traffic: SliceTriple
    allocation: SliceTriple
    utilization: SliceTriple
    violations: SliceFlags
    capacity: SliceTriple
    demand_pressure: float


class HistoryBlock(BaseModel):
    """①.get_history() 출력. lstm_forecast 가 (1, 10, 11) 로 쓴다."""
    n: int
    features: list[list[float]]
    columns: list[str]


# ── ② policy ───────────────────────────────────────────────────
class PolicyInfo(BaseModel):
    name: PolicyName
    description: str
    requires: Optional[str] = None
    available: bool
    unavailable_reason: Optional[str] = None


class PolicyProposal(BaseModel):
    policy: PolicyName          # ⚠️ 요청한 정책. 절대 다른 값으로 바꾸지 않는다
    allocation: Optional[SliceTriple]
    confidence: float
    in_distribution: bool
    status: Status
    reason: Optional[str] = None
    rationale: str


class DemandClass(BaseModel):
    dominant: SliceType
    probabilities: dict[str, float]
    margin: float
    available: bool


# ── ③ market ───────────────────────────────────────────────────
class Offering(BaseModel):
    vendor_id: str
    name: str
    slice_type: SliceType
    latency: float      # ms
    bandwidth: float    # Mbps
    reliability: float  # %
    cost: float         # 시간당
    regions: list[str]
    rating: float


class ScoredOffering(BaseModel):
    rank: int
    vendor_id: str
    name: str
    score: float
    rating: float
    cost: float


class ScoreBreakdown(BaseModel):
    total: float
    criteria_scores: dict[str, float]
    weights: dict[str, float]
    contributions: dict[str, float]
    explanation: str


class Procurement(BaseModel):
    slice_id: Optional[str]
    status: Literal["active", "rejected"]
    vendor_id: str
    cost_total: float
    capacity_gain: float
    expires_at_step: Optional[int]
    reason: Optional[str] = None


class RatingUpdate(BaseModel):
    vendor_id: str
    rating_before: float
    rating_after: float
    delta: float


# ── ⑤ feedback ─────────────────────────────────────────────────
class Outcome(BaseModel):
    sla_met: bool
    policy: PolicyName
    error: float
    ideal_allocation: SliceTriple
    applied_allocation: SliceTriple
    requested_allocation: SliceTriple
    actuator_delta: float
    observed_violations: SliceFlags
    vendor_id: Optional[str]
    reliability_before: float
    reliability_after: float


class ReliabilityEntry(BaseModel):
    reliability: float
    n: int
    effective: float      # 축소 보정값. 에이전트는 이걸 쓴다
    recent_error: float   # ②.propose_allocation(recent_error=...) 로 중계
