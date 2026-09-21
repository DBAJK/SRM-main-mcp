"""9스텝 골격.

호출 순서·횟수·시점을 코드가 보장한다. 판단은 주입된 decider 가 한다.
arm 분기가 이 파일에 없다 — arms/ 가 서로 다른 decider 를 넘긴다.

계약: claude/spec/tools.md:33~46 · claude/flow/data-chain.md
"""

import logging
from typing import Callable, Optional

from .schema import (
    HISTORY_N,
    PROCURE_PRESSURE,
    Decision,
    StepContext,
    StepResult,
)
from .tools import Tools

logger = logging.getLogger(__name__)

Decider = Callable[[StepContext, "BoundProposer"], Decision]

# 조달 기본 파라미터. 비용은 제약이 아니므로(spec/market.md:199) 길이만 정한다.
PROCURE_DURATION_STEPS = 10

# 압력이 가장 큰 슬라이스를 고를 때 쓰는 이름 대응.
# ③은 "eMBB"/"URLLC"/"mMTC", ①은 "embb"/"urllc"/"mmtc" (spec/common.md:25)
SLICE_TYPE = {"embb": "eMBB", "urllc": "URLLC", "mmtc": "mMTC"}


class BoundProposer:
    """② 호출 창구. situation 이 정해진 뒤에만 쓸 수 있다.

    판단자가 ②를 직접 부르지 않고 이걸 통하게 해서, 루프가
    "situation 없이 ②를 부르는" 실수를 구조적으로 막는다.
    """

    def __init__(self, tools: Tools, ctx: StepContext):
        self._tools = tools
        self._ctx = ctx
        self.proposals: list[dict] = []

    def propose(self, policy: str, situation: str) -> dict:
        out = self._tools.propose_allocation(
            policy=policy,
            observation=self._ctx.observation,
            situation=situation,
            history=self._ctx.history,
            recent_error=self._ctx.recent_error(policy),
        )
        self.proposals.append(out)
        return out

    def compare(self, situation: str) -> list[dict]:
        out = self._tools.compare_policies(
            observation=self._ctx.observation,
            situation=situation,
            history=self._ctx.history,
            recent_errors=self._ctx.recent_errors(),
        )
        self.proposals.extend(out)
        return out


def run_step(tools: Tools, decide: Decider, run_id: str) -> StepResult:
    """한 스텝. 부작용 있는 도구의 호출 횟수는 명세가 정한 대로만 일어난다."""
    tools.reset_counts()

    # ── 1. 관측 ──────────────────────────────────────────────────────
    obs = tools.get_observation()
    step_no = int(obs["step"])

    # ── 2. 판단 재료 수집 → 에이전트가 situation 추론 ────────────────
    demand_class = tools.classify_demand(obs)
    reliability = tools.get_reliability_table()
    history = tools.get_history(HISTORY_N)

    ctx = StepContext(
        run_id=run_id,
        step=step_no,
        observation=obs,
        history=history,
        reliability=reliability,
        demand_class=demand_class,
    )

    # ── 3. 판단 (② 호출은 판단자가 proposer 로 한다) ─────────────────
    proposer = BoundProposer(tools, ctx)
    decision = decide(ctx, proposer)

    # ── 4. 조달 분기 ─────────────────────────────────────────────────
    # 명세 순서상 5번이지만 record_decision 앞에 둔다. slice_id·vendor_id 를
    # record_decision 에 기록해야 하고(spec/audit.md:20~21), ⑤가 그 vendor_id 를
    # 읽어 돌려주기 때문이다. tools.md:41 의 번호와 다른 점은 팀에 확인 필요.
    procurement = None
    if decision.procure and ctx.demand_pressure >= PROCURE_PRESSURE:
        procurement = _procure(tools, obs, step_no)

    # ── 5. 기록 (실행보다 먼저) ──────────────────────────────────────
    if decision.escalate:
        esc = tools.record_escalation(
            step=step_no,
            observation=obs,
            situation=decision.situation,
            reason=_escalation_reason(decision),
            confidence=decision.confidence(),
        )
        # 한 호출이 escalation + decision 레코드를 둘 다 남긴다 (spec/audit.md:53)
        decision_id = esc["decision_id"]
        allocation = esc["fallback_allocation"]
        escalated = True
    else:
        rec = tools.record_decision(
            step=step_no,
            observation=obs,
            situation=decision.situation,
            chosen_policy=decision.policy,
            allocation=decision.allocation,
            confidence=decision.confidence(),
            rationale=decision.rationale,
            in_distribution=decision.in_distribution,
            demand_class=decision.demand_class,
            considered=decision.considered or None,
            slice_id=procurement.get("slice_id") if procurement else None,
            vendor_id=procurement.get("vendor_id") if procurement else None,
        )
        decision_id = rec["decision_id"]
        allocation = decision.allocation
        escalated = False

    # ── 6. 적용 ──────────────────────────────────────────────────────
    applied = tools.apply_allocation(**allocation)

    # ── 7. 전진 ──────────────────────────────────────────────────────
    advanced = tools.step(1)
    obs_next = advanced["observation"]

    # ── 8. 채점 (step 이후여야 한다) ─────────────────────────────────
    outcome = tools.report_outcome(decision_id=decision_id, observed=obs_next)

    # ── 9. 벤더 평판 중계 ────────────────────────────────────────────
    if outcome.get("vendor_id"):
        tools.update_rating(
            vendor_id=outcome["vendor_id"],
            outcome={"sla_met": outcome["sla_met"], "decision_id": decision_id},
        )

    return StepResult(
        step=step_no,
        decision=decision,
        decision_id=decision_id,
        escalated=escalated,
        applied=applied,
        outcome=outcome,
        procurement=procurement,
        episode_done=bool(advanced.get("episode_done")),
        tool_calls=sum(tools.calls.values()),
    )


