"""규칙 판단자 — LLM 자리를 메우는 임시 구현.

LLM 을 붙이기 전에 루프 구조를 안정화하기 위한 것이다. 논문의 비교군이
아니다 (비교군은 arms/ 가 정의한다).

이 파일이 하는 일이 곧 decide.py 가 LLM 으로 대체할 일이다:
  situation 추론 · 정책 선택 · 조달 판단
에스컬레이션은 Decision 이 파생시킨다 (schema.py).
"""

from ..schema import Decision, PROCURE_PRESSURE, StepContext

# 이용률이 임계의 몇 배를 넘으면 그 슬라이스가 지배적이라고 볼지
DOMINANT_RATIO = 1.15


def rule_decider(ctx: StepContext, proposer) -> Decision:
    situation = infer_situation(ctx)
    policy = pick_policy(ctx)

    prop = proposer.propose(policy, situation)

    # 정책이 실패하면 다른 정책으로 한 번 더 시도한다.
    # ②는 조용한 폴백을 하지 않으므로(spec/policy.md:58) 여기가 그 판단 지점이다.
    considered = []
    if prop.get("status") != "ok":
        considered.append(
            {"policy": policy, "confidence": prop.get("confidence", 0.0),
             "status": prop.get("status")}
        )
        policy = "rule_based"
        prop = proposer.propose(policy, situation)

    return Decision(
        situation=situation,
        policy=prop["policy"],
        allocation=prop.get("allocation"),
        conf_intrinsic=float(prop.get("confidence", 0.0)),
        conf_empirical=ctx.effective(prop["policy"]),
        rationale=prop.get("rationale", ""),
        procure=ctx.demand_pressure >= PROCURE_PRESSURE,
        in_distribution=bool(prop.get("in_distribution", True)),
        considered=considered,
        demand_class=ctx.demand_class,
    )


def infer_situation(ctx: StepContext) -> str:
    """관측만으로 상황을 추론한다.

    정답 플래그를 쓰지 않는다 — 어차피 ①이 주지 않는다.
    이용률 / 임계값 비가 가장 큰 슬라이스를 보고 해당 상황으로 판정한다.
    """
    obs = ctx.observation
    util, thr = obs["utilization"], obs["thresholds"]
    ratio = {k: util[k] / max(thr[k], 1e-9) for k in util}

    top = max(ratio, key=ratio.get)
    if ratio[top] < DOMINANT_RATIO:
        return "normal"
    return {"urllc": "emergency", "embb": "special_event", "mmtc": "iot_surge"}[top]


def pick_policy(ctx: StepContext) -> str:
    """경험적 신뢰도가 가장 높은 정책을 고른다.

    이력이 10스텝 미만이면 lstm_forecast 는 어차피 unavailable 이므로 제외한다
    (spec/policy.md:150).
    """
    candidates = ["rule_based"]
    if (ctx.history or {}).get("n_available", 0) >= 10:
        candidates.append("lstm_forecast")
    return max(candidates, key=ctx.effective)