def run_episode(
    tools: Tools,
    decide: Decider,
    run_id: str,
    scenario: str = "normal",
    seed: int = 0,
    max_steps: Optional[int] = None,
) -> list[StepResult]:
    """한 에피소드 전체. reset 으로 시작한다."""
    info = tools.reset(run_id=run_id, scenario=scenario, seed=seed)
    total = int(info.get("total_steps", 60))
    limit = total if max_steps is None else min(total, max_steps)

    results: list[StepResult] = []
    for _ in range(limit):
        r = run_step(tools, decide, run_id)
        results.append(r)
        if r.episode_done:
            break

    logger.info(
        "%s: %d스텝 · 개입 %d · SLA위반 %d",
        run_id,
        len(results),
        sum(1 for r in results if r.escalated),
        sum(1 for r in results if r.sla_met is False),
    )
    return results


# ── 내부 ──────────────────────────────────────────────────────────────
def _procure(tools: Tools, obs: dict, step_no: int) -> Optional[dict]:
    """압력이 가장 큰 슬라이스를 1순위 벤더에게서 조달하고 ①에 중계한다.

    ③과 ①은 직접 대화하지 않는다 — capacity_gain 을 에이전트가 옮겨 심는다
    (flow/data-chain.md:68).
    """
    key = _most_pressured(obs)
    slice_type = SLICE_TYPE[key]
    qos = _qos_from_observation(obs, key)

    scored = tools.score_offerings(slice_type=slice_type, qos_requirements=qos)
    if not scored:
        return None

    proc = tools.procure(
        vendor_id=scored[0]["vendor_id"],
        slice_type=slice_type,
        qos_requirements=qos,
        duration_steps=PROCURE_DURATION_STEPS,
        current_step=step_no,
    )
    if proc.get("status") != "active":
        return proc

    # 용량 상한(2.0)을 넘으면 ①이 거부한다. 조달 비용은 이미 청구됐다
    # (spec/observe.md:224) — 호출 전 capacity 확인이 바람직하다.
    cap = tools.add_capacity(
        slice_type=slice_type,
        amount=proc["capacity_gain"],
        expires_at_step=proc["expires_at_step"],
        slice_id=proc["slice_id"],
    )
    return {**proc, "capacity_state": cap}


def _most_pressured(obs: dict) -> str:
    """이용률 / 임계값 비가 가장 큰 슬라이스."""
    util = obs["utilization"]
    thr = obs["thresholds"]
    return max(util, key=lambda k: util[k] / max(thr[k], 1e-9))


def _qos_from_observation(obs: dict, key: str) -> dict:
    """관측에서 조달 요구사항을 만든다.

    ③의 점수 공식은 요구치 대비 상대 평가이므로, 슬라이스 성격에 맞는
    기준값을 쓴다. 키에 단위를 붙이지 않는다 (spec/market.md:16).
    """
    defaults = {
        "embb": {"latency": 20.0, "bandwidth": 1000.0, "reliability": 99.9},
        "urllc": {"latency": 1.0, "bandwidth": 400.0, "reliability": 99.99},
        "mmtc": {"latency": 50.0, "bandwidth": 100.0, "reliability": 99.5},
    }
    return dict(defaults[key])


def _escalation_reason(d: Decision) -> str:
    if d.allocation is None:
        return f"policy_failed: {d.policy} returned no allocation"
    return (
        f"low_confidence: combined {d.combined:.3f} < 0.45 "
        f"(intrinsic {d.conf_intrinsic:.3f}, empirical {d.conf_empirical:.3f})"
    )
